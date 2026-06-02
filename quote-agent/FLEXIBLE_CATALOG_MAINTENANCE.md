# Flexible Pricing Catalog Maintenance

## Data Source

- **Primary**: `data/flexible-pricing-catalog.json` — the single pricing file read by both `pricebook.py` and `flexible_pricing.py` at runtime.
- **Upstream**: `/root/SMBReference/Huawei Cloud Price.xlsx` — Huawei's official LATAM price list (manual update).

## Import Tool

Location: `scripts/flexible_catalog_import.py`

### Commands

| Command | Purpose |
|---------|---------|
| `preview <xlsx>` | Read Excel → normalize → print rows. No files written. |
| `patch <xlsx> -o patch.json` | Read Excel → normalize → validate → write patch JSON. |
| `patch <xlsx> --dry-run --catalog <path>` | Compare patch against existing catalog; print new/updated/unchanged counts. |
| `validate <catalog.json>` | Check catalog consistency (schema, critical SKUs, conflicts). |

### Workflow

```
1. preview  →  review normalized rows
2. patch --dry-run  →  review impact (new/updated/conflicts)
3. patch -o patch.json  →  generate patch file
4. validate  →  confirm catalog is healthy
5. Manually merge approved patch items into flexible-pricing-catalog.json
6. Re-run validate + pytest
```

**Never auto-apply patches.** Always review before merging.

## Multi-Region Rule

Excel uses `&` to indicate "same price applies to multiple regions":

| Excel Value | Expanded Regions |
|---|---|
| `Santiago&Mexico` | chile, mexico |
| `Santiago&Mexico&Sao Paulo` | chile, mexico, brazil |
| `Santiago & Mexico` | chile, mexico (spaces OK) |

Each expanded region produces a separate catalog entry with the same price.

## When to Hand-Patch

- Adding a product not yet in `PRODUCT_MAPPING` or `SPEC_MAPPING`
- Fixing a one-off price error discovered in production
- Adding a region not in `SUPPORTED_REGIONS`

After hand-patching, always run `validate` and the test suite.

## Required Tests After Any Catalog Change

```bash
cd quote-agent
python3 scripts/flexible_catalog_import.py validate data/flexible-pricing-catalog.json
pytest -q tests/test_flexible_catalog_import.py
pytest -q tests/test_workflow.py -k "row_quote"
```

All three must pass before committing.
