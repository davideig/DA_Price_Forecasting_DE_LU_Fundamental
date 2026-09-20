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

RQ3 cutoff-grid configs and their order are documented in:

```text
configs/rq3_cutoff_grid/RUN_ORDER.md
```

## Data Modes

Users can work in three modes:

1. Sample mode: use a tiny sample feature pack for smoke tests.
2. Feature-pack mode: download processed data produced by the thesis pipeline.
3. Full rebuild mode: refetch ENTSO-E/Open-Meteo/DWD/MaStR data and rerun preprocessing.

See `docs/data_catalog.md` for the required files.
