# genomde-dk-validator

Validate **genomDE Datenkranz** JSON (BfArM Modellvorhaben Genomsequenzierung, §64e SGB V)
against the **authoritative BfArM JSON Schemas** — KDK (Oncology / Rare Diseases) and GRZ.

- **Self-contained** — the BfArM schemas are vendored as package data; validation runs fully
  offline (the schemas' GitHub `$ref`s are resolved to the local copies, no network access).
- **Branch auto-detection** — Oncology / Rare Diseases / GRZ picked from the payload.
- **Unknown-field detection** — the BfArM schemas never set `additionalProperties: false`, so
  fields not defined in the schema pass a plain JSON-Schema check silently. This tool reports
  them (warning by default, error with `--strict`) — catching typos and renamed/extra fields
  (e.g. `priorDiagnostic` vs the schema's `priorDiagnostics`).

## Install

```bash
pip install git+https://github.com/KohlbacherLab/genomde-dk-validator.git
# or, from a checkout:
pip install .
```
Requires Python ≥ 3.9 (pulls in `jsonschema` ≥ 4.18 for Draft 2020-12 + the `referencing` registry).

## CLI

```bash
genomde-dk-validator path/to/datenkranz.json           # one file
genomde-dk-validator data/ another/dir                 # directories (recursive)
genomde-dk-validator "data/**/*.json"                  # glob

genomde-dk-validator --strict data/                    # unknown fields => errors (exit 1)
genomde-dk-validator --no-unknown data/                # schema validation only
genomde-dk-validator --json data/ > report.json        # machine-readable
genomde-dk-validator -q data/                          # summary only
```

Exit code `0` = all pass, `1` = at least one file failed (schema error, or — with `--strict` —
unknown fields), `2` = no input files. Example:

```
=== genomDE Datenkranz schema validation (500 files) ===
branches: {'oncology': 500}
schema-invalid: 476 | with unknown fields: 0 | no-schema (branch): 0
verdict: FAIL (476 file(s))

--- oncology: top findings ---
   431x [schema/type] /plan/recommendedSystemicTherapies/[]/identifier: ...
```

## Python API

```python
from genomde_dk_validator import DatenkranzValidator

v = DatenkranzValidator()                 # build once, reuse
r = v.validate_file("datenkranz.json")    # or v.validate(dict, name=...)

r.branch            # "oncology" | "rare-disease" | "grz" | "legacy-variant" | "unknown"
r.schema_errors     # list[Finding]  — JSON-Schema violations
r.unknown_fields    # list[Finding]  — fields not declared in the schema
r.ok()              # True if schema-valid (unknowns are warnings)
r.ok(strict=True)   # False if any unknown fields
```

Each `Finding` has `.kind` (`"schema"`/`"unknown"`), `.path` (JSON pointer), `.message`,
and `.validator` (the failing JSON-Schema keyword, for schema errors).

## Branch → schema

| detected by | branch | root schema |
|---|---|---|
| `case.diagnosisOd` | oncology | KDK `Oncology.json` |
| `case.diagnosisRd` | rare-disease | KDK `RareDiseases.json` |
| `donors` + `submission` | grz | GRZ `grz-schema.json` |

## Schema provenance

Vendored under `src/genomde_dk_validator/schemas/`, byte-identical to the authoritative BfArM
releases (see `schemas/PROVENANCE.md`):

| schema | repo | release tag | content version |
|---|---|---|---|
| KDK | [BfArM-MVH/MVGenomseq_KDK](https://github.com/BfArM-MVH/MVGenomseq_KDK) | v2.3 | 1.7.1 |
| GRZ | [BfArM-MVH/MVGenomseq_GRZ](https://github.com/BfArM-MVH/MVGenomseq_GRZ) | v1.3.0 | 1.2.3 |

To update, replace the files under `schemas/` from the upstream tag and bump the versions above.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
