"""
Alternative rule backend: the BfArM QS criteria as **FHIRPath invariants**.

Each rule is authored like a FHIR `ElementDefinition.constraint` — `key`, `severity`, `human`,
`source`, and a FHIRPath `expression` that MUST evaluate to boolean `true` for a valid case —
but evaluated over the *plain* KDK/GRZ Datenkranz JSON (which is not FHIR). This works because
core FHIRPath (navigation, `where`/`exists`/`all`/`implies`, comparisons, arithmetic) is
data-model-agnostic; the pure-Python `fhirpathpy` engine runs it over plain dicts.

Selected with `--fhirpath` alongside `--kdk-rules` / `--grz-rules`. `fhirpathpy` is an optional
dependency (`pip install genomde-dk-validator[fhirpath]`). Files: rules/{kdk,grz}.invariants.json.

`%context` gives each expression the document root; `--rules-config` values are exposed as
`%variables` (e.g. `%le_ids`, `%clinical_data_node_id`) and gated by a rule's `requires_config`.
"""
from __future__ import annotations

import json
from importlib import resources

from .rules import RuleFinding


def load_invariants(name: str) -> dict:
    path = resources.files(__package__) / "rules" / f"{name}.invariants.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluator():
    try:
        from fhirpathpy import evaluate
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "--fhirpath needs the 'fhirpathpy' package: pip install 'genomde-dk-validator[fhirpath]' "
            "(or pip install fhirpathpy).") from e
    return evaluate


def run_invariants(dk, ruleset: str, config: dict | None = None) -> list[RuleFinding]:
    evaluate = _evaluator()
    config = config or {}
    env = dict(config)                       # config keys become %variables
    out: list[RuleFinding] = []
    for inv in load_invariants(ruleset).get("invariants", []):
        key, sev, human = inv["key"], inv.get("severity", "error"), inv.get("human", "")
        need = inv.get("requires_config")
        needs = [need] if isinstance(need, str) else (need or [])
        if any(k not in config for k in needs):
            out.append(RuleFinding(key, "fhirpath-invariant", "info",
                                   f"skipped: needs --rules-config {needs}"))
            continue
        try:
            res = evaluate(dk, inv["expression"], env)
        except Exception as e:
            out.append(RuleFinding(key, "fhirpath-invariant", "error",
                                   f"invariant error: {type(e).__name__}: {e}"))
            continue
        if res == [True]:
            continue                          # satisfied
        if res == [False]:
            out.append(RuleFinding(key, "fhirpath-invariant", sev, human))
        else:                                 # invariants must yield a single boolean
            out.append(RuleFinding(key, "fhirpath-invariant", "error",
                                   f"invariant did not evaluate to a boolean (got {res!r}) "
                                   f"— rule authoring error"))
    return out
