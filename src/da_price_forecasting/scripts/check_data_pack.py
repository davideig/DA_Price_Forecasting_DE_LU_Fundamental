from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from da_price_forecasting.config.base import load_config_payload
from da_price_forecasting.paths import find_repo_root


PROFILE_PATTERNS = {
    "operational": (
        "configs/final/load/load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml",
        "configs/final/renewable/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_paper_febjul.yaml",
        "configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml",
        "configs/final/load/price_inputs/*.yaml",
        "configs/final/renewable/price_inputs/*.yaml",
        "configs/pricebase_sweep/oos_pgen_c2_d70.yaml",
        "configs/rq3_cutoff_grid/load_0700_direct_open_meteo_icon_d2_run00_morning0615_tw224_f180.yaml",
        "configs/rq3_cutoff_grid/load_0800_direct_open_meteo_icon_d2_run00_morning0715_tw224_f180.yaml",
        "configs/rq3_cutoff_grid/load_0900_direct_open_meteo_icon_d2_run00_morning0815_tw224_f180.yaml",
        "configs/rq3_cutoff_grid/load_1000_direct_open_meteo_icon_d2_run06_morning0915_tw224_f180.yaml",
        "configs/rq3_cutoff_grid/load_1100_residual_open_meteo_icon_d2_run06_morning1015_tw224_f180.yaml",
        "configs/rq3_cutoff_grid/load_1200_residual_open_meteo_icon_d2_run06_morning1115_tw224_f180.yaml",
        "configs/rq3_cutoff_grid/solar_0700_dwd_mastr_tso_c25_run00_cloud_geometry_physics_morning0615_d90.yaml",
        "configs/rq3_cutoff_grid/solar_0[89]00_dwd_mastr_tso_c25_run00_cloud_geometry_physics_morning*.yaml",
        "configs/rq3_cutoff_grid/solar_1[012]00_dwd_mastr_tso_c25_run06_cloud_geometry_physics_morning*.yaml",
        "configs/rq3_cutoff_grid/wind_0700_dwd_mastr_c100_multi_provider7_run00_p80_morning0615_d180.yaml",
        "configs/rq3_cutoff_grid/wind_0[89]00_dwd_mastr_c100_multi_provider7_run00_p80_morning*.yaml",
        "configs/rq3_cutoff_grid/wind_1[012]00_dwd_mastr_c100_multi_provider7_run06_p80_morning*.yaml",
        "configs/rq3_cutoff_grid/price_0700_noexaa_direct_load_renewables_weather_c2_run00_d70.yaml",
        "configs/rq3_cutoff_grid/price_0800_noexaa_direct_load_renewables_weather_c2_run00_d70.yaml",
        "configs/rq3_cutoff_grid/price_0900_noexaa_direct_load_renewables_weather_c2_run00_d70.yaml",
        "configs/rq3_cutoff_grid/price_1000_noexaa_direct_load_renewables_weather_c2_run06_d70.yaml",
        "configs/rq3_cutoff_grid/price_1100_noexaa_residual_load_renewables_weather_c2_run06_d70.yaml",
        "configs/rq3_cutoff_grid/price_1200_exaa_residual_load_renewables_weather_c2_run06_d70.yaml",
        "configs/preprocessing/weather_aggregation/dwd_icon_mastr_wind_c100_run06_daily_update.yaml",
        "configs/preprocessing/weather_aggregation/dwd_icon_mastr_solar_tso_c25_run06_daily_update.yaml",
        "configs/preprocessing/weather_aggregation/dwd_icon_c2_run06_daily_update.yaml",
        "configs/preprocessing/renewable_features/regional_renewable_features_dwd_icon_mastr_wind_c100_run06_paper_febjul.yaml",
        "configs/preprocessing/renewable_features/regional_renewable_features_dwd_icon_mastr_solar_tso_c25_run06_solar_spread.yaml",
        "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_icon_d2_single_run06_mastr_solar_tso_c25_cloud_cover.yaml",
        "configs/preprocessing/renewable_features/regional_renewable_features_open_meteo_*_single_run06_wind_hub_p80_provider_common_paper_febjul.yaml",
    ),
    "final": (
        "configs/final/load/load_forecast_hybrid_entsoe_residual_open_meteo_p10_morning1015_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml",
        "configs/final/load/load_forecast_direct_actual_open_meteo_p10_morning0915_daily_weather_lightgbm_paper_febjul_tw224_f180_pop_weighted_quantiles.yaml",
        "configs/final/renewable/renewable_generation_dwd_icon_mastr_solar_tso_c25_run06_tso_components_cloud_geometry_physics_residual_own_region_daylight_suspicious_totalbias_hgb_solar_bias45_hour_s075_d90_cutoff1000_paper_febjul.yaml",
        "configs/final/renewable/renewable_generation_hybrid_dwd_mastr_wind_c100_multi_provider7_run06_summary_meanstd_onoff_split_wind_hub_p80_common_hgb_wind_struct_minleaf60_maxfeat08_bias30_mtu_s08_d180_cutoff1000_paper_febjul.yaml",
        "configs/final/benchmarks/*.yaml",
    ),
    "final-comparisons": (
        "configs/final/load/*.yaml",
        "configs/final/renewable/*.yaml",
        "configs/final/benchmarks/*.yaml",
    ),
    "rq2": (
        "configs/pricebase_sweep/*.yaml",
    ),
    "price-final": (
        "configs/final/load/price_inputs/*.yaml",
        "configs/final/renewable/price_inputs/*.yaml",
        "configs/pricebase_sweep/oos_pgen_c2_d70.yaml",
    ),
    "rq3": (
        "configs/rq3_cutoff_grid/load_*.yaml",
        "configs/rq3_cutoff_grid/solar_*.yaml",
        "configs/rq3_cutoff_grid/wind_*.yaml",
        "configs/rq3_cutoff_grid/price_*.yaml",
        "configs/rq3_cutoff_grid/evaluation_*.yaml",
    ),
}
PROFILE_PATTERNS["thesis"] = (
    PROFILE_PATTERNS["final"]
    + PROFILE_PATTERNS["price-final"]
    + PROFILE_PATTERNS["rq2"]
    + PROFILE_PATTERNS["rq3"]
)

