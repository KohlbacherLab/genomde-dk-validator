"""Command-line interface: genomde-dk-validator [paths...]"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

from .validator import DatenkranzValidator, ROOTS


def _discover(paths: list[str]) -> list[str]:
    files: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.json"), recursive=True)
        elif os.path.isfile(p):
            files.append(p)
        else:
            files += glob.glob(p, recursive=True)
    return sorted(set(files))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="genomde-dk-validator",
        description="Validate genomDE Datenkranz JSON against the BfArM JSON Schemas (KDK + GRZ).",
    )
    ap.add_argument("paths", nargs="+", help="JSON file(s), directory(ies), or glob(s)")
    ap.add_argument("--strict", action="store_true",
                    help="treat unknown fields (not in the schema) as errors, not warnings")
    ap.add_argument("--no-unknown", action="store_true",
                    help="disable unknown-field detection (schema validation only)")
    ap.add_argument("--kdk-rules", action="store_true",
                    help="enforce the BfArM KDK quality-assurance semantic rules (oncology/rare-disease)")
    ap.add_argument("--grz-rules", action="store_true",
                    help="enforce the BfArM GRZ quality-assurance semantic rules")
    ap.add_argument("--rules-config", metavar="FILE",
                    help="JSON with external inputs for rules (e.g. {\"clinical_data_node_id\":\"...\", "
                         "\"genomic_data_center_id\":\"...\", \"le_ids\":[...]})")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="emit a machine-readable JSON report to stdout")
    ap.add_argument("--quiet", "-q", action="store_true",
                    help="summary only; do not list per-file findings")
    ap.add_argument("--show", type=int, default=15, help="max error patterns per branch (text mode)")
    a = ap.parse_args(argv)

    if a.kdk_rules and a.grz_rules:
        print("choose only one of --kdk-rules / --grz-rules", file=sys.stderr)
        return 2
    ruleset = "kdk" if a.kdk_rules else "grz" if a.grz_rules else None
    rules_config = None
    if a.rules_config:
        try:
            rules_config = json.loads(open(a.rules_config, encoding="utf-8").read())
        except Exception as e:
            print(f"could not read --rules-config {a.rules_config}: {e}", file=sys.stderr)
            return 2

    files = _discover(a.paths)
    if not files:
        print(f"no JSON files found under {a.paths}", file=sys.stderr)
        return 2

    v = DatenkranzValidator(check_unknown=not a.no_unknown)
    results = [v.validate_file(f, rules=ruleset, rules_config=rules_config) for f in files]

    n_err = sum(1 for r in results if r.schema_errors)
    n_unknown = sum(1 for r in results if r.unknown_fields)
    n_rule = sum(1 for r in results if r.rule_errors)
    n_noschema = sum(1 for r in results if not r.has_schema)
    failed = sum(1 for r in results if not r.ok(strict=a.strict))

    if a.as_json:
        print(json.dumps({
            "files": len(files), "strict": a.strict,
            "ruleset": ruleset,
            "results": [{
                "file": r.file, "branch": r.branch, "ok": r.ok(strict=a.strict),
                "schema_errors": [vars(f) for f in r.schema_errors],
                "unknown_fields": [vars(f) for f in r.unknown_fields],
                "rule_findings": [vars(f) for f in r.rule_findings],
            } for r in results],
        }, indent=2, ensure_ascii=False))
        return 1 if failed else 0

    # text report
    per_branch = collections.Counter(r.branch for r in results)
    print(f"\n=== genomDE Datenkranz schema validation ({len(files)} files) ===")
    print(f"branches: {dict(per_branch)}"
          f"{'  | rules: '+ruleset.upper() if ruleset else ''}")
    print(f"schema-invalid: {n_err} | with unknown fields: {n_unknown}"
          f"{' | rule-violations: '+str(n_rule) if ruleset else ''} | no-schema (branch): {n_noschema}")
    print(f"verdict: {'PASS' if not failed else f'FAIL ({failed} file(s))'}"
          f"{' [strict: unknown=error]' if a.strict else ''}")

    if not a.quiet:
        # aggregate error patterns per branch
        pats = collections.defaultdict(collections.Counter)
        for r in results:
            for e in r.schema_errors:
                pats[r.branch][("schema", e.validator, e.path, e.message[:70])] += 1
            for e in r.unknown_fields:
                pats[r.branch][("unknown", None, e.path, "field not in schema")] += 1
            for e in r.rule_findings:
                if e.level in ("error", "fatal"):
                    pats[r.branch][("rule:" + e.rule_id, None, e.path, e.message[:70])] += 1
        for branch, ctr in pats.items():
            if not ctr:
                continue
            print(f"\n--- {branch}: top findings ---")
            for (kind, val, path, msg), n in ctr.most_common(a.show):
                tag = "UNKNOWN" if kind == "unknown" else kind if kind.startswith("rule:") else f"schema/{val}"
                print(f"  {n:5}x [{tag}] {path}: {msg}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
