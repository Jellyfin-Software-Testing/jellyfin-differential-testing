import json
import os
from pathlib import Path
import subprocess
import time

import pytest
import requests

from scripts import G2_15_user_state_favorites as runner

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker" / "docker-compose.yml"


def _compose(*args: str) -> None:
    context_host = subprocess.run(
        ["docker", "context", "inspect", "default", "--format", "{{.Endpoints.docker.Host}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not context_host.startswith("unix://"):
        raise RuntimeError(f"Refusing to manage Jellyfin through non-local Docker context: {context_host}")

    working_dir = subprocess.run(
        [
            "docker", "--context", "default", "inspect", "--format",
            '{{index .Config.Labels "com.docker.compose.project.working_dir"}}',
            "jellyfin-v10.8.13-test",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if Path(working_dir).resolve() != COMPOSE_FILE.parent.resolve():
        raise RuntimeError(f"Refusing to manage Jellyfin container from Compose directory {working_dir}")

    subprocess.run(
        [
            "docker", "--context", "default", "compose",
            "--project-directory", str(COMPOSE_FILE.parent),
            "--project-name", "docker", "-f", str(COMPOSE_FILE), *args,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _wait_until_healthy(url: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{url.rstrip('/')}/health", timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise AssertionError(f"Jellyfin did not become healthy at {url}")


@pytest.mark.integration
@pytest.mark.xdist_group(name="serial_tests")
def test_live_g2_18_db_validator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if os.environ.get("G2_18_LIVE") != "1":
        pytest.skip("Skipping live integration test: G2_18_LIVE!=1")

    # v10.9 must be readable live with WAL sidecars during at least one observation.
    wal_path = ROOT / "docker" / "v10.9" / "config" / "data" / "library.db-wal"
    shm_path = ROOT / "docker" / "v10.9" / "config" / "data" / "library.db-shm"

    report_path = tmp_path / "g2-18-live-report.json"
    v108_url = os.environ.get("JELLYFIN_V108_URL", "http://localhost:8096")
    v109_url = os.environ.get("JELLYFIN_V109_URL", "http://localhost:8097")
    assert v108_url.rstrip("/") in {
        "http://localhost:8096",
        "http://127.0.0.1:8096",
    }, "Offline v10.8 snapshots require the local Docker Compose endpoint"
    assert v109_url.rstrip("/") in {
        "http://localhost:8097",
        "http://127.0.0.1:8097",
    }, "Live v10.9 WAL snapshots require the local Docker Compose endpoint"

    original_record_db_validation = runner.record_db_validation
    live_wal_observed = False

    def record_with_version_snapshot(record, client, step, user_id, item_id, api_state):
        nonlocal live_wal_observed
        if client.server.label == "v10.8.13":
            try:
                _compose("stop", "jellyfin-v108")
                passed = original_record_db_validation(
                    record, client, step, user_id, item_id, api_state
                )
                record["db_validation"][-1]["snapshot_mode"] = "offline_server_stopped"
            finally:
                _compose("up", "-d", "jellyfin-v108")
                _wait_until_healthy(v108_url)
                client.authenticate("admin", os.environ.get("JELLYFIN_ADMIN_PASSWORD", "admin123456"))
            return passed

        wal_active = (
            wal_path.exists()
            and shm_path.exists()
            and os.access(wal_path, os.R_OK)
            and os.access(shm_path, os.R_OK)
        )
        passed = original_record_db_validation(
            record, client, step, user_id, item_id, api_state
        )
        record["db_validation"][-1]["snapshot_mode"] = "live_wal"
        record["db_validation"][-1]["wal_sidecars_present"] = wal_active
        live_wal_observed = live_wal_observed or wal_active
        return passed

    monkeypatch.setattr(runner, "record_db_validation", record_with_version_snapshot)

    exit_code = runner.main([
        "--v108-url", v108_url,
        "--v109-url", v109_url,
        "--report", str(report_path),
    ])
    assert exit_code == 0, f"G2-15 main runner failed with exit code {exit_code}"
    assert live_wal_observed, "No v10.9 DB snapshot was read while WAL sidecars were present"

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

        expected_mode = "offline_server_stopped" if version_key == "v10.8.13" else "live_wal"
        assert all(v.get("snapshot_mode") == expected_mode for v in validations)
        if version_key == "v10.9.0":
            assert any(v.get("wal_sidecars_present") for v in validations)

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
