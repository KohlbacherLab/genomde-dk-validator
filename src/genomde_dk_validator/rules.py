"""
Semantic-rule engine for genomDE Datenkranz — mechanics adopted from mzPeakValidator:
rules are DATA (JSON), not code. Each rule is an instance of a named *primitive* from the
catalog implemented below; the engine reads only `id / primitive / severity / params`
(`about` / `doc` / `fix` are documentation). Rule files live under `rules/` as package data:
`rules/kdk.rules.json` and `rules/grz.rules.json`.

Rules encode the BfArM "Qualitätssicherung" criteria (QS durch KDK / QS durch GRZ, 06/2026).
They are OFF by default and enforced only via the CLI (`--kdk-rules` / `--grz-rules`), so the
plain schema validation is unchanged unless a rule set is explicitly requested.

Some criteria need external resources not in the JSON (KDK: LE-ID list, own node id;
GRZ: own centre id) — their primitives SKIP (info) unless the resource is supplied via
`--rules-config`. Terminology resolvability (KDK criterion 4) is handled by the separate
schema/terminology tooling, not here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Any, Callable, Iterator

from . import validator as _V

CATALOG_VERSION = 1


# --------------------------------------------------------------------------- paths & dates

def resolve(inst: Any, path: str) -> Iterator[tuple[str, Any]]:
    """Yield (json_pointer, value) for a dotted path with `[]` array wildcards."""
    toks = re.findall(r"[^.\[\]]+|\[\]", path)

    def rec(node, ts, ptr):
        if not ts:
            yield ptr, node
            return
        t, rest = ts[0], ts[1:]
        if t == "[]":
            if isinstance(node, list):
                for i, el in enumerate(node):
                    yield from rec(el, rest, f"{ptr}/{i}")
        elif isinstance(node, dict) and t in node:
            yield from rec(node[t], rest, f"{ptr}/{t}")
        elif isinstance(node, list) and t.isdigit() and int(t) < len(node):
            yield from rec(node[int(t)], rest, f"{ptr}/{t}")

    yield from rec(inst, toks, "")


def _date_tuple(s: Any):
    """Parse 'YYYY' | 'YYYY-MM' | 'YYYY-MM-DD' -> (y,m,d), missing parts = 1 (floor).
    End-anchored + calendar-validated: junk like '2026-99-99x' or '2026-13' returns None."""
    if not isinstance(s, str):
        return None
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", s.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    try:
        import datetime
        datetime.date(y, mo, d)
    except ValueError:
        return None
    return (y, mo, d)


@dataclass
class RuleFinding:
    rule_id: str
    primitive: str
    level: str          # "error" | "warning" | "info"
    message: str
    path: str = ""


class _Ctx:
    """Everything a primitive may need: the instance, branch, schema store, external config."""
    def __init__(self, validator: "_V.DatenkranzValidator", branch: str, config: dict):
        self.v = validator
        self.branch = branch
        self.config = config or {}
        self._root_uri = _V.ROOTS.get(branch)

    def date_fields(self, inst) -> list[tuple[str, Any]]:
        """All (pointer, value) whose schema leaf declares format:date (authoritative)."""
        if not self._root_uri:
            return []
        out: list[tuple[str, Any]] = []
        self._walk_dates(inst, self.v._store[self._root_uri], self._root_uri, "", out)
        return out

    def _walk_dates(self, inst, schema, uri, ptr, out, depth=0):
        if depth > 60 or not isinstance(schema, dict):
            return
        # resolve $ref to find format on the leaf
        s = schema
        seen = 0
        while isinstance(s, dict) and "$ref" in s and seen < 20:
            s, uri = _V._deref(s["$ref"], uri, self.v._store)
            seen += 1
            if s is None:
                return
        if not isinstance(s, dict):
            return
        if isinstance(inst, str) and s.get("format") == "date":
            out.append((ptr, inst))
            return
        props, items = _V._effective(s, uri, self.v._store)
        if isinstance(inst, dict):
            for k, v in inst.items():
                if k in props:
                    sub, suri = props[k]
                    self._walk_dates(v, sub, suri, f"{ptr}/{k}", out, depth + 1)
        elif isinstance(inst, list) and items is not None:
            isch, iuri = items
            for i, el in enumerate(inst):
                self._walk_dates(el, isch, iuri, f"{ptr}/{i}", out, depth + 1)


# --------------------------------------------------------------------------- primitives

_REGISTRY: dict[str, Callable] = {}


def primitive(name):
    def deco(fn):
        _REGISTRY[name] = fn
        return fn
    return deco


def _vals(inst, path):
    return [(p, v) for p, v in resolve(inst, path) if v is not None]


@primitive("age_years_range")
def _age(inst, pr, ctx):
    frm = next((v for _, v in _vals(inst, pr["from"])), None)
    to = next((v for _, v in _vals(inst, pr["to"])), None)
    a, b = _date_tuple(to), _date_tuple(frm)
    if a and b:
        age = a[0] - b[0]
        if not (pr["min"] <= age <= pr["max"]):
            yield RuleFinding("", "", "", f"age {age}y outside [{pr['min']},{pr['max']}] "
                              f"({pr['from']}={frm} vs {pr['to']}={to})", pr["to"])


@primitive("enum_allowed")
def _enum(inst, pr, ctx):
    allowed = set(pr["allowed"])
    for p, v in _vals(inst, pr["path"]):
        if v not in allowed:
            yield RuleFinding("", "", "", f"value {v!r} not in allowed {sorted(allowed)}", p)


@primitive("array_contains")
def _contains(inst, pr, ctx):
    where = pr["where"]
    for base, arr in resolve(inst, pr["array"]):
        if not isinstance(arr, list):
            continue
        if not any(isinstance(e, dict) and all(e.get(k) == val for k, val in where.items()) for e in arr):
            yield RuleFinding("", "", "", f"no element of {pr['array']} matches {where}", base)


@primitive("date_order")
def _order(inst, pr, ctx):
    """Every value at `before` must be <= (or < if allow_equal false) every value at `after`."""
    allow_eq = pr.get("allow_equal", True)
    befores = [(p, _date_tuple(v)) for p, v in _vals(inst, pr["before"])]
    afters = [(p, _date_tuple(v)) for p, v in _vals(inst, pr["after"])]
    for pb, b in befores:
        for pa, a in afters:
            if b and a and (b > a or (b == a and not allow_eq)):
                yield RuleFinding("", "", "", f"{pr['before']}({pb}) must be "
                                  f"{'<=' if allow_eq else '<'} {pr['after']}({pa})", pb)


@primitive("dates_after")
def _after(inst, pr, ctx):
    """Every value at each of `paths` must be >= `anchor`."""
    anchor = next((_date_tuple(v) for _, v in _vals(inst, pr["anchor"])), None)
    if not anchor:
        return
    for path in pr["paths"]:
        for p, v in _vals(inst, path):
            t = _date_tuple(v)
            if t and t < anchor:
                yield RuleFinding("", "", "", f"{path}({v}) is before {pr['anchor']} consent date", p)


@primitive("all_dates_not_before")
def _not_before_birth(inst, pr, ctx):
    floor = next((_date_tuple(v) for _, v in _vals(inst, pr["floor"])), None)
    if not floor:
        return
    excl = set(pr.get("exclude_pointers", []))
    for ptr, v in ctx.date_fields(inst):
        if any(ptr.startswith(e) for e in excl):
            continue
        t = _date_tuple(v)
        if t and t < floor:
            yield RuleFinding("", "", "", f"date {v} at {ptr} is before birthDate floor {pr['floor']}", ptr)


@primitive("all_dates_before_by_condition")
def _before_anchor(inst, pr, ctx):
    cond = next((v for _, v in _vals(inst, pr["condition"])), None)
    spec = pr["cases"].get(cond)
    if not spec:
        return  # condition value has no anchor (e.g. 'test') -> skip
    paths = [spec] if isinstance(spec, str) else spec   # a case may list OD + RD anchors
    anchor_ptrs, anchor = set(), None
    for ap in paths:
        for ptr, v in _vals(inst, ap):
            anchor_ptrs.add(ptr)
            t = _date_tuple(v)
            if t and anchor is None:
                anchor = t
    if anchor is None:
        return
    excl = tuple(pr.get("exclude_regex", []))
    for ptr, v in ctx.date_fields(inst):
        if ptr in anchor_ptrs:            # never compare the active anchor against itself
            continue
        if any(re.search(rx, ptr) for rx in excl):
            continue
        t = _date_tuple(v)
        if t and t > anchor:
            yield RuleFinding("", "", "", f"date {v} at {ptr} not before {paths} "
                              f"(submission type {cond})", ptr)


def _tnm_category(e):
    """T/N/M category from a TNM entry. UICC/AJCC codes are 'T3'/'N0'; SNOMED codes are numeric
    with the notation in display/text (e.g. 'cT1a1','cN1','pM1' — optional c/p/y/r/a prefix)."""
    if not isinstance(e, dict):
        return None
    for s in (e.get("display"), e.get("text"), e.get("code")):
        # find a TNM notation token anywhere: optional staging prefix (c/p/y/r/a) + T|N|M +
        # a value char (digit / x / i(s)). Works for 'T3', 'cT1a1', 'cN1', 'pM1', and verbose
        # SNOMED displays like 'American Joint Committee on Cancer cT1 ...'.
        m = re.search(r"(?:^|[^A-Za-z])[cpyra]{0,2}([TNM])[0-9xXi]", s or "")
        if m:
            return m.group(1).upper()
    return None


@primitive("tnm_one_each")
def _tnm(inst, pr, ctx):
    for base, arr in resolve(inst, pr["array"]):
        if not isinstance(arr, list) or not arr:
            continue
        cat = {"T": 0, "N": 0, "M": 0}
        for e in arr:
            c = _tnm_category(e)
            if c in cat:
                cat[c] += 1
        if any(n != 1 for n in cat.values()):
            yield RuleFinding("", "", "", f"TNM must have exactly one T,N,M; got {cat}", base)


@primitive("enum_by_condition")
def _enum_cond(inst, pr, ctx):
    cond = next((v for _, v in _vals(inst, pr["condition"])), None)
    if cond != pr["equals"]:
        return
    allowed = set(pr["allowed"])
    for path in pr["paths"]:
        for p, v in _vals(inst, path):
            if v not in allowed:
                yield RuleFinding("", "", "", f"{path}={v!r} not in {sorted(allowed)} "
                                  f"when {pr['condition']}={pr['equals']!r}", p)


@primitive("id_equals_config")
def _id_eq(inst, pr, ctx):
    want = ctx.config.get(pr["config_key"])
    if want is None:
        yield RuleFinding("", "", "info", f"skipped: needs config '{pr['config_key']}' "
                          f"to check {pr['path']}", pr["path"])
        return
    for p, v in _vals(inst, pr["path"]):
        if v != want:
            yield RuleFinding("", "", "", f"{pr['path']}={v!r} != configured {pr['config_key']}={want!r}", p)


@primitive("id_in_list")
def _id_in(inst, pr, ctx):
    lst = ctx.config.get(pr["config_key"])
    if lst is None:
        yield RuleFinding("", "", "info", f"skipped: needs config list '{pr['config_key']}' "
                          f"to check {pr['path']}", pr["path"])
        return
    allowed = set(lst)
    for p, v in _vals(inst, pr["path"]):
        if v not in allowed:
            yield RuleFinding("", "", "", f"{pr['path']}={v!r} not in configured '{pr['config_key']}'", p)


# --------------------------------------------------------------------------- engine

def load_ruleset(name: str) -> dict:
    path = resources.files(__package__) / "rules" / f"{name}.rules.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_rules(validator, dk, branch: str, ruleset: str, config: dict | None = None) -> list[RuleFinding]:
    ctx = _Ctx(validator, branch, config or {})
    findings: list[RuleFinding] = []
    for rule in load_ruleset(ruleset).get("rules", []):
        if rule.get("enabled") is False:
            continue
        prim = rule.get("primitive")
        fn = _REGISTRY.get(prim)
        rid, sev = rule.get("id", "?"), rule.get("severity", "error")
        if fn is None:
            # rules are explicitly requested here, so a rule that cannot run must FAIL, not pass
            findings.append(RuleFinding(rid, prim or "?", "error", f"unknown primitive {prim!r}"))
            continue
        try:
            for f in fn(dk, rule.get("params", {}), ctx):
                f.rule_id, f.primitive = rid, prim
                f.level = f.level or sev   # primitive may downgrade to info (skips)
                findings.append(f)
        except Exception as e:  # a broken rule must not crash validation — but must not pass silently
            findings.append(RuleFinding(rid, prim, "error", f"rule error: {type(e).__name__}: {e}"))
    return findings
