# Data Directory

Raw weather downloads are not part of the clean release repo. The reusable
operational archive is tracked separately under:

```text
data/archive/operational/
```

That archive stores compact Parquet copies of the processed CSV/cache files plus
a manifest. Restore it into the normal runtime layout before running models:

```bash
pixi run operational-archive restore
pixi run check-data-thesis
```

Expected local layout:

```text
data/
  archive/operational/
  shapefile/
  processed/
  cache/
  raw/
```

Use one of the following approaches:

1. Restore the Git-tracked Parquet archive with `pixi run operational-archive restore`.
2. Download a prepared thesis feature pack and unpack it into `data/`.
3. Rebuild the processed files with configs under `configs/preprocessing/`.
4. Use sample data under `data/sample/` if provided by a release package.

See `docs/data_catalog.md` for the required files per model.
