"""Copy a clean, reusable release tree from the research/workbench repo.

The exporter is intentionally copy-only:

- it never moves files,
- it never deletes files from the source repository,
- it defaults to a dry run,
- it refuses to write into a non-empty destination.

Usage:

    python scripts/export_release_repo.py ../DA_Price_Forecasting_Pipeline_DE_LU_release
    python scripts/export_release_repo.py ../DA_Price_Forecasting_Pipeline_DE_LU_release --execute
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CopyItem:
    source: Path
    destination: Path
    is_dir: bool


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _matches_exclude(relative_path: Path, patterns: list[str]) -> bool:
    rel = relative_path.as_posix()
    parts = relative_path.parts
    for pattern in patterns:
        if rel == pattern or fnmatch.fnmatch(rel, pattern):
            return True
        if pattern in parts:
            return True
    return False


def _load_manifest(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _collect_items(repo_root: Path, destination_root: Path, manifest: dict) -> list[CopyItem]:
    include = manifest.get("include", {})
    paths = include.get("paths", [])
    optional_paths = set(include.get("optional_paths", []))
    missing: list[str] = []
    items: list[CopyItem] = []

    for raw in [*paths, *sorted(optional_paths)]:
        relative = Path(raw)
        source = repo_root / relative
        if not source.exists():
            if raw in optional_paths:
                continue
            missing.append(raw)
            continue
        items.append(
            CopyItem(
                source=source,
                destination=destination_root / relative,
                is_dir=source.is_dir(),
            )
        )

    if missing:
        missing_text = "\n".join(f"  - {item}" for item in missing)
        raise FileNotFoundError(f"Release manifest references missing paths:\n{missing_text}")

    return items


def _copy_filtered_tree(source: Path, destination: Path, repo_root: Path, exclude_patterns: list[str]) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(repo_root)
        if _matches_exclude(relative, exclude_patterns):
            continue
        target = destination / path.relative_to(source)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _copy_items(items: list[CopyItem], repo_root: Path, exclude_patterns: list[str]) -> None:
    for item in items:
        relative = item.source.relative_to(repo_root)
        if _matches_exclude(relative, exclude_patterns):
            continue
        if item.is_dir:
            item.destination.mkdir(parents=True, exist_ok=True)
            _copy_filtered_tree(item.source, item.destination, repo_root, exclude_patterns)
        else:
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source, item.destination)


def _print_plan(items: list[CopyItem], repo_root: Path, destination_root: Path) -> None:
    print(f"Source:      {repo_root}")
    print(f"Destination: {destination_root}")
    print("")
    print("Release copy plan:")
    for item in items:
        kind = "dir " if item.is_dir else "file"
        print(f"  {kind}  {item.source.relative_to(repo_root)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="Destination directory for the clean release copy.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("release_manifest.toml"),
        help="Release manifest path relative to the repo root.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually copy files. Without this flag, the command only prints the plan.",
    )
    parser.add_argument(
        "--allow-inside-source",
        action="store_true",
        help="Allow destination to be inside the source repo. Not recommended.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = repo_root / manifest_path
    manifest = _load_manifest(manifest_path)

    destination_root = args.destination.expanduser()
    if not destination_root.is_absolute():
        destination_root = (Path.cwd() / destination_root).resolve()
    else:
        destination_root = destination_root.resolve()

    if destination_root == repo_root:
        print("Refusing to export into the source repository root.", file=sys.stderr)
        return 2
    if _is_relative_to(destination_root, repo_root) and not args.allow_inside_source:
        print(
            "Refusing to export inside the source repository. "
            "Choose a sibling directory or pass --allow-inside-source.",
            file=sys.stderr,
        )
        return 2
    if destination_root.exists() and any(destination_root.iterdir()):
        print("Refusing to write into a non-empty destination directory.", file=sys.stderr)
        return 2

    exclude_patterns = manifest.get("exclude", {}).get("patterns", [])
    items = _collect_items(repo_root, destination_root, manifest)
    _print_plan(items, repo_root, destination_root)

    if not args.execute:
        print("")
        print("Dry run only. Re-run with --execute to copy files.")
        return 0

    destination_root.mkdir(parents=True, exist_ok=True)
    _copy_items(items, repo_root, exclude_patterns)
    print("")
    print("Release export complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
