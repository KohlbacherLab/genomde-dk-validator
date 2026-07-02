# Datenkranz JSON Schema provenance

These are the **authoritative BfArM MVGenomseq schemas**, vendored locally so
`scripts/validate_datenkranz.py` runs offline against pinned copies.

| dir | source repo | release tag | schema content version | verified |
|---|---|---|---|---|
| `kdk/` | https://github.com/BfArM-MVH/MVGenomseq_KDK (`KDK/`) | **v2.3** | **1.7.1** (2025-09-05) | 2026-07-02 — all 14 files byte-identical to upstream |
| `grz/` | https://github.com/BfArM-MVH/MVGenomseq_GRZ (`GRZ/`) | **v1.3.0** | **1.2.3** (2025-09-05) | 2026-07-02 — byte-identical to upstream |

Note the two-track versioning: the repos use release **tags** (`v2.x`, `v1.3.0`) while each schema's
own **CHANGELOG** uses semantic content versions (KDK 1.7.1, GRZ 1.2.3). The latest tag ships the
latest content version; both are pinned here.

The KDK root schemas `$ref` sibling files by absolute URL
(`https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_KDK/main/KDK/...`); the validator maps
those to these local files via a `referencing` Registry, so no network fetch happens at validation time.

## Refresh / re-verify against upstream
```bash
# KDK (14 files under KDK/)
for f in $(cd schemas/kdk && find . -name '*.json' | sed 's#^\./##'); do
  curl -sf "https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_KDK/v2.3/KDK/$f" -o "schemas/kdk/$f"
done
# GRZ
curl -sf "https://raw.githubusercontent.com/BfArM-MVH/MVGenomseq_GRZ/v1.3.0/GRZ/grz-schema.json" -o schemas/grz/grz-schema.json
git diff --stat schemas/   # empty => still current; else review the upstream change
```
Bump the tags above when BfArM publishes a new release, then re-run `validate_datenkranz.py`.
