from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from da_price_forecasting.paths import find_repo_root
from da_price_forecasting.scripts.check_data_pack import _expand_profile, collect_required_paths


ARCHIVE_VERSION = 1
DEFAULT_ARCHIVE_ROOT = Path("data/archive/operational")
MANIFEST_NAME = "manifest.json"

DEFAULT_INCLUDE_PATHS = (
    "data/clustering",
    "data/shapefile",
    "data/raw/renewable_capacity",
    "data/cache/entsoe",
    "data/processed",
    "results/load_forecast_results",
    "results/renewable_generation_results",
    "results/price_forecast_results",
)

PROFILE_BASE_INCLUDE_PATHS = (
    "data/clustering",
    "data/shapefile",
    "data/raw/renewable_capacity",
    "data/cache/entsoe",
)

DEFAULT_EXCLUDE_NAMES = {
    ".DS_Store",
    "__pycache__",
}

TABLE_SUFFIXES = {".csv", ".parquet"}
COPY_SUFFIXES = {".json", ".yaml", ".yml", ".txt", ".pkl", ".xlsx"}


@dataclass(frozen=True)
class ArchiveEntry:
    source_path: str
    archive_path: str
    kind: Literal["csv_parquet", "parquet_copy", "file_copy"]
    original_suffix: str
    source_size_bytes: int
    archive_size_bytes: int
    source_sha256: str
    archive_sha256: str
    row_count: int | None = None
    column_count: int | None = None
    csv_header_comments: list[str] | None = None
    csv_blank_first_column: bool = False


@dataclass(frozen=True)
class ArchiveManifest:
    version: int
    created_at_utc: str
    repo_root: str
    archive_root: str
    include_paths: list[str]
    missing_optional_paths: list[str]
    entries: list[ArchiveEntry]


def _is_excluded(path: Path) -> bool:
    return any(part in DEFAULT_EXCLUDE_NAMES for part in path.parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_source_files(repo_root: Path, paths: list[Path], archive_root: Path) -> tuple[list[Path], list[str]]:
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
            if path.resolve().is_relative_to(archive_root.resolve()):
                continue
            suffix = path.suffix.lower()
            if suffix not in TABLE_SUFFIXES and suffix not in COPY_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)

    return files, missing


def _archive_path_for(repo_root: Path, archive_root: Path, source: Path) -> Path:
    relative = source.relative_to(repo_root)
    if source.suffix.lower() == ".csv":
        relative = relative.with_suffix(".parquet")
    return archive_root / relative


def _read_csv_header_comments(path: Path) -> list[str]:
    comments: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            comments.append(line.rstrip("\n"))
    return comments


def _read_csv_as_table(path: Path) -> tuple[pd.DataFrame, list[str], bool]:
    comments = _read_csv_header_comments(path)
    df = pd.read_csv(path, comment="#", low_memory=False)
    blank_first_column = len(df.columns) > 0 and str(df.columns[0]).startswith("Unnamed:")
    return df, comments, blank_first_column


