# DA Price Forecasting Pipeline DE-LU

This repository contains an operational forecasting pipeline for the German-Luxembourg bidding zone. It started as a day-ahead price forecasting project and now contains the linked sub-models needed for a fundamental price forecast:

- **Load forecasting** for DE-LU, including both a direct load model and a residual model around the ENTSO-E day-ahead load forecast.
- **Renewable generation forecasting** for solar and wind, using MaStR capacity data, weather forecasts, and ENTSO-E actual generation targets.
- **Day-ahead electricity price forecasting** for EPEX DE-LU, with point forecast models over controlled information sets.

The operational target is to generate all forecasts before the EPEX DE-LU auction gate closure at 12:00 Europe/Berlin time. All production-facing inputs are either available through APIs before gate closure or are cached from API/backfill runs into `data/processed/`.

> **Note**: The repository now contains a modular Python implementation under `src/da_price_forecasting/`. The notebooks are kept as fallback/reference, but the intended execution path is via configs plus standalone scripts or CLI commands.

## Current Forecasting Tasks

The most relevant current model families are:

### Load Forecasting

Current reference point model:

```text
configs/final/load/load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml
```

This model predicts ENTSO-E actual load by learning the residual around the ENTSO-E day-ahead load forecast. It uses calendar and holiday features, lagged actual load, a partial morning load shape from day `D-1`, the ENTSO-E day-ahead load forecast, and Open-Meteo ICON-D2 weather features. The Open-Meteo weather is sampled as p10 grid means per ICON-D2 cluster and then converted into population-weighted, daily, quantile, spread, and time-interaction features. The fixed thesis comparison evaluates it over the February-July 2026 window, where it reaches about **1.75 GW RMSE**.

For the load research question there is also a direct model that intentionally does **not** use the ENTSO-E load forecast:

```text
configs/final/load/load_forecast_direct_actual_open_meteo_p10_morning0915_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml
```

That direct model is useful for comparing (i) our own pre-ENTSO-E load forecast, (ii) the ENTSO-E benchmark, and (iii) the stronger residual model that is available once the ENTSO-E load forecast has been published.

### Renewable Generation Forecasting

Current reference solar model:

```text
configs/final/renewable/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_paper_febjul.yaml
```

The solar model trains four component models for the German TSO control areas and sums them to national DE-LU solar generation. The target is ENTSO-E actual solar generation per control area. The feature set combines MaStR capacity-weighted solar clusters, DWD ICON-D2 run-06 radiation and temperature features, Open-Meteo cloud-cover features, deterministic solar geometry, and physics-style solar baseline features. The fixed thesis comparison evaluates it over the February-July 2026 window.

Current reference wind model:

```text
configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml
```

The wind model predicts ENTSO-E onshore and offshore wind generation separately and sums them to total wind. It combines MaStR wind-capacity clusters, DWD ICON-D2 run-06 near-surface wind/weather features, and a seven-provider Open-Meteo run-06 hub-height weather ensemble represented by provider mean/std features over 80 capacity-weighted wind points. The fixed thesis comparison evaluates it over the February-July 2026 window. ENTSO-E renewable forecasts remain useful offline benchmarks, but they are not treated as operational inputs because their publication timing is not compatible with the pre-12:00 price forecast.

### Price Forecasting

The price pipeline compares several information sets:

- **Fundamental without EXAA**: weather, calendar, lagged prices, and optional generated load/renewable inputs.
- **EXAA-enriched**: fundamental inputs plus EXAA day-ahead prices once they are published.
- **EXAA-only**: a compact late-running model driven by EXAA prices.
- Legacy SQRA/quantile tooling remains in the repository for older Energy Arena
  experiments, but the fixed thesis result path is based on point forecasts.

The current no-EXAA config that wires generated load and renewable forecasts into LEAR is:

```text
configs/pricebase_sweep/oos_pgen_c2_d70.yaml
```

The controlled RQ2 baseline and generated-forecast variants live in
`configs/pricebase_sweep/`. The cutoff-grid RQ3 models live in
`configs/rq3_cutoff_grid/` and are documented in that folder's `RUN_ORDER.md`.

