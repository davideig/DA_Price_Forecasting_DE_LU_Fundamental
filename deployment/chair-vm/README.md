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

Install Git LFS before cloning so the operational Parquet archive is checked out
as data rather than pointer files. Inside WSL:

```bash
sudo apt-get update
sudo apt-get install -y git-lfs
git lfs install
cd ~
git clone https://github.com/davideig/DA_Price_Forecasting_DE_LU_Fundamental.git DA_Price_Forecasting_Pipeline_DE_LU_release
cd DA_Price_Forecasting_Pipeline_DE_LU_release
git lfs pull
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

Optionally set `SYNERGIE_BACKUP_DIR` to a WSL-visible Synergie drive folder.
The scheduled backup job copies the compact operational archive and task logs
there after the Git archive commit:

```text
SYNERGIE_BACKUP_DIR=/mnt/synergie-diplomanden/MK_Eiglsperger/DA_Price_Forecasting/backups
```

## 3. Restore Operational Data

The preferred workflow is to restore the Git-tracked Parquet archive:

```bash
git lfs pull
pixi run operational-archive verify
pixi run operational-archive restore
pixi run check-data-thesis
```

The archive lives under `data/archive/operational/` in Git. It contains compact,
time-partitioned Parquet copies of the processed data and selected forecast
caches; the restore command materializes the CSV/parquet files expected by the
model configs. Complete derived feature histories are retained. Bulky
intermediate DWD aggregations use a rolling 14-issue-day continuation window.

If the archive is not available yet, bootstrap from a local bundle or an old VM
backup with these directories/files:

```text
data/clustering/
data/shapefile/
data/raw/renewable_capacity/
data/cache/entsoe/
data/processed/
results/load_forecast_results/
results/renewable_generation_results/
results/price_forecast_results/
```

Do not transfer `data/raw/dwd_icon_daily/` as an archive. The scheduled DWD jobs
download the current run, aggregate it, and delete raw GRIB folders afterwards.
The setup and DWD jobs also ensure the small Natural Earth country shapefile is
present under `data/shapefile/`; it is used to build the Germany grid mask.

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
10:00 dwd-wind-update (wind plus c2 price weather; keeps raw files for solar)
10:35 renewable-wind-warmup
10:50 dwd-solar-update
11:10 renewable-solar-submit
11:20 renewable-wind-submit
11:30 price-submit
11:35 load-point-submit
11:54 price-deadline-safety-submit
12:25 repair-operational-data
14:00 commit-operational-archive
14:30 backup-operational-artifacts
```

`price-deadline-safety-submit` is independent of the main price computation. It
does nothing when a response already exists. Otherwise it submits a completed
current-day price forecast if available, or remaps the latest complete cached
price day as an explicitly logged last-mile fallback before the 12:00 deadline.

The registered `wsl.exe` action remains attached until its Linux job finishes.
Consequently, Task Scheduler's `Running` state and `LastTaskResult` describe the
forecasting job itself; closing an unrelated terminal or RDP window does not stop it.

`repair-operational-data` runs after the Energy-Arena deadline. It retries any
missing current run00/run06 DWD inputs, forcibly revisits the target renewable
feature day so a morning fallback can be replaced, and writes a dated report to
`data/processed/operational_quality/`. A failed source remains visible in that
report and in the task result; it does not block the next day's retry.

`commit-operational-archive` waits for the repair job if necessary. It then
exports the updated live caches and quality report to
`data/archive/operational/`, verifies every artifact against the manifest,
commits changed archive files, and pushes them to Git so the repository data
archive stays current. Unchanged artifacts are reused on later exports.

`backup-operational-artifacts` waits for the archive job if necessary and is
optional. If `SYNERGIE_BACKUP_DIR` is set in
`.env`, it writes a `latest/` copy and a daily snapshot of
`data/archive/operational/` and `logs/chair_vm_tasks/` to the Synergie drive. If
the variable is unset, it exits successfully after logging a skip.

To additionally register the RQ3 cutoff submissions, run this separate
PowerShell script after filling `ENERGY_ARENA_PRICE_CHALLENGE_ID` in `.env`:

```powershell
.\deployment\chair-vm\register_cutoff_tasks.ps1
```

The optional cutoff tasks submit load, solar, onshore wind, and price for the
same cutoff information set from 07:00 through 11:00. The 12:00 RQ3 task is
compute-only because the dedicated final-paper jobs own the single effective
12:00 leaderboard slot for this participant:

```text
04:05 dwd-run00-update
05:15 renewable-run00-features-update
06:40 price-cutoff-0700-submit
07:40 price-cutoff-0800-submit
08:40 price-cutoff-0900-submit
09:23 dwd-run06-cutoff-update
09:40 renewable-cutoff-features-update
09:45 price-cutoff-1000-submit
10:40 price-cutoff-1100-submit
11:40 price-cutoff-1200-compute
```

The compute-only task still writes the 12:00 RQ3 forecasts and dry-run payloads
for auditing and reproducibility. It does not call the Energy-Arena submission
API. The registration script removes the former
`DAForecastCutoff-price-cutoff-1200-submit` task so an obsolete scheduled task
cannot supersede the final-paper submissions.

The two early tasks prepare the causal `00` UTC weather inputs used by the
07:00, 08:00, and 09:00 operational adapters. On its first run, the feature
task seeds missing historical `run00` tables from the schema-compatible
`run06` cache and logs every seeded file. Fresh `run00` weather is then
appended for the target day. Subsequent runs update only the new day and retain
the native `run00` history.

These three early adapters are deliberately distinct from the retrospective
paper configs, whose `06` UTC weather is not observable at those live cutoffs.
Historical `03` UTC single-run data is not consistently available across the
training period, so deployment uses the reproducible `00` UTC archive instead.

At 09:23 the deployment downloads and aggregates the newly available `06` UTC
weather for the 10:00-12:00 models. The feature job waits for that download,
and the 10:00 submission waits for both preparation jobs before forecasting.

Before the first production day, pre-warm all cutoff-specific rolling forecast
caches outside the submission window:

```bash
./deployment/chair-vm/run_scheduled_job.sh cutoff-prewarm-all
```

This runs the six complete cutoff workflows sequentially in dry-run mode. It
does not contact the Energy Arena submission endpoint, and it continues with
the remaining cutoffs if one cutoff fails. The final log summary lists any
cutoffs that still need attention.

After a production day, inspect the machine-readable data-quality report with:

```bash
cat data/processed/operational_quality/$(TZ=Europe/Berlin date +%F).json
```

It records the six expected DWD processed inputs, missing operational-profile
inputs, logged fallback events, and the Energy-Arena response artifacts found
for the target day. The report is part of the Git-tracked operational archive.

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
