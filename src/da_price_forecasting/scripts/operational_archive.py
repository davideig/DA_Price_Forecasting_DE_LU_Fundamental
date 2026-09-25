from __future__ import annotations

import argparse
import hashlib
import json
import re
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
from da_price_forecasting.scripts.check_data_pack import (
    RequiredPath,
    _expand_profile,
    collect_required_paths,
)


ARCHIVE_VERSION = 2
DEFAULT_ARCHIVE_ROOT = Path("data/archive/operational")
DEFAULT_DWD_RETENTION_DAYS = 14
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
    "data/processed/operational_quality",
)

DEFAULT_EXCLUDE_NAMES = {
    ".DS_Store",
    "__pycache__",
}

TABLE_SUFFIXES = {".csv", ".parquet"}
COPY_SUFFIXES = {".json", ".yaml", ".yml", ".txt", ".pkl", ".xlsx"}
DWD_ISSUE_DIRECTORY_RE = re.compile(r"^dwd_icon_daily_(?P<day>\d{8})_(?P<run>\d{2})$")
BUNDLE_SOURCE_COLUMN = "__archive_source_path"
BUNDLE_ROW_COLUMN = "__archive_row_order"


@dataclass(frozen=True)
class ArchivePart:
    archive_path: str
    archive_size_bytes: int
    archive_sha256: str
    row_count: int | None = None


@dataclass(frozen=True)
class ArchiveEntry:
    source_path: str
    archive_path: str
    kind: Literal["csv_parquet", "csv_partitioned", "csv_bundle", "parquet_copy", "file_copy"]
    original_suffix: str
    source_size_bytes: int
    archive_size_bytes: int
    source_sha256: str
    archive_sha256: str
    source_mtime_ns: int = 0
    row_count: int | None = None
    column_count: int | None = None
    csv_header_comments: list[str] | None = None
    csv_blank_first_column: bool = False
    csv_columns: list[str] | None = None
    archive_parts: list[ArchivePart] | None = None


@dataclass(frozen=True)
class ArchiveManifest:
    version: int
    created_at_utc: str
    repo_root: str
    archive_root: str
    include_paths: list[str]
    missing_optional_paths: list[str]
    dwd_retention_days: int
    omitted_dwd_source_files: int
    entries: list[ArchiveEntry]