PATH_KEY_SUFFIXES = ("_file", "_files", "_dir", "_path", "_paths")
OUTPUT_KEY_PARTS = ("export", "output", "report", "figure")
SKIP_KEYS = {
    "repo_root",
    "open_meteo_base_url",
    "open_meteo_api_key_env",
    "entsoe_api_key_env",
    "api_key_env",
}
SKIP_VALUE_PREFIXES = (
    "http://",
    "https://",
)


@dataclass(frozen=True)
class RequiredPath:
    config: str
    key: str
    path: str
    exists: bool


def _looks_like_input_path_key(key: str) -> bool:
    normalized = key.lower()
    if normalized in SKIP_KEYS:
        return False
    if any(part in normalized for part in OUTPUT_KEY_PARTS):
        return False
    return normalized.endswith(PATH_KEY_SUFFIXES)


def _looks_like_local_path(value: str) -> bool:
    if not value or value.startswith(SKIP_VALUE_PREFIXES):
        return False
    if value.startswith("$"):
        return False
    if "\n" in value:
        return False
    return "/" in value or value.endswith((".csv", ".parquet", ".json", ".yaml", ".yml", ".pkl", ".xlsx"))


def _iter_config_paths(value: Any, key: str = "") -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            normalized = str(child_key)
            if _looks_like_input_path_key(normalized):
                if isinstance(child_value, str) and _looks_like_local_path(child_value):
                    paths.append((normalized, child_value))
                elif isinstance(child_value, list):
                    for item in child_value:
                        if isinstance(item, str) and _looks_like_local_path(item):
                            paths.append((normalized, item))
            paths.extend(_iter_config_paths(child_value, normalized))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_iter_config_paths(item, key))
    return paths


def _expand_profile(repo_root: Path, profile: str) -> list[Path]:
    patterns = PROFILE_PATTERNS.get(profile)
    if patterns is None:
        valid = ", ".join(sorted(PROFILE_PATTERNS))
        raise ValueError(f"Unknown profile {profile!r}. Valid profiles: {valid}")

    configs: list[Path] = []
    for pattern in patterns:
        configs.extend(sorted(repo_root.glob(pattern)))
    return configs


def _resolve_required_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else repo_root / path


def collect_required_paths(repo_root: Path, configs: list[Path]) -> list[RequiredPath]:
    required: list[RequiredPath] = []
    seen: set[tuple[str, str, str]] = set()

    for config_path in configs:
        payload = load_config_payload(config_path)
        config_body = payload.get("config", payload)
        for key, raw_path in _iter_config_paths(config_body):
            resolved = _resolve_required_path(repo_root, raw_path)
            item = RequiredPath(
                config=config_path.relative_to(repo_root).as_posix(),
                key=key,
                path=raw_path,
                exists=resolved.exists(),
            )
            marker = (item.config, item.key, item.path)
            if marker in seen:
                continue
            seen.add(marker)
            required.append(item)

    return required


def _print_report(required: list[RequiredPath]) -> None:
    missing = [item for item in required if not item.exists]
    present = [item for item in required if item.exists]

    print(f"Required local inputs checked: {len(required)}")
    print(f"Present: {len(present)}")
    print(f"Missing: {len(missing)}")
    if not missing:
        print("")
        print("All checked input files/directories are present.")
        return

    print("")
    print("Missing inputs:")
    for item in missing:
        print(f"  - {item.path}")
        print(f"    config: {item.config}")
        print(f"    key:    {item.key}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether local data files required by model configs are present."
    )
    parser.add_argument(
        "configs",
        type=Path,
        nargs="*",
        help="Config files to check. If omitted, --profile is used.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_PATTERNS),
        default="final",
        help="Built-in config group to check when no explicit configs are provided.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a human report.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())
    configs = [path if path.is_absolute() else repo_root / path for path in args.configs]
    if not configs:
        configs = _expand_profile(repo_root, args.profile)
    missing_configs = [path for path in configs if not path.exists()]
    if missing_configs:
        for path in missing_configs:
            print(f"Config not found: {path}", flush=True)
        return 2

    required = collect_required_paths(repo_root, configs)
    if args.json:
        print(json.dumps([asdict(item) for item in required], indent=2, sort_keys=True))
    else:
        _print_report(required)

    return 1 if any(not item.exists for item in required) else 0


if __name__ == "__main__":
    raise SystemExit(main())
