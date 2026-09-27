from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


RUN_TOKEN = re.compile(r"\d{8}(00|03|06)")
RUN00_AGGREGATIONS = (
    Path("data/processed/icon_aggregated_c2_run00"),
    Path("data/processed/icon_aggregated_mastr_solar_tso_c25_run00"),
    Path("data/processed/icon_aggregated_mastr_wind_c100_run00"),
)
RUN00_FEATURE_GLOBS = (
    "dwd_icon_*run00*regional_renewable_features.csv",
    "open_meteo_*single_run00*regional_renewable_features.csv",
    "open_meteo_*single_run00*cloud_cover_features.csv",
)


def _contains_foreign_run(folder: Path, expected_run: str) -> bool:
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        match = RUN_TOKEN.search(path.name)
        if match and match.group(1) != expected_run:
            return True
    return False


def migration_candidates(repo_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for relative_root in RUN00_AGGREGATIONS:
        root = repo_root / relative_root
        if not root.exists():
            continue
        candidates.extend(
            folder
            for folder in sorted(root.iterdir())
            if folder.is_dir() and _contains_foreign_run(folder, "00")
        )

    proxy_root = repo_root / "data/processed/renewable_proxy"
    if proxy_root.exists():
        for pattern in RUN00_FEATURE_GLOBS:
            candidates.extend(sorted(path for path in proxy_root.glob(pattern) if path.is_file()))
    return sorted(set(candidates))


def migrate(repo_root: Path, *, apply: bool) -> Path | None:
    candidates = migration_candidates(repo_root)
    if not candidates:
        print("No legacy cross-run weather history was found.")
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine = repo_root / "data/quarantine/cutoff_weather_migration" / stamp
    for source in candidates:
        relative = source.relative_to(repo_root)
        destination = quarantine / relative
        action = "MOVE" if apply else "WOULD MOVE"
        print(f"{action}: {relative} -> {destination.relative_to(repo_root)}")
        if apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
    if not apply:
        print("Dry run only. Re-run with --apply after reviewing the paths above.")
        return None
    print(f"Quarantined {len(candidates)} path(s) under {quarantine}.")
    return quarantine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Quarantine legacy run06-to-run00 weather cache copies before deploying fixed-run cutoffs."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true", help="Move candidates; without this flag only report them.")
    args = parser.parse_args(argv)
    migrate(args.repo_root.resolve(), apply=args.apply)


if __name__ == "__main__":
    main()