## Final Boosted-Tree Commands

The historical Pixi environment name `lear` is kept for backwards compatibility,
but the reusable boosted-tree workflow should use the clearer `forecast` task
aliases. These commands run the selected final/reference configs without having
to paste long YAML paths:

```bash
pixi run forecast-load-final
pixi run forecast-load-direct
pixi run forecast-solar-final
pixi run forecast-wind-final
```

Optional comparison runs:

```bash
pixi run forecast-solar-ensemble
pixi run forecast-wind-full-weather
```

The task names map to these model roles:

- `forecast-load-final`: residual LightGBM load model around the ENTSO-E day-ahead load forecast.
- `forecast-load-direct`: direct LightGBM load model without the ENTSO-E day-ahead load forecast.
- `forecast-solar-final`: current TSO-split solar HGB model with MaStR/DWD/Open-Meteo/solar-geometry features.
- `forecast-solar-ensemble`: solar multi-provider weather ensemble variant for comparison.
- `forecast-wind-final`: current compact multi-provider wind HGB model with common hub-height ensemble features.
- `forecast-wind-full-weather`: heavier wind variant with additional weather variables for comparison.

Raw configs can still be run directly with:

```bash
pixi run -e forecast da-price-forecast --config configs/SOME_CONFIG.yaml
```

## Clean Release Export

This repository is the research/workbench repo and intentionally keeps the
paper, local data, results, and archived experiments. To create a clean
copy-only release repo for users, run the exporter:

```bash
python scripts/export_release_repo.py ../DA_Price_Forecasting_Pipeline_DE_LU_release
python scripts/export_release_repo.py ../DA_Price_Forecasting_Pipeline_DE_LU_release --execute
```

The first command is a dry run. The second command copies only the whitelisted
files from `release_manifest.toml`. It never moves or deletes anything from this
repo and refuses to write into a non-empty destination.

## Repository Structure

```text
DA_Price_Forecasting_Pipeline_DE_LU/
├── .cache/               # Local caches and model weights, ignored by Git
├── data/                  # Raw and processed data, clustering files, shapefiles
├── configs/               # Local YAML configs plus reusable examples
├── notebooks/             # Legacy notebooks kept as reference
├── output/figures/        # Generated thesis/report figures and tables
├── pixi.toml              # Pixi environments and runnable tasks
├── scripts/               # Notebook-free runner scripts
├── results/               # Forecast outputs and evaluation metrics
├── src/                   # Modular package implementation
└── visualization/         # Plotting scripts
```

## Data

The pipeline uses these external data sources:

- **ENTSO-E Transparency Platform**: actual load, day-ahead load forecast, actual solar and wind generation, TSO-level solar generation targets, EPEX DE-LU day-ahead prices, and benchmark generation forecasts. Access via API key (set `ENTSOE_API_KEY` in `.env`, see `.env.example`).
- **MaStR**: installed renewable capacity, coordinates, technology labels, and commissioning dates. The renewable models use MaStR to build capacity-weighted solar and wind weather clusters.
- **DWD ICON-D2**: operational NWP forecasts, usually run 06, retrieved from DWD Open Data or from the LSDF archive for historical backfills. Aggregated weather features are stored under cluster-specific folders such as `data/processed/icon_aggregated_*`.
- **Open-Meteo ICON-D2 single-run API**: cached operational weather features that are not available or not convenient in the local DWD archive, especially p10 weather samples for load, cloud cover for solar, and hub-height wind for wind. API access is rate-limited, so the cache in `data/processed/open_meteo/` and `data/processed/renewable_proxy/` is part of the operational data layer.
- **Population weights**: cluster-level population weights for load weather aggregation, stored in `data/processed/load_forecast/`.
- **EXAA prices**: optional late-arriving price input for EXAA-enriched and EXAA-only price models.
- **ERA5 Reanalysis**: legacy/benchmark weather source. Retrieved from the Copernicus Climate Data Store (CDS) with `era5_download`, then aggregated with `era5_aggregate`.

Generated data layout:

