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

Install [Git LFS](https://git-lfs.com/) and [Pixi](https://pixi.sh), then clone
and install the environments:

```bash
git lfs install
git clone https://github.com/davideig/DA_Price_Forecasting_DE_LU_Fundamental.git
cd DA_Price_Forecasting_DE_LU_Fundamental
git lfs pull
pixi install
```

Copy the credential template and fill the API keys used by current-data
updates:

```bash
cp .env.example .env
```

Run any released next-day model with one command:

```bash
pixi run forecast-next-day --model wind --cutoff 1100
pixi run forecast-next-day --model price --cutoff final
pixi run forecast-next-day --model all --cutoff final
```

The command restores the Git archive on a fresh clone, fetches and appends the
required current inputs, runs the exact selected config and its dependencies,
and writes target-day CSVs under:

```text
results/operational_forecasts/<forecast-date>/<cutoff>/<model>.csv
```

Local CSV generation is the default. Energy Arena submission is deliberately
opt-in:

```bash
pixi run forecast-next-day --model all --cutoff final --submit
```

The older config-specific tasks remain available for exact historical
experiments. See [docs/quickstart.md](docs/quickstart.md) for the complete
cutoff matrix and offline-cache options.

## Credentials

Copy the template only when an API-backed update or submission is needed:

```bash
cp .env.example .env
```

The principal variables are:

| Variable | Needed for |
| --- | --- |
| `ENTSOE_API_KEY` | Updating load, generation, and price data |
| `OPEN_METEO_API_KEY` | Optional customer quota for single-run weather updates |
| `ENERGY_ARENA_API_KEY` | Live Energy Arena submissions |
| `ENERGY_ARENA_*_CHALLENGE_ID` | Selecting live submission challenges |

Do not commit `.env`. Offline reproduction from a complete data archive does
not require Energy Arena credentials. Without `OPEN_METEO_API_KEY`, fixed-run
weather requests automatically use Open-Meteo's rate-limited public
non-commercial single-runs endpoint with the same fixed `run=` requests. Set a
customer key for commercial use, large backfills, or production reliability.

## Data And Outputs

Live runtime data is materialized under `data/processed/` and `data/cache/`.
The portable Git representation uses compressed, time-partitioned Parquet under
`data/archive/operational/`. Consolidated feature histories remain complete;
only bulky intermediate DWD aggregations use a rolling 14-issue-day window.
Model outputs are written below `results/`.

Upstream attribution and redistribution notices are documented in
[docs/data_sources_and_licenses.md](docs/data_sources_and_licenses.md).

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
retries missing inputs after the deadline, records a dated data-quality report,
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
