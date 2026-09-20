# Preprocessing Configs

These configs rebuild the feature files consumed by the final models.

- `load_weather/`: Open-Meteo load-weather backfills.
- `price_weather/`: optional Open-Meteo price-weather backfills.
- `renewable_features/`: MaStR/DWD/Open-Meteo renewable proxy feature builders.
- `weather_aggregation/`: LSDF/DWD ICON aggregation and daily update configs.
- `capacity/`: MaStR capacity and population-weight preprocessing.

The RQ3 cutoff-grid preprocessing remains self-contained in
`configs/rq3_cutoff_grid/`.