- `data/archive/operational/`: Git-tracked Parquet mirror of the reusable processed archive
- `data/raw/era5/`: downloaded ERA5 GRIB files
- `data/processed/era5_aggregated/`: derived ERA5 cluster features used by LEAR
- `data/processed/icon_aggregated_c*/`: derived ICON-D2 cluster features used by LEAR
- `data/processed/open_meteo/`: cached Open-Meteo load-weather archives
- `data/processed/renewable_proxy/`: renewable weather/proxy feature files
- `data/processed/load_forecast/`: actual load, ENTSO-E load forecast, population weights, and load diagnostics
- `data/processed/renewable_generation/`: ENTSO-E actual generation targets and related renewable data
- `.cache/models/tabpfn/`: local TabPFN checkpoint downloads, ignored by Git
- `results/`: model forecasts, metrics, runtime logs, and Energy Arena payload artifacts
- `output/figures/`: thesis/report PDFs generated by `visualization/`

### Operational Archive And Feature Pack

Raw weather/API downloads are not committed to Git. The reusable processed cache
is tracked as a compact Parquet archive under `data/archive/operational/`.
Restore it into the normal runtime paths after cloning:

```bash
pixi run operational-archive restore
pixi run check-data-thesis
```

The production VM updates the live CSV caches during the morning jobs and exports
the archive after the submission window:

```bash
pixi run operational-archive export
git add data/archive/operational
git commit -m "Update operational data archive YYYY-MM-DD"
git push
```

For immutable paper snapshots, you can also distribute a versioned tar.gz data
pack next to a GitHub Release, Zenodo record, OSF upload, or institutional
storage object.

Create a pack from a machine that already has the processed caches:

```bash
pixi run create-feature-pack --dry-run
pixi run create-feature-pack
```

Include existing model outputs as well when users should be able to reproduce
price/evaluation tables without rerunning first-stage models:

```bash
pixi run create-feature-pack --include-results
```

After unpacking a pack, users can verify local inputs before running models:

```bash
pixi run check-data-final
pixi run check-data-pack --profile thesis
```

See `docs/data_pack.md` for the full workflow and expected archive layout.

## Operational Information Set

For a delivery day `D`, the normal production run happens on day `D-1` before 12:00 Europe/Berlin:

- Calendar, holidays, bridge days, and Fourier seasonality are known in advance.
- Historical actual load and actual generation are used only with operational lags. Current configs avoid using full day `D-1`; partial morning features stop at a configured cutoff such as 09:15 or 10:15.
- The ENTSO-E day-ahead load forecast is used only by the residual load model and is assumed available around 10:30 on `D-1`.
- DWD/Open-Meteo weather forecasts use the morning run and are cached before the model run.
- EXAA prices are only used in EXAA-enriched or EXAA-only price configs after they are published.
- ENTSO-E renewable generation forecasts are used as offline benchmarks, not as operational renewable model inputs.

### Open-Meteo run availability check

For the multi-provider wind weather ensemble, log which Open-Meteo model runs are actually available before gate closure. Run this once per day close to the operational decision time, ideally around 11:20-11:30 Europe/Berlin:

```bash
pixi run open-meteo-availability
```

This appends one row per provider to:

```text
data/processed/open_meteo/model_run_availability_log.csv
```

The default check assumes `11:20` Europe/Berlin, target run `06 UTC`, a 10 minute safety buffer, and the customer Open-Meteo endpoint using `OPEN_METEO_API_KEY` from `.env`. Running it much later is useful as a smoke test, but less useful as operational evidence because the metadata endpoint reports the latest current provider state.

Optional cron reminder:

```cron
25 11 * * * cd /path/to/DA_Price_Forecasting_Pipeline_DE_LU && pixi run open-meteo-availability >> logs/open_meteo_availability.log 2>&1
```

## Setup

The repo uses Pixi to manage the different dependency stacks. Install Pixi once, then let it create the local `.pixi/` environments from `pixi.toml`:

```bash
pixi install --all
```

Running `pixi install --all` is optional. `pixi run` installs the selected environment automatically the first time you use it.

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Open-Meteo customer access is configured through `.env`:

```dotenv
OPEN_METEO_API_KEY=your_open_meteo_customer_key_here
```

The YAML configs should point `open_meteo_api_key_env` to that environment
variable. For archived single model runs, use the customer endpoint:

