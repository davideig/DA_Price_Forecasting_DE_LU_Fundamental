# User Guide

This guide is for researchers or practitioners who want to reproduce forecasts
or use the generated load, solar, wind, and price signals in another pipeline.

## 1. Requirements

- Git
- Pixi
- macOS or Linux for local research runs
- Windows with WSL only for the provided production scheduler
- A processed data archive or data pack

The supported Python version and all package dependencies are managed by Pixi.
Do not create a separate Conda or virtualenv environment.

## 2. Clone And Install

```bash
git clone https://github.com/davideig/DA_Price_Forecasting_DE_LU_Fundamental.git
cd DA_Price_Forecasting_DE_LU_Fundamental
pixi install
```

Verify the code installation independently of model data:

```bash
pixi run test
```

## 3. Restore Model Data

### Option A: Git operational archive

Check whether the current revision contains an archive:

```bash
test -f data/archive/operational/manifest.json \
  && echo "archive present" \
  || echo "archive missing"
```

When present, restore its Parquet files to the runtime CSV/directory layout:

```bash
pixi run operational-archive restore
```

### Option B: Versioned data pack

If the Git archive is absent, download the data pack attached to the matching
project release and unpack it in the repository root:

```bash
tar -xzf DA_Price_Forecasting_DE_LU_Fundamental_data_v0.1.0.tar.gz
```

The archive must contain paths beginning with `data/` and, for immediately
runnable price models, the required first-stage files under `results/`.

Do not use the VM's Synergie backup as a public dependency. It is only a second
copy for disaster recovery and is unavailable to normal repository users.

## 4. Verify Inputs

For the deployed model family:

```bash
pixi run check-data-pack --profile operational
```

For the three fixed first-stage models:

```bash
pixi run check-data-final
```

For the final generated-input price model:

```bash
pixi run check-data-price-final
```

For every fixed thesis config:

```bash
pixi run check-data-thesis
```

Do not start a long model run until its check reports `Missing: 0`.

## 5. Configure API Access

Historical reproduction from a complete archive can run without submission
credentials. To update API-backed inputs or submit forecasts, create `.env`:

```bash
cp .env.example .env
```

Fill only the variables needed for the intended operation. At minimum:

```dotenv
ENTSOE_API_KEY=...
OPEN_METEO_API_KEY=...
```

Live submissions additionally require:

```dotenv
ENERGY_ARENA_API_KEY=...
ENERGY_ARENA_PRICE_CHALLENGE_ID=...
ENERGY_ARENA_LOAD_CHALLENGE_ID=...
ENERGY_ARENA_SOLAR_CHALLENGE_ID=...
ENERGY_ARENA_WIND_CHALLENGE_ID=...
```

Keep `.env` local. It is ignored by Git and is never included in data packs.

## 6. Run The Final Models

Run first-stage forecasts:

```bash
pixi run forecast-load-final
pixi run forecast-solar-final
pixi run forecast-wind-final
```

The corresponding outputs are written below:

```text
results/load_forecast_results/
results/renewable_generation_results/
```

Run the final operational price workflow without submitting:

```bash
pixi run energy-arena-price-final-daily --dry-run
```

When a supplied archive already contains the first-stage forecast CSVs, avoid
refreshing them with:

```bash
pixi run energy-arena-price-final-daily \
  --dry-run \
  --skip-first-stage-refresh
```

Dry-run payloads and live response files are written under:

```text
results/energy_arena_submissions/
```

## 7. Run RQ3 Cutoffs

The operational runner supports `0700`, `0800`, `0900`, `1000`, `1100`, and
`1200`:

```bash
pixi run energy-arena-price-cutoff-daily \
  --cutoff 0900 \
  --submit-first-stage \
  --dry-run
```

`--dry-run` builds forecasts and payloads but never contacts the submission
endpoint. The exact retrospective paper workflow is different from the live
weather-availability adapter and is documented in
`configs/rq3_cutoff_grid/RUN_ORDER.md`.

## 8. Use Forecasts Elsewhere

Forecast files are timestamp-indexed CSVs. Important point columns include:

```text
Load_Model_MW
Solar_Model_MW
Wind_Onshore_Model_MW
y_pred
```

See `docs/output_schemas.md` before integrating them into another pipeline.
Keep the timezone information attached to timestamps and validate that each
delivery day contains the expected 92, 96, or 100 quarter-hours around daylight
saving transitions.

## 9. Update And Redistribute Data

Normal users should consume a versioned archive. Maintainers can export current
runtime caches as compressed Parquet:

```bash
pixi run operational-archive export --profile operational
git add data/archive/operational
git commit -m "Update operational data archive YYYY-MM-DD"
git push
```

For immutable paper snapshots, create a separate versioned pack:

```bash
pixi run create-feature-pack --include-results
```

The pack is deliberately not committed to Git. Publish it as a release asset or
through a research-data repository, together with its coverage dates and SHA256
checksum.

## 10. Production Deployment

The WSL/Windows scheduler, retry behavior, fallbacks, Git archive publishing,
and Synergie backup are operational concerns. They are documented in
`deployment/chair-vm/README.md` and are not required for normal reuse.
