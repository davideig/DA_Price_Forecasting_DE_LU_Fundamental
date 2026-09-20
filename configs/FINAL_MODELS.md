# Final Thesis Configs

This file is the short index for the fixed thesis models. Historical sweeps and
failed experiments are kept under `configs/archive/`; do not use them unless you
are deliberately revisiting old experiments.

## First-stage Forecasts

### Load

Residual load model used for the main RQ1 comparison and as generated load input
after the ENTSO-E day-ahead load forecast is available:

```bash
pixi run -e forecast da-price-forecast --config configs/final/load/load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml
```

Direct load model without the ENTSO-E load forecast, used for early cutoff
experiments:

```bash
pixi run -e forecast da-price-forecast --config configs/final/load/load_forecast_direct_actual_open_meteo_p10_morning0915_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml
```

### Renewable Generation

Solar:

```bash
pixi run -e forecast da-price-forecast --config configs/final/renewable/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_paper_febjul.yaml
```

Wind:

```bash
pixi run -e forecast da-price-forecast --config configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml
```

## RQ1 Benchmarks and Evaluation

```bash
pixi run -e forecast da-price-forecast --config configs/final/benchmarks/entsoe_load_forecast_benchmark_paper_febjul.yaml
pixi run -e forecast da-price-forecast --config configs/final/benchmarks/entsoe_renewable_forecast_benchmark_paper_febjul.yaml
pixi run -e forecast da-price-forecast --config configs/final/benchmarks/evaluation_load_direct_vs_entsoe_residual_paper_febjul.yaml
```

## RQ2 Price Models

Controlled base/generated/weather-free price configs live in
`configs/pricebase_sweep/`.

```bash
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/oos_pbase_c2_d70.yaml
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/oos_pgen_c2_d70.yaml
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/oos_pgen_nowea_c2_d70.yaml
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/evaluation_oos_rq2_controlled_c2_d70_paper_febjul.yaml
pixi run -e forecast da-price-forecast --config configs/pricebase_sweep/evaluation_oos_rq2_weather_replacement_c2_d70_paper_febjul.yaml
```

## RQ3 Cutoff Grid

The complete cutoff-grid workflow is documented in:

```text
configs/rq3_cutoff_grid/RUN_ORDER.md
```

The main selected cutoff-grid evaluation configs are:

```bash
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/evaluation_price_cutoff_grid_c2_d70_selected_points_paper_febjul_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/evaluation_price_cutoff_grid_c2_d70_reserve_vs_noreserve_points_paper_febjul_lsdf.yaml
```

## Diagnostics

Price-model grouped feature importance:

```bash
pixi run -e forecast python -m da_price_forecasting.scripts.price_feature_importance \
  --config configs/pricebase_sweep/oos_pbase_c2_d70.yaml --label rq2_base \
  --config configs/pricebase_sweep/oos_pgen_c2_d70.yaml --label rq2_generated \
  --config configs/pricebase_sweep/oos_pgen_nowea_c2_d70.yaml --label rq2_generated_no_weather \
  --output-dir output/diagnostics/price_feature_importance/paper_core_fast \
  --max-days 4 --mtu-step 12
```