```yaml
open_meteo_base_url: https://customer-single-runs-api.open-meteo.com/v1/forecast
open_meteo_api_key_env: OPEN_METEO_API_KEY
```

Reusable research and deployment configs live under `configs/`. The tracked templates in `configs/examples/` are useful starting points for one-off local configs.

## bwCloud VM Usage

The pipeline can be run on a bwCloud/OpenStack VM with the same Pixi commands used locally. Use an Ubuntu image such as Ubuntu 24.04 and a flavor with enough memory for model runs. The `m1.xlarge` flavor is a practical starting point for heavier experiments, but the default root disk is small, so large `data/` and `results/` folders should live on an attached volume.

Private SSH keys must not be stored in this repository or in `.env`. Keep them under `~/.ssh/` with restrictive permissions. API keys belong in the untracked `.env` file on the machine that runs the pipeline.

From your local machine, move the bwCloud private key out of the repo:

```bash
mkdir -p ~/.ssh
mv key.txt ~/.ssh/bwcloud_forecasting
chmod 600 ~/.ssh/bwcloud_forecasting
```

Add a local SSH config entry:

```sshconfig
Host bwcloud-forecasting
  HostName 193.196.37.255
  User ubuntu
  IdentityFile ~/.ssh/bwcloud_forecasting
  ServerAliveInterval 60
```

Connect from your local machine:

```bash
ssh bwcloud-forecasting
```

On a fresh VM, install the base system tools and Pixi:

```bash
sudo apt update
sudo apt install -y git curl build-essential tmux htop rsync
curl -fsSL https://pixi.sh/install.sh | bash
source ~/.bashrc
```

Set up GitHub access on the VM with a VM-specific SSH key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_bwcloud -C "bwcloud-github"
cat ~/.ssh/github_bwcloud.pub
```

Add the printed public key in GitHub under `Settings -> SSH and GPG keys`, then configure SSH on the VM:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_bwcloud
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github.com
```

Clone and test the release repository on the VM:

```bash
git clone git@github.com:davideig/DA_Price_Forecasting_DE_LU_Fundamental.git DA_Price_Forecasting_Pipeline_DE_LU_release
cd DA_Price_Forecasting_Pipeline_DE_LU_release
pixi run test
```

For long-running jobs, use `tmux` so the run survives SSH disconnects:

```bash
tmux new -s forecasting
pixi run -e lear da-price-forecast --config configs/deployment/lear_point_predictions.yaml
```

Detach with `Ctrl-b`, then `d`, and reattach later with:

```bash
tmux attach -t forecasting
```

Create a VM-local `.env` for API keys:

```bash
cp .env.example .env
nano .env
```

### Daily Energy Arena price automation

The deployed price runner is the final paper `P_gen` stack:

- generated load forecast cache
- generated solar forecast cache
- generated wind forecast cache
- `configs/pricebase_sweep/oos_pgen_c2_d70.yaml`

For each run it targets tomorrow in `Europe/Berlin`, refreshes the generated
load/solar/wind forecast caches, runs the final LightGBM price model, writes
date-specific generated configs under
`results/energy_arena_work/price_final_pgen/<forecast-date>/`, and submits the
point forecast. Set `ENERGY_ARENA_PRICE_CHALLENGE_ID` in `.env`.

The VM service uses a retry window. The example below starts at 11:30 and
retries every 5 minutes until 11:55. The final retry is intentionally before
12:00 so the forecast can still be submitted before the Energy Arena deadline.
If a first-stage load/solar/wind refresh fails, the runner logs a `[fallback]`
message and tries the already cached first-stage CSVs. It does not silently
impute data; the final price run still fails if the cache does not cover the
target day.

Run a dry run first. This still builds forecasts and payloads, but does not submit to Energy Arena:

```bash
pixi run energy-arena-price-final-daily --dry-run
```

To test a specific target day:

```bash
pixi run energy-arena-price-final-daily --dry-run --forecast-date 2026-04-29
```

To submit manually:

```bash
pixi run energy-arena-price-final-daily
```

To submit manually with the same retry behavior as the VM timer:

