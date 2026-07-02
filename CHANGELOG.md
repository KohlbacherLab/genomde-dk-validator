# Changelog

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
