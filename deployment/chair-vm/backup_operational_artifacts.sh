#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

read_env_var() {
  local key="$1"
  local value=""
  if [ -f .env ]; then
    value="$(grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2- || true)"
  fi
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

backup_root="$(read_env_var SYNERGIE_BACKUP_DIR)"
if [ -z "$backup_root" ]; then
  echo "[backup] SYNERGIE_BACKUP_DIR is not set in .env; skipping Synergie backup."
  exit 0
fi

date_stamp="$(TZ=Europe/Berlin date +%F)"
target="$backup_root/DA_Price_Forecasting_Pipeline_DE_LU_release"
latest="$target/latest"
snapshot="$target/snapshots/$date_stamp"

mkdir -p "$latest" "$snapshot"

copy_path() {
  local source="$1"
  local destination="$2"
  if [ -e "$source" ]; then
    mkdir -p "$(dirname "$destination")"
    rsync -a --delete "$source" "$destination"
  else
    echo "[backup] Missing, skipping: $source"
  fi
}

echo "[backup] Target: $target"

copy_path "data/archive/operational/" "$latest/data/archive/operational/"
copy_path "logs/chair_vm_tasks/" "$latest/logs/chair_vm_tasks/"

mkdir -p "$snapshot/data/archive" "$snapshot/logs"
rsync -a --delete "$latest/data/archive/operational/" "$snapshot/data/archive/operational/"
rsync -a --delete "$latest/logs/chair_vm_tasks/" "$snapshot/logs/chair_vm_tasks/"

{
  echo "created_at=$(date -Is)"
  echo "repo_root=$repo_root"
  echo "git_commit=$(git rev-parse HEAD 2>/dev/null || true)"
} > "$latest/BACKUP_MANIFEST.txt"
cp "$latest/BACKUP_MANIFEST.txt" "$snapshot/BACKUP_MANIFEST.txt"

echo "[backup] Done: $latest"
echo "[backup] Snapshot: $snapshot"