```bash
pixi run energy-arena-price-final-daily --retry-until 11:55 --retry-interval-minutes 5
```

On the VM, set the system timezone and create a user-level systemd timer:

```bash
sudo timedatectl set-timezone Europe/Berlin
loginctl enable-linger ubuntu
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/energy-arena-price-final-daily.service <<'EOF'
[Unit]
Description=Daily Energy Arena final P_gen price submission

[Service]
Type=oneshot
WorkingDirectory=%h/DA_Price_Forecasting_Pipeline_DE_LU_release
ExecStart=%h/.pixi/bin/pixi run energy-arena-price-final-daily --retry-until 11:55 --retry-interval-minutes 5
EOF

cat > ~/.config/systemd/user/energy-arena-price-final-daily.timer <<'EOF'
[Unit]
Description=Run Energy Arena submission daily at 11:30 Europe/Berlin

[Timer]
OnCalendar=*-*-* 11:30:00
Persistent=true
Unit=energy-arena-price-final-daily.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now energy-arena-price-final-daily.timer
systemctl --user list-timers energy-arena-price-final-daily.timer
```

Inspect logs with:

```bash
journalctl --user -u energy-arena-price-final-daily.service -f
```

### Daily Energy Arena load automation

The load challenge uses the same VM pattern, but the source is a load model config instead of the EXAA-only price task. The current reference load model is the fixed thesis Open-Meteo residual LightGBM config:

```text
configs/final/load/load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml
```

Set the load challenge ids in the VM-local `.env`:

```bash
nano .env
# ENERGY_ARENA_LOAD_CHALLENGE_ID=<load challenge id>
```

The Open-Meteo daily wrapper targets tomorrow in `Europe/Berlin`, rewrites the load model evaluation window to that one day, extends the cached ENTSO-E actual/load-forecast CSVs when needed, resumes the Open-Meteo cache if the target-day weather is missing, and submits the `Load_Model_MW` column as a point forecast:

```bash
pixi run energy-arena-load-open-meteo-daily --dry-run --forecast-date 2026-05-23
pixi run energy-arena-load-open-meteo-daily --retry-until 11:55 --retry-interval-minutes 5
```

On the VM, create a point-forecast timer:

```bash
cat > ~/.config/systemd/user/energy-arena-load-open-meteo-daily.service <<'EOF'
[Unit]
Description=Daily Energy Arena Open-Meteo load forecast submission

[Service]
Type=oneshot
WorkingDirectory=%h/DA_Price_Forecasting_Pipeline_DE_LU_release
ExecStart=%h/.pixi/bin/pixi run energy-arena-load-open-meteo-daily --retry-until 11:55 --retry-interval-minutes 5
EOF

cat > ~/.config/systemd/user/energy-arena-load-open-meteo-daily.timer <<'EOF'
[Unit]
Description=Run Energy Arena Open-Meteo load submission daily at 11:35 Europe/Berlin

[Timer]
OnCalendar=*-*-* 11:35:00
Persistent=true
Unit=energy-arena-load-open-meteo-daily.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now energy-arena-load-open-meteo-daily.timer
systemctl --user list-timers energy-arena-load-open-meteo-daily.timer
```

Inspect Open-Meteo load logs with:

```bash
journalctl --user -u energy-arena-load-open-meteo-daily.service -f
```

The older DWD daily update task is still available for DWD-based configs, but the current reference load model relies on the Open-Meteo cache instead:

```bash
pixi run dwd-icon-daily-update --forecast-date 2026-05-23
```

For data/results transfer, use `rsync` from your local machine:

```bash
rsync -av --progress data/ <vm-host>:~/DA_Price_Forecasting_Pipeline_DE_LU_release/data/
rsync -av --progress <vm-host>:~/DA_Price_Forecasting_Pipeline_DE_LU_release/results/ results/
```

### Renewable generation model runs

The current solar and wind reference models depend on precomputed renewable proxy files. Refresh or backfill those feature files first when the weather archive has changed:

