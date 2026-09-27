from __future__ import annotations

import importlib.util
from pathlib import Path


def _migration_module():
    path = Path("deployment/chair-vm/migrate_cutoff_weather_histories.py")
    spec = importlib.util.spec_from_file_location("cutoff_weather_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_quarantines_cross_run_folders_and_run00_feature_cache(tmp_path: Path) -> None:
    migration = _migration_module()
    aggregation = tmp_path / "data/processed/icon_aggregated_c2_run00"
    contaminated = aggregation / "dwd_icon_daily_20260925_00"
    contaminated.mkdir(parents=True)
    (contaminated / "t2m_K_2026092506_raw.csv").write_text("copied run06", encoding="utf-8")
    clean = aggregation / "dwd_icon_daily_20260926_00"
    clean.mkdir()
    (clean / "t2m_K_2026092600_raw.csv").write_text("real run00", encoding="utf-8")
    proxy = tmp_path / "data/processed/renewable_proxy"
    proxy.mkdir(parents=True)
    feature = proxy / "dwd_icon_mastr_wind_c100_run00_regional_renewable_features.csv"
    feature.write_text("mixed provenance", encoding="utf-8")

    candidates = migration.migration_candidates(tmp_path)
    assert contaminated in candidates
    assert feature in candidates
    assert clean not in candidates

    quarantine = migration.migrate(tmp_path, apply=True)
    assert quarantine is not None
    assert not contaminated.exists()
    assert not feature.exists()
    assert clean.exists()
    assert (quarantine / contaminated.relative_to(tmp_path)).exists()
    assert (quarantine / feature.relative_to(tmp_path)).exists()
