# Model Card: Load Forecast

## Target

ENTSO-E actual load for DE-LU.

## Final Models

- Residual model: predicts a correction around the ENTSO-E day-ahead load
  forecast.
- Direct model: predicts load without using the ENTSO-E day-ahead load forecast.

## Main Inputs

- Calendar and holiday features.
- Lagged actual load.
- Partial morning load on day `D-1`.
- Open-Meteo ICON-D2 weather features.
- ENTSO-E day-ahead load forecast for the residual model only.

## Commands

```bash
pixi run forecast-load-final
pixi run forecast-load-direct
```

## Output

The main downstream column is `Load_Model_MW`.