```bash
pixi run -e lear da-price-forecast --config configs/preprocessing/renewable_features/regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml
pixi run -e lear da-price-forecast --config configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_icon_d2_single_run06_mastr_solar_tso_c25_cloud_cover.yaml
pixi run -e lear da-price-forecast --config configs/preprocessing/renewable_features/regional_renewable_features_dwd_icon_mastr_wind_c100_run06_paper_febjul.yaml
pixi run -e lear da-price-forecast --config configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_icon_d2_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml
```

Then run the current reference models with the short task names:

```bash
pixi run forecast-solar-final
pixi run forecast-wind-final
```

For live Energy Arena renewable submissions, pass explicit `--feature-config`, `--extra-feature-config`, and `--model-config` arguments to `pixi run energy-arena-renewable-daily`; the command default still points to an older joint Open-Meteo benchmark config. The Energy Arena DE-LU wind challenges use ENTSO-E **Wind Onshore** (`psrType=B19`), not total wind, so the daily wrapper submits `Wind_Onshore_Model_MW` by default. If you pass a custom value column, keep it onshore for challenge 6/12/18:

```bash
pixi run energy-arena-renewable-daily \
  --model-config configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml \
  --wind-value-column Wind_Onshore_Model_MW
```

## Modular Workflow

The main workflow is notebook-free:

1. Prepare a top-level run YAML in `configs/`
2. Run preprocessing via Pixi tasks or the single runner
3. Run final boosted-tree models via `pixi run forecast-*` tasks, or run a config directly with `pixi run -e forecast da-price-forecast --config ...`
4. Run Energy Arena submission or visualization reports from saved artifacts

The notebooks in `notebooks/` are fallback/reference only.

## Pixi Environments

The repo still uses separate dependency stacks because the operational point models, legacy SQRA, preprocessing/visualization, and TabPFN have incompatible package constraints. Pixi keeps those stacks declarative in one file instead of using hand-managed `.venv` folders:

- `core`: preprocessing, visualization, and general package tooling
- `ops`: operational preprocessing plus LEAR dependencies, used for DWD ICON daily updates and heavier aggregation jobs
- `lear`: LEAR operational and ANC runs
- `sqra`: legacy SQRA probabilistic post-processing
- `tabpfn`: TabPFN-TS and local TabPFN, pinned to Python 3.11
- `dev`: core plus test tooling

You can inspect tasks with:

```bash
pixi task list
```

## Running Without Notebooks

Create top-level run configs from the examples:

```bash
cp configs/examples/run_lear_operational.example.yaml configs/deployment/lear_point_predictions.yaml
cp configs/examples/run_sqra.example.yaml configs/deployment/sqra_quantile_predictions.yaml
cp configs/examples/run_energy_arena_point_submission.example.yaml configs/deployment/energy_arena_point_submission.yaml
cp configs/examples/run_lear_anc.example.yaml configs/lear_anc.yaml
cp configs/examples/run_tabpfn_ts.example.yaml configs/tabpfn_ts.yaml
cp configs/examples/run_tabpfn_local.example.yaml configs/tabpfn_local.yaml
cp configs/examples/run_visualization_report.example.yaml configs/visualization_report.yaml
cp configs/examples/run_evaluation.example.yaml configs/evaluation.yaml
cp configs/examples/run_era5_download.example.yaml configs/era5_download.yaml
cp configs/examples/run_era5_aggregate.example.yaml configs/era5_aggregate.yaml
cp configs/examples/run_icon_aggregate.example.yaml configs/icon_aggregate.yaml
```

Each run YAML has a `kind` such as `lear_operational`, `sqra`, or `energy_arena_submit`, plus the detailed model settings under `config`.

Then run Pixi tasks. All tasks call the same installed repo entry point, `da-price-forecast`, in the correct Pixi environment:

```bash
pixi run era5-download
pixi run era5-aggregate
pixi run icon-aggregate
pixi run lear-operational
pixi run lear-anc
pixi run sqra
pixi run tabpfn-ts
pixi run tabpfn-local
pixi run energy-arena-point
pixi run energy-arena-load-daily --dry-run
pixi run visualization-report
pixi run evaluation
```

For custom runs, call the single runner in the matching Pixi environment:

