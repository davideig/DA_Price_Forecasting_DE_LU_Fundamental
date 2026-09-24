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
DWD_WIND_CONFIG="configs/preprocessing/weather_aggregation/dwd_icon_mastr_wind_c100_run06_daily_update.yaml"
DWD_SOLAR_CONFIG="configs/preprocessing/weather_aggregation/dwd_icon_mastr_solar_tso_c25_run06_daily_update.yaml"
DWD_PRICE_CONFIG="configs/preprocessing/weather_aggregation/dwd_icon_c2_run06_daily_update.yaml"
WIND_FEATURE_CONFIG="configs/preprocessing/renewable_features/regional_renewable_features_dwd_icon_mastr_wind_c100_run06_paper_febjul.yaml"
SOLAR_FEATURE_CONFIG="configs/preprocessing/renewable_features/regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml"
SOLAR_EXTRA_FEATURE_CONFIG="configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_icon_d2_single_run06_mastr_solar_tso_c25_cloud_cover.yaml"
SOLAR_MODEL_CONFIG="configs/final/renewable/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_paper_febjul.yaml"
WIND_MODEL_CONFIG="configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml"
WIND_EXTRA_FEATURE_CONFIGS=(
  "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_icon_d2_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml"
  "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_ecmwf_ifs025_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml"
  "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_arpege_europe_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml"
  "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_ukmo_seamless_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml"
  "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_gfs_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml"
  "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_dmi_harmonie_arome_europe_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml"
  "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_icon_eu_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml"
)

wind_extra_feature_args=()
for config_path in "${WIND_EXTRA_FEATURE_CONFIGS[@]}"; do
  wind_extra_feature_args+=(--extra-feature-config "$config_path")
done

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

job_lock_dir=".chair_vm_job_locks/${job}.lock"
mkdir -p .chair_vm_job_locks
if ! mkdir "$job_lock_dir" 2>/dev/null; then
  echo "Job already running; lock exists: $job_lock_dir" >&2
  exit 0
fi
trap 'code=$?; rmdir "$job_lock_dir" 2>/dev/null || true; if [ "$code" -ne 0 ]; then echo "=== $(date -Is) job=$job failed exit=$code ==="; fi; exit "$code"' EXIT

cleanup_raw_dwd() {
  rm -rf data/raw/dwd_icon_daily/dwd_icon_daily_* || true
}

ensure_natural_earth_shapefile() {
  deployment/chair-vm/ensure_natural_earth_shapefile.sh
}

case "$job" in
  dwd-wind-update)
    ensure_natural_earth_shapefile
    cleanup_raw_dwd
    "$PIXI" run -e ops da-price-dwd-icon-daily-update \
      --config "$DWD_WIND_CONFIG" \
      --no-catch-up-missing-days
    "$PIXI" run -e ops da-price-dwd-icon-daily-update \
      --config "$DWD_PRICE_CONFIG" \
      --no-catch-up-missing-days
    ;;

  dwd-solar-update)
    ensure_natural_earth_shapefile
    "$PIXI" run -e ops da-price-dwd-icon-daily-update \
      --config "$DWD_SOLAR_CONFIG" \
      --no-catch-up-missing-days
    cleanup_raw_dwd
    ;;

  renewable-wind-warmup)
    "$PIXI" run energy-arena-renewable-daily \
      --feature-config "$WIND_FEATURE_CONFIG" \
      "${wind_extra_feature_args[@]}" \
      --model-config "$WIND_MODEL_CONFIG" \
      --skip-solar \
      --wind-value-column Wind_Onshore_Model_MW \
      --wind-approach-name renewable_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_onshore \
      --dry-run
    ;;

  renewable-cutoff-features-update)
    "$PIXI" run energy-arena-renewable-daily \
      --feature-config "$WIND_FEATURE_CONFIG" \
      "${wind_extra_feature_args[@]}" \
      --model-config "$WIND_MODEL_CONFIG" \
      --skip-solar \
      --features-only
    "$PIXI" run energy-arena-renewable-daily \
      --feature-config "$SOLAR_FEATURE_CONFIG" \
      --extra-feature-config "$SOLAR_EXTRA_FEATURE_CONFIG" \
      --model-config "$SOLAR_MODEL_CONFIG" \
      --skip-wind \
      --features-only
    ;;

  renewable-solar-submit)
    "$PIXI" run energy-arena-renewable-daily \
      --feature-config "$SOLAR_FEATURE_CONFIG" \
      --extra-feature-config "$SOLAR_EXTRA_FEATURE_CONFIG" \
      --model-config "$SOLAR_MODEL_CONFIG" \
      --skip-wind \
      --solar-approach-name renewable_dwd_icon_mastr_solar_tso_c25_run06_cloud_geometry_physics_hgb_solar \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  renewable-wind-submit)
    "$PIXI" run energy-arena-renewable-daily \
      --feature-config "$WIND_FEATURE_CONFIG" \
      "${wind_extra_feature_args[@]}" \
      --model-config "$WIND_MODEL_CONFIG" \
      --skip-solar \
      --wind-value-column Wind_Onshore_Model_MW \
      --wind-approach-name renewable_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_onshore \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  price-submit)
    "$PIXI" run energy-arena-price-final-daily \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  price-deadline-safety-submit)
    "$PIXI" run energy-arena-price-final-daily \
      --cached-safety-submit
    ;;

  price-cutoff-0700-submit)
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 0700 \
      --submit-first-stage \
      --retry-until 06:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-0800-submit)
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 0800 \
      --submit-first-stage \
      --retry-until 07:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-0900-submit)
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 0900 \
      --submit-first-stage \
      --retry-until 08:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-1000-submit)
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 1000 \
      --submit-first-stage \
      --retry-until 09:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-1100-submit)
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 1100 \
      --submit-first-stage \
      --retry-until 10:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-1200-submit)
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 1200 \
      --submit-first-stage \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  load-point-submit)
    "$PIXI" run energy-arena-load-open-meteo-daily \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  commit-operational-archive)
    git pull --ff-only
    "$PIXI" run operational-archive export --profile operational
    git add data/archive/operational
    if git diff --cached --quiet -- data/archive/operational; then
      echo "No operational archive changes to commit."
    else
      git \
        -c user.name="DA Forecasting VM" \
        -c user.email="davideig@users.noreply.github.com" \
        commit -m "Update operational data archive $(TZ=Europe/Berlin date +%F)"
      git push
    fi
    ;;

  backup-operational-artifacts)
    deployment/chair-vm/backup_operational_artifacts.sh
    ;;

  load-quantile-submit)
    echo "Load quantile submission is not packaged in this release repo yet." >&2
    echo "Port a load config with include_rolling_residual_quantiles before scheduling this job." >&2
    exit 2
    ;;

  *)
    echo "Unknown job: $job" >&2
    exit 2
    ;;
esac

echo "=== $(date -Is) job=$job complete ==="
