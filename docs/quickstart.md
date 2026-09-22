# Quickstart

This repository exports reusable load, solar, wind, and price forecasting models
for the DE-LU day-ahead market.

## Setup

```bash
pixi install --all
cp .env.example .env
```

Fill in the required API keys in `.env`, especially:

```dotenv
ENTSOE_API_KEY=...
OPEN_METEO_API_KEY=...
```

## Run Final First-Stage Models

```bash
pixi run forecast-load-final
pixi run forecast-solar-final
pixi run forecast-wind-final
```

The direct load model, which does not use the ENTSO-E day-ahead load forecast,
is available with:

```bash
pixi run forecast-load-direct
```

## Run Price Experiments

RQ2 price configs are in `configs/pricebase_sweep/`.

```bash
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/oos_pbase_c2_d70.yaml
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/oos_pgen_c2_d70.yaml
```

For the operational final paper stack submitted to Energy Arena, use:

```bash
pixi run energy-arena-price-final-daily --dry-run
```

This refreshes the generated load, solar, and wind forecast caches first, then
runs the final `P_gen` LightGBM price model. To reuse already-unpacked cache
files without refreshing first-stage forecasts:

```bash
pixi run energy-arena-price-final-daily --dry-run --skip-first-stage-refresh
```

RQ3 cutoff-grid configs and their order are documented in:

```text
configs/rq3_cutoff_grid/RUN_ORDER.md
```

The operational cutoff runner supports the six paper cutoff times and refreshes
the matching own load, solar, and wind first-stage forecasts:

```bash
pixi run energy-arena-price-cutoff-daily --cutoff 0700 --dry-run
pixi run energy-arena-price-cutoff-daily --cutoff 1200 --dry-run
```

These runs all submit to the DE-LU point price challenge ID in
`ENERGY_ARENA_PRICE_CHALLENGE_ID`. The Energy-Arena cutoff leaderboard is chosen
from the actual submission timestamp.

For production, the registered cutoff tasks use `--submit-first-stage` so load,
solar, onshore wind, and price are submitted for the same cutoff information set.

## Data Modes

Users can work in three modes:

1. Sample mode: use a tiny sample feature pack for smoke tests.
2. Feature-pack mode: download processed data produced by the thesis pipeline.
3. Full rebuild mode: refetch ENTSO-E/Open-Meteo/DWD/MaStR data and rerun preprocessing.

See `docs/data_catalog.md` for the required files.

## Recommended Reuse Path

For most users, the practical path is feature-pack mode:

```bash
tar -xzf DA_Price_Forecasting_DE_LU_Fundamental_data_v0.1.0.tar.gz
pixi run check-data-final
pixi run check-data-price-final
pixi run forecast-load-final
pixi run forecast-solar-final
pixi run forecast-wind-final
```

The data pack is not stored in Git. Download it from the matching GitHub
Release, Zenodo, OSF, or the distribution location named in the release notes.
See `docs/data_pack.md` for packaging and verification details.