```bash
pixi run -e lear da-price-forecast --config configs/deployment/lear_point_predictions.yaml
pixi run -e sqra da-price-forecast --config configs/deployment/sqra_quantile_predictions.yaml
pixi run -e lear da-price-forecast --config configs/deployment/energy_arena_point_submission.yaml --submit
pixi run -e core da-price-forecast --config configs/visualization_report.yaml
pixi run -e core da-price-forecast --config configs/evaluation.yaml
```

## Evaluation

The evaluation pipeline ports the reusable parts of `notebooks/evaluation.ipynb` into the normal config-driven CLI path. It reads `forecast.csv` artifacts, aligns them on a shared 15-minute evaluation window, and writes reproducible CSV outputs:

- `point_metrics.csv` with MAE, RMSE, and bias
- `point_gw_mae.csv` with pairwise Giacomini-White p-values for absolute-error loss
- `quantile_metrics.csv` with median MAE and aggregated pinball score
- `quantile_coverage.csv` with empirical interval coverage and Kupiec MTU counts
- `quantile_gw_aps.csv` with pairwise Giacomini-White p-values for APS loss

Create a config from the example and edit the forecast registry as needed:

```bash
cp configs/examples/run_evaluation.example.yaml configs/evaluation.yaml
pixi run evaluation
```

## Visualization Reports

The visualization layer is downstream of the forecasting pipelines. It reads saved artifacts from `results/` and reusable spatial inputs from `data/`, then writes thesis/report PDFs to `output/figures/`.

Use a separate report config instead of wiring plots into individual model configs:

```bash
cp configs/examples/run_visualization_report.example.yaml configs/visualization_report.yaml
pixi run visualization-report
```

The report config can generate:

- MAE/RMSE comparison tables from artifact folders containing `metrics.csv`
- runtime comparison tables from artifact folders containing `runtime.csv`
- probabilistic forecast examples from quantile `forecast.csv` files
- evaluation plots from `results/evaluation/...` folders, including point forecasts, quantile fans, coverage, and hourly error diagnostics
- ANC bar charts from `results/lear_anc_results/...`
- ANC cluster heatmaps using ANC CSVs, `data/clustering/`, and `data/shapefile/`

For example, copy the visualization template, point it at the result folders you
want to compare, and run:

```bash
cp configs/examples/run_visualization_report.example.yaml configs/visualization_report.yaml
pixi run visualization-report
```

## TabPFN-TS Benchmark

The `tabpfn-ts` pipeline is a separate model family for benchmarking against LEAR and SQRA. It uses Prior Labs' `tabpfn-time-series` package and writes the shared artifact layout:

- `forecast.csv` with `y_pred`, `y_true`, and quantile columns such as `q0.100`
- `runtime.csv`
- `metrics.csv` when realized prices are available
- `config.json`

The example config uses EXAA and load forecast covariates, both known for the target day in operational mode:

```bash
pixi run tabpfn-ts
```

Important:

- `tabpfn_mode = "client"` may use Prior Labs' hosted inference service.
- `disable_telemetry = true` sets `TABPFN_DISABLE_TELEMETRY=1` by default.
- Use `tabpfn_mode = "local"` only when the local TabPFN runtime and model weights are available.
- Local TabPFN-TS checkpoints are stored under `.cache/models/tabpfn/` by default, not in the repo root.

## Local TabPFN Benchmark

The `tabpfn-local` pipeline is a separate model family from `tabpfn-ts`. It uses `tabpfn.TabPFNRegressor` locally, so it does not call the TabPFN-TS hosted time-series client and is not subject to client API rate limits. It turns the price series into supervised quarter-hour rows and fits a fresh local regressor for each forecast day.

Default features:

- lagged SDAC prices for the same quarter-hour from 1, 2, and 7 days ago
- EXAA day-ahead prices when `use_exaa = true`
- ENTSO-E load forecast when `use_load_forecast = true`
- calendar features such as MTU, hour, day of week, month, weekend flag, sine/cosine cycles, and `is_15min_market`

Important settings:

- `max_train_rows` controls the trailing rows passed to TabPFN for each daily fit
- `train_window_days` limits the rolling training window before `max_train_rows` is applied
- `n_estimators`, `device`, `fit_mode`, and `inference_precision` are passed to `TabPFNRegressor`
- `point_output_type` selects the point forecast from `mean`, `median`, or `mode`
- `predict_batch_size` batches each 96-step daily prediction to reduce Apple MPS/GPU memory pressure

