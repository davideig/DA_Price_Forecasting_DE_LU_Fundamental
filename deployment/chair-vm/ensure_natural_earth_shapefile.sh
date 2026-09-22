#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
target_dir="$repo_root/data/shapefile"
target_base="$target_dir/ne_10m_admin_0_countries"
url="https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip"

required=(
  "${target_base}.shp"
  "${target_base}.shx"
  "${target_base}.dbf"
  "${target_base}.prj"
)

missing=0
for path in "${required[@]}"; do
  if [ ! -f "$path" ]; then
    missing=1
    break
  fi
done

if [ "$missing" -eq 0 ]; then
  echo "[setup] Natural Earth shapefile already present: ${target_base}.shp"
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download the Natural Earth shapefile." >&2
  exit 127
fi

if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required to extract the Natural Earth shapefile." >&2
  exit 127
fi

mkdir -p "$target_dir"
tmp_zip="$(mktemp "${TMPDIR:-/tmp}/natural_earth_XXXXXX.zip")"
trap 'rm -f "$tmp_zip"' EXIT

echo "[setup] Downloading Natural Earth country shapefile..."
curl -fsSL "$url" -o "$tmp_zip"
unzip -oq "$tmp_zip" -d "$target_dir"

for path in "${required[@]}"; do
  if [ ! -f "$path" ]; then
    echo "Natural Earth shapefile download did not create required file: $path" >&2
    exit 1
  fi
done

echo "[setup] Natural Earth shapefile ready: ${target_base}.shp"
