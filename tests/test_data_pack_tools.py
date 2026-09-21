from __future__ import annotations

import tarfile
from pathlib import Path

from da_price_forecasting.scripts.check_data_pack import collect_required_paths
from da_price_forecasting.scripts.create_feature_pack import build_feature_pack


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
