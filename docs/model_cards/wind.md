# Model Card: Wind Generation Forecast

## Target

ENTSO-E actual wind generation, with onshore and offshore components modeled
separately where supported by the config.

## Main Inputs

- MaStR wind-capacity clusters.
- DWD ICON-D2 near-surface wind/weather features.
- Open-Meteo multi-provider hub-height weather features.
- Onshore/offshore split features.

## Command

```bash
pixi run forecast-wind-final
```

## Output

Downstream columns:

```text
Renewable_Wind_Proxy_MW
Wind_Onshore_Model_MW
Wind_Offshore_Model_MW
```
