# Data Directory

Raw weather downloads are not part of the clean release repo. When published,
the reusable operational archive is tracked under:

```text
data/archive/operational/
```

That archive stores compact, time-partitioned Parquet copies of the processed
CSV/cache files plus a checksum manifest. Confirm and verify the manifest, then
restore it into the normal runtime layout before running models:

```bash
test -f data/archive/operational/manifest.json
pixi run operational-archive verify
pixi run operational-archive restore
pixi run check-data-pack --profile operational
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

See `docs/data_catalog.md` for the required files per model.
