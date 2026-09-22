#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

echo "[setup] Repository: $repo_root"

if command -v timedatectl >/dev/null 2>&1; then
  sudo timedatectl set-timezone Europe/Berlin || true
fi

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y git curl ca-certificates unzip tar rsync
fi

if ! command -v pixi >/dev/null 2>&1 && [ ! -x "$HOME/.pixi/bin/pixi" ]; then
  echo "[setup] Installing Pixi..."
  curl -fsSL https://pixi.sh/install.sh | bash
fi

export PATH="$HOME/.pixi/bin:$PATH"

if ! command -v pixi >/dev/null 2>&1; then
  echo "[setup] Pixi was not found after installation. Open a new shell or add ~/.pixi/bin to PATH." >&2
  exit 1
fi

echo "[setup] Installing Pixi environments..."
pixi install

mkdir -p \
  data/raw/dwd_icon_daily \
  data/raw/renewable_capacity \
  data/processed/open_meteo \
  data/processed/renewable_proxy \
  data/processed/renewable_generation \
  logs/chair_vm_tasks \
  results/load_forecast_results \
  results/renewable_generation_results \
  results/price_forecast_results \
  results/sqra_results \
  results/energy_arena_submissions \
  results/energy_arena_work

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[setup] Created .env from .env.example. Fill in API keys and challenge ids before running submissions."
fi

chmod +x deployment/chair-vm/run_scheduled_job.sh

echo "[setup] Done. Next:"
echo "  1. Fill .env"
echo "  2. Transfer operational data"
echo "  3. Run dry runs from deployment/chair-vm/README.md"
