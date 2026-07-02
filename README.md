# genomde-dk-validator

Validate **genomDE Datenkranz** JSON (BfArM Modellvorhaben Genomsequenzierung, §64e SGB V) against
the authoritative **BfArM JSON Schemas** (KDK Oncology/Rare-Diseases + GRZ) — self-contained
(schemas vendored, validates fully offline), with **unknown-field detection** and opt-in **BfArM
Qualitätssicherung semantic rules**.

## Install
```bash
pip install git+https://github.com/KohlbacherLab/genomde-dk-validator.git   # or: pip install .
```
**Python ≥ 3.8** (uses `jsonschema` ≥ 4.18). The Anaconda **base** env is often Python 3.7 (EOL) —
there the install is refused with a clear message; use a ≥3.8 interpreter, e.g.
`python3.11 -m pip install …` or `conda create -n dkv python=3.11` first.

Every finding reports its location in the input file as `file:line:col`.

## CLI
```bash
genomde-dk-validator FILE|DIR|GLOB ...     # schema + unknown-field check (recursive)
  --strict            # unknown fields => errors (else warnings)
  --no-unknown        # schema only
  --kdk-rules         # + BfArM KDK QS rules   (oncology / rare-disease)
  --grz-rules         # + BfArM GRZ QS rules
  --rules-config F    # JSON of external inputs for rules (see below)
  --json | -q         # machine-readable report | summary only
```
Exit `0` all pass · `1` a file failed (schema error, rule error, or `--strict` unknowns) · `2` no input.
Branch is auto-detected → root schema:

| detected by | branch | schema |
|---|---|---|
| `case.diagnosisOd` | oncology | KDK `Oncology.json` |
| `case.diagnosisRd` | rare-disease | KDK `RareDiseases.json` |
| `donors`+`submission` | grz | GRZ `grz-schema.json` |

**Unknown fields:** the BfArM schemas never set `additionalProperties:false`, so undeclared fields
pass a plain JSON-Schema check — this tool reports them (e.g. `priorDiagnostic` vs schema
`priorDiagnostics`).

## Python API
```python
from genomde_dk_validator import DatenkranzValidator
r = DatenkranzValidator().validate_file("dk.json", rules="kdk")   # rules optional
r.branch; r.schema_errors; r.unknown_fields; r.rule_findings; r.ok(strict=False)
```

## Semantic rules (BfArM Qualitätssicherung)
QS criteria (QS-KDK v01.2; QS-GRZ v01.4) are enforced as **data-defined rules** — off by default,
enabled with `--kdk-rules`/`--grz-rules`. A sanity check rejects the wrong rule set for the detected
branch. Some criteria need external inputs via `--rules-config`; without them those rules *skip* (info):
```json
{ "clinical_data_node_id": "KDKTUE005", "genomic_data_center_id": "GRZTUE002", "le_ids": ["260840108"] }
```
KDK criteria 1,3,5,6,7,8,9,10,12 enforced (2,11 need config; 4 = terminology, out of scope); GRZ
Tabelle-1 (rare→libraryType, centre-id, noScopeJustification). GRZ Detailprüfung QC (depth/quality)
runs on FASTQ/BAM, not JSON.

### Adding / editing rules
Rules live in [`src/genomde_dk_validator/rules/`](src/genomde_dk_validator/rules/)
(`kdk.rules.json`, `grz.rules.json`). Each is an instance of a *primitive* implemented in
[`rules.py`](src/genomde_dk_validator/rules.py); the engine reads only `id`/`primitive`/`severity`/
`params` (`source`/`doc` are documentation — always cite the BfArM criterion in `source`):
```json
{ "id": "kdk-1-age", "primitive": "age_years_range", "severity": "error",
  "source": "QS durch KDK v01.2, Tabelle 1, Kriterium 1",
  "params": { "from": "metaData.birthDate", "to": "metaData.submission.date", "min": 0, "max": 130 } }
```
Available primitives: `age_years_range`, `enum_allowed`, `enum_by_condition`, `array_contains`,
`date_order`, `dates_after`, `all_dates_not_before`, `all_dates_before_by_condition`, `tnm_one_each`,
`id_equals_config`, `id_in_list`. Paths use dotted keys with `[]` array wildcards
(`metaData.mvConsent.scope[].date`). To add a **new** primitive, write a
`@primitive("name")` generator in `rules.py` yielding `RuleFinding`s. Rule files are validated on load;
a bad `primitive` name surfaces as a warning finding.

## Schema provenance
Vendored under `src/genomde_dk_validator/schemas/`, byte-identical to upstream
([`schemas/PROVENANCE.md`](src/genomde_dk_validator/schemas/PROVENANCE.md)):
KDK [MVGenomseq_KDK](https://github.com/BfArM-MVH/MVGenomseq_KDK) v2.3 (content 1.7.1);
GRZ [MVGenomseq_GRZ](https://github.com/BfArM-MVH/MVGenomseq_GRZ) v1.3.0 (content 1.2.3).
To update: replace the files from the upstream tag and bump `PROVENANCE.md`.

## Development
```bash
pip install -e ".[dev]" && pytest
```
MIT — see [LICENSE](LICENSE).
