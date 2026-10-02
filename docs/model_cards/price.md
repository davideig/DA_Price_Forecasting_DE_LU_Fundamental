# Model Card: Price Forecast

## Target

EPEX DE-LU day-ahead price at quarter-hour resolution.

## Released Profiles

The operational profiles cover 07:00 through 12:00 on day D-1 and use only
inputs observable by the selected cutoff. Their fixed configs are in
`configs/deployment/cutoffs/`.

The `final` profile is the released generated-input LightGBM model at
`configs/final/price/price_pgen_lightgbm_c2_d70.yaml`. It uses calendar,
lagged-price, clustered DWD ICON-D2 weather, and self-generated load, solar,
wind, and residual-load forecasts with a 70-day rolling training window.

## Commands

Generate a stable CSV for reuse:

```bash
pixi run forecast-next-day --model price --cutoff 1200
pixi run forecast-next-day --model price --cutoff final
```

Build cutoff submission payloads without contacting Energy Arena:

```bash
pixi run energy-arena-price-cutoff-daily --cutoff 0700 --dry-run
pixi run energy-arena-price-cutoff-daily --cutoff 1200 --dry-run
```

Selecting a price profile refreshes and runs its matching load, solar, and wind
dependencies first. The main forecast column is `y_pred`.
