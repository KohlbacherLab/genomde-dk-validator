# Changelog

## 1.1.2
- Docs: list the `--show` flag, correct the `-q` description for the minimal-default output. No behavior change.

## 1.1.1
- Minimal default output: without `-v`, a clean run prints just `PASS` and a failing run prints only
  the error findings + `FAIL (N)`. The header, summary block, and "lower-severity hidden" hint now
  appear only with `-v`/`-vv`.

## 1.1.0
- **Verbosity levels**: text output shows **errors only** by default; `-v` adds warnings, `-vv` adds
  info (rules skipped for missing `--rules-config`). Hidden lower-severity findings are counted with a
  hint. `-q` stays "verdict + summary only".
- **Severity-based exit codes**: `0` clean · `3` warnings only (e.g. non-strict unknown fields) ·
  `1` errors · `2` usage/no-input. (Previously warnings-only also returned `0`.)
- **`-o FILE`** writes the JSON report (all findings, ignoring `-v`) to a file; `--json` still prints
  it to stdout. JSON now carries a top-level `exit_code` and `summary` block.

## 1.0.0
Correctness + cleanup pass (both rule engines stay byte-identical on the corpus: 1182 KDK + 1006 GRZ).
- **FHIRPath date rules complete**: rules 6/7 now enumerate the full schema-derived set of
  `format:date` paths (24; was missing `case.priorProcedures.therapyResponseDate`,
  `case.priorRds.diagnosticDate`, `followUp.followUpOds.additionalDiagnoses.date`) — the union is
  generated from the schema, not hand-listed.
- **TNM invariant (rule 5) aligned to the primitive**: reads the T/N/M category from `display`, `text`
  *or* `code`, token anywhere (was `display`-only, anchored) — no longer diverges on code-only TNM.
- **Malformed JSON** reports the syntax-error `line:col` (was dropped).
- **Unclassifiable input** emits an actionable `(root)` finding instead of a silent fail.
- Source-position map uses stdlib `json.decoder.scanstring` (correct escape / surrogate-pair handling).
- `--fhirpath` without the extra fails cleanly (exit 2) instead of a traceback; config-gated
  **rules-skipped** count is surfaced in the summary so a gated PASS isn't misleading.
- Cleanup: dropped the dead pre-3.8 `referencing` fallback, `_make_validator`, `CATALOG_VERSION`,
  and an unused import; the offline registry is built once.

## 0.10.0
- **FHIRPath invariant rule backend** (`--fhirpath`, optional `[fhirpath]` extra): the BfArM QS
  criteria authored as FHIR-`constraint`-style invariants (key/severity/human/expression/source) and
  evaluated over the plain Datenkranz JSON via `fhirpathpy` — the DK isn't FHIR, but core FHIRPath is
  data-model-agnostic. Produces **identical results to the primitive engine on the full corpus**
  (1098 KDK + 1000 GRZ). Files: `rules/{kdk,grz}.invariants.json`. Authoring notes captured:
  cross-field refs inside `all()`/`where()` must use `%context`; optional fields need empty-guards;
  "all date-format field" rules enumerate the schema's date paths (no reliable `descendants()`).

## 0.9.2
- Unknown-field detection ignores all `$`-prefixed JSON Schema / structural meta-keys (`$schema`, `$id`, `$ref`, `$comment`, …) at any level — they are annotations/hints, not Datenkranz data fields. (Schema validation itself is unchanged: it uses `jsonschema` and already permits them since the BfArM schemas don't set `additionalProperties:false`.)

## 0.9.1
- **Findings now report `file:line:col`** in the input file (pure-Python JSON source-position map),
  and the text report lists findings per file with their location instead of cross-file patterns.
- Top-level JSON meta-key `$schema` is no longer flagged as an unknown field.
- **Python floor is ≥ 3.8** (`jsonschema` ≥ 4.18 needs it). On Python 3.7 (Anaconda base) `pip` now
  refuses cleanly (`requires a different Python`) instead of the confusing `jsonschema` resolution
  error. `referencing` is declared explicitly.

## 0.9.0
First tagged pre-release.

- Schema validation against vendored BfArM KDK+GRZ schemas (offline `$ref` registry), branch
  auto-detection, and unknown-field detection (`--strict`).
- BfArM Qualitätssicherung semantic-rule engine (rules-as-data + primitive catalog), enabled with
  `--kdk-rules` / `--grz-rules`; each rule cites its source criterion. Branch sanity check +
  `--rules-config` for external inputs.
- Hardened per two adversarial reviews (rule set + code): format checking enabled; broken/unknown
  rules fail rather than pass silently; crash-safe error sorting; hostile-input tolerance; portable
  package-data access (zip-wheel safe); strict date parsing; `referencing` declared. Verified on
  clean Python 3.9. 18 tests.

### Known follow-ups for 1.0
- Filter the mvConsent anchor to `type=permit, domain=mvSequencing` (kdk-9b).
- Interval-aware comparison for month-only dates (`YYYY-MM`).
- KDK criterion 2 indication-admission (beyond LE-ID membership).
- `patternProperties` / JSON-Pointer key escaping in the unknown-field walker.
