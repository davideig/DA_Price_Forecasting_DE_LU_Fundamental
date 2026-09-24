# Data Archive And Pack Guide

The Git repository intentionally avoids raw weather/API downloads. For reusable
model inputs, it supports two layers:

1. a Git-tracked operational archive under `data/archive/operational/`;
2. optional immutable data packs for GitHub Releases, Zenodo, or OSF.

The operational archive is the intended default for the chair VM and for users
who want to clone the repo and run the final models directly. A revision is
self-contained only when `data/archive/operational/manifest.json` is actually
tracked. Until that first archive is published, users need the separately
distributed data pack. The archive stores processed CSV caches as compressed
Parquet and restores them into the normal runtime layout.

## Git-Tracked Operational Archive

Restore the archive after cloning:

```bash
test -f data/archive/operational/manifest.json
pixi run operational-archive restore
pixi run check-data-pack --profile operational
```

Export a new archive from a machine that has up-to-date live caches:

```bash
pixi run operational-archive export --dry-run
pixi run operational-archive export
git add data/archive/operational
git commit -m "Update operational data archive YYYY-MM-DD"
git push
```

The export includes these live paths by default:

```text
data/clustering/
data/shapefile/
data/raw/renewable_capacity/
data/cache/entsoe/
data/processed/
results/load_forecast_results/
results/renewable_generation_results/
results/price_forecast_results/
```

Raw DWD GRIB folders, Energy Arena submission artifacts, logs, `.env`, and
machine-specific files are deliberately excluded. The exporter refuses files
larger than 95 MiB by default because normal Git/GitHub cannot handle very large
single files gracefully.

On the chair VM, `deployment/chair-vm/register_tasks.ps1` registers a
post-deadline task named `DAForecast-commit-operational-archive`. It runs after
the forecast submissions, exports the bounded `operational` profile, commits
changed archive files, and pushes them. The profile contains the inputs used by
the deployed final and RQ3 cutoff configs; it does not sweep every research file
under `data/processed/`.

## What The Data Pack Contains

The optional tar.gz data pack contains the same kind of processed inputs. The
default pack includes:

```text
data/processed/
data/clustering/
data/shapefile/
data/raw/renewable_capacity/
data/cache/entsoe/
```

These folders contain the processed model inputs: ENTSO-E target series,
Open-Meteo archives, DWD/ICON aggregations, MaStR-derived renewable proxy
features, population weights, reserve-market features, clustering maps, and the
small Natural Earth country shapefile needed for DWD Germany masking.

If you also want users to run price experiments immediately without regenerating
first-stage forecasts, include model outputs too:

```text
results/load_forecast_results/
results/renewable_generation_results/
results/price_forecast_results/
results/sqra_results/
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

Do not commit the tar.gz pack to Git. Attach it to one of:

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
pixi run energy-arena-price-final-daily --dry-run --skip-first-stage-refresh
```

For price experiments that rely on generated first-stage forecasts, either:

1. unpack a pack created with `--include-results`, or
2. run the load, solar, and wind configs first so their `results/` files exist.

Operationally, `energy-arena-price-final-daily` refreshes those first-stage
caches before submitting. If a refresh fails, it logs a `[fallback]` message and
tries the already cached CSVs. This is deliberately auditable cache reuse, not
silent imputation.

RQ3 cutoff dry runs use the same data pack, the same
`ENERGY_ARENA_PRICE_CHALLENGE_ID`, and the cutoff-grid configs. Energy-Arena
assigns the submitted forecast to cutoff leaderboards from the submission time.
Pass `--submit-first-stage` to submit the generated load, solar, and onshore
wind forecasts for the same cutoff as well.

```bash
pixi run energy-arena-price-cutoff-daily --cutoff 0700 --dry-run --skip-first-stage-refresh
pixi run energy-arena-price-cutoff-daily --cutoff 1200 --dry-run --skip-first-stage-refresh
```

## Verify Data Availability

Check the final first-stage configs:

```bash
pixi run check-data-final
```

Check all fixed thesis configs:

```bash
pixi run check-data-pack --profile thesis
```

Check the final paper price stack inputs:

```bash
pixi run check-data-price-final
```

Check a single config:

```bash
pixi run check-data-pack configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml
```

The checker reports missing local input files before a model run starts. It does
not download anything.