def _write_csv_from_table(
    df: pd.DataFrame,
    path: Path,
    *,
    header_comments: list[str] | None,
    blank_first_column: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy()
    if blank_first_column and len(output.columns) > 0:
        columns = list(output.columns)
        columns[0] = ""
        output.columns = columns

    with path.open("w", encoding="utf-8", newline="") as handle:
        if header_comments:
            handle.write("\n".join(header_comments) + "\n")
        output.to_csv(handle, index=False)


def _export_file(
    repo_root: Path,
    archive_root: Path,
    source: Path,
    compression: str,
    published_archive_root: Path | None = None,
) -> ArchiveEntry:
    archive_path = _archive_path_for(repo_root, archive_root, source)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()

    row_count: int | None = None
    column_count: int | None = None
    comments: list[str] | None = None
    blank_first_column = False

    if suffix == ".csv":
        df, comments, blank_first_column = _read_csv_as_table(source)
        df.to_parquet(archive_path, index=False, compression=compression)
        kind: Literal["csv_parquet", "parquet_copy", "file_copy"] = "csv_parquet"
        row_count = len(df)
        column_count = len(df.columns)
    elif suffix == ".parquet":
        shutil.copy2(source, archive_path)
        kind = "parquet_copy"
    else:
        shutil.copy2(source, archive_path)
        kind = "file_copy"

    published_path = _archive_path_for(repo_root, published_archive_root or archive_root, source)
    try:
        archive_path_label = published_path.relative_to(repo_root).as_posix()
    except ValueError:
        archive_path_label = published_path.as_posix()
    return ArchiveEntry(
        source_path=source.relative_to(repo_root).as_posix(),
        archive_path=archive_path_label,
        kind=kind,
        original_suffix=suffix,
        source_size_bytes=source.stat().st_size,
        archive_size_bytes=archive_path.stat().st_size,
        source_sha256=_sha256(source),
        archive_sha256=_sha256(archive_path),
        row_count=row_count,
        column_count=column_count,
        csv_header_comments=comments,
        csv_blank_first_column=blank_first_column,
    )


def export_archive(
    repo_root: Path,
    archive_root: Path,
    include_paths: list[Path],
    compression: str,
    dry_run: bool,
    max_file_mb: float,
    allow_large_files: bool,
) -> int:
    sources, missing = _iter_source_files(repo_root, include_paths, archive_root=archive_root)
    print(f"Repo root:    {repo_root}")
    print(f"Archive root: {archive_root}")
    print(f"Source files: {len(sources):,}")
    if missing:
        print("")
        print("Missing optional paths:")
        for path in missing:
            print(f"  - {path}")

    if dry_run:
        total_size = sum(path.stat().st_size for path in sources)
        print("")
        print(f"Dry run only. Source size: {total_size / 1024 / 1024:.1f} MiB")
        return 0

    archive_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=f".{archive_root.name}.staging-", dir=archive_root.parent))
    try:
        entries = [
            _export_file(
                repo_root=repo_root,
                archive_root=staging_root,
                source=source,
                compression=compression,
                published_archive_root=archive_root,
            )
            for source in sources
        ]
        large_entries = [
            entry
            for entry in entries
            if entry.archive_size_bytes > max_file_mb * 1024 * 1024
        ]
        if large_entries and not allow_large_files:
            print("")
            print(f"Refusing to finish because archive file(s) exceed {max_file_mb:.1f} MiB:")
            for entry in large_entries:
                print(f"  - {entry.archive_path}: {entry.archive_size_bytes / 1024 / 1024:.1f} MiB")
            print("Use --allow-large-files only if the remote can accept these files.")
            return 3

        try:
            archive_root_label = archive_root.relative_to(repo_root).as_posix()
        except ValueError:
            archive_root_label = archive_root.as_posix()
        manifest = ArchiveManifest(
            version=ARCHIVE_VERSION,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            repo_root=repo_root.as_posix(),
            archive_root=archive_root_label,
            include_paths=[path.as_posix() for path in include_paths],
            missing_optional_paths=missing,
            entries=entries,
        )
        manifest_path = staging_root / MANIFEST_NAME
        manifest_path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")

        previous_root: Path | None = None
        if archive_root.exists():
            previous_root = archive_root.with_name(f".{archive_root.name}.previous-{uuid.uuid4().hex}")
            archive_root.rename(previous_root)
        try:
            staging_root.rename(archive_root)
        except Exception:
            if previous_root is not None:
                previous_root.rename(archive_root)
            raise
        else:
            if previous_root is not None:
                shutil.rmtree(previous_root)
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)

    source_size = sum(entry.source_size_bytes for entry in entries)
    archive_size = sum(entry.archive_size_bytes for entry in entries)
    print("")
    print(f"Archived files: {len(entries):,}")
    print(f"Source size:    {source_size / 1024 / 1024:.1f} MiB")
    print(f"Archive size:   {archive_size / 1024 / 1024:.1f} MiB")
    try:
        manifest_label = (archive_root / MANIFEST_NAME).relative_to(repo_root).as_posix()
    except ValueError:
        manifest_label = (archive_root / MANIFEST_NAME).as_posix()
    print(f"Manifest:       {manifest_label}")
    return 0


def _load_manifest(repo_root: Path, archive_root: Path) -> ArchiveManifest:
    manifest_path = archive_root / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"Operational archive manifest not found: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return ArchiveManifest(
        version=int(payload["version"]),
        created_at_utc=str(payload["created_at_utc"]),
        repo_root=str(payload["repo_root"]),
        archive_root=str(payload["archive_root"]),
        include_paths=list(payload["include_paths"]),
        missing_optional_paths=list(payload.get("missing_optional_paths", [])),
        entries=[ArchiveEntry(**entry) for entry in payload["entries"]],
    )


