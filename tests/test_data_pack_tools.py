from __future__ import annotations

import tarfile
from pathlib import Path

from da_price_forecasting.scripts.check_data_pack import collect_required_paths
from da_price_forecasting.scripts.create_feature_pack import build_feature_pack
from da_price_forecasting.scripts.operational_archive import (
    _profile_include_paths,
    export_archive,
    main as operational_archive_main,
    restore_archive,
    verify_archive,
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
  dwd_icon_raw_dir: data/raw/dwd_icon_daily
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
    bundle = (
        tmp_path
        / "data"
        / "archive"
        / "operational"
        / "bundles"
        / "data"
        / "processed"
        / "icon_aggregated_c2_run06"
        / "dwd_icon_daily_20260921_06.parquet"
    )
    assert bundle.exists()
    assert verify_archive(tmp_path, tmp_path / "data" / "archive" / "operational") == 0

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
    assert (archive_root / "files" / "data" / "processed" / "values" / "2026-09.parquet").exists()
    assert not (archive_root / "files" / "data" / "processed" / "._values").exists()


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


def test_operational_profile_export_refuses_missing_configured_inputs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config = tmp_path / "configs" / "model.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "kind: demo\nconfig:\n  input_file: data/processed/missing.csv\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "da_price_forecasting.scripts.operational_archive._expand_profile",
        lambda repo_root, profile: [config],
    )

    status = operational_archive_main(
        [
            "--repo-root",
            str(tmp_path),
            "export",
            "--profile",
            "operational",
            "--dry-run",
        ]
    )

    assert status == 4
    assert "Refusing to export incomplete" in capsys.readouterr().err


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

    assert (archive_root / "files" / "data" / "processed" / "first" / "2026-09.parquet").exists()
    assert not (archive_root / "files" / "data" / "processed" / "stale").exists()


def test_operational_archive_bundles_and_restores_one_dwd_issue(tmp_path: Path) -> None:
    issue = (
        tmp_path
        / "data"
        / "processed"
        / "icon_aggregated_c2_run06"
        / "dwd_icon_daily_20260925_06"
    )
    issue.mkdir(parents=True)
    first = issue / "t2m_K_2026092506_raw.csv"
    second = issue / "u10_m_s-1_2026092506_raw.csv"
    first.write_text("timestamp,cluster_0\n2026-09-25T06:00:00Z,280\n", encoding="utf-8")
    second.write_text("timestamp,cluster_0\n2026-09-25T06:00:00Z,4\n", encoding="utf-8")
    archive_root = tmp_path / "data" / "archive" / "operational"

    assert export_archive(tmp_path, archive_root, [Path("data/processed")], "zstd", False, 95.0, False) == 0
    artifacts = list((archive_root / "bundles").rglob("*.parquet"))
    assert len(artifacts) == 1

    first.unlink()
    second.unlink()
    assert restore_archive(tmp_path, archive_root, dry_run=False, overwrite=True) == 0
    assert first.read_text(encoding="utf-8").endswith(",280\n")
    assert second.read_text(encoding="utf-8").endswith(",4\n")


def test_operational_archive_retains_latest_dwd_issue_days(tmp_path: Path, capsys) -> None:
    root = tmp_path / "data" / "processed" / "icon_aggregated_c2_run06"
    for day in ("20260923", "20260924", "20260925"):
        issue = root / f"dwd_icon_daily_{day}_06"
        issue.mkdir(parents=True)
        (issue / f"t2m_K_{day}06_raw.csv").write_text(
            f"timestamp,cluster_0\n{day[:4]}-{day[4:6]}-{day[6:]}T06:00:00Z,280\n",
            encoding="utf-8",
        )
    archive_root = tmp_path / "data" / "archive" / "operational"

    assert export_archive(
        tmp_path,
        archive_root,
        [Path("data/processed")],
        "zstd",
        False,
        95.0,
        False,
        dwd_retention_days=2,
    ) == 0

    bundles = {path.name for path in (archive_root / "bundles").rglob("*.parquet")}
    assert bundles == {
        "dwd_icon_daily_20260924_06.parquet",
        "dwd_icon_daily_20260925_06.parquet",
    }
    assert "Older DWD files omitted: 1" in capsys.readouterr().out


def test_operational_archive_reuses_unchanged_artifacts(tmp_path: Path, capsys) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "values.csv").write_text("timestamp,value\n2026-09-25T00:00:00Z,1\n", encoding="utf-8")
    archive_root = tmp_path / "data" / "archive" / "operational"

    assert export_archive(tmp_path, archive_root, [Path("data/processed")], "zstd", False, 95.0, False) == 0
    capsys.readouterr()
    assert export_archive(tmp_path, archive_root, [Path("data/processed")], "zstd", False, 95.0, False) == 0

    assert "Reused source groups: 1" in capsys.readouterr().out


def test_operational_archive_partitions_history_and_restores_row_order(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    history = processed / "history.csv"
    history.write_text(
        "timestamp,value\n"
        "2026-10-01T00:00:00Z,2\n"
        "2026-09-30T23:00:00Z,1\n",
        encoding="utf-8",
    )
    archive_root = tmp_path / "data" / "archive" / "operational"

    assert export_archive(tmp_path, archive_root, [Path("data/processed")], "zstd", False, 95.0, False) == 0
    parts = archive_root / "files" / "data" / "processed" / "history"
    assert {path.name for path in parts.glob("*.parquet")} == {
        "2026-09.parquet",
        "2026-10.parquet",
    }

    history.unlink()
    assert restore_archive(tmp_path, archive_root, dry_run=False, overwrite=True) == 0
    assert history.read_text(encoding="utf-8").splitlines()[1:] == [
        "2026-10-01T00:00:00Z,2",
        "2026-09-30T23:00:00Z,1",
    ]


def test_operational_archive_verification_detects_damage(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "values.csv").write_text("timestamp,value\n2026-09-25T00:00:00Z,1\n", encoding="utf-8")
    archive_root = tmp_path / "data" / "archive" / "operational"

    assert export_archive(tmp_path, archive_root, [Path("data/processed")], "zstd", False, 95.0, False) == 0
    artifact = archive_root / "files" / "data" / "processed" / "values" / "2026-09.parquet"
    artifact.write_bytes(b"damaged")

    assert verify_archive(tmp_path, archive_root) == 1
