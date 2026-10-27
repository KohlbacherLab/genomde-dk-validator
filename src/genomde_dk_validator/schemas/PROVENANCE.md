# Datenkranz JSON Schema provenance

These are the **authoritative BfArM MVGenomseq schemas**, vendored locally so
`scripts/validate_datenkranz.py` runs offline against pinned copies.

| dir | source repo | release tag | schema content version | verified |
|---|---|---|---|---|
| `kdk/` | https://github.com/BfArM-MVH/MVGenomseq_KDK (`KDK/`) | **v2.3** + untagged `main` commit [`fe724ff`](https://github.com/BfArM-MVH/MVGenomseq_KDK/commit/fe724ff09172a284cb1334c677db030643b99203) (2026-08-05) | **1.7.1** (2025-09-05; `fe724ff` adds no CHANGELOG entry) | 2026-10-27 — all 14 files byte-identical to `fe724ff` (= `main`) |
| `grz/` | https://github.com/BfArM-MVH/MVGenomseq_GRZ (`GRZ/`) | **v1.3.1** (`0c60bb6`, 2026-08-05) | schema `version` **1.3.1**; CHANGELOG still ends at 1.2.3 | 2026-10-27 — byte-identical to v1.3.1 |

**Consent `schemaVersion` enum.** KDK `fe724ff` and GRZ v1.3.1 both widen the enum of
`researchConsents[].schemaVersion` (the version of the embedded `de.medizininformatikinitiative.kerndatensatz.consent`
object) from `2025.0.1` to `2025.0.1`, `2025.0.2`, `2025.0.3`, `2025.0.4`, `2026.0.0`, `2026.0.1`. Nothing else
changed. KDK `develop` (unreleased, breaking: `Submission.confirmationId`, renamed OncologyPlan field, required
`OncologyCase.variantTypes`) is deliberately not vendored.

Note the two-track versioning: the repos use release **tags** (`v2.x`, `v1.3.x`) while each schema's
own **CHANGELOG** uses semantic content versions (KDK 1.7.1, GRZ 1.2.3). The latest tag ships the
latest content version; both are pinned here.

The KDK root schemas `$ref` sibling files by absolute URL
(`https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_KDK/main/KDK/...`); the validator maps
those to these local files via a `referencing` Registry, so no network fetch happens at validation time.

## Refresh / re-verify against upstream
```bash
# KDK (14 files under KDK/)
for f in $(cd schemas/kdk && find . -name '*.json' | sed 's#^\./##'); do
  curl -sf "https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_KDK/fe724ff09172a284cb1334c677db030643b99203/KDK/$f" -o "schemas/kdk/$f"
done
# GRZ
curl -sf "https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_GRZ/v1.3.1/GRZ/grz-schema.json" -o schemas/grz/grz-schema.json
git diff --stat schemas/   # empty => still current; else review the upstream change
```
Bump the tags above when BfArM publishes a new release, then re-run `validate_datenkranz.py`.
