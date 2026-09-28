from __future__ import annotations

from pathlib import Path

import yaml


def test_cutoff_schedule_matches_operational_spec() -> None:
    script = Path("deployment/chair-vm/register_cutoff_tasks.ps1").read_text(encoding="utf-8")
    expected = {
        "dwd-run03-update": "06:21",
        "renewable-run03-features-update": "06:24",
        "price-cutoff-0700-submit": "06:40",
        "price-cutoff-0800-submit": "07:40",
        "reserve-publication-poll": "07:55",
        "price-cutoff-0900-submit": "08:40",
        "dwd-run06-cutoff-update": "09:23",
        "renewable-cutoff-features-update": "09:38",
        "price-cutoff-1000-submit": "09:40",
        "price-cutoff-1100-submit": "10:40",
        "price-cutoff-1200-submit": "11:40",
    }
    for job, time in expected.items():
        assert f'Name = "{job}"; Time = "{time}"; Job = "{job}"' in script
    jobs_block = script.split("$jobs = @(", 1)[1].split(")", 1)[0]
    assert "dwd-run00-update" not in jobs_block
    assert "renewable-run00-features-update" not in jobs_block


def test_runner_has_no_cross_run_bootstrap_or_multi_provider_wind() -> None:
    script = Path("deployment/chair-vm/run_scheduled_job.sh").read_text(encoding="utf-8")
    assert "bootstrap_run00" not in script
    assert "Seeded" not in script
    assert "ecmwf_ifs025" not in script
    assert "arpege_europe" not in script
    assert "ukmo_seamless" not in script
    assert "gfs_single" not in script
    assert "icon_eu" not in script
    assert "dmi_harmonie" not in script
    assert "wind_open_meteo_features_run${run}.yaml" in script
    assert "backfill-operational-reserve-market" in script
    assert "for run in 03 06" in script
    assert 'backfill_end - 180 days' in script
    assert '--set "open_meteo_start_date=$backfill_start"' in script
    assert "wait_for_job_lock renewable-run03-features-update 3600" in script


def test_general_schedule_removes_duplicate_submission_jobs() -> None:
    script = Path("deployment/chair-vm/register_tasks.ps1").read_text(encoding="utf-8")
    jobs_block = script.split("$jobs = @(", 1)[1].split(")", 1)[0]
    assert "submit" not in jobs_block
    assert "dwd-wind-update" not in jobs_block
    assert "dwd-solar-update" not in jobs_block
    assert "repair-operational-data" in jobs_block
    assert "commit-operational-archive" in jobs_block
    assert "backup-operational-artifacts" in jobs_block


def test_all_deployment_preprocessing_uses_fixed_static_snapshots() -> None:
    configs = Path("configs/deployment/cutoff_preprocessing").glob("*.yaml")
    cluster_paths: dict[str, set[str]] = {"solar": set(), "wind": set(), "load": set()}
    capacity_paths: set[str] = set()

    for config_path in configs:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))["config"]
        if "solar" in config_path.name:
            cluster_paths["solar"].add(
                payload.get("cluster_file") or payload.get("dwd_icon_aggregation_cluster_output_file")
            )
        elif "wind" in config_path.name:
            cluster_paths["wind"].add(
                payload.get("cluster_file") or payload.get("dwd_icon_aggregation_cluster_output_file")
            )
        elif "load_open_meteo" in config_path.name:
            cluster_paths["load"].add(payload["open_meteo_cluster_file"])
        capacity_path = payload.get("capacity_file") or payload.get("dwd_icon_aggregation_capacity_file")
        if capacity_path:
            capacity_paths.add(capacity_path)

    assert cluster_paths["solar"] == {"data/clustering/icon_d2_mastr_solar_tso_c25.csv"}
    assert cluster_paths["wind"] == {
        "data/clustering/icon_d2_mastr_wind_c100.csv",
        "data/clustering/icon_d2_clustering_c25.parquet",
    }
    assert cluster_paths["load"] == {"data/clustering/icon_d2_clustering_c25.parquet"}
    assert capacity_paths == {"data/raw/renewable_capacity/installed_capacity.csv"}
