# Config Organization

Top-level `configs/` is intentionally kept almost empty. Runnable configs live
in named subfolders so the final thesis models are not mixed with one-off
experiments.

For the fixed thesis models and the commands that reproduce the final result
tables, start with [`FINAL_MODELS.md`](FINAL_MODELS.md).

## Main Folders

- `configs/final/`: fixed thesis/reference models and benchmark evaluations.
  - `load/`: final direct and residual load models.
  - `load/price_inputs/`: first-stage load runs used by RQ2 price inputs.
  - `renewable/`: final solar and wind generation models.
  - `renewable/price_inputs/`: first-stage renewable runs used by RQ2 price inputs.
  - `benchmarks/`: ENTSO-E benchmark/evaluation configs for RQ1.
- `configs/preprocessing/`: configs that rebuild final model inputs.
  - `load_weather/`: Open-Meteo load-weather archives.
  - `price_weather/`: optional price-weather archives.
  - `renewable_features/`: renewable weather/proxy feature builders.
  - `weather_aggregation/`: LSDF/DWD ICON aggregation configs.
  - `capacity/`: MaStR/population support preprocessing.
- `configs/pricebase_sweep/`: final RQ2 controlled price-model configs.
- `configs/rq3_cutoff_grid/`: final RQ3 cutoff-grid workflow and run order.
- `configs/deployment/`: Energy Arena and legacy deployment wrappers.
- `configs/diagnostics/`: visualization/diagnostic configs.
- `configs/examples/`: templates for local configs that you copy and edit.

## Use Ignored Subdirectories

- `configs/archive/`: historical or failed experiment configs kept for local reference.
- `configs/local/`: machine-specific one-off configs.
- `configs/tmp/`: temporary configs generated during exploration.

The repository `.gitignore` keeps broad scratch configs quiet while explicitly
allowing the final thesis/operational configs to be tracked.
