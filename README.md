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

## Semantic rules (BfArM Qualitätssicherung)

Beyond schema + unknown-field checks, the validator can enforce the BfArM **quality-assurance**
criteria (QS durch KDK v01.2; QS durch GRZ v01.4) as **JSON-defined semantic rules** — the
mechanics are adopted from mzPeakValidator: rules are *data*, each an instance of a named
*primitive* (implemented in `rules.py`); the engine reads only `id / primitive / severity / params`.
Rule files: `src/genomde_dk_validator/rules/{kdk,grz}.rules.json`.

Rules are **off by default** and opt-in per data set:

```bash
genomde-dk-validator --kdk-rules  kdk_data/     # enforce the 12 KDK QS criteria
genomde-dk-validator --grz-rules  grz_data/     # enforce the GRZ QS criteria
genomde-dk-validator --kdk-rules --rules-config cfg.json  data/
```

**Sanity check:** `--kdk-rules` on a GRZ file (or vice-versa) fails with a `*-sanity` error — the
detected branch must match the requested rule set (KDK = oncology/rare-disease, GRZ = grz).

**External inputs** (`--rules-config cfg.json`) — some criteria need data not in the JSON; without
the config those rules *skip* (info):
```json
{ "clinical_data_node_id": "KDKTUE005", "genomic_data_center_id": "GRZTUE002", "le_ids": ["260840108"] }
```

Coverage: KDK criteria 1,3,5,6,7,8,9,10,12 are fully enforced; 2 (LE-ID list) and 11 (own node id)
need `--rules-config`; 4 (terminology resolvability) is handled by the schema/terminology tooling.
GRZ Tabelle-1 criteria (rare→libraryType, centre-id, noScopeJustification) are enforced; the GRZ
Detailprüfung QC thresholds (depth/read-length/quality) and raw-data checks run on FASTQ/BAM, not
JSON — out of scope here (see `grz.rules.json` `about`). See `docs/`/`about` blocks for the mapping
of each criterion to its actual JSON path.

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
