# Model Card: Solar Generation Forecast

## Target

ENTSO-E actual solar generation for Germany/DE-LU, modeled through TSO-level
solar component forecasts and then summed.

## Main Inputs

- MaStR solar capacity data.
- DWD ICON-D2 radiation and temperature features.
- Open-Meteo cloud-cover features.
- Deterministic solar geometry and physics-inspired solar baseline features.
- Lagged and partial actual generation features where operationally admissible.

## Command

```bash
pixi run forecast-solar-final
```

## Output

The main downstream column is `Renewable_Solar_Proxy_MW`.
