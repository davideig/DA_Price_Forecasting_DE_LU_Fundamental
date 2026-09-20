#!/usr/bin/env bash
set -euo pipefail

job="${1:-}"
if [ -z "$job" ]; then
  echo "Usage: $0 <job-name>" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

find_pixi() {
  if command -v pixi >/dev/null 2>&1; then
    command -v pixi
    return
  fi
  if [ -x "$HOME/.pixi/bin/pixi" ]; then
    printf '%s\n' "$HOME/.pixi/bin/pixi"
    return
  fi
  echo "pixi not found. Run deployment/chair-vm/setup_wsl_repo.sh first." >&2
  exit 127
}

PIXI="$(find_pixi)"

status() {
  local target
  target="$(TZ=Europe/Berlin date -d tomorrow +%F)"
  echo "repo: $repo_root"
  echo "target: $target"
  echo "--- submission responses ---"
  find results/energy_arena_submissions \
    -path "*/$target/*/submission_response.json" \
    -printf "%T+ %p\n" 2>/dev/null | sort || true
  echo "--- recent logs ---"
  find logs/chair_vm_tasks -type f -name "*_$(TZ=Europe/Berlin date +%F).log" \
    -printf "%T+ %p\n" 2>/dev/null | sort || true
}

if [ "$job" = "status" ]; then
  status
  exit 0
fi

mkdir -p logs/chair_vm_tasks
log_file="logs/chair_vm_tasks/${job}_$(TZ=Europe/Berlin date +%F).log"
exec >>"$log_file" 2>&1

echo "=== $(date -Is) job=$job ==="
echo "repo=$repo_root"
echo "pixi=$PIXI"

trap 'code=$?; echo "=== $(date -Is) job=$job failed exit=$code ==="; exit "$code"' ERR

cleanup_raw_dwd() {
  rm -rf data/raw/dwd_icon_daily/dwd_icon_daily_* || true
}

case "$job" in
  dwd-wind-update)
    cleanup_raw_dwd
    "$PIXI" run -e ops da-price-dwd-icon-daily-update \
      --config configs/dwd_icon_mastr_wind_c100_run06_daily_update.yaml \
      --no-catch-up-missing-days
    cleanup_raw_dwd
    ;;

  dwd-solar-update)
    cleanup_raw_dwd
    "$PIXI" run -e ops da-price-dwd-icon-daily-update \
      --config configs/dwd_icon_mastr_solar_tso_c25_run06_daily_update.yaml \
      --no-catch-up-missing-days
    cleanup_raw_dwd
    ;;

  renewable-wind-warmup)
    "$PIXI" run energy-arena-renewable-daily \
      --model-config configs/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d90_cutoff1000_febmay22.yaml \
      --skip-solar \
      --wind-value-column Wind_Onshore_Model_MW \
      --wind-approach-name renewable_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_onshore \
      --dry-run
    ;;

  renewable-solar-submit)
    "$PIXI" run energy-arena-renewable-daily \
      --feature-config configs/regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml \
      --extra-feature-config configs/regional_renewable_features_open_meteo_icon_d2_single_run06_mastr_solar_tso_c25_cloud_cover.yaml \
      --model-config configs/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_febmay22.yaml \
      --skip-wind \
      --solar-approach-name renewable_dwd_icon_mastr_solar_tso_c25_run06_cloud_geometry_physics_hgb_solar \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  renewable-wind-submit)
    "$PIXI" run energy-arena-renewable-daily \
      --model-config configs/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d90_cutoff1000_febmay22.yaml \
      --skip-solar \
      --wind-value-column Wind_Onshore_Model_MW \
      --wind-approach-name renewable_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_onshore \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  price-submit)
    "$PIXI" run energy-arena-daily \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  load-point-submit)
    "$PIXI" run energy-arena-load-open-meteo-daily \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  load-quantile-submit)
    "$PIXI" run energy-arena-load-open-meteo-quantile-daily \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  *)
    echo "Unknown job: $job" >&2
    exit 2
    ;;
esac

echo "=== $(date -Is) job=$job complete ==="

