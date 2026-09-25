# Data Catalog

The release repository should not contain heavy raw weather downloads. It can
track the compact operational archive under `data/archive/operational/`: CSV
caches are stored there as compressed, monthly Parquet partitions and restored
into the runtime paths before a model run. Intermediate DWD aggregations retain
the latest 14 issue days, while their derived model-feature histories remain
complete.

```bash
pixi run operational-archive verify
pixi run operational-archive restore
pixi run check-data-thesis
```

## Required Processed Data

Load models:

- `data/processed/load_forecast/`
- `data/processed/open_meteo/`

Solar model:

- `data/shapefile/ne_10m_admin_0_countries.*`
- `data/processed/renewable_generation/`
- `data/processed/renewable_proxy/`
- `data/processed/icon_aggregated_mastr_solar_tso_c25_run06/` or the matching
  configured DWD aggregation folder

Wind model:

- `data/shapefile/ne_10m_admin_0_countries.*`
- `data/processed/renewable_generation/`
- `data/processed/renewable_proxy/`
- `data/processed/icon_aggregated_mastr_wind_c100_run06/` or the matching
  configured DWD aggregation folder

Price models:

- `data/cache/entsoe/` or live ENTSO-E API access
- `data/processed/icon_aggregated_c2_run06/`
- first-stage forecast outputs under `results/load_forecast_results/` and
  `results/renewable_generation_results/`

RQ3:

- all files produced by the run order in `configs/rq3_cutoff_grid/RUN_ORDER.md`

## Recommended Distribution

The preferred day-to-day workflow is the Git-tracked operational archive:

```text
data/archive/operational/manifest.json
data/archive/operational/files/**/*.parquet
data/archive/operational/bundles/**/*.parquet
```

The VM updates the live CSV caches during the morning runs, exports this archive
after the submission window, and pushes the changed Parquet files to Git. Users
clone the repo, restore the archive, and run the same configs as the VM.

For immutable paper releases, also publish a compressed feature pack outside
Git, for example on Zenodo, OSF, or a GitHub Release asset:

```text
data_processed_feature_pack_thesis_febjul.tar.zst
```

The feature pack should unpack into `data/processed/` and, if needed,
`data/cache/entsoe/`.

This repository includes helper commands for both workflows:

```bash
pixi run operational-archive restore
pixi run operational-archive export --dry-run
pixi run operational-archive verify
pixi run create-feature-pack --dry-run
pixi run create-feature-pack
pixi run create-feature-pack --include-results
pixi run check-data-final
pixi run check-data-pack --profile thesis
```

Use `--include-results` when the pack should also contain first-stage forecasts
and price/evaluation outputs. That is useful for reproducing thesis tables
without rerunning load, solar, and wind models first.

See `docs/data_pack.md` for the full workflow.
