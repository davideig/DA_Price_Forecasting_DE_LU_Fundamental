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
OPEN_METEO_API_KEY
ENERGY_ARENA_API_KEY
ENERGY_ARENA_PRICE_CHALLENGE_ID
ENERGY_ARENA_LOAD_CHALLENGE_ID
ENERGY_ARENA_SOLAR_CHALLENGE_ID
ENERGY_ARENA_WIND_CHALLENGE_ID
```

`OPEN_METEO_API_KEY` is required because the cutoff deployment requests the
explicit 03 and 06 UTC runs from the Open-Meteo customer single-run archive.
The 00 UTC run is eligible only as the previous-run fallback for a requested
03 UTC run. The deployment never substitutes the provider's latest run.

Optionally set `SYNERGIE_BACKUP_DIR` to a WSL-visible Synergie drive folder.
The scheduled backup job copies the compact operational archive and task logs
there after the Git archive commit:

```text
SYNERGIE_BACKUP_DIR=/mnt/synergie-diplomanden/MK_Eiglsperger/DA_Price_Forecasting/backups
```

For a persistent Synergie mount, store the SMB credentials in
`/home/ujmyz/.smbcredentials-synergie` with mode `600`, create the mount point,
and add this single line to `/etc/fstab` (adjust the user, IDs, and paths for a
different VM account):

```text
//iipsrv-file1.iip.kit.edu/synergie-diplomanden /mnt/synergie-diplomanden cifs credentials=/home/ujmyz/.smbcredentials-synergie,iocharset=utf8,vers=3.0,uid=1000,gid=1000,file_mode=0755,dir_mode=0755,_netdev,nofail,user,x-systemd.automount 0 0
```

Validate it with `sudo mount -a` and `findmnt -T "$SYNERGIE_BACKUP_DIR"`.
The backup job attempts this fstab mount once if CIFS is missing and refuses to
write into the local mount-point directory if the share remains unavailable.

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
model configs. Complete derived feature histories and the compact c2 weather
history consumed directly by the price models are retained. Bulky intermediate
DWD wind and solar aggregations use a rolling 14-issue-day continuation window.

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

The operational cutoff contract is documented in
[`docs/operational_cutoff_data_spec.md`](../../docs/operational_cutoff_data_spec.md).
Before the first deployment of that contract, inspect and quarantine caches
created by the former run06-to-run00 bootstrap:

```bash
python deployment/chair-vm/migrate_cutoff_weather_histories.py
python deployment/chair-vm/migrate_cutoff_weather_histories.py --apply
```

The migration moves suspect paths to `data/quarantine/`; it does not delete
them. Review the dry-run list before using `--apply`. Then back-fill the 03 and
06 UTC Open-Meteo single-run histories where the provider archive permits
it:

```bash
./deployment/chair-vm/run_scheduled_job.sh backfill-fixed-run-open-meteo
```

That job finishes by auditing every run/model cache. You can also run the audit
directly:

```bash
pixi run open-meteo-coverage --end-date "$(TZ=Europe/Berlin date +%F)"
```

It writes
`data/processed/operational_quality/open_meteo_coverage.json`. Missing days
before the first archived day are reported as transition coverage; cached days
without provenance, invalid runs, and gaps within the archive window fail the
command.

The backfill overrides the old backtest endpoint in these configs and requests
history through the current local date. It does not modify the YAML files.

Finally, pre-warm all component and price caches without submitting:

```bash
./deployment/chair-vm/run_scheduled_job.sh cutoff-prewarm-all
```

The pre-warm uses the deployment configs under `configs/deployment/cutoffs/`.
It requests one fixed weather run per cutoff and never submits to Energy Arena.

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

The general task file now owns maintenance only:

```text
12:25 repair-operational-data
14:00 commit-operational-archive
14:30 backup-operational-artifacts
```

Registering it removes the obsolete duplicate DWD and final-paper submission
tasks. All live load, solar, wind, and price submissions are owned by the
cutoff task file below.

The registered `wsl.exe` action remains attached until its Linux job finishes.
Consequently, Task Scheduler's `Running` state and `LastTaskResult` describe the
forecasting job itself; closing an unrelated terminal or RDP window does not stop it.

`repair-operational-data` runs after the Energy-Arena deadline. It retries any
missing current run03/run06 DWD inputs, forcibly revisits the target renewable
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

The cutoff tasks submit load, solar, onshore wind, and price for the same
cutoff information set at every cutoff from 07:00 through 12:00:

```text
06:21 dwd-run03-update
06:24 renewable-run03-features-update
06:40 price-cutoff-0700-submit
07:40 price-cutoff-0800-submit
07:55 reserve-publication-poll
08:40 price-cutoff-0900-submit
09:23 dwd-run06-cutoff-update
09:38 renewable-cutoff-features-update
09:40 price-cutoff-1000-submit
10:40 price-cutoff-1100-submit
11:40 price-cutoff-1200-submit
```

`reserve-publication-poll` remains observational. Once per minute it checks the
public regelleistung.net capacity-results endpoint for tomorrow's FCR, aFRR,
and mFRR results. It records the first observed publication time in:

```text
data/processed/operational_quality/reserve_publication_times.csv
```

The task stops after all three products are observed or at 11:20. Existing
observations are resumed without being overwritten, so a restarted task does
not replace an earlier publication time. On 2026-09-28, FCR appeared at 08:14,
aFRR at 09:16, and mFRR at 10:23. The live price models now use FCR from 09:00,
FCR plus aFRR from 10:00, and all three products from 11:00. Each cutoff job
downloads the admissible products and appends them to the operational reserve
history before fitting the price model.
The 14:00 operational-archive job includes this CSV in the Git archive, and the
task's console output is also retained in `logs/chair_vm_tasks/`.

The weather mapping is fixed: 07:00-09:00 use 03 UTC and 10:00-12:00 use 06 UTC
for both DWD GRIB and Open-Meteo. The 03 and 06 UTC runs each have their own
primary weather history. The 00 UTC run is only an explicitly flagged fallback
for a missing or incomplete 03 UTC run; it has no separate live history. The
runner contains no cross-run copy bootstrap, and fallback only moves to the
immediately preceding run and requires complete delivery-day coverage. Wind
uses DWD ICON-D2 plus Open-Meteo ICON-D2
only.

At 09:23 the deployment downloads and aggregates the newly available `06` UTC
weather for the 10:00-12:00 models. The 09:38 feature job waits for that
download, and the 09:40 model job waits for feature preparation if necessary.

Each cutoff writes immutable load/solar/wind histories under
`data/processed/component_forecast_history/<cutoff>/` before running price.
Past delivery days are never overwritten; reruns are stored separately and
fallback use is recorded. These histories are included in the operational
archive and daily Git/Synergie backups.

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
