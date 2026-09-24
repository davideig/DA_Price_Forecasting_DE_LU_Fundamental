# Quickstart

## Install

```bash
git clone https://github.com/davideig/DA_Price_Forecasting_DE_LU_Fundamental.git
cd DA_Price_Forecasting_DE_LU_Fundamental
pixi install
```

## Restore Data

If the Git revision contains `data/archive/operational/manifest.json`:

```bash
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

## Run Final Models

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

## Credentials

API updates and live submissions require a local `.env`:

```bash
cp .env.example .env
```

Historical reproduction from a complete archive does not require Energy Arena
credentials. Never commit `.env`.

See [user_guide.md](user_guide.md) for data distribution, output locations,
RQ3 cutoff runs, and integration guidance.
