# Released Models

The normal interface is the one-command next-day runner:

```bash
pixi run forecast-next-day --model load --cutoff 0700
pixi run forecast-next-day --model solar --cutoff 0900
pixi run forecast-next-day --model wind --cutoff 1100
pixi run forecast-next-day --model price --cutoff 1200
pixi run forecast-next-day --model all --cutoff final
```

All four targets support `0700`, `0800`, `0900`, `1000`, `1100`, `1200`, and
`final`. Selecting `price` automatically runs the matching load, solar, and
wind forecasts first.

## Operational Cutoffs

The fixed cutoff configs are under `configs/deployment/cutoffs/`. Cutoffs
07:00-09:00 use the 03 UTC weather run; cutoffs 10:00-12:00 use the 06 UTC run.
Load changes from a direct model to a residual model at 11:00. Price models add
reserve-market inputs as those results become observable.

Run a cutoff workflow directly without submitting:

```bash
pixi run energy-arena-price-cutoff-daily \
  --cutoff 0900 \
  --submit-first-stage \
  --dry-run
```

## Final Profile

The `final` profile uses these released configs:

- Load: `configs/final/load/load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml`
- Solar: `configs/final/renewable/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_paper_febjul.yaml`
- Wind: `configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml`
- Price: `configs/final/price/price_pgen_lightgbm_c2_d70.yaml`

The price model uses the generated load, solar, and wind forecasts produced by
the three `price_inputs/` configs before fitting its 70-day rolling window.

Individual lower-level commands remain available:

```bash
pixi run forecast-load-final
pixi run forecast-solar-final
pixi run forecast-wind-final
pixi run energy-arena-price-final-daily --dry-run
```