def restore_archive(repo_root: Path, archive_root: Path, dry_run: bool, overwrite: bool) -> int:
    try:
        manifest = _load_manifest(repo_root, archive_root)
    except FileNotFoundError:
        print(
            f"Operational archive is not available at {archive_root}.\n"
            "Download and unpack the matching release data pack, or use a Git revision "
            "that contains data/archive/operational/manifest.json.",
            file=sys.stderr,
        )
        return 2
    restored = 0
    skipped = 0
    print(f"Repo root:    {repo_root}")
    print(f"Archive root: {archive_root}")
    print(f"Created UTC:  {manifest.created_at_utc}")
    print(f"Entries:      {len(manifest.entries):,}")

    for entry in manifest.entries:
        source_path = repo_root / entry.source_path
        archive_path = repo_root / entry.archive_path
        if not archive_path.exists():
            raise FileNotFoundError(f"Archived file missing: {archive_path}")
        if source_path.exists() and not overwrite:
            skipped += 1
            continue
        if dry_run:
            restored += 1
            continue
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if entry.kind == "csv_parquet":
            df = pd.read_parquet(archive_path)
            _write_csv_from_table(
                df,
                source_path,
                header_comments=entry.csv_header_comments,
                blank_first_column=entry.csv_blank_first_column,
            )
        else:
            shutil.copy2(archive_path, source_path)
        restored += 1

    print("")
    if dry_run:
        print(f"Dry run only. Would restore {restored:,} files; skipped {skipped:,}.")
    else:
        print(f"Restored {restored:,} files; skipped {skipped:,}.")
    return 0


def _default_include_paths(include_results: bool) -> list[Path]:
    paths = [Path(path) for path in DEFAULT_INCLUDE_PATHS]
    if not include_results:
        paths = [path for path in paths if not path.parts or path.parts[0] != "results"]
    return paths


def _profile_include_paths(repo_root: Path, profile: str) -> list[Path]:
    configs = _expand_profile(repo_root, profile)
    required = collect_required_paths(repo_root, configs)
    paths = [Path(path) for path in PROFILE_BASE_INCLUDE_PATHS]
    paths.extend(Path(item.path) for item in required if not Path(item.path).is_absolute())
    return list(dict.fromkeys(paths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export or restore the Git-tracked operational data archive."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=DEFAULT_ARCHIVE_ROOT,
        help="Repo-relative archive root. Defaults to data/archive/operational.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Convert live cache files into the Parquet archive.")
    export_parser.add_argument(
        "--include-path",
        type=Path,
        action="append",
        default=[],
        help="Additional repo-relative file or directory to archive.",
    )
    export_parser.add_argument(
        "--profile",
        default=None,
        help="Archive only repo-local inputs required by a check-data-pack profile, plus small shared operational inputs.",
    )
    export_parser.add_argument(
        "--no-default-paths",
        action="store_true",
        help="Archive only paths passed with --include-path.",
    )
    export_parser.add_argument(
        "--no-results",
        action="store_true",
        help="Do not include results/load_forecast_results, results/renewable_generation_results, or results/price_forecast_results.",
    )
    export_parser.add_argument(
        "--compression",
        default="zstd",
        help="Parquet compression codec. Defaults to zstd.",
    )
    export_parser.add_argument(
        "--max-file-mb",
        type=float,
        default=95.0,
        help="Refuse export if any archive file exceeds this size unless --allow-large-files is set.",
    )
    export_parser.add_argument(
        "--allow-large-files",
        action="store_true",
        help="Allow archive files larger than --max-file-mb.",
    )
    export_parser.add_argument("--dry-run", action="store_true")

    restore_parser = subparsers.add_parser("restore", help="Materialize CSV/cache files from the archive.")
    restore_parser.add_argument("--dry-run", action="store_true")
    restore_parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip files that already exist in the live data/results folders.",
    )

    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path.cwd())
    archive_root = args.archive_root if args.archive_root.is_absolute() else repo_root / args.archive_root

    if args.command == "export":
        if args.profile:
            include_paths = _profile_include_paths(repo_root, args.profile)
        else:
            include_paths = [] if args.no_default_paths else _default_include_paths(include_results=not args.no_results)
        include_paths.extend(args.include_path)
        return export_archive(
            repo_root=repo_root,
            archive_root=archive_root,
            include_paths=include_paths,
            compression=args.compression,
            dry_run=args.dry_run,
            max_file_mb=args.max_file_mb,
            allow_large_files=args.allow_large_files,
        )

    if args.command == "restore":
        return restore_archive(
            repo_root=repo_root,
            archive_root=archive_root,
            dry_run=args.dry_run,
            overwrite=not args.no_overwrite,
        )

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
