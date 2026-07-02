"""
Validate genomDE Datenkranz JSON against the authoritative BfArM JSON Schemas.

Branch is auto-detected and mapped to its root schema:
  case.diagnosisOd  -> KDK Oncology.json
  case.diagnosisRd  -> KDK RareDiseases.json
  donors+submission -> GRZ grz-schema.json

Two kinds of finding:
  * schema errors  — the instance violates the JSON Schema (jsonschema, Draft 2020-12).
  * unknown fields — properties present in the data but NOT declared anywhere in the schema.
    The BfArM schemas never set `additionalProperties: false`, so such fields pass jsonschema
    silently; we detect and report them (warning by default, error with strict=True).

Schemas are vendored as package data; the KDK root schemas $ref siblings by absolute BfArM
GitHub URL, resolved to the local copies via an in-memory store — no network access.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Iterator

from jsonschema import Draft202012Validator, FormatChecker

# `referencing` is the modern (jsonschema >= 4.18, Python >= 3.8) $ref registry. On older jsonschema
# (down to 4.0 on Python 3.7) it is absent — fall back to the legacy RefResolver so the package still
# installs and runs. The unknown-field walker uses its own store-based resolver either way.
try:
    from referencing import Registry
    from referencing.jsonschema import DRAFT202012
    _HAVE_REFERENCING = True
except ImportError:  # pragma: no cover - exercised on old jsonschema
    _HAVE_REFERENCING = False

# canonical URLs the vendored schemas use / are published at
KDK_BASE = "https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_KDK/main/KDK/"
GRZ_URL = "https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_GRZ/main/GRZ/grz-schema.json"

ROOTS = {  # branch -> root schema URI in the store
    "oncology": KDK_BASE + "Oncology.json",
    "rare-disease": KDK_BASE + "RareDiseases.json",
    "grz": GRZ_URL,
}

# which detected branches each semantic rule set legitimately applies to (sanity check)
RULESET_BRANCHES = {"kdk": {"oncology", "rare-disease"}, "grz": {"grz"}}


def _schema_root():
    return resources.files(__package__) / "schemas"


def _iter_json(trav, prefix=""):
    """Recurse a Traversable yielding (relative_posix_path, resource) for *.json — uses only the
    portable importlib.resources API (iterdir/is_dir/name), so it works from a zip wheel too."""
    for entry in trav.iterdir():
        rel = f"{prefix}{entry.name}"
        if entry.is_dir():
            yield from _iter_json(entry, prefix=f"{rel}/")
        elif entry.name.endswith(".json"):
            yield rel, entry


def _build_store() -> dict[str, Any]:
    """uri -> schema contents for every vendored schema file."""
    root = _schema_root()
    store: dict[str, Any] = {}
    for rel, res in _iter_json(root / "kdk"):     # OncologyCase.json | data-types/Coding.json | ...
        store[KDK_BASE + rel] = json.loads(res.read_text(encoding="utf-8"))
    store[GRZ_URL] = json.loads((root / "grz" / "grz-schema.json").read_text(encoding="utf-8"))
    return store


def _build_registry(store: dict[str, Any]):
    return Registry().with_resources(
        [(uri, DRAFT202012.create_resource(contents)) for uri, contents in store.items()]
    )


def _make_validator(schema, uri, store):
    """A Draft 2020-12 validator whose $refs resolve offline against `store`."""
    if not _HAVE_REFERENCING:
        raise RuntimeError(
            "genomde-dk-validator requires jsonschema >= 4.18 with the 'referencing' package "
            "(Python >= 3.8). Install under Python >= 3.8, e.g. `python3.11 -m pip install ...`.")
    return Draft202012Validator(schema, registry=_build_registry(store),
                                format_checker=FormatChecker())   # instance form is version-portable


# --------------------------------------------------------------------------- branch

def _is_meta_key(key: str) -> bool:
    """`$`-prefixed keys are JSON Schema / structural meta-keywords ($schema, $id, $ref, $comment,
    $defs, $anchor, $vocabulary, $dynamicRef, ...), never genomDE Datenkranz data fields — so they
    are annotations/hints, not unknown data. genomDE field names are camelCase words."""
    return key.startswith("$")


def _source_map(text: str) -> dict[str, tuple]:
    """Map JSON pointer -> (line, col) (1-based) for every value, by a position-tracking scan.
    Pointers use plain '/'-joined keys (matching the finding pointers). Best-effort: returns {}
    if the text is not parseable (schema validation already reported the malformed JSON)."""
    n = len(text)
    line_starts = [0] + [i + 1 for i, c in enumerate(text) if c == "\n"]

    def linecol(off):
        import bisect
        ln = bisect.bisect_right(line_starts, off)
        return ln, off - line_starts[ln - 1] + 1

    pos: dict[str, tuple] = {}

    def ws(i):
        while i < n and text[i] in " \t\r\n":
            i += 1
        return i

    def string(i):                       # text[i] == '"'; returns (value, next_i)
        j = i + 1
        buf = []
        while j < n:
            c = text[j]
            if c == "\\":
                e = text[j + 1]
                if e == "u":
                    buf.append(chr(int(text[j + 2:j + 6], 16))); j += 6; continue
                buf.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}.get(e, e)); j += 2; continue
            if c == '"':
                return "".join(buf), j + 1
            buf.append(c); j += 1
        raise ValueError("unterminated string")

    def value(i, ptr):
        i = ws(i)
        pos[ptr] = linecol(i)
        c = text[i]
        if c == "{":
            i += 1
            while True:
                i = ws(i)
                if text[i] == "}":
                    return i + 1
                key, i = string(ws(i))
                i = ws(i) + 1                         # skip ':'
                i = value(i, f"{ptr}/{key}")
                i = ws(i)
                if text[i] == ",":
                    i += 1
                elif text[i] == "}":
                    return i + 1
        elif c == "[":
            i += 1
            idx = 0
            while True:
                i = ws(i)
                if text[i] == "]":
                    return i + 1
                i = value(i, f"{ptr}/{idx}")
                idx += 1
                i = ws(i)
                if text[i] == ",":
                    i += 1
                elif text[i] == "]":
                    return i + 1
        elif c == '"':
            return string(i)[1]
        else:
            j = i
            while j < n and text[j] not in ",}] \t\r\n":
                j += 1
            return j

    try:
        value(0, "")
    except Exception:
        return {}
    return pos


def _to_pointer(path: str):
    """Normalize a finding path to a JSON pointer for source-map lookup, or None if not addressable."""
    if not path or path == "(root)" or path == "(file)":
        return ""
    if path.startswith("/"):
        return path
    if "[]" in path:                     # unresolved rule wildcard, no single location
        return None
    return "/" + path.replace(".", "/")  # dotted rule path -> pointer


def classify(dk: Any) -> str:
    if not isinstance(dk, dict):
        return "unknown"
    if "donors" in dk and "submission" in dk:
        return "grz"
    case = dk.get("case")
    case = case if isinstance(case, dict) else {}
    if "diagnosisOd" in case:
        return "oncology"
    if "diagnosisRd" in case:
        return "rare-disease"
    if "metadata" in dk and "metaData" not in dk:
        return "legacy-variant"
    return "unknown"


# --------------------------------------------------------------------------- unknown-field walk

def _deref(ref: str, cur_uri: str, store: dict[str, Any]):
    """Resolve a $ref (absolute URL, absolute#frag, or #frag). Returns (node, new_cur_uri)."""
    base, _, frag = ref.partition("#")
    doc_uri = base or cur_uri
    doc = store.get(doc_uri)
    if doc is None:
        return None, cur_uri
    node = doc
    if frag:
        for part in frag.strip("/").split("/"):
            if part == "":
                continue
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(node, list):
                try:
                    node = node[int(part)]
                except (ValueError, IndexError):
                    return None, doc_uri
            elif isinstance(node, dict):
                node = node.get(part)
                if node is None:
                    return None, doc_uri
            else:
                return None, doc_uri
    return node, doc_uri


def _effective(schema, cur_uri, store, _depth=0):
    """
    Follow $ref and merge combinators to a single view of an object schema.
    Returns (props: dict[name->(subschema, sub_uri)], items: (schema, uri)|None).
    Property names are unioned across properties + allOf/anyOf/oneOf branches (permissive:
    a field allowed by ANY branch is 'known', so we never false-flag).
    """
    if not isinstance(schema, dict) or _depth > 40:
        return {}, None
    if "$ref" in schema:
        node, nuri = _deref(schema["$ref"], cur_uri, store)
        return _effective(node, nuri, store, _depth + 1)
    props: dict[str, tuple] = {}
    for k, v in (schema.get("properties") or {}).items():
        props.setdefault(k, (v, cur_uri))
    for comb in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(comb) or []:
            p2, _ = _effective(sub, cur_uri, store, _depth + 1)
            for k, v in p2.items():
                props.setdefault(k, v)
    items = schema.get("items")
    items_pair = (items, cur_uri) if isinstance(items, dict) else None
    return props, items_pair


def _walk_unknown(instance, schema, cur_uri, store, path="") -> Iterator[str]:
    props, items = _effective(schema, cur_uri, store)
    if isinstance(instance, dict):
        # only flag unknowns when the schema actually describes an object (has declared props)
        if props:
            for key in instance:
                if key in props:
                    sub, suri = props[key]
                    yield from _walk_unknown(instance[key], sub, suri, store, f"{path}/{key}")
                elif not _is_meta_key(key):     # ignore JSON Schema meta-keys ($schema, $id, ...)
                    yield f"{path}/{key}"
    elif isinstance(instance, list) and items is not None:
        isch, iuri = items
        for i, el in enumerate(instance):
            yield from _walk_unknown(el, isch, iuri, store, f"{path}/{i}")


# --------------------------------------------------------------------------- result + API

@dataclass
class Finding:
    kind: str          # "schema" | "unknown"
    path: str
    message: str
    validator: str | None = None
    line: int | None = None   # 1-based source location in the input file (set by validate_file)
    col: int | None = None


@dataclass
class Result:
    file: str
    branch: str
    schema_errors: list[Finding] = field(default_factory=list)
    unknown_fields: list[Finding] = field(default_factory=list)
    rule_findings: list = field(default_factory=list)   # list[rules.RuleFinding]

    @property
    def has_schema(self) -> bool:
        return self.branch in ROOTS

    @property
    def rule_errors(self) -> list:
        return [f for f in self.rule_findings if f.level in ("error", "fatal")]

    def ok(self, strict: bool = False) -> bool:
        if not self.has_schema:
            return False
        if self.schema_errors or self.rule_errors:
            return False
        return not (strict and self.unknown_fields)


class DatenkranzValidator:
    """Reusable validator: build once, validate many."""

    def __init__(self, check_unknown: bool = True):
        self._store = _build_store()
        self._validators = {b: _make_validator(self._store[uri], uri, self._store)
                            for b, uri in ROOTS.items()}
        self.check_unknown = check_unknown

    def validate(self, dk: Any, name: str = "<data>", rules: str | None = None,
                 rules_config: dict | None = None) -> Result:
        branch = classify(dk)
        res = Result(file=name, branch=branch)
        if branch not in ROOTS:
            if rules:  # sanity: asked to run a rule set on something that isn't KDK/GRZ
                res.rule_findings.append(self._sanity(rules, branch))
            return res
        v = self._validators[branch]
        for e in sorted(v.iter_errors(dk), key=lambda e: [str(p) for p in e.absolute_path]):
            loc = "/" + "/".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
            res.schema_errors.append(Finding("schema", loc, e.message[:300], e.validator))
        if self.check_unknown:
            for p in _walk_unknown(dk, self._store[ROOTS[branch]], ROOTS[branch], self._store):
                res.unknown_fields.append(Finding("unknown", p, "field not declared in schema"))
        if rules:
            expected = RULESET_BRANCHES.get(rules, set())
            if branch not in expected:
                res.rule_findings.append(self._sanity(rules, branch))
            else:
                from . import rules as _rules
                res.rule_findings.extend(_rules.run_rules(self, dk, branch, rules, rules_config))
        return res

    @staticmethod
    def _sanity(ruleset: str, branch: str):
        from .rules import RuleFinding
        return RuleFinding(f"{ruleset}-sanity", "branch_check", "error",
                           f"--{ruleset}-rules requested but this is not a {ruleset.upper()} "
                           f"Datenkranz (detected branch: {branch})")

    def validate_file(self, path, rules: str | None = None, rules_config: dict | None = None) -> Result:
        import pathlib
        p = pathlib.Path(path)
        try:
            text = p.read_text(encoding="utf-8")
            dk = json.loads(text)
        except Exception as e:
            r = Result(file=str(p), branch="unreadable")
            r.schema_errors.append(Finding("schema", "(file)", f"unreadable: {e}"))
            return r
        res = self.validate(dk, name=str(p), rules=rules, rules_config=rules_config)
        smap = _source_map(text)          # attach input-file line/col to every finding
        for f in (*res.schema_errors, *res.unknown_fields, *res.rule_findings):
            ptr = _to_pointer(f.path)
            if ptr is not None and ptr in smap:
                f.line, f.col = smap[ptr]
        return res
