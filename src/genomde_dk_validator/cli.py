"""Command-line interface: genomde-dk-validator [paths...]"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

from .validator import DatenkranzValidator


def _discover(paths: list[str]) -> list[str]:
    files: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.json"), recursive=True)
        elif os.path.isfile(p):
            files.append(p)
        else:
            files += glob.glob(p, recursive=True)
    # dedup by resolved path; keep only real files (a glob/dir can surface directories)
    return sorted({os.path.realpath(f) for f in files if os.path.isfile(f)})


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
    ap.add_argument("--fhirpath", action="store_true",
                    help="evaluate the rules as FHIRPath invariants (needs the 'fhirpathpy' extra) "
                         "instead of the built-in primitive engine")
    ap.add_argument("--rules-config", metavar="FILE",
                    help="JSON with external inputs for rules (e.g. {\"clinical_data_node_id\":\"...\", "
                         "\"genomic_data_center_id\":\"...\", \"le_ids\":[...]})")
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="show more finding levels: default = errors only; -v adds warnings; "
                         "-vv adds info (skipped rules)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable JSON report to stdout")
    ap.add_argument("-o", "--output", metavar="FILE",
                    help="write the JSON report to FILE (all findings, regardless of -v) instead of text")
    ap.add_argument("--quiet", "-q", action="store_true",
                    help="verdict only; no per-finding list (the summary needs -v)")
    ap.add_argument("--show", type=int, default=40, help="max findings listed in text mode (raise it or use -o for all)")
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
        if not isinstance(rules_config, dict):
            print(f"--rules-config must be a JSON object, got {type(rules_config).__name__}", file=sys.stderr)
            return 2

    files = _discover(a.paths)
    if not files:
        print(f"no JSON files found under {a.paths}", file=sys.stderr)
        return 2

    if a.fhirpath and not ruleset:
        print("--fhirpath only applies with --kdk-rules/--grz-rules", file=sys.stderr)
        return 2
    if a.fhirpath:
        try:
            import fhirpathpy  # noqa: F401
        except ImportError:
            print("--fhirpath needs the 'fhirpath' extra: "
                  "pip install 'genomde-dk-validator[fhirpath]'", file=sys.stderr)
            return 2
    engine = "fhirpath" if a.fhirpath else "primitive"
    v = DatenkranzValidator(check_unknown=not a.no_unknown)
    results = [v.validate_file(f, rules=ruleset, rules_config=rules_config, rules_engine=engine)
               for f in files]

    # tally by severity. unknown fields are warnings unless --strict promotes them to errors.
    unk_level = "error" if a.strict else "warning"
    n_schema = sum(1 for r in results if r.schema_errors)
    n_unknown = sum(1 for r in results if r.unknown_fields)
    n_rule = sum(1 for r in results if r.rule_errors)
    n_warn = sum((0 if a.strict else len(r.unknown_fields))
                 + sum(1 for f in r.rule_findings if f.level == "warning") for r in results)
    n_info = sum(1 for r in results for f in r.rule_findings if f.level == "info")
    n_noschema = sum(1 for r in results if not r.has_schema)
    failed = sum(1 for r in results if not r.ok(strict=a.strict))
    # exit code by worst outcome: 1 errors > 3 warnings-only > 0 clean (2 is reserved for usage errors)
    code = 1 if failed else 3 if n_warn else 0

    if a.json or a.output:
        text = json.dumps({
            "files": len(files), "strict": a.strict, "ruleset": ruleset, "exit_code": code,
            "summary": {"failed": failed, "warnings": n_warn, "info": n_info,
                        "schema_invalid": n_schema, "no_schema": n_noschema},
            "results": [{
                "file": r.file, "branch": r.branch, "ok": r.ok(strict=a.strict),
                "schema_errors": [vars(f) for f in r.schema_errors],
                "unknown_fields": [vars(f) for f in r.unknown_fields],
                "rule_findings": [vars(f) for f in r.rule_findings],
            } for r in results],
        }, indent=2, ensure_ascii=False)
        if a.output:
            with open(a.output, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            print(f"wrote JSON report to {a.output}", file=sys.stderr)
        else:
            print(text)
        return code

    # text report. Default (no -v) is minimal: just the error findings + a one-line verdict.
    # -v/-vv add the header + summary block, the extra finding levels, and the hidden-count hint.
    verdict = "PASS" if not failed else f"FAIL ({failed} file(s))"
    if not failed and n_warn:
        verdict += f", {n_warn} warning(s)"

    if a.verbose >= 1:
        per_branch = collections.Counter(r.branch for r in results)
        print(f"\n=== genomDE Datenkranz schema validation ({len(files)} files) ===")
        print(f"branches: {dict(per_branch)}{'  | rules: '+ruleset.upper() if ruleset else ''}")
        print(f"schema-invalid: {n_schema} | warnings: {n_warn}"
              f"{' | rule-violations: '+str(n_rule) if ruleset else ''}"
              f"{f' | info skipped (need --rules-config): {n_info}' if n_info else ''}"
              f" | no-schema (branch): {n_noschema}")

    if not a.quiet:
        levels = {"error"}                       # default: errors only
        if a.verbose >= 1: levels.add("warning")  # -v
        if a.verbose >= 2: levels.add("info")     # -vv
        shown = more = hidden = 0
        for r in results:
            items = [("error", f"schema/{e.validator}", e) for e in r.schema_errors]
            items += [(unk_level, "unknown-field", e) for e in r.unknown_fields]
            items += [(e.level, f"rule:{e.rule_id}", e) for e in r.rule_findings]
            for level, tag, e in items:
                if level not in levels:
                    hidden += 1
                    continue
                if shown >= a.show:
                    more += 1
                    continue
                where = f"{r.file}:{e.line}:{e.col}" if getattr(e, "line", None) else r.file
                print(f"  [{level:7} {tag}] {where}  {e.path}: {e.message[:110]}")
                shown += 1
        if more:
            print(f"  … {more} more shown-level finding(s) — raise --show or use -o for the full report")
        if hidden and a.verbose >= 1:          # only hint about lower levels once the user opted into -v
            print(f"  … {hidden} lower-severity finding(s) hidden"
                  + (" (-vv for info)" if a.verbose == 1 else ""))

    print(f"verdict: {verdict}   [exit {code}]" if a.verbose >= 1 else verdict)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
