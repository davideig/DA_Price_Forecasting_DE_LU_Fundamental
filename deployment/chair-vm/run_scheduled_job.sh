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
DEPLOYMENT_PREPROCESSING="configs/deployment/cutoff_preprocessing"
DEPLOYMENT_CUTOFFS="configs/deployment/cutoffs"

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

run_dwd_update() {
  local run="$1"
  ensure_natural_earth_shapefile
  cleanup_raw_dwd
  local config
  for config in \
    "$DEPLOYMENT_PREPROCESSING/dwd_wind_run${run}.yaml" \
    "$DEPLOYMENT_PREPROCESSING/dwd_icon_c2_run${run}.yaml" \
    "$DEPLOYMENT_PREPROCESSING/dwd_solar_run${run}.yaml"; do
    "$PIXI" run -e ops da-price-dwd-icon-daily-update \
      --config "$config" \
      --no-catch-up-missing-days
  done
  cleanup_raw_dwd
}

refresh_weather_features() {
  local run="$1"
  local model_cutoff
  shift
  case "$run" in
    00) model_cutoff="0700" ;;
    03) model_cutoff="0800" ;;
    06) model_cutoff="1000" ;;
    *) echo "Unsupported weather run: $run" >&2; return 2 ;;
  esac

  "$PIXI" run energy-arena-renewable-daily \
    --feature-config "$DEPLOYMENT_PREPROCESSING/wind_dwd_features_run${run}.yaml" \
    --extra-feature-config "$DEPLOYMENT_PREPROCESSING/wind_open_meteo_features_run${run}.yaml" \
    --model-config "$DEPLOYMENT_CUTOFFS/wind_${model_cutoff}_run${run}.yaml" \
    --skip-solar \
    --features-only \
    "$@"

  "$PIXI" run energy-arena-renewable-daily \
    --feature-config "$DEPLOYMENT_PREPROCESSING/solar_dwd_features_run${run}.yaml" \
    --extra-feature-config "$DEPLOYMENT_PREPROCESSING/solar_open_meteo_features_run${run}.yaml" \
    --model-config "$DEPLOYMENT_CUTOFFS/solar_${model_cutoff}_run${run}.yaml" \
    --skip-wind \
    --features-only \
    "$@"
}

wait_for_job_lock() {
  local other_job="$1"
  local timeout_seconds="${2:-10800}"
  local waited=0
  while [ -d ".chair_vm_job_locks/${other_job}.lock" ]; do
    if [ "$waited" -ge "$timeout_seconds" ]; then
      echo "Timed out waiting for job lock: $other_job" >&2
      return 1
    fi
    if [ $((waited % 300)) -eq 0 ]; then
      echo "Waiting for $other_job to finish before continuing."
    fi
    sleep 30
    waited=$((waited + 30))
  done
}

