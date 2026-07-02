# Changelog

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
