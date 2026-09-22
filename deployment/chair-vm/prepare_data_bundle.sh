#!/usr/bin/env bash
set -euo pipefail

out="${1:-chair_vm_operational_data_$(date +%Y%m%d).tar.gz}"

paths=(
  "configs/deployment/energy_arena_point_submission.yaml"
  "configs/deployment/energy_arena_sqra_quantile_submission.yaml"
  "data/clustering"
  "data/shapefile"
  "data/raw/renewable_capacity"
  "data/processed/load_forecast"
  "data/processed/open_meteo"
  "data/processed/renewable_proxy"
  "data/processed/renewable_generation"
  "data/processed/icon_aggregated_mastr_solar_tso_c25_run06"
  "data/processed/icon_aggregated_mastr_wind_c100_run06"
  "data/processed/icon_aggregated_c2_run06"
  "results/load_forecast_results"
  "results/renewable_generation_results"
  "results/price_forecast_results"
  "results/sqra_results"
)

existing=()
for path in "${paths[@]}"; do
  if [ -e "$path" ]; then
    existing+=("$path")
  else
    echo "[bundle] Missing, skipping: $path" >&2
  fi
done

if [ "${#existing[@]}" -eq 0 ]; then
  echo "[bundle] No paths found to bundle." >&2
  exit 1
fi

echo "[bundle] Writing $out"
tar -czf "$out" "${existing[@]}"
echo "[bundle] Done: $out"
echo "[bundle] Note: .env is intentionally not included. Create/copy it separately on the VM."