def _is_excluded(path: Path) -> bool:
    return any(part in DEFAULT_EXCLUDE_NAMES or part.startswith("._") for part in path.parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dwd_issue_directory(path: Path, repo_root: Path) -> tuple[Path, str] | None:
    relative = path.relative_to(repo_root)
    for index, part in enumerate(relative.parts):
        match = DWD_ISSUE_DIRECTORY_RE.fullmatch(part)
        if match is not None:
            return Path(*relative.parts[: index + 1]), match.group("day")
    return None


def _apply_dwd_retention(
    repo_root: Path,
    files: list[Path],
    retention_days: int,
) -> tuple[list[Path], int]:
    if retention_days < 1:
        raise ValueError("DWD retention must be at least one issue day.")

    issue_days_by_root: dict[Path, set[str]] = {}
    issues_by_file: dict[Path, tuple[Path, str]] = {}
    for path in files:
        issue = _dwd_issue_directory(path, repo_root)
        if issue is None:
            continue
        issue_dir, day = issue
        aggregation_root = issue_dir.parent
        issue_days_by_root.setdefault(aggregation_root, set()).add(day)
        issues_by_file[path] = (aggregation_root, day)

    retained_days = {
        root: set(sorted(days)[-retention_days:])
        for root, days in issue_days_by_root.items()
    }
    selected = [
        path
        for path in files
        if path not in issues_by_file
        or issues_by_file[path][1] in retained_days[issues_by_file[path][0]]
    ]
    return selected, len(files) - len(selected)


def _iter_source_files(
    repo_root: Path,
    paths: list[Path],
    archive_root: Path,
    dwd_retention_days: int,
) -> tuple[list[Path], list[str], int]:
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

    selected, omitted = _apply_dwd_retention(repo_root, files, dwd_retention_days)
    return selected, missing, omitted


def _individual_archive_relative(repo_root: Path, source: Path) -> Path:
    relative = Path("files") / source.relative_to(repo_root)
    return relative.with_suffix(".parquet") if source.suffix.lower() == ".csv" else relative


def _csv_archive_relative(repo_root: Path, source: Path, partition: str) -> Path:
    relative = Path("files") / source.relative_to(repo_root).with_suffix("")
    return relative / f"{partition}.parquet"


def _bundle_archive_relative(issue_directory: Path) -> Path:
    return Path("bundles") / issue_directory.parent / f"{issue_directory.name}.parquet"


def _published_archive_label(repo_root: Path, archive_root: Path, relative: Path) -> str:
    path = archive_root / relative
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _entry_parts(entry: ArchiveEntry) -> list[ArchivePart]:
    if entry.archive_parts:
        return entry.archive_parts
    return [
        ArchivePart(
            archive_path=entry.archive_path,
            archive_size_bytes=entry.archive_size_bytes,
            archive_sha256=entry.archive_sha256,
            row_count=entry.row_count,
        )
    ]


def _artifact_relative(repo_root: Path, archive_root: Path, archive_path: str) -> Path:
    path = Path(archive_path)
    absolute = path if path.is_absolute() else repo_root / path
    return absolute.relative_to(archive_root)


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


def _entry_is_unchanged(entry: ArchiveEntry, source: Path) -> bool:
    stat = source.stat()
    return (
        entry.source_size_bytes == stat.st_size
        and entry.source_mtime_ns != 0
        and entry.source_mtime_ns == stat.st_mtime_ns
    )


def _copy_existing_artifact(archive_root: Path, staging_root: Path, relative: Path) -> bool:
    source = archive_root / relative
    if not source.exists():
        return False
    target = staging_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def _entry_for_artifact(
    *,
    repo_root: Path,
    archive_root: Path,
    source: Path,
    artifact: Path,
    archive_relative: Path,
    kind: Literal["csv_parquet", "csv_partitioned", "csv_bundle", "parquet_copy", "file_copy"],
    row_count: int | None = None,
    column_count: int | None = None,
    comments: list[str] | None = None,
    blank_first_column: bool = False,
    csv_columns: list[str] | None = None,
) -> ArchiveEntry:
    stat = source.stat()
    archive_path = _published_archive_label(repo_root, archive_root, archive_relative)
    archive_size = artifact.stat().st_size
    archive_sha = _sha256(artifact)
    return ArchiveEntry(
        source_path=source.relative_to(repo_root).as_posix(),
        archive_path=archive_path,
        kind=kind,
        original_suffix=source.suffix.lower(),
        source_size_bytes=stat.st_size,
        archive_size_bytes=archive_size,
        source_sha256=_sha256(source),
        archive_sha256=archive_sha,
        source_mtime_ns=stat.st_mtime_ns,
        row_count=row_count,
        column_count=column_count,
        csv_header_comments=comments,
        csv_blank_first_column=blank_first_column,
        csv_columns=csv_columns,
        archive_parts=[ArchivePart(archive_path, archive_size, archive_sha, row_count)],
    )


def _timestamp_partitions(df: pd.DataFrame) -> dict[str, pd.Series]:
    if df.empty:
        return {"empty": pd.Series([], index=df.index, dtype=bool)}

    normalized = {str(column).lower(): column for column in df.columns}
    preferred = ("timestamp", "datetime", "valid_time", "forecast_time", "time", "date")
    candidates = [normalized[name] for name in preferred if name in normalized]
    candidates.extend(
        column
        for column in df.columns
        if column not in candidates and ("time" in str(column).lower() or "date" in str(column).lower())
    )
    for column in candidates:
        parsed = pd.to_datetime(df[column], errors="coerce", utc=True)
        if int(parsed.notna().sum()) < max(1, int(len(df) * 0.8)):
            continue
        labels = parsed.dt.strftime("%Y-%m").fillna("undated")
        return {label: labels == label for label in sorted(labels.unique())}
    return {"all": pd.Series(True, index=df.index)}


def _export_individual_file(
    repo_root: Path,
    archive_root: Path,
    staging_root: Path,
    source: Path,
    compression: str,
) -> ArchiveEntry:
    relative = _individual_archive_relative(repo_root, source)
    artifact = staging_root / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()

    if suffix == ".csv":
        df, comments, blank_first_column = _read_csv_as_table(source)
        if BUNDLE_ROW_COLUMN in df.columns:
            raise ValueError(f"Reserved archive column present in {source}")
        parts: list[ArchivePart] = []
        for partition, mask in _timestamp_partitions(df).items():
            partition_relative = _csv_archive_relative(repo_root, source, partition)
            partition_artifact = staging_root / partition_relative
            partition_artifact.parent.mkdir(parents=True, exist_ok=True)
            frame = df.loc[mask].copy()
            frame[BUNDLE_ROW_COLUMN] = frame.index
            frame.to_parquet(partition_artifact, index=False, compression=compression)
            parts.append(
                ArchivePart(
                    archive_path=_published_archive_label(repo_root, archive_root, partition_relative),
                    archive_size_bytes=partition_artifact.stat().st_size,
                    archive_sha256=_sha256(partition_artifact),
                    row_count=len(frame),
                )
            )
        source_stat = source.stat()
        combined_sha = hashlib.sha256("".join(part.archive_sha256 for part in parts).encode("ascii")).hexdigest()
        return ArchiveEntry(
            source_path=source.relative_to(repo_root).as_posix(),
            archive_path=parts[0].archive_path,
            kind="csv_partitioned",
            original_suffix=".csv",
            source_size_bytes=source_stat.st_size,
            archive_size_bytes=sum(part.archive_size_bytes for part in parts),
            source_sha256=_sha256(source),
            archive_sha256=combined_sha,
            source_mtime_ns=source_stat.st_mtime_ns,
            row_count=len(df),
            column_count=len(df.columns),
            csv_header_comments=comments,
            csv_blank_first_column=blank_first_column,
            csv_columns=[str(column) for column in df.columns],
            archive_parts=parts,
        )

    shutil.copy2(source, artifact)
    return _entry_for_artifact(
        repo_root=repo_root,
        archive_root=archive_root,
        source=source,
        artifact=artifact,
        archive_relative=relative,
        kind="parquet_copy" if suffix == ".parquet" else "file_copy",
    )


def _export_dwd_bundle(
    repo_root: Path,
    archive_root: Path,
    staging_root: Path,
    issue_directory: Path,
    sources: list[Path],
    compression: str,
) -> list[ArchiveEntry]:
    relative = _bundle_archive_relative(issue_directory)
    artifact = staging_root / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    metadata: list[tuple[Path, list[str], bool, list[str], int]] = []

    for source in sorted(sources):
        df, comments, blank_first_column = _read_csv_as_table(source)
        if BUNDLE_SOURCE_COLUMN in df.columns or BUNDLE_ROW_COLUMN in df.columns:
            raise ValueError(f"Reserved archive column present in {source}")
        columns = [str(column) for column in df.columns]
        frame = df.copy()
        frame[BUNDLE_SOURCE_COLUMN] = source.relative_to(repo_root).as_posix()
        frame[BUNDLE_ROW_COLUMN] = range(len(frame))
        frames.append(frame)
        metadata.append((source, comments, blank_first_column, columns, len(frame)))

    bundle = pd.concat(frames, ignore_index=True, sort=False)
    bundle.to_parquet(artifact, index=False, compression=compression)
    artifact_size = artifact.stat().st_size
    artifact_sha = _sha256(artifact)
    archive_path = _published_archive_label(repo_root, archive_root, relative)

    entries: list[ArchiveEntry] = []
    for source, comments, blank_first_column, columns, row_count in metadata:
        stat = source.stat()
        entries.append(
            ArchiveEntry(
                source_path=source.relative_to(repo_root).as_posix(),
                archive_path=archive_path,
                kind="csv_bundle",
                original_suffix=".csv",
                source_size_bytes=stat.st_size,
                archive_size_bytes=artifact_size,
                source_sha256=_sha256(source),
                archive_sha256=artifact_sha,
                source_mtime_ns=stat.st_mtime_ns,
                row_count=row_count,
                column_count=len(columns),
                csv_header_comments=comments,
                csv_blank_first_column=blank_first_column,
                csv_columns=columns,
                archive_parts=[ArchivePart(archive_path, artifact_size, artifact_sha, None)],
            )
        )
    return entries


def _load_previous_entries(repo_root: Path, archive_root: Path) -> dict[str, ArchiveEntry]:
    try:
        manifest = _load_manifest(repo_root, archive_root)
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return {}
    if manifest.version != ARCHIVE_VERSION:
        return {}
    return {entry.source_path: entry for entry in manifest.entries}


def _reuse_individual_entry(
    *,
    repo_root: Path,
    archive_root: Path,
    staging_root: Path,
    source: Path,
    previous: ArchiveEntry | None,
) -> ArchiveEntry | None:
    if previous is None:
        return None
    if not _entry_is_unchanged(previous, source):
        return None
    for part in _entry_parts(previous):
        relative = _artifact_relative(repo_root, archive_root, part.archive_path)
        if not _copy_existing_artifact(archive_root, staging_root, relative):
            return None
    return previous


def _reuse_bundle_entries(
    *,
    repo_root: Path,
    archive_root: Path,
    staging_root: Path,
    issue_directory: Path,
    sources: list[Path],
    previous_entries: dict[str, ArchiveEntry],
) -> list[ArchiveEntry] | None:
    relative = _bundle_archive_relative(issue_directory)
    expected_path = _published_archive_label(repo_root, archive_root, relative)
    ordered_sources = sorted(sources)
    previous = [previous_entries.get(source.relative_to(repo_root).as_posix()) for source in ordered_sources]
    if any(entry is None for entry in previous):
        return None
    typed = [entry for entry in previous if entry is not None]
    if any(entry.kind != "csv_bundle" or entry.archive_path != expected_path for entry in typed):
        return None
    if any(not _entry_is_unchanged(entry, source) for entry, source in zip(typed, ordered_sources, strict=True)):
        return None
    for part in _entry_parts(typed[0]):
        part_relative = _artifact_relative(repo_root, archive_root, part.archive_path)
        if not _copy_existing_artifact(archive_root, staging_root, part_relative):
            return None
    return typed


def export_archive(
    repo_root: Path,
    archive_root: Path,
    include_paths: list[Path],
    compression: str,
    dry_run: bool,
    max_file_mb: float,
    allow_large_files: bool,
    dwd_retention_days: int = DEFAULT_DWD_RETENTION_DAYS,
) -> int:
    sources, missing, omitted = _iter_source_files(
        repo_root,
        include_paths,
        archive_root=archive_root,
        dwd_retention_days=dwd_retention_days,
    )
    bundle_groups: dict[Path, list[Path]] = {}
    individual_sources: list[Path] = []
    for source in sources:
        issue = _dwd_issue_directory(source, repo_root)
        if issue is not None and source.suffix.lower() == ".csv":
            bundle_groups.setdefault(issue[0], []).append(source)
        else:
            individual_sources.append(source)

    source_group_count = len(bundle_groups) + len(individual_sources)
    print(f"Repo root:               {repo_root}")
    print(f"Archive root:            {archive_root}")
    print(f"Selected source files:   {len(sources):,}")
    print(f"Source groups:           {source_group_count:,}")
    print(f"DWD retention:           {dwd_retention_days} latest issue days per aggregation")
    print(f"Older DWD files omitted: {omitted:,}")
    if missing:
        print("")
        print("Missing optional paths:")
        for path in missing:
            print(f"  - {path}")

    if dry_run:
        total_size = sum(path.stat().st_size for path in sources)
        print("")
        print(f"Dry run only. Selected source size: {total_size / 1024 / 1024:.1f} MiB")
        return 0

    archive_root.parent.mkdir(parents=True, exist_ok=True)
    previous_entries = _load_previous_entries(repo_root, archive_root)
    staging_root = Path(tempfile.mkdtemp(prefix=f".{archive_root.name}.staging-", dir=archive_root.parent))
    reused_artifacts = 0
    try:
        entries: list[ArchiveEntry] = []
        for issue_directory, group_sources in sorted(bundle_groups.items()):
            reused = _reuse_bundle_entries(
                repo_root=repo_root,
                archive_root=archive_root,
                staging_root=staging_root,
                issue_directory=issue_directory,
                sources=group_sources,
                previous_entries=previous_entries,
            )
            if reused is not None:
                entries.extend(reused)
                reused_artifacts += 1
            else:
                entries.extend(
                    _export_dwd_bundle(
                        repo_root,
                        archive_root,
                        staging_root,
                        issue_directory,
                        group_sources,
                        compression,
                    )
                )

        for source in sorted(individual_sources):
            source_label = source.relative_to(repo_root).as_posix()
            reused = _reuse_individual_entry(
                repo_root=repo_root,
                archive_root=archive_root,
                staging_root=staging_root,
                source=source,
                previous=previous_entries.get(source_label),
            )
            if reused is not None:
                entries.append(reused)
                reused_artifacts += 1
            else:
                entries.append(
                    _export_individual_file(
                        repo_root=repo_root,
                        archive_root=archive_root,
                        staging_root=staging_root,
                        source=source,
                        compression=compression,
                    )
                )

        entries.sort(key=lambda entry: entry.source_path)
        artifacts: dict[str, ArchivePart] = {}
        for entry in entries:
            for part in _entry_parts(entry):
                existing = artifacts.setdefault(part.archive_path, part)
                if existing.archive_sha256 != part.archive_sha256:
                    raise ValueError(f"Conflicting checksums for shared artifact {part.archive_path}")
        large_entries = [
            part
            for part in artifacts.values()
            if part.archive_size_bytes > max_file_mb * 1024 * 1024
        ]
        if large_entries and not allow_large_files:
            print("")
            print(f"Refusing to finish because archive artifact(s) exceed {max_file_mb:.1f} MiB:")
            for part in large_entries:
                print(f"  - {part.archive_path}: {part.archive_size_bytes / 1024 / 1024:.1f} MiB")
            print("Use a narrower archive profile or --allow-large-files after checking remote limits.")
            return 3

        try:
            archive_root_label = archive_root.relative_to(repo_root).as_posix()
        except ValueError:
            archive_root_label = archive_root.as_posix()
        manifest = ArchiveManifest(
            version=ARCHIVE_VERSION,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            repo_root=".",
            archive_root=archive_root_label,
            include_paths=[path.as_posix() for path in include_paths],
            missing_optional_paths=missing,
            dwd_retention_days=dwd_retention_days,
            omitted_dwd_source_files=omitted,
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
    archive_size = sum(part.archive_size_bytes for part in artifacts.values())
    print("")
    print(f"Archived sources:  {len(entries):,}")
    print(f"Archive artifacts: {len(artifacts):,}")
    print(f"Reused source groups: {reused_artifacts:,}")
    print(f"Source size:       {source_size / 1024 / 1024:.1f} MiB")
    print(f"Archive size:      {archive_size / 1024 / 1024:.1f} MiB")
    try:
        manifest_label = (archive_root / MANIFEST_NAME).relative_to(repo_root).as_posix()
    except ValueError:
        manifest_label = (archive_root / MANIFEST_NAME).as_posix()
    print(f"Manifest:          {manifest_label}")
    return 0


def _load_manifest(repo_root: Path, archive_root: Path) -> ArchiveManifest:
    del repo_root
    manifest_path = archive_root / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"Operational archive manifest not found: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries: list[ArchiveEntry] = []
    for raw_entry in payload["entries"]:
        entry = dict(raw_entry)
        entry.setdefault("source_mtime_ns", 0)
        entry.setdefault("csv_columns", None)
        raw_parts = entry.get("archive_parts")
        entry["archive_parts"] = (
            [ArchivePart(**part) for part in raw_parts]
            if raw_parts
            else None
        )
        entries.append(ArchiveEntry(**entry))
    return ArchiveManifest(
        version=int(payload["version"]),
        created_at_utc=str(payload["created_at_utc"]),
        repo_root=str(payload["repo_root"]),
        archive_root=str(payload["archive_root"]),
        include_paths=list(payload["include_paths"]),
        missing_optional_paths=list(payload.get("missing_optional_paths", [])),
        dwd_retention_days=int(payload.get("dwd_retention_days", 0)),
        omitted_dwd_source_files=int(payload.get("omitted_dwd_source_files", 0)),
        entries=entries,
    )


def verify_archive(repo_root: Path, archive_root: Path) -> int:
    try:
        manifest = _load_manifest(repo_root, archive_root)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 2
    if manifest.version not in {1, ARCHIVE_VERSION}:
        print(f"Unsupported operational archive version: {manifest.version}", file=sys.stderr)
        return 2

    expected: dict[str, tuple[int, str]] = {}
    errors: list[str] = []
    for entry in manifest.entries:
        for part in _entry_parts(entry):
            marker = (part.archive_size_bytes, part.archive_sha256)
            previous = expected.setdefault(part.archive_path, marker)
            if previous != marker:
                errors.append(f"Conflicting manifest metadata: {part.archive_path}")

    for archive_path, (expected_size, expected_sha) in sorted(expected.items()):
        path = Path(archive_path)
        path = path if path.is_absolute() else repo_root / path
        if not path.exists():
            errors.append(f"Missing artifact: {archive_path}")
            continue
        if path.stat().st_size != expected_size:
            errors.append(f"Size mismatch: {archive_path}")
            continue
        if _sha256(path) != expected_sha:
            errors.append(f"Checksum mismatch: {archive_path}")

    print(f"Manifest version:  {manifest.version}")
    print(f"Archived sources:  {len(manifest.entries):,}")
    print(f"Archive artifacts: {len(expected):,}")
    if errors:
        print("")
        print("Archive verification failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Archive verification passed.")
    return 0


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
    if manifest.version not in {1, ARCHIVE_VERSION}:
        print(f"Unsupported operational archive version: {manifest.version}", file=sys.stderr)
        return 2
    restored = 0
    skipped = 0
    print(f"Repo root:    {repo_root}")
    print(f"Archive root: {archive_root}")
    print(f"Created UTC:  {manifest.created_at_utc}")
    print(f"Entries:      {len(manifest.entries):,}")

    loaded_bundle_path: Path | None = None
    loaded_bundle: pd.DataFrame | None = None
    for entry in manifest.entries:
        source_path = repo_root / entry.source_path
        archive_paths: list[Path] = []
        for part in _entry_parts(entry):
            archive_path = Path(part.archive_path)
            archive_path = archive_path if archive_path.is_absolute() else repo_root / archive_path
            if not archive_path.exists():
                raise FileNotFoundError(f"Archived file missing: {archive_path}")
            archive_paths.append(archive_path)
        if source_path.exists() and not overwrite:
            skipped += 1
            continue
        if dry_run:
            restored += 1
            continue
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if entry.kind == "csv_bundle":
            archive_path = archive_paths[0]
            if loaded_bundle_path != archive_path:
                loaded_bundle = pd.read_parquet(archive_path)
                loaded_bundle_path = archive_path
            assert loaded_bundle is not None
            frame = loaded_bundle.loc[loaded_bundle[BUNDLE_SOURCE_COLUMN] == entry.source_path].copy()
            frame.sort_values(BUNDLE_ROW_COLUMN, inplace=True)
            columns = entry.csv_columns or [
                column
                for column in frame.columns
                if column not in {BUNDLE_SOURCE_COLUMN, BUNDLE_ROW_COLUMN}
            ]
            frame = frame.loc[:, columns]
            _write_csv_from_table(
                frame,
                source_path,
                header_comments=entry.csv_header_comments,
                blank_first_column=entry.csv_blank_first_column,
            )
        elif entry.kind == "csv_partitioned":
            frames = [pd.read_parquet(path) for path in archive_paths]
            df = pd.concat(frames, ignore_index=True)
            df.sort_values(BUNDLE_ROW_COLUMN, inplace=True)
            if entry.csv_columns:
                df = df.loc[:, entry.csv_columns]
            else:
                df.drop(columns=[BUNDLE_ROW_COLUMN], inplace=True)
            _write_csv_from_table(
                df,
                source_path,
                header_comments=entry.csv_header_comments,
                blank_first_column=entry.csv_blank_first_column,
            )
        elif entry.kind == "csv_parquet":
            df = pd.read_parquet(archive_paths[0])
            if entry.csv_columns:
                df = df.loc[:, entry.csv_columns]
            _write_csv_from_table(
                df,
                source_path,
                header_comments=entry.csv_header_comments,
                blank_first_column=entry.csv_blank_first_column,
            )
        else:
            shutil.copy2(archive_paths[0], source_path)
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


def _profile_required_paths(repo_root: Path, profile: str) -> list[RequiredPath]:
    configs = _expand_profile(repo_root, profile)
    return collect_required_paths(repo_root, configs)


def _profile_include_paths(repo_root: Path, profile: str) -> list[Path]:
    required = _profile_required_paths(repo_root, profile)
    paths = [Path(path) for path in PROFILE_BASE_INCLUDE_PATHS]
    paths.extend(Path(item.path) for item in required if not Path(item.path).is_absolute())
    return list(dict.fromkeys(paths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export, verify, or restore the Git-tracked operational data archive."
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
        "--dwd-retention-days",
        type=int,
        default=DEFAULT_DWD_RETENTION_DAYS,
        help="Keep the latest N DWD issue days per aggregation; processed feature histories remain complete.",
    )
    export_parser.add_argument(
        "--max-file-mb",
        type=float,
        default=95.0,
        help="Refuse export if any archive artifact exceeds this size unless --allow-large-files is set.",
    )
    export_parser.add_argument(
        "--allow-large-files",
        action="store_true",
        help="Allow archive artifacts larger than --max-file-mb.",
    )
    export_parser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("verify", help="Verify archive artifacts against manifest checksums.")

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
            required = _profile_required_paths(repo_root, args.profile)
            missing_required = [item for item in required if not item.exists]
            if missing_required:
                print(
                    f"Refusing to export incomplete {args.profile!r} profile; "
                    f"{len(missing_required)} configured input(s) are missing:",
                    file=sys.stderr,
                )
                for item in missing_required:
                    print(f"  - {item.path} ({item.config})", file=sys.stderr)
                return 4
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
            dwd_retention_days=args.dwd_retention_days,
        )

    if args.command == "verify":
        return verify_archive(repo_root=repo_root, archive_root=archive_root)

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
