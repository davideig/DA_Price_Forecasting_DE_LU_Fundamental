# Data Pack Guide

The Git repository intentionally tracks code, configs, and documentation, not
large historical weather/API caches. To make the thesis models reusable, publish
a versioned data pack next to the Git release.

## What The Data Pack Contains

The default pack includes:

```text
data/processed/
data/clustering/
data/cache/entsoe/
```

These folders contain the processed model inputs: ENTSO-E target series,
Open-Meteo archives, DWD/ICON aggregations, MaStR-derived renewable proxy
features, population weights, reserve-market features, and clustering maps.

If you also want users to run price experiments immediately without regenerating
first-stage forecasts, include model outputs too:

```text
results/load_forecast_results/
results/renewable_generation_results/
results/price_forecast_results/
results/evaluation/
```

## Create A Data Pack

From a machine that already has the processed caches:

```bash
pixi run create-feature-pack --dry-run
pixi run create-feature-pack
```

The archive is written to:

```text
output/data_packs/da_price_forecasting_de_lu_data_<YYYYMMDD>.tar.gz
```

To include first-stage and price result outputs:

```bash
pixi run create-feature-pack --include-results
```

The archive contains a `DATA_PACK_MANIFEST.json` with file counts, sizes, and
the paths included in the pack.

## Publish The Pack

Do not commit the archive to Git. Attach it to one of:

- a GitHub Release, for example `v0.1.0`;
- Zenodo;
- OSF;
- an institutional object store.

Use a versioned name, for example:

```text
DA_Price_Forecasting_DE_LU_Fundamental_data_v0.1.0.tar.gz
```

The release notes should state the coverage window, for example:

```text
Processed feature cache covering 2025-01-01 through 2026-07-31.
```

## Use A Data Pack

Clone the repository, install dependencies, then unpack the archive in the repo
root:

```bash
tar -xzf DA_Price_Forecasting_DE_LU_Fundamental_data_v0.1.0.tar.gz
pixi run check-data-final
pixi run forecast-load-final
pixi run forecast-solar-final
pixi run forecast-wind-final
```

For price experiments that rely on generated first-stage forecasts, either:

1. unpack a pack created with `--include-results`, or
2. run the load, solar, and wind configs first so their `results/` files exist.

## Verify Data Availability

Check the final first-stage configs:

```bash
pixi run check-data-final
```

Check all fixed thesis configs:

```bash
pixi run check-data-pack --profile thesis
```

Check a single config:

```bash
pixi run check-data-pack configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml
```

The checker reports missing local input files before a model run starts. It does
not download anything.
