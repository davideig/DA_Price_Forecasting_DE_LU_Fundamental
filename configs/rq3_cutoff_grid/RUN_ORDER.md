# RQ3 cutoff-grid run order

This folder implements the literal information-accrual table for cutoffs
07:00, 08:00, 09:00, 10:00, 11:00, and 12:00 on day D-1.

Assumptions encoded in the LSDF configs:

- 07:00, 08:00, and 09:00 use the DWD ICON-D2 `06 UTC` run from LSDF.
- 10:00, 11:00, and 12:00 use the DWD ICON-D2 `09 UTC` run from LSDF.
- This is a thesis evaluation convention based on the fully available LSDF
  archive. If the thesis uses local German clock time, state this availability
  assumption explicitly.
- Morning actual load/generation uses data up to 45 minutes before the cutoff:
  06:15, 07:15, 08:15, 09:15, 10:15, and 11:15.
- 07:00-10:00 use the direct load model, because the public ENTSO-E
  day-ahead load forecast is not yet available.
- 11:00 and 12:00 use the residual-correction load model, because the
  public ENTSO-E day-ahead load forecast is available.
- The 12:00 price model adds EXAA prices.

## 1. Preprocessing

For the main thesis cutoff-grid experiment, use the complete LSDF/DWD ICON-D2
archive rather than Open-Meteo single-run data. This keeps the full February-July
evaluation window intact and avoids the Open-Meteo archive gap before April 2026.

Raw ICON aggregation uses the `ops` environment because it needs the
GRIB/geospatial stack. All configs use `skip_existing_output: true`, so already
processed days are reused.

### 1.1 Aggregate LSDF/DWD weather

Run `06` for the morning baseline and `09` only if the later cutoff models are
configured to use the newer late-morning weather run.

```bash
pixi run -e ops da-price-forecast --config configs/rq3_cutoff_grid/preprocess_icon_aggregate_all_lsdf_paper_febjul.yaml
```

This single config writes all eight required aggregation outputs:

- load weather: C25, runs `06` and `09`
- price weather: C2, runs `06` and `09`
- solar weather: MaStR/TSO C25, runs `06` and `09`
- wind weather: MaStR C100, runs `06` and `09`

It streams each available GRIB variable once per day/run and fans it out to the
requested cluster layouts. Keep the separate preprocessing configs only as a
fallback if one output needs to be repaired independently.

### 1.2 Build renewable weather proxy features

These commands convert the aggregated solar/wind DWD weather into the renewable
feature files consumed by the first-stage solar and wind models.

```bash
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/preprocess_regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/preprocess_regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run09_solar_spread.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/preprocess_regional_renewable_features_dwd_icon_mastr_wind_c100_run06.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/preprocess_regional_renewable_features_dwd_icon_mastr_wind_c100_run09.yaml
```

## 2. First-stage cutoff forecasts

```bash
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/load_0700_direct_dwd_icon_c25_run06_morning0615_tw224_f180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/solar_0700_dwd_icon_mastr_tso_c25_run06_solar_spread_geometry_physics_morning0615_d90.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/wind_0700_dwd_icon_mastr_c100_run06_morning0615_d180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/load_0800_direct_dwd_icon_c25_run06_morning0715_tw224_f180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/solar_0800_dwd_icon_mastr_tso_c25_run06_solar_spread_geometry_physics_morning0715_d90.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/wind_0800_dwd_icon_mastr_c100_run06_morning0715_d180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/load_0900_direct_dwd_icon_c25_run06_morning0815_tw224_f180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/solar_0900_dwd_icon_mastr_tso_c25_run06_solar_spread_geometry_physics_morning0815_d90.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/wind_0900_dwd_icon_mastr_c100_run06_morning0815_d180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/load_1000_direct_dwd_icon_c25_run09_morning0915_tw224_f180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/solar_1000_dwd_icon_mastr_tso_c25_run09_solar_spread_geometry_physics_morning0915_d90.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/wind_1000_dwd_icon_mastr_c100_run09_morning0915_d180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/load_1100_residual_dwd_icon_c25_run09_morning1015_tw224_f180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/solar_1100_dwd_icon_mastr_tso_c25_run09_solar_spread_geometry_physics_morning1015_d90.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/wind_1100_dwd_icon_mastr_c100_run09_morning1015_d180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/load_1200_residual_dwd_icon_c25_run09_morning1115_tw224_f180.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/solar_1200_dwd_icon_mastr_tso_c25_run09_solar_spread_geometry_physics_morning1115_d90.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/wind_1200_dwd_icon_mastr_c100_run09_morning1115_d180.yaml
```

## 3. Price cutoff forecasts

```bash
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_0700_noexaa_direct_load_renewables_weather_c2_run06_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_0800_noexaa_direct_load_renewables_weather_c2_run06_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_0900_noexaa_direct_load_renewables_weather_c2_run06_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_1000_noexaa_direct_load_renewables_weather_c2_run09_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_1100_noexaa_residual_load_renewables_weather_c2_run09_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_1200_exaa_residual_load_renewables_weather_c2_run09_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_1200_exaa_only_c2_d70_lsdf.yaml
```

## 4. Final SQRA and evaluation

```bash
pixi run -e sqra da-price-forecast --config configs/rq3_cutoff_grid/sqra_price_cutoff_grid_c2_d70_paper_febjul_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/evaluation_price_cutoff_grid_c2_d70_paper_febjul_lsdf.yaml
```

## 5. Optional reserve-market capacity experiment

This add-on tests whether German balancing capacity-market results from
regelleistung.net improve the price cutoff ladder. It uses only capacity-market
results, not intraday energy-market activations. With the publication convention
encoded here, 07:00 and 08:00 stay unchanged, 09:00 adds FCR, 10:00 adds
FCR+aFRR, and 11:00/12:00 add FCR+aFRR+mFRR.

First build the cached reserve-market feature archive:

```bash
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/preprocess_reserve_market_regelleistung_capacity_paper_febjul.yaml
```

Then run the reserve-augmented price models:

```bash
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_0900_noexaa_direct_load_renewables_weather_reserve_fcr_c2_run06_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_1000_noexaa_direct_load_renewables_weather_reserve_fcr_afrr_c2_run09_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_1100_noexaa_residual_load_renewables_weather_reserve_all_c2_run09_d70_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/price_1200_exaa_residual_load_renewables_weather_reserve_all_c2_run09_d70_lsdf.yaml
```

Finally run the reserve SQRA/evaluation pair:

```bash
pixi run -e sqra da-price-forecast --config configs/rq3_cutoff_grid/sqra_price_cutoff_grid_c2_d70_reserve_paper_febjul_lsdf.yaml
pixi run -e forecast da-price-forecast --config configs/rq3_cutoff_grid/evaluation_price_cutoff_grid_c2_d70_reserve_paper_febjul_lsdf.yaml
```
