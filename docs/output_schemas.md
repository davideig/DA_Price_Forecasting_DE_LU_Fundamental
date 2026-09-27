# Output Schemas

The reusable next-day runner writes regular CSV files under:

```text
results/operational_forecasts/<forecast-date>/<cutoff>/<model>.csv
```

Each file contains only the requested local delivery day. Lower-level model
outputs and historical caches remain in their existing directories under
`results/`.

## Load Forecast

Required columns for downstream use:

```text
timestamp
Load_Model_MW
```

Important optional columns:

```text
Load_Actual_MW
Load_Forecast_MW
Residual_Model_MW
```

## Solar Forecast

Required columns:

```text
timestamp
Renewable_Solar_Proxy_MW
```

## Wind Forecast

Required columns:

```text
timestamp
Renewable_Wind_Proxy_MW
Wind_Onshore_Model_MW
Wind_Offshore_Model_MW
```

Energy Arena wind submissions use the onshore column unless the challenge
explicitly requests total wind.

## Combined Renewable Forecast

Useful downstream columns:

```text
timestamp
Renewable_Solar_Proxy_MW
Renewable_Wind_Proxy_MW
Renewable_Total_Proxy_MW
```

## Price Forecast

Typical point forecast columns:

```text
timestamp
y_pred
y_true
```

Some price/evaluation outputs also include model-specific columns and error
diagnostics.
