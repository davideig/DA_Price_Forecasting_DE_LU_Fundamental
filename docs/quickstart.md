# Quickstart

## Install

```bash
git lfs install
git clone https://github.com/davideig/DA_Price_Forecasting_DE_LU_Fundamental.git
cd DA_Price_Forecasting_DE_LU_Fundamental
git lfs pull
pixi install
```

Git LFS is required because the compact operational Parquet archive is stored
through LFS rather than in ordinary Git history.

## Configure Credentials

Create a local environment file:

```bash
cp .env.example .env
```

Set `ENTSOE_API_KEY` and `OPEN_METEO_API_KEY` for current-data updates. Add the
Energy Arena API key and challenge IDs only when using `--submit`.

## Run A Next-Day Model

The public operational runner restores the bundled archive when needed,
fetches and appends current inputs, runs the selected model, and exports a
target-day CSV:

```bash
pixi run forecast-next-day --model load --cutoff 0700
pixi run forecast-next-day --model solar --cutoff 0900
pixi run forecast-next-day --model wind --cutoff 1100
pixi run forecast-next-day --model price --cutoff 1200
pixi run forecast-next-day --model all --cutoff final
```

Valid models are `load`, `solar`, `wind`, `price`, and `all`. Valid cutoff
profiles are `0700`, `0800`, `0900`, `1000`, `1100`, `1200`, and `final`.
`price` automatically runs the corresponding load, solar, and wind inputs.

Outputs have one local delivery day and are stored at:

```text
results/operational_forecasts/<forecast-date>/<cutoff>/<model>.csv
```

Generate locally by default. Submit only when explicitly requested:

```bash
pixi run forecast-next-day --model all --cutoff final --submit
```

Use restored/cached data without API updates:

```bash
pixi run forecast-next-day --model wind --cutoff 1100 --skip-data-refresh
```

The operational profiles use information available by each live cutoff:

| Profile | Weather run | Load specification |
| --- | --- | --- |
| `0700`-`0900` | ICON-D2 03 UTC | Direct load |
| `1000` | ICON-D2 06 UTC | Direct load |
| `1100`-`1200` | ICON-D2 06 UTC | Residual load |
| `final` | ICON-D2 06 UTC | Final paper model family |

The early operational profiles are causally deployable adaptations. The exact
retrospective thesis grid is retained separately in
`configs/rq3_cutoff_grid/RUN_ORDER.md`.

## Verify Or Restore Data Manually

If the Git revision contains `data/archive/operational/manifest.json`:

```bash
pixi run operational-archive verify
pixi run operational-archive restore
```

Otherwise download the matching versioned data pack and unpack it in the
repository root:

```bash
tar -xzf DA_Price_Forecasting_DE_LU_Fundamental_data_v0.1.0.tar.gz
```

Verify the deployed model inputs:

```bash
pixi run check-data-pack --profile operational
```

Continue only when the check reports `Missing: 0`.

The one-command runner performs the restore automatically on a fresh clone.
These commands are useful for inspecting or repairing the archive directly.

## Run Configs Directly

```bash
pixi run forecast-load-final
pixi run forecast-solar-final
pixi run forecast-wind-final
```

Run the final generated-input price workflow without submitting:

```bash
pixi run energy-arena-price-final-daily --dry-run
```

Reuse supplied first-stage forecast caches without API refreshes:

```bash
pixi run energy-arena-price-final-daily \
  --dry-run \
  --skip-first-stage-refresh
```

Historical reproduction from a complete archive does not require Energy Arena
credentials. Never commit `.env`.

See [user_guide.md](user_guide.md) for data distribution, output locations,
RQ3 cutoff runs, and integration guidance.
