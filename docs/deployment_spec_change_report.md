# Operational cutoff deployment change report

This report describes the `deployment-spec` implementation of
`docs/operational_cutoff_data_spec.md`. Merging this branch to `main` deploys it
to the chair VM at the next 14:00 pull; do not merge until the migration and
rollout steps have been reviewed.

## Live submission configs

Each cutoff submits its own load, solar, onshore-wind, and price forecasts.
The price model consumes the immutable component histories written by that
same cutoff job.

| Cutoff | Weather run | Load | Solar | Wind | Price |
| --- | --- | --- | --- | --- | --- |
| 07:00 | 00 UTC | `configs/deployment/cutoffs/load_0700_run00.yaml` | `configs/deployment/cutoffs/solar_0700_run00.yaml` | `configs/deployment/cutoffs/wind_0700_run00.yaml` | `configs/deployment/cutoffs/price_0700_run00.yaml` |
| 08:00 | 03 UTC | `configs/deployment/cutoffs/load_0800_run03.yaml` | `configs/deployment/cutoffs/solar_0800_run03.yaml` | `configs/deployment/cutoffs/wind_0800_run03.yaml` | `configs/deployment/cutoffs/price_0800_run03.yaml` |
| 09:00 | 03 UTC | `configs/deployment/cutoffs/load_0900_run03.yaml` | `configs/deployment/cutoffs/solar_0900_run03.yaml` | `configs/deployment/cutoffs/wind_0900_run03.yaml` | `configs/deployment/cutoffs/price_0900_run03.yaml` |
| 10:00 | 06 UTC | `configs/deployment/cutoffs/load_1000_run06.yaml` | `configs/deployment/cutoffs/solar_1000_run06.yaml` | `configs/deployment/cutoffs/wind_1000_run06.yaml` | `configs/deployment/cutoffs/price_1000_run06.yaml` |
| 11:00 | 06 UTC | `configs/deployment/cutoffs/load_1100_run06.yaml` | `configs/deployment/cutoffs/solar_1100_run06.yaml` | `configs/deployment/cutoffs/wind_1100_run06.yaml` | `configs/deployment/cutoffs/price_1100_run06.yaml` |
| 12:00 | 06 UTC | `configs/deployment/cutoffs/load_1200_run06.yaml` | `configs/deployment/cutoffs/solar_1200_run06.yaml` | `configs/deployment/cutoffs/wind_1200_run06.yaml` | `configs/deployment/cutoffs/price_1200_run06.yaml` |

All load configs require weather-backed training rows and refresh the trailing
14 days of ENTSO-E realized load. All solar and wind configs refresh the
trailing 14 days of realized generation. Wind has one Open-Meteo input,
ICON-D2, rather than the former seven-provider set. Open-Meteo previous-run
fallback is enabled throughout the deployment configs with a strict three-hour
lookback. Required variables are checked for finite values before a run is
accepted. Wind checks the six speed/direction fields at 80, 120, and 180 m;
`boundary_layer_height` remains requested for feature compatibility but is not
part of the validity check. DWD uses the same previous-run policy. Both sources
store the requested and actual run in provenance metadata, and those files are
included in the operational archive.

The six wind configs use `min_train_days: 20`, matching the corrected thesis
warm-up variant. Delivery day 2026-02-07 is excluded where wind enters the
forecast because no corresponding archived weather run remains available.

Reserve publication was measured on 2026-09-28 at 08:14 for FCR, 09:16 for
aFRR, and 10:23 for mFRR. The live price configs therefore use no reserve data
at 07:00/08:00, FCR at 09:00, FCR plus aFRR at 10:00, and all three products at
11:00/12:00. Each applicable cutoff refreshes and appends the published result
for its delivery day before running the component and price models.

The realized-data limits are 05:30, 06:30, 07:30, 08:30, 09:30, and 10:30 for
the six load models. Solar and wind use the same sequence except that their
12:00 final-paper configuration remains at 10:00 as required by the spec.

## Weather preprocessing configs

The 00, 03, and 06 UTC histories have separate aggregation and feature output
paths under `configs/deployment/cutoff_preprocessing/`. For each run this
directory contains:

- `dwd_icon_c2_runXX.yaml`
- `dwd_solar_runXX.yaml`
- `dwd_wind_runXX.yaml`
- `load_open_meteo_history_runXX.yaml`
- `solar_dwd_features_runXX.yaml`
- `solar_open_meteo_features_runXX.yaml`
- `wind_dwd_features_runXX.yaml`
- `wind_open_meteo_features_runXX.yaml`

The cluster assignments, population weights, MaStR capacity inputs, and
state-to-TSO mappings remain fixed snapshots. They are not scheduled for
automatic updates.

## Schedule changes

The cutoff scheduler owns every live submission:

| Local time | Job | Change |
| --- | --- | --- |
| 04:05 | `dwd-run00-update` | unchanged time; now uses strict deployment configs |
| 05:15 | `renewable-run00-features-update` | unchanged time; cross-run bootstrap removed |
| 06:25 | `dwd-run03-update` | added |
| 06:40 | `price-cutoff-0700-submit` | unchanged |
| 06:50 | `renewable-run03-features-update` | added |
| 07:40 | `price-cutoff-0800-submit` | now uses run03 |
| 07:55 | `reserve-publication-poll` | unchanged; observational only |
| 08:40 | `price-cutoff-0900-submit` | now uses run03 |
| 09:23 | `dwd-run06-cutoff-update` | unchanged time; downloads all three run06 aggregations |
| 09:38 | `renewable-cutoff-features-update` | moved from 09:40 |
| 09:40 | `price-cutoff-1000-submit` | moved from 09:45 |
| 10:40 | `price-cutoff-1100-submit` | unchanged |
| 11:40 | `price-cutoff-1200-submit` | replaces compute-only task and now submits |

The general scheduler unregisters the obsolete duplicate weather, warm-up,
final-paper submission, and deadline-safety tasks. It retains only:

- 12:25 `repair-operational-data`
- 14:00 `commit-operational-archive`
- 14:30 `backup-operational-artifacts`

## Component forecast histories

Each cutoff job writes load, solar, and wind forecasts before price runs to:

```text
data/processed/component_forecast_history/<cutoff>/<component>.csv
```

Rows for a delivery day are immutable after first write. A later rerun is
stored under `reruns/`. Historical warm-up rows are marked `backfilled`; cached
or imputed target-day forecasts are marked `fallback_used`. Weather-run and
renewable-feature fallback provenance is propagated into that flag, including
load weather. The complete directory is included in the operational archive.

## One-time rollout

Run this sequence outside the submission window after merging but before
enabling the new tasks:

```bash
python deployment/chair-vm/migrate_cutoff_weather_histories.py
python deployment/chair-vm/migrate_cutoff_weather_histories.py --apply
./deployment/chair-vm/run_scheduled_job.sh backfill-fixed-run-open-meteo
./deployment/chair-vm/run_scheduled_job.sh backfill-operational-reserve-market
./deployment/chair-vm/run_scheduled_job.sh cutoff-prewarm-all
```

The migration quarantines legacy run06-to-run00 copies; it does not delete
them. Run the reserve backfill after 10:23, when all products for the next
delivery day are available. Then register both PowerShell task files and verify
the next-run times. The 07:55 publication poll remains enabled to monitor
whether the measured timings drift.