case "$job" in
  dwd-run00-update)
    run_dwd_update 00
    ;;

  renewable-run00-features-update)
    wait_for_job_lock dwd-run00-update 3600
    refresh_weather_features 00
    ;;

  dwd-run03-update)
    run_dwd_update 03
    ;;

  renewable-run03-features-update)
    wait_for_job_lock dwd-run03-update 1800
    refresh_weather_features 03
    ;;

  dwd-run06-cutoff-update)
    run_dwd_update 06
    ;;

  renewable-cutoff-features-update)
    wait_for_job_lock dwd-run06-cutoff-update 2400
    refresh_weather_features 06
    ;;

  reserve-publication-poll)
    "$PIXI" run poll-reserve-publication
    ;;

  backfill-operational-reserve-market)
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 1100 \
      --reserve-only \
      --reserve-history-days 90
    ;;

  cutoff-prewarm-all)
    echo "--- Preparing fixed-run feature histories ---"
    refresh_weather_features 00
    refresh_weather_features 03
    refresh_weather_features 06
    failed_cutoffs=()
    for cutoff in 0700 0800 0900 1000 1100 1200; do
      echo "--- Pre-warming cutoff $cutoff ---"
      if ! "$PIXI" run energy-arena-price-cutoff-daily \
        --cutoff "$cutoff" \
        --submit-first-stage \
        --dry-run; then
        failed_cutoffs+=("$cutoff")
        echo "[prewarm] Cutoff $cutoff failed; continuing with the remaining cutoffs." >&2
      fi
    done
    if [ "${#failed_cutoffs[@]}" -gt 0 ]; then
      echo "[prewarm] Failed cutoffs: ${failed_cutoffs[*]}" >&2
      exit 1
    fi
    echo "[prewarm] All cutoff caches and dry-run submission payloads completed."
    ;;

  price-cutoff-0700-submit)
    wait_for_job_lock renewable-run00-features-update 3600
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 0700 \
      --submit-first-stage \
      --retry-until 06:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-0800-submit)
    wait_for_job_lock renewable-run03-features-update 3600
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 0800 \
      --submit-first-stage \
      --retry-until 07:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-0900-submit)
    wait_for_job_lock renewable-run03-features-update 3600
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 0900 \
      --submit-first-stage \
      --retry-until 08:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-1000-submit)
    wait_for_job_lock dwd-run06-cutoff-update 1800
    wait_for_job_lock renewable-cutoff-features-update 1800
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 1000 \
      --submit-first-stage \
      --retry-until 09:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-1100-submit)
    wait_for_job_lock renewable-cutoff-features-update 3600
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 1100 \
      --submit-first-stage \
      --retry-until 10:55 \
      --retry-interval-minutes 5
    ;;

  price-cutoff-1200-submit)
    wait_for_job_lock renewable-cutoff-features-update 3600
    "$PIXI" run energy-arena-price-cutoff-daily \
      --cutoff 1200 \
      --submit-first-stage \
      --retry-until 11:55 \
      --retry-interval-minutes 5
    ;;

  backfill-fixed-run-open-meteo)
    for run in 00 03; do
      echo "--- Back-filling Open-Meteo fixed run $run UTC ---"
      "$PIXI" run -e forecast da-price-forecast \
        --config "$DEPLOYMENT_PREPROCESSING/load_open_meteo_history_run${run}.yaml"
      "$PIXI" run -e forecast da-price-forecast \
        --config "$DEPLOYMENT_PREPROCESSING/wind_open_meteo_features_run${run}.yaml"
      "$PIXI" run -e forecast da-price-forecast \
        --config "$DEPLOYMENT_PREPROCESSING/solar_open_meteo_features_run${run}.yaml"
    done
    ;;

  repair-operational-data)
    ensure_natural_earth_shapefile
    cleanup_raw_dwd
    repair_failures=()
    repair_step() {
      local label="$1"
      shift
      echo "--- Repairing $label ---"
      if "$@"; then
        echo "[repair] $label complete."
      else
        local code=$?
        repair_failures+=("$label (exit $code)")
        echo "[repair] $label failed with exit $code; continuing." >&2
      fi
    }

    repair_step "DWD run00" run_dwd_update 00
    repair_step "DWD run03" run_dwd_update 03
    repair_step "DWD run06" run_dwd_update 06
    cleanup_raw_dwd

    repair_step "run00 renewable features" refresh_weather_features 00 --force-feature-refresh
    repair_step "run03 renewable features" refresh_weather_features 03 --force-feature-refresh
    repair_step "run06 renewable features" refresh_weather_features 06 --force-feature-refresh
    repair_step "operational quality report" "$PIXI" run operational-data-quality

    if [ "${#repair_failures[@]}" -gt 0 ]; then
      printf '[repair] Failed steps: %s\n' "${repair_failures[*]}" >&2
      exit 1
    fi
    echo "[repair] All current operational inputs were refreshed successfully."
    ;;

  commit-operational-archive)
    wait_for_job_lock repair-operational-data
    if ! git lfs version >/dev/null 2>&1; then
      echo "Git LFS is required to publish the operational Parquet archive." >&2
      echo "Install git-lfs and run 'git lfs install --local' in the repository." >&2
      exit 1
    fi
    git pull --ff-only
    "$PIXI" run operational-archive export --profile operational
    "$PIXI" run operational-archive verify
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
    wait_for_job_lock commit-operational-archive
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
