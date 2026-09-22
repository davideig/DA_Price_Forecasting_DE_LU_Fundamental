from __future__ import annotations

import argparse
import json
import tarfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from da_price_forecasting.paths import find_repo_root


DEFAULT_INCLUDE_PATHS = (
    "data/processed",
    "data/clustering",
    "data/raw/renewable_capacity",
    "data/cache/entsoe",
)

DEFAULT_RESULT_PATHS = (
    "results/load_forecast_results",
    "results/renewable_generation_results",
    "results/price_forecast_results",
    "results/sqra_results",
    "results/evaluation",
)

DEFAULT_EXCLUDE_NAMES = {
    ".DS_Store",
    "__pycache__",
}


@dataclass(frozen=True)
class FeaturePackEntry:
    path: str
    size_bytes: int


@dataclass(frozen=True)
class FeaturePackManifest:
    created_at_utc: str
    repo_root: str
    include_results: bool
    entries: list[FeaturePackEntry]
    missing_optional_paths: list[str]


def _is_excluded(path: Path) -> bool:
    return any(part in DEFAULT_EXCLUDE_NAMES for part in path.parts)


def _iter_files(repo_root: Path, paths: list[Path]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    missing: list[str] = []
    seen: set[Path] = set()

    for relative in paths:
        source = repo_root / relative
        if not source.exists():
            missing.append(relative.as_posix())
            continue
        candidates = [source] if source.is_file() else sorted(path for path in source.rglob("*") if path.is_file())
        for path in candidates:
            if _is_excluded(path):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)

    return files, missing


def _default_output_path(repo_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return repo_root / "output" / "data_packs" / f"da_price_forecasting_de_lu_data_{stamp}.tar.gz"


def _build_manifest(
    repo_root: Path,
    files: list[Path],
    missing: list[str],
    include_results: bool,
) -> FeaturePackManifest:
    entries = [
        FeaturePackEntry(
            path=file.relative_to(repo_root).as_posix(),
            size_bytes=file.stat().st_size,
        )
        for file in files
    ]
    return FeaturePackManifest(
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        repo_root=repo_root.as_posix(),
        include_results=include_results,
        entries=entries,
        missing_optional_paths=missing,
    )


def _add_manifest(tar: tarfile.TarFile, manifest: FeaturePackManifest) -> None:
    payload = json.dumps(
        {
            **asdict(manifest),
            "total_files": len(manifest.entries),
            "total_size_bytes": sum(entry.size_bytes for entry in manifest.entries),
        },
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    info = tarfile.TarInfo("DATA_PACK_MANIFEST.json")
    info.size = len(payload)
    info.mtime = datetime.now(timezone.utc).timestamp()
    import io

    tar.addfile(info, io.BytesIO(payload))


def build_feature_pack(
    repo_root: Path,
    output_path: Path,
    include_results: bool,
    extra_paths: list[Path],
    dry_run: bool,
) -> int:
    include_paths = [Path(path) for path in DEFAULT_INCLUDE_PATHS]
    if include_results:
        include_paths.extend(Path(path) for path in DEFAULT_RESULT_PATHS)
    include_paths.extend(extra_paths)

    files, missing = _iter_files(repo_root, include_paths)
    manifest = _build_manifest(repo_root, files, missing, include_results=include_results)
    total_size = sum(entry.size_bytes for entry in manifest.entries)

    print(f"Repo root: {repo_root}")
    print(f"Output:    {output_path}")
    print(f"Files:     {len(files):,}")
    print(f"Size:      {total_size / 1024 / 1024:.1f} MiB before compression")
    if missing:
        print("")
        print("Missing optional paths:")
        for path in missing:
            print(f"  - {path}")

    if dry_run:
        print("")
        print("Dry run only. Re-run without --dry-run to create the archive.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, mode="w:gz") as tar:
        _add_manifest(tar, manifest)
        for file in files:
            tar.add(file, arcname=file.relative_to(repo_root).as_posix(), recursive=False)

    print("")
    print(f"Feature pack written to {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a compressed feature/cache pack for the final forecasting models."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Archive output path. Defaults to output/data_packs/da_price_forecasting_de_lu_data_<date>.tar.gz.",
    )
    parser.add_argument(
        "--include-results",
        action="store_true",
        help="Also include model result folders so price/evaluation configs can run immediately.",
    )
    parser.add_argument(
        "--extra-path",
        type=Path,
        action="append",
        default=[],
        help="Additional repo-relative file or directory to include. Can be passed multiple times.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be packaged without creating an archive.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())
    output_path = args.output or _default_output_path(repo_root)
    if not output_path.is_absolute():
        output_path = repo_root / output_path

    return build_feature_pack(
        repo_root=repo_root,
        output_path=output_path,
        include_results=args.include_results,
        extra_paths=args.extra_path,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
