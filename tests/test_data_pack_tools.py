from __future__ import annotations

import tarfile
from pathlib import Path

from da_price_forecasting.scripts.check_data_pack import collect_required_paths
from da_price_forecasting.scripts.create_feature_pack import build_feature_pack
from da_price_forecasting.scripts.operational_archive import (
    _profile_include_paths,
    export_archive,
    restore_archive,
)


def test_check_data_pack_collects_inputs_but_not_outputs(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    existing = tmp_path / "data" / "processed" / "input.csv"
    existing.parent.mkdir(parents=True)
    existing.write_text("x\n", encoding="utf-8")
    config.write_text(
        """
kind: demo
config:
  actual_load_file: data/processed/input.csv
  extra_renewable_proxy_files:
    - data/processed/missing.csv
  export_dir: results/demo
  open_meteo_base_url: https://example.test
""".strip(),
        encoding="utf-8",
    )

    required = collect_required_paths(tmp_path, [config])

    assert {(item.key, item.path, item.exists) for item in required} == {
        ("actual_load_file", "data/processed/input.csv", True),
        ("extra_renewable_proxy_files", "data/processed/missing.csv", False),
    }


def test_create_feature_pack_includes_processed_files(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed" / "load_forecast"
    processed.mkdir(parents=True)
    (processed / "actual_load.csv").write_text("timestamp,load\n", encoding="utf-8")
    shapefile = tmp_path / "data" / "shapefile"
    shapefile.mkdir(parents=True)
    (shapefile / "ne_10m_admin_0_countries.shp").write_text("placeholder\n", encoding="utf-8")
    output = tmp_path / "pack.tar.gz"

    status = build_feature_pack(
        repo_root=tmp_path,
        output_path=output,
        include_results=False,
        extra_paths=[],
        dry_run=False,
    )

    assert status == 0
    with tarfile.open(output, mode="r:gz") as archive:
        names = set(archive.getnames())
    assert "DATA_PACK_MANIFEST.json" in names
    assert "data/processed/load_forecast/actual_load.csv" in names
    assert "data/shapefile/ne_10m_admin_0_countries.shp" in names


def test_operational_archive_round_trips_csv_with_header_comments(tmp_path: Path) -> None:
    source = tmp_path / "data" / "processed" / "icon_aggregated_c2_run06" / "dwd_icon_daily_20260921_06"
    source.mkdir(parents=True)
    csv_path = source / "ASWDIR_S_W_m-2_2026092106_instantaneous.csv"
    csv_path.write_text(
        "\n".join(
            [
                "# Folder: aswdir_s",
                "# Variable: ASWDIR_S",
                "timestamp,cluster_0,cluster_1",
                "2026-09-22T00:00:00+00:00,1.5,2.5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    status = export_archive(
        repo_root=tmp_path,
        archive_root=tmp_path / "data" / "archive" / "operational",
        include_paths=[Path("data/processed")],
        compression="zstd",
        dry_run=False,
        max_file_mb=95.0,
        allow_large_files=False,
    )
    assert status == 0
    assert (tmp_path / "data" / "archive" / "operational" / "manifest.json").exists()
    assert (
        tmp_path
        / "data"
        / "archive"
        / "operational"
        / "data"
        / "processed"
        / "icon_aggregated_c2_run06"
        / "dwd_icon_daily_20260921_06"
        / "ASWDIR_S_W_m-2_2026092106_instantaneous.parquet"
    ).exists()

    csv_path.unlink()

    status = restore_archive(
        repo_root=tmp_path,
        archive_root=tmp_path / "data" / "archive" / "operational",
        dry_run=False,
        overwrite=True,
    )

    assert status == 0
    restored = csv_path.read_text(encoding="utf-8")
    assert "# Variable: ASWDIR_S" in restored
    assert "timestamp,cluster_0,cluster_1" in restored
    assert "2026-09-22T00:00:00+00:00,1.5,2.5" in restored


def test_operational_archive_ignores_appledouble_metadata(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "values.csv").write_text("timestamp,value\n2026-09-25T00:00:00Z,1\n", encoding="utf-8")
    (processed / "._values.csv").write_bytes(b"\x00\x05\x16\x07\xa3appledouble")

    archive_root = tmp_path / "data" / "archive" / "operational"
    status = export_archive(
        repo_root=tmp_path,
        archive_root=archive_root,
        include_paths=[Path("data/processed")],
        compression="zstd",
        dry_run=False,
        max_file_mb=95.0,
        allow_large_files=False,
    )

    assert status == 0
    assert (archive_root / "data" / "processed" / "values.parquet").exists()
    assert not (archive_root / "data" / "processed" / "._values.parquet").exists()


def test_operational_archive_restore_explains_missing_manifest(tmp_path: Path, capsys) -> None:
    status = restore_archive(
        repo_root=tmp_path,
        archive_root=tmp_path / "data" / "archive" / "operational",
        dry_run=False,
        overwrite=True,
    )

    assert status == 2
    assert "Operational archive is not available" in capsys.readouterr().err


def test_operational_archive_profile_uses_required_inputs_only(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "configs" / "model.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "kind: demo\nconfig:\n  input_file: data/processed/needed.csv\n  output_file: data/processed/generated.csv\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "da_price_forecasting.scripts.operational_archive._expand_profile",
        lambda repo_root, profile: [config],
    )

    paths = _profile_include_paths(tmp_path, "operational")

    assert Path("data/processed/needed.csv") in paths
    assert Path("data/processed/generated.csv") not in paths
    assert Path("data/processed") not in paths
    assert Path("data/processed/operational_quality") in paths


def test_operational_archive_replaces_stale_entries(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    first = processed / "first.csv"
    stale = processed / "stale.csv"
    first.write_text("timestamp,value\n2026-09-23T00:00:00Z,1\n", encoding="utf-8")
    stale.write_text("timestamp,value\n2026-09-23T00:00:00Z,2\n", encoding="utf-8")
    archive_root = tmp_path / "data" / "archive" / "operational"

    assert export_archive(tmp_path, archive_root, [Path("data/processed")], "zstd", False, 95.0, False) == 0
    stale.unlink()
    assert export_archive(tmp_path, archive_root, [Path("data/processed")], "zstd", False, 95.0, False) == 0

    assert (archive_root / "data" / "processed" / "first.parquet").exists()
    assert not (archive_root / "data" / "processed" / "stale.parquet").exists()
