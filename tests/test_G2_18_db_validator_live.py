import json
import os
from pathlib import Path

import pytest

from scripts.G2_15_user_state_favorites import main

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
@pytest.mark.xdist_group(name="serial_tests")
def test_live_g2_18_db_validator(tmp_path: Path):
    if os.environ.get("G2_18_LIVE") != "1":
        pytest.skip("Skipping live integration test: G2_18_LIVE!=1")

    # Verify v10.9 WAL and SHM sidecars exist and are readable
    wal_path = ROOT / "docker" / "v10.9" / "config" / "data" / "library.db-wal"
    shm_path = ROOT / "docker" / "v10.9" / "config" / "data" / "library.db-shm"

    assert wal_path.exists(), f"WAL file {wal_path} does not exist"
    assert shm_path.exists(), f"SHM file {shm_path} does not exist"
    assert os.access(wal_path, os.R_OK), f"WAL file {wal_path} is not readable"
    assert os.access(shm_path, os.R_OK), f"SHM file {shm_path} is not readable"

    report_path = tmp_path / "g2-18-live-report.json"
    v108_url = os.environ.get("JELLYFIN_V108_URL", "http://localhost:8096")
    v109_url = os.environ.get("JELLYFIN_V109_URL", "http://localhost:8097")

    exit_code = main([
        "--v108-url", v108_url,
        "--v109-url", v109_url,
        "--report", str(report_path),
    ])
    assert exit_code == 0, f"G2-15 main runner failed with exit code {exit_code}"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["parity"] == "equivalent"

    instances = report.get("instances", {})
    assert "v10.8.13" in instances
    assert "v10.9.0" in instances

    for version_key, inst in instances.items():
        assert inst["success"] is True, f"Instance {version_key} failed: {inst.get('error')}"
        validations = inst.get("db_validation", [])
        assert len(validations) >= 4, f"Instance {version_key} missing expected db_validation entries"

        for v in validations:
            assert v["passed"] is True, f"DB validation failed in {version_key} at step {v.get('step')}: {v.get('error')} {v.get('mismatch_codes')}"
            assert v["error"] is None
            assert v["mismatch_codes"] == []

        # Normalized transition evidence is false -> true -> false
        norm_step = (
            "normalize_initial"
            if (inst.get("normalize_initial") or {}).get("action")
            else "initial_state"
        )
        steps_map = {v["step"]: v["db_is_favorite"] for v in validations}
        assert norm_step in steps_map, f"Missing normalized initial step {norm_step} in {version_key}"
        assert "verify_favorite" in steps_map, f"Missing verify_favorite in {version_key}"
        assert "verify_unfavorite" in steps_map, f"Missing verify_unfavorite in {version_key}"
        normalized_transition = [
            steps_map[norm_step],
            steps_map["verify_favorite"],
            steps_map["verify_unfavorite"],
        ]
        assert normalized_transition == [False, True, False], (
            f"Unexpected normalized transition DB values in {version_key}: {normalized_transition}"
        )


        # Cleanup restores original value
        orig_fav = inst["original_state"]["is_favorite"]
        assert inst["cleanup"]["status"] == "passed"
        assert inst["cleanup"]["restored_to"] == orig_fav
