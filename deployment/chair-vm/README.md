# Chair VM Migration

This directory contains the Windows/WSL deployment helper for the IIP chair VM.

The chair guide describes a Windows VM reached via Remote Desktop:

```text
iip-vcomp122.iip.kit.edu
```

Use `KIT\<your KIT acronym>` as the login user. The forecasting pipeline should run inside WSL/Linux, because the repository is currently locked for `linux-64` and `osx-arm64`, not native Windows.

## 1. Check WSL

On the chair VM, open PowerShell and run:

```powershell
wsl -l -v
```

If Ubuntu is listed, continue below. If WSL is missing, ask for a Linux VM or permission to install WSL. Avoid changing the repo to `win-64` unless you want to debug dependency resolution on Windows.

## 2. Clone And Install

Inside WSL:

```bash
cd ~
git clone https://github.com/davideig/DA_Price_Forecasting_DE_LU_Fundamental.git DA_Price_Forecasting_Pipeline_DE_LU_release
cd DA_Price_Forecasting_Pipeline_DE_LU_release
bash deployment/chair-vm/setup_wsl_repo.sh
```

Create `.env` on the VM. Do not commit it:

```bash
cp .env.example .env
nano .env
```

Required keys:

```text
ENTSOE_API_KEY
ENERGY_ARENA_API_KEY
ENERGY_ARENA_PRICE_CHALLENGE_ID
ENERGY_ARENA_LOAD_CHALLENGE_ID
ENERGY_ARENA_SOLAR_CHALLENGE_ID
ENERGY_ARENA_WIND_CHALLENGE_ID
```

`OPEN_METEO_API_KEY` is optional for the current public Open-Meteo configs that set `open_meteo_api_key_env: null`, but keep it if you still have a key.

## 3. Transfer Operational Data

Transfer these directories/files from local storage or from a backup of the old VM:

```text
data/clustering/
data/raw/renewable_capacity/
data/processed/open_meteo/
data/processed/renewable_proxy/
data/processed/renewable_generation/
data/processed/icon_aggregated_mastr_solar_tso_c25_run06/
data/processed/icon_aggregated_mastr_wind_c100_run06/
data/processed/icon_aggregated_c2_run06/
results/load_forecast_results/
results/renewable_generation_results/
results/price_forecast_results/
results/sqra_results/
```

Do not transfer `data/raw/dwd_icon_daily/` as an archive. The scheduled DWD jobs download the current run, aggregate it, and delete raw GRIB folders afterwards.

If you use Remote Desktop, enable local folder redirection and copy the files into WSL via `/mnt/c/...`. If the chair network drive is available, store large bundles there and unpack them from WSL.

## 4. Smoke Tests

Run these inside WSL after `.env` and data are in place:

```bash
./deployment/chair-vm/run_scheduled_job.sh dwd-wind-update
./deployment/chair-vm/run_scheduled_job.sh dwd-solar-update

pixi run energy-arena-load-open-meteo-daily --dry-run

pixi run energy-arena-renewable-daily \
  --feature-config configs/preprocessing/renewable_features/regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml \
  --extra-feature-config configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_icon_d2_single_run06_mastr_solar_tso_c25_cloud_cover.yaml \
  --model-config configs/final/renewable/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_paper_febjul.yaml \
  --skip-wind \
  --dry-run

pixi run energy-arena-renewable-daily \
  --model-config configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml \
  --skip-solar \
  --wind-value-column Wind_Onshore_Model_MW \
  --dry-run

pixi run energy-arena-price-final-daily --dry-run
```

The price dry run is the final paper `P_gen` stack. It refreshes the generated
load/solar/wind forecast caches first, then runs the LightGBM price model. If you
only want to test the final submission formatter against already-present cache
files, add:

```bash
pixi run energy-arena-price-final-daily --dry-run --skip-first-stage-refresh
```

If one first-stage refresh fails operationally, the price runner logs a
`[fallback]` line and tries the already cached first-stage CSVs. It does not
silently impute missing values; the final price run still fails if the cache does
not cover the target day.

RQ3 cutoff submissions are available through a separate runner. Energy-Arena
uses the same challenge ID for all cutoff leaderboards of a target; the
submission timestamp decides whether the forecast counts for the 07:00, 08:00,
09:00, 10:00, 11:00, or 12:00 cutoff. Each price cutoff run refreshes its own
load, solar, and wind first-stage forecasts before running the matching RQ3
price model:

```bash
pixi run energy-arena-price-cutoff-daily --cutoff 0700 --dry-run
pixi run energy-arena-price-cutoff-daily --cutoff 1200 --dry-run
```

The supported cutoffs are `0700`, `0800`, `0900`, `1000`, `1100`, and `1200`.
They all read `ENERGY_ARENA_PRICE_CHALLENGE_ID` from `.env`. Add
`--submit-first-stage` to also submit the generated load, solar, and onshore
wind forecasts to `ENERGY_ARENA_LOAD_CHALLENGE_ID`,
`ENERGY_ARENA_SOLAR_CHALLENGE_ID`, and `ENERGY_ARENA_WIND_CHALLENGE_ID`.

## 5. Register Daily Tasks

From Windows PowerShell in the checked-out repo directory mounted through WSL, run:

```powershell
.\deployment\chair-vm\register_tasks.ps1
```

The default WSL repo path is:

```text
/home/<WindowsUserName>/DA_Price_Forecasting_Pipeline_DE_LU_release
```

If your WSL username differs, pass it explicitly:

```powershell
.\deployment\chair-vm\register_tasks.ps1 -RepoLinuxPath "/home/<wsl-user>/DA_Price_Forecasting_Pipeline_DE_LU_release"
```

The tasks are:

```text
10:00 dwd-wind-update
10:35 renewable-wind-warmup
10:50 dwd-solar-update
11:10 renewable-solar-submit
11:20 renewable-wind-submit
11:30 price-submit
11:35 load-point-submit
```

To additionally register the RQ3 cutoff submissions, run this separate
PowerShell script after filling `ENERGY_ARENA_PRICE_CHALLENGE_ID` in `.env`:

```powershell
.\deployment\chair-vm\register_cutoff_tasks.ps1
```

The optional cutoff tasks submit load, solar, onshore wind, and price for the
same cutoff information set:

```text
06:40 price-cutoff-0700-submit
07:40 price-cutoff-0800-submit
08:40 price-cutoff-0900-submit
09:40 price-cutoff-1000-submit
10:40 price-cutoff-1100-submit
11:40 price-cutoff-1200-submit
```

## 6. Check Status

From PowerShell:

```powershell
.\deployment\chair-vm\check_status.ps1
```

Or directly inside WSL:

```bash
./deployment/chair-vm/run_scheduled_job.sh status
```

Logs are written under:

```text
logs/chair_vm_tasks/
```
