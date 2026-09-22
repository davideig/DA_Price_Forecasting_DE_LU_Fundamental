# Model Card: Price Forecast

## Target

EPEX DE-LU day-ahead price.

## Main Experiment Families

- RQ2: price model with baseline weather/calendar/price information versus
  generated load and renewable forecasts.
- RQ3: cutoff-grid price models with different operational information sets
  from 07:00 to 12:00 on day `D-1`.

## Commands

RQ2:

```bash
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/oos_pbase_c2_d70.yaml
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/oos_pgen_c2_d70.yaml
```

Operational final paper stack:

```bash
pixi run energy-arena-price-final-daily --dry-run
```

This submission path uses `configs/pricebase_sweep/oos_pgen_c2_d70.yaml` and
refreshes the generated load, solar, and wind input forecasts before submitting.

RQ3:

```text
configs/rq3_cutoff_grid/RUN_ORDER.md
```

Operational RQ3 cutoff submission examples:

```bash
pixi run energy-arena-price-cutoff-daily --cutoff 0700 --dry-run
pixi run energy-arena-price-cutoff-daily --cutoff 1200 --dry-run
```

All cutoff submissions use the DE-LU point price challenge ID from
`ENERGY_ARENA_PRICE_CHALLENGE_ID`; Energy-Arena assigns them to cutoff
leaderboards based on the submission timestamp.

The deployment tasks run the cutoff runner with `--submit-first-stage`, so each
cutoff also submits the generated load, solar, and onshore wind forecasts that
feed the price model.

## Output

The main forecast column is `y_pred`.
