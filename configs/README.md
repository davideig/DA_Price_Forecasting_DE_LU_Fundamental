# Configuration Layout

The tracked configurations are the fixed inputs for released models and the
production deployment. Exploratory sweeps and result-table configurations live
in the separate thesis reproducibility repository.

- `configs/deployment/cutoffs/`: load, solar, wind, and price models for the
  07:00 through 12:00 operational cutoffs.
- `configs/deployment/cutoff_preprocessing/`: fixed-run DWD, Open-Meteo, and
  reserve-market refresh jobs used by those cutoffs.
- `configs/final/`: released load, solar, wind, and generated-input price model
  family exposed by `forecast-next-day --cutoff final`.
- `configs/preprocessing/`: rebuild configurations for model input histories.
- `configs/feature_allowlists/`: fixed feature selections used by released
  models.

Start with [`FINAL_MODELS.md`](FINAL_MODELS.md) for commands. Machine-specific
or experimental YAML belongs under ignored `configs/local/`, `configs/tmp/`,
or in a separate research workspace.
