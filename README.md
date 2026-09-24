# DA Price Forecasting Pipeline DE-LU

Reusable load, solar, onshore wind, and day-ahead electricity price forecasting
pipelines for the German-Luxembourg bidding zone.

The repository contains the fixed model configurations used for the thesis
experiments and the operational adapters used for daily Energy Arena
submissions. The implementation lives in `src/da_price_forecasting/`; YAML
files select data sources, information cutoffs, models, and output paths.

## Release Status

The source code and model configurations are complete. Running the final models
also requires the processed data archive. A clone is self-contained only when
this file is present:

```text
data/archive/operational/manifest.json
```

If it is absent, obtain the matching data pack from the project release or wait
for the production VM to publish the operational archive. Raw weather files are
intentionally not stored in Git.

Start with [docs/user_guide.md](docs/user_guide.md). The shorter command-only
version is [docs/quickstart.md](docs/quickstart.md).

## Models

The fixed first-stage models are:

- Load: residual LightGBM model around the ENTSO-E day-ahead forecast.
- Solar: TSO-component HGB model using MaStR capacity, DWD ICON-D2, Open-Meteo,
  and solar geometry/physics features.
- Wind: onshore/offshore HGB model using MaStR capacity and a seven-provider
  weather ensemble. Energy Arena receives the onshore component.
- Price: LightGBM `P_gen` model using the generated load, solar, and wind
  forecasts in addition to calendar, lagged-price, and weather inputs.

The exact config index is [configs/FINAL_MODELS.md](configs/FINAL_MODELS.md).
RQ3 cutoff experiments are documented in
[configs/rq3_cutoff_grid/RUN_ORDER.md](configs/rq3_cutoff_grid/RUN_ORDER.md).

## Quick Start

Install [Pixi](https://pixi.sh), then clone and install the environments:

```bash
git clone https://github.com/davideig/DA_Price_Forecasting_DE_LU_Fundamental.git
cd DA_Price_Forecasting_DE_LU_Fundamental
pixi install
```

Restore the processed archive when it is included in the clone:

```bash
test -f data/archive/operational/manifest.json
pixi run operational-archive restore
pixi run check-data-pack --profile operational
```

If the manifest check fails, unpack the separately published data pack in the
repository root instead. See [docs/data_pack.md](docs/data_pack.md).

Run the final first-stage models:

```bash
pixi run forecast-load-final
pixi run forecast-solar-final
pixi run forecast-wind-final
```

Run the final price workflow without submitting to Energy Arena:

```bash
pixi run energy-arena-price-final-daily --dry-run
```

To evaluate an already restored set of first-stage forecast caches without
refreshing APIs:

```bash
pixi run energy-arena-price-final-daily \
  --dry-run \
  --skip-first-stage-refresh
```

## Credentials

Copy the template only when an API-backed update or submission is needed:

```bash
cp .env.example .env
```

The principal variables are:

| Variable | Needed for |
| --- | --- |
| `ENTSOE_API_KEY` | Updating load, generation, and price data |
| `OPEN_METEO_API_KEY` | Updating customer single-run weather data |
| `ENERGY_ARENA_API_KEY` | Live Energy Arena submissions |
| `ENERGY_ARENA_*_CHALLENGE_ID` | Selecting live submission challenges |

Do not commit `.env`. Offline reproduction from a complete data archive does
not require Energy Arena credentials.

## Data And Outputs

Live runtime data is materialized under `data/processed/` and `data/cache/`.
The portable Git representation uses compressed Parquet under
`data/archive/operational/`. Model outputs are written below `results/`.

Useful checks:

```bash
pixi run check-data-final
pixi run check-data-price-final
pixi run check-data-pack --profile operational
pixi run check-data-thesis
```

The checks only report availability. They do not download data.

## Operational Deployment

The production deployment runs in WSL through Windows Task Scheduler. It
collects current data, runs the cutoff and final models, submits forecasts,
exports the updated operational archive, and backs up operational artifacts.

Deployment instructions are isolated in
[deployment/chair-vm/README.md](deployment/chair-vm/README.md). Normal users do
not need the VM scripts or access to the institutional Synergie drive.

The operational RQ3 adapters preserve the paper model structures while using
weather runs that are actually available at the live cutoff. The retrospective
paper availability convention remains documented separately in `RUN_ORDER.md`.

## Repository Layout

```text
configs/                 Fixed model and preprocessing configurations
data/                    Archive documentation and restored runtime data
deployment/chair-vm/     Production WSL scheduling and backup scripts
docs/                    User, data, and output documentation
src/da_price_forecasting Python package
tests/                   Automated tests
pixi.toml                Environments and command aliases
```

## Development

Run the test suite with:

```bash
pixi run test
```

Run a config directly with:

```bash
pixi run -e forecast da-price-forecast --config path/to/config.yaml
```

## License

No reuse license has been selected yet. Until a license file is added, standard
copyright restrictions apply. A license must be chosen before describing the
repository as an open-source release.
