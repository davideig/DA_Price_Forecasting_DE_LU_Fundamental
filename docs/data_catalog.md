# Data Catalog

The release repository should not contain heavy raw or processed data. It should
document what is required and where the files must be placed.

## Required Processed Data

Load models:

- `data/processed/load_forecast/`
- `data/processed/open_meteo/`

Solar model:

- `data/processed/renewable_generation/`
- `data/processed/renewable_proxy/`
- `data/processed/icon_aggregated_mastr_solar_tso_c25_run06/` or the matching
  configured DWD aggregation folder

Wind model:

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

For reproducibility, publish a compressed feature pack outside Git, for example
on Zenodo, OSF, or a GitHub Release asset:

```text
data_processed_feature_pack_thesis_febjul.tar.zst
```

The feature pack should unpack into `data/processed/` and, if needed,
`data/cache/entsoe/`.