The example configs default to a conservative CPU baseline (`device = "cpu"`, `max_train_rows = 1000`, `n_estimators = 4`) because Apple MPS can run out of memory on the local TabPFN regressor even with one prediction row, and TabPFN's CPU path refuses more than 1000 samples unless `ignore_pretraining_limits = true` or `TABPFN_ALLOW_CPU_LARGE_DATASET=1` is set. Increase these settings only after the baseline run is stable.

Run it with:

```bash
pixi run tabpfn-local
```

## Energy Arena Submission

The Energy Arena integration is config-driven and can submit dense `values` payloads for both point and quantile challenges.

Current scope:

- Generates or loads a forecast for one target day without notebook code
- Supports LEAR operational sources, SQRA sources, TabPFN-TS sources, local TabPFN sources, load forecast model sources, and already-saved forecast CSVs
- Supports point payloads where each `values` entry is a scalar
- Supports quantile payloads where each `values` entry is a fixed quantile vector
- Exports the exact `test_payload.json`-style payload and forecast artifacts
- Submits directly to the Energy Arena API
- Supports payload templating via `configs/examples/energy_arena_dense_payload_template.example.json`

Point forecast example:

```bash
cp configs/examples/run_energy_arena_point_submission.example.yaml configs/deployment/energy_arena_point_submission.yaml
pixi run energy-arena-point
```

Quantile forecast example:

Use the same `energy_arena_submit` run kind with `objective: quantile` and an SQRA source config embedded under `config.source.config`.

TabPFN-TS point or quantile example:

Use the same `energy_arena_submit` run kind with `source.kind: tabpfn_ts` and the TabPFN-TS settings embedded under `config.source.config`.

Local TabPFN point or quantile example:

Use the same `energy_arena_submit` run kind with `source.kind: tabpfn_local` and the local TabPFN settings embedded under `config.source.config`.

This runs in dry-run mode by default and writes artifacts under `results/energy_arena_submissions/`.

The main artifact to use with Energy Arena is:

- `test_payload.json`

With `--submit`, this payload is submitted directly from this repo through the Energy Arena API endpoint.

Important:

- `source.kind = "lear_operational"` runs a LEAR operational config and submits its `y_pred` column by default
- `source.kind = "sqra"` runs an SQRA config and can submit either quantile columns or the median column
- `source.kind = "tabpfn_ts"` runs a TabPFN-TS config and can submit either `y_pred` or quantile columns
- `source.kind = "tabpfn_local"` runs a local TabPFN config and can submit either `y_pred` or quantile columns
- `source.kind = "load_forecast_model"` runs a load forecasting config and submits `Load_Model_MW` by default
- `source.kind = "forecast_file"` submits an existing CSV artifact with a timestamp index
- Non-EXAA-only LEAR direct submission requires target-day weather and load forecast features to be available
- The dense payload template matches the current `challenge_id` / `target_start` / `values` example format for both point and quantile challenges
- Direct API submission requires `ENERGY_ARENA_API_KEY` in `.env`
- The default Energy Arena API base URL is `https://api.energy-arena.org`; override `api_base_url` only if the platform changes it

## ERA5 Download

To download the raw ERA5 inputs used by the ERA5 aggregation pipeline:

1. Create a CDS account and accept the ERA5 dataset terms on the CDS website.
2. Create `~/.cdsapirc` with your CDS personal access token.
3. Run:

```bash
pixi run era5-download
```

By default, this writes:

- `data/raw/era5/era5_main.grib`
- `data/raw/era5/era5_solar.grib`

Aggregated ERA5 and ICON-D2 feature CSVs are written to `data/processed/era5_aggregated/` and cluster-specific ICON-D2 folders such as `data/processed/icon_aggregated_c5/`.

## Legacy Notebooks

`notebooks/lear_pipeline.ipynb` and `notebooks/sqra_pipeline.ipynb` are kept as fallback/reference while the modular code is validated. They are no longer the primary execution path.
