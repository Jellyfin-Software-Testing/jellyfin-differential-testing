import importlib.util
import json
import sys
from pathlib import Path

import pytest

from models.user_data_model import FavoriteAction, FavoriteState, UserDataTestModel
from scripts.G1_06_setup_and_verify import SetupError

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "G2_15_user_state_favorites.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("g2_15_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code=204, content=b"", json_data=None):
        self.status_code = status_code
        self.content = content if json_data is None else json.dumps(json_data).encode("utf-8")
        self._json_data = json_data

    def json(self):
        if self._json_data is not None:
            return self._json_data
        if not self.content:
            raise ValueError("No JSON content")
        return json.loads(self.content.decode("utf-8"))


class FakeClient:
    def __init__(self, label="v10.8.13", user_id="admin-id"):
        self.server = type("Server", (), {"label": label, "base_url": f"http://{label}"})()
        self.user_id = user_id
        self.calls = []
        self.responses = []

    def queue_response(self, resp):
        self.responses.append(resp)

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("params"), kwargs.get("payload")))
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(204, b"")

    def json(self, method, path, **kwargs):
        resp = self.request(method, path, **kwargs)
        return resp.json()


def test_find_seed_item_success():
    runner = load_runner_module()
    client = FakeClient()
    client.queue_response(
        FakeResponse(
            200,
            json_data={
                "Items": [
                    {"Id": "item-audio-1", "Name": "01 - Reference Tone", "Type": "Audio"},
                    {"Id": "item-other-2", "Name": "01 - Reference Tone", "Type": "Folder"},
                ]
            },
        )
    )

    seed = runner.find_seed_item(client, "01 - Reference Tone", "Audio")
    assert seed["Id"] == "item-audio-1"
    assert seed["Name"] == "01 - Reference Tone"
    assert seed["Type"] == "Audio"


def test_find_seed_item_missing_and_duplicate():
    runner = load_runner_module()
    client = FakeClient()

    # Missing
    client.queue_response(FakeResponse(200, json_data={"Items": []}))
    with pytest.raises(SetupError, match="expected exactly one seed item"):
        runner.find_seed_item(client, "01 - Reference Tone", "Audio")

    # Duplicate
    client.queue_response(
        FakeResponse(
            200,
            json_data={
                "Items": [
                    {"Id": "item-1", "Name": "Tone", "Type": "Audio"},
                    {"Id": "item-2", "Name": "Tone", "Type": "Audio"},
                ]
            },
        )
    )
    with pytest.raises(SetupError, match="expected exactly one seed item"):
        runner.find_seed_item(client, "Tone", "Audio")


def test_favorite_request_maps_versioned_routes():
    runner = load_runner_module()
    legacy = FakeClient("v10.8.13")
    current = FakeClient("v10.9.0")

    runner.favorite_request(legacy, FavoriteAction.MARK_FAVORITE, "user-1", "item-1")
    runner.favorite_request(current, FavoriteAction.UNMARK_FAVORITE, "user-1", "item-1")

    assert legacy.calls == [("POST", "/Users/user-1/FavoriteItems/item-1", None, None)]
    assert current.calls == [("DELETE", "/UserFavoriteItems/item-1", {"userId": "user-1"}, None)]


def test_favorite_request_response_invariants():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"

    # Valid 204 no body
    c204 = FakeClient("v10.8.13")
    c204.queue_response(FakeResponse(204, b""))
    res = runner.favorite_request(c204, FavoriteAction.MARK_FAVORITE, "u", target_id)
    assert res["status_code"] == 204
    assert res["body"] is None

    # Invalid 204 with body
    c204_bad = FakeClient("v10.8.13")
    c204_bad.queue_response(FakeResponse(204, json_data={"IsFavorite": True}))
    with pytest.raises(SetupError, match="204 must have no body"):
        runner.favorite_request(c204_bad, FavoriteAction.MARK_FAVORITE, "u", target_id)

    # Valid 200 with DTO
    c200 = FakeClient("v10.9.0")
    c200.queue_response(
        FakeResponse(
            200,
            json_data={
                "ItemId": "758cdd3734433b1bc7c6213a5c7179f2",
                "IsFavorite": True,
                "PlayCount": 0,
            },
        )
    )
    res200 = runner.favorite_request(c200, FavoriteAction.MARK_FAVORITE, "u", target_id)
    assert res200["status_code"] == 200
    assert res200["body"]["IsFavorite"] is True

    # Invalid 200 with mismatched IsFavorite
    c200_bad = FakeClient("v10.9.0")
    c200_bad.queue_response(
        FakeResponse(
            200,
            json_data={
                "ItemId": target_id,
                "IsFavorite": False,
            },
        )
    )
    with pytest.raises(SetupError, match="expected IsFavorite to be True"):
        runner.favorite_request(c200_bad, FavoriteAction.MARK_FAVORITE, "u", target_id)


def test_read_state_versioned_routes():
    runner = load_runner_module()
    legacy = FakeClient("v10.8.13")
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"

    # Queue item response then collection response
    legacy.queue_response(FakeResponse(200, json_data={"UserData": {"IsFavorite": True}}))
    legacy.queue_response(FakeResponse(200, json_data={"Items": [{"Id": target_id}]}))

    state = runner.read_state(legacy, "user-1", target_id)
    assert state == {"is_favorite": True, "in_favorites": True}
    assert legacy.calls[0] == ("GET", f"/Users/user-1/Items/{target_id}", None, None)
    assert legacy.calls[1] == (
        "GET",
        "/Items",
        {"userId": "user-1", "ids": target_id, "isFavorite": "true"},
        None,
    )

    current = FakeClient("v10.9.0")
    current.queue_response(FakeResponse(200, json_data={"UserData": {"IsFavorite": False}}))
    current.queue_response(FakeResponse(200, json_data={"Items": []}))

    state_curr = runner.read_state(current, "user-1", target_id)
    assert state_curr == {"is_favorite": False, "in_favorites": False}
    assert current.calls[0] == ("GET", f"/Items/{target_id}", {"userId": "user-1"}, None)


@pytest.mark.parametrize("raw_value", [None, "false", 0])
def test_read_state_rejects_non_boolean_is_favorite(raw_value):
    runner = load_runner_module()
    client = FakeClient()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    client.queue_response(
        FakeResponse(200, json_data={"UserData": {"IsFavorite": raw_value}})
    )
    client.queue_response(FakeResponse(200, json_data={"Items": []}))

    with pytest.raises(SetupError, match="boolean UserData.IsFavorite"):
        runner.read_state(client, "user-1", target_id)


class StatefulFakeClient:
    def __init__(self, label="v10.9.0", initial_favorite=False, initial_in_favs=None, raise_on_post=False, fail_cleanup=False):
        self.server = type("Server", (), {"label": label, "base_url": f"http://{label}"})()
        self.user_id = "admin"
        self.calls = []
        self.is_fav = initial_favorite
        self.in_favs = initial_favorite if initial_in_favs is None else initial_in_favs
        self.raise_on_post = raise_on_post
        self.fail_cleanup = fail_cleanup
        self.cleanup_phase = False

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("params")))
        if self.cleanup_phase and self.fail_cleanup:
            raise SetupError(f"{self.server.label}: simulated cleanup failure")

        if method == "POST" and "Favorite" in path:
            if self.raise_on_post:
                # Mutate state before raising
                self.is_fav = True
                self.in_favs = True
                raise SetupError(f"{self.server.label}: simulated POST mutation failure")
            self.is_fav = True
            self.in_favs = True
            return FakeResponse(204, b"")

        if method == "DELETE" and "Favorite" in path:
            self.is_fav = False
            self.in_favs = False
            return FakeResponse(204, b"")

        return FakeResponse(204, b"")

    def json(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("params")))
        if path.startswith("/Items/") or "/Items/" in path:
            return {"UserData": {"IsFavorite": self.is_fav}}
        if path == "/Items":
            target_id = kwargs.get("params", {}).get("ids", "test-item-id")
            if self.in_favs:
                return {"Items": [{"Id": target_id}]}
            return {"Items": []}
        return {}


def test_run_instance_inconsistent_initial_snapshot():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    seed = {"Id": target_id, "Name": "Tone", "Type": "Audio"}

    # Inconsistent: is_favorite=True, in_favorites=False
    client = StatefulFakeClient(initial_favorite=True, initial_in_favs=False)
    res = runner.run_instance(client, "admin", seed)

    assert res["success"] is False
    assert "inconsistent" in res["error"].lower()
    # Confirm no mutation occurred
    assert not any(m in ("POST", "DELETE") for m, p, _ in client.calls)


def test_run_instance_false_baseline_flow():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    seed = {"Id": target_id, "Name": "Tone", "Type": "Audio"}

    client = StatefulFakeClient(initial_favorite=False)
    res = runner.run_instance(client, "admin", seed)

    assert res["success"] is True
    assert res["error"] is None
    assert res["seed_id"] == target_id
    assert res["original_state"] == {"is_favorite": False, "in_favorites": False}

    # Verify 4 main-flow checkpoints
    steps = res["steps"]
    assert steps["post_favorite"]["status"] == "passed"
    assert steps["verify_favorite"]["is_favorite"] is True
    assert steps["verify_favorite"]["in_favorites"] is True
    assert steps["delete_favorite"]["status"] == "passed"
    assert steps["verify_unfavorite"]["is_favorite"] is False
    assert steps["verify_unfavorite"]["in_favorites"] is False

    # Cleanup passed
    assert res["cleanup"]["status"] == "passed"


def test_run_instance_true_baseline_normalizes_and_restores():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    seed = {"Id": target_id, "Name": "Tone", "Type": "Audio"}

    client = StatefulFakeClient(initial_favorite=True)
    res = runner.run_instance(client, "admin", seed)

    assert res["success"] is True
    assert res["original_state"] == {"is_favorite": True, "in_favorites": True}
    assert res["normalize_initial"]["status"] == "passed"
    assert client.is_fav is True  # Restored to True
    assert res["cleanup"]["status"] == "passed"


def test_run_instance_cleanup_after_mutation_failure():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    seed = {"Id": target_id, "Name": "Tone", "Type": "Audio"}

    # Baseline is False, but POST mutates to True and then raises
    client = StatefulFakeClient(initial_favorite=False, raise_on_post=True)
    res = runner.run_instance(client, "admin", seed)

    assert res["success"] is False
    assert "simulated post mutation failure" in res["error"].lower()
    # Cleanup should have detected changed state (True) and restored baseline (False)
    assert client.is_fav is False
    assert res["cleanup"]["status"] == "passed"
    assert res["cleanup"]["restored_to"] is False


def test_run_instance_cleanup_failure_marks_instance_failed():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    seed = {"Id": target_id, "Name": "Tone", "Type": "Audio"}

    # Baseline is True. Normalization unmarks to False, but in finally restore fails
    client = StatefulFakeClient(initial_favorite=True, fail_cleanup=True)
    res = runner.run_instance(client, "admin", seed)

    assert res["success"] is False
    assert res["cleanup"]["status"] == "failed"
    assert "simulated cleanup failure" in res["cleanup"]["error"]


def _make_dummy_instance(server, seed_id, original_fav, status_code=204, is_fav=True, in_favs=True):
    return {
        "server": server,
        "seed_id": seed_id,
        "original_state": {"is_favorite": original_fav, "in_favorites": original_fav},
        "normalize_initial": {"action": "DELETE", "status": "passed"} if original_fav else {"skipped": True},
        "steps": {
            "post_favorite": {"status": "passed", "status_code": status_code},
            "verify_favorite": {"status": "passed", "is_favorite": is_fav, "in_favorites": in_favs},
            "delete_favorite": {"status": "passed", "status_code": status_code},
            "verify_unfavorite": {"status": "passed", "is_favorite": False, "in_favorites": False},
        },
        "cleanup": {"status": "passed"},
        "success": True,
        "error": None,
    }


def test_compare_semantics_passes_with_status_drift_and_different_ids():
    runner = load_runner_module()
    # v10.8 has item-1, baseline False, status 204
    inst_108 = _make_dummy_instance("v10.8.13", "item-1", original_fav=False, status_code=204)
    # v10.9 has item-2, baseline True (normalized), status 200
    inst_109 = _make_dummy_instance("v10.9.0", "item-2", original_fav=True, status_code=200)

    eq, diffs = runner.compare_semantics(inst_108, inst_109)
    assert eq is True
    assert diffs == []


def test_compare_semantics_fails_on_state_mismatch():
    runner = load_runner_module()
    inst_108 = _make_dummy_instance("v10.8.13", "item-1", original_fav=False, is_fav=True, in_favs=True)
    inst_109 = _make_dummy_instance("v10.9.0", "item-2", original_fav=False, is_fav=False, in_favs=False)

    eq, diffs = runner.compare_semantics(inst_108, inst_109)
    assert eq is False
    assert any("verify_favorite" in d for d in diffs)


def test_compare_semantics_fails_on_missing_checkpoint():
    runner = load_runner_module()
    inst_108 = _make_dummy_instance("v10.8.13", "item-1", original_fav=False)
    inst_109 = _make_dummy_instance("v10.9.0", "item-2", original_fav=False)
    del inst_109["steps"]["delete_favorite"]

    eq, diffs = runner.compare_semantics(inst_108, inst_109)
    assert eq is False
    assert any("delete_favorite" in d for d in diffs)


def test_main_help():
    runner = load_runner_module()
    with pytest.raises(SystemExit) as exc:
        runner.main(["--help"])
    assert exc.value.code == 0


def test_main_success(tmp_path, monkeypatch):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"

    # Mock client init & auth
    def mock_auth(self, username, password):
        self.user_id = "mock-admin"
    monkeypatch.setattr(runner.JellyfinClient, "authenticate", mock_auth)

    # Mock find_seed_item
    monkeypatch.setattr(
        runner,
        "find_seed_item",
        lambda client, name, item_type: {"Id": f"seed-{client.server.label}", "Name": name, "Type": item_type},
    )

    # Mock run_instance to return dummy successful instances
    monkeypatch.setattr(
        runner,
        "run_instance",
        lambda client, user_id, seed: _make_dummy_instance(client.server.label, seed["Id"], original_fav=False),
    )

    exit_code = runner.main(["--report", str(report_file)])
    assert exit_code == 0
    assert report_file.exists()

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["task"] == "G2-15"
    assert report["status"] == "passed"
    assert report["parity"] == "equivalent"
    assert "v10.8.13" in report["instances"]
    assert "v10.9.0" in report["instances"]


def test_main_mismatch_returns_nonzero(tmp_path, monkeypatch):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"

    monkeypatch.setattr(runner.JellyfinClient, "authenticate", lambda self, u, p: setattr(self, "user_id", "admin"))
    monkeypatch.setattr(runner, "find_seed_item", lambda client, n, t: {"Id": "seed-1", "Name": n, "Type": t})

    def mock_run(client, user_id, seed):
        if "10.8" in client.server.label:
            return _make_dummy_instance(client.server.label, seed["Id"], original_fav=False, is_fav=True, in_favs=True)
        return _make_dummy_instance(client.server.label, seed["Id"], original_fav=False, is_fav=False, in_favs=False)

    monkeypatch.setattr(runner, "run_instance", mock_run)

    exit_code = runner.main(["--report", str(report_file)])
    assert exit_code != 0

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["parity"] == "mismatched"
    assert len(report["parity_diffs"]) > 0


def test_main_peer_setup_failure_runs_healthy_peer(tmp_path, monkeypatch):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"

    monkeypatch.setattr(runner.JellyfinClient, "authenticate", lambda self, u, p: setattr(self, "user_id", "admin"))

    def mock_find_seed(client, n, t):
        if "10.8" in client.server.label:
            raise SetupError(f"{client.server.label}: seed not found")
        return {"Id": "seed-109", "Name": n, "Type": t}

    monkeypatch.setattr(runner, "find_seed_item", mock_find_seed)
    monkeypatch.setattr(
        runner,
        "run_instance",
        lambda client, user_id, seed: _make_dummy_instance(client.server.label, seed["Id"], original_fav=False),
    )

    exit_code = runner.main(["--report", str(report_file)])
    assert exit_code != 0

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    # Both instances present
    assert report["instances"]["v10.8.13"]["error"] is not None
    assert report["instances"]["v10.9.0"]["success"] is True
    assert report["parity"] == "mismatched"


def test_main_g1_report_validation(tmp_path, monkeypatch):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"
    g1_file = tmp_path / "g1-evidence.json"

    monkeypatch.setattr(runner.JellyfinClient, "authenticate", lambda self, u, p: setattr(self, "user_id", "admin"))
    monkeypatch.setattr(runner, "find_seed_item", lambda client, n, t: {"Id": "seed-1", "Name": n, "Type": t})
    monkeypatch.setattr(
        runner,
        "run_instance",
        lambda client, user_id, seed: _make_dummy_instance(client.server.label, seed["Id"], original_fav=False),
    )

    # Invalid G1 report (status != "equivalent")
    g1_file.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    exit_code = runner.main(["--report", str(report_file), "--g1-report", str(g1_file)])
    assert exit_code != 0
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert "g1-06" in report["error"].lower()

    # Valid G1 report
    g1_file.write_text(json.dumps({"status": "equivalent"}), encoding="utf-8")
    exit_code_ok = runner.main(["--report", str(report_file), "--g1-report", str(g1_file)])
    assert exit_code_ok == 0


def test_main_cleanup_failure_fails_overall_run(tmp_path, monkeypatch):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"

    monkeypatch.setattr(runner.JellyfinClient, "authenticate", lambda self, u, p: setattr(self, "user_id", "admin"))
    monkeypatch.setattr(runner, "find_seed_item", lambda client, n, t: {"Id": "seed-1", "Name": n, "Type": t})

    def mock_run(client, user_id, seed):
        inst = _make_dummy_instance(client.server.label, seed["Id"], original_fav=False)
        if "10.8" in client.server.label:
            inst["cleanup"] = {"status": "failed", "error": "simulated cleanup fail"}
            inst["success"] = False
        return inst

    monkeypatch.setattr(runner, "run_instance", mock_run)

    exit_code = runner.main(["--report", str(report_file)])
    assert exit_code != 0
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["status"] == "failed"


def test_main_report_write_failure(monkeypatch):
    runner = load_runner_module()

    monkeypatch.setattr(runner.JellyfinClient, "authenticate", lambda self, u, p: setattr(self, "user_id", "admin"))
    monkeypatch.setattr(runner, "find_seed_item", lambda client, n, t: {"Id": "seed-1", "Name": n, "Type": t})
    monkeypatch.setattr(
        runner,
        "run_instance",
        lambda client, user_id, seed: _make_dummy_instance(client.server.label, seed["Id"], original_fav=False),
    )
    monkeypatch.setattr(runner, "write_report", lambda p, d: (_ for _ in ()).throw(OSError("Disk write error")))

    exit_code = runner.main(["--report", "/unwritable/path/report.json"])
    assert exit_code != 0


def test_run_instance_preserves_failed_step_evidence():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    seed = {"Id": target_id, "Name": "Tone", "Type": "Audio"}

    # Fake client where POST succeeds but state remains unfavorited
    class VerifyFailClient(StatefulFakeClient):
        def request(self, method, path, **kwargs):
            self.calls.append((method, path, kwargs.get("params")))
            # Return 204 but don't flip is_fav to True
            return FakeResponse(204, b"")

    client = VerifyFailClient(initial_favorite=False)
    res = runner.run_instance(client, "admin", seed)

    assert res["success"] is False
    assert "verify_favorite" in res["steps"]
    step = res["steps"]["verify_favorite"]
    assert step["status"] == "failed"
    assert step["is_favorite"] is False
    assert step["in_favorites"] is False


def test_cleanup_detects_in_favorites_desync():
    runner = load_runner_module()
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    seed = {"Id": target_id, "Name": "Tone", "Type": "Audio"}

    # Initial state is consistent (False, False).
    # But during main flow DELETE, in_favs fails to clear and stays True.
    # In cleanup phase, DELETE finally clears in_favs.
    class DesyncClient(StatefulFakeClient):
        def request(self, method, path, **kwargs):
            self.calls.append((method, path, kwargs.get("params")))
            if method == "DELETE":
                if self.cleanup_phase:
                    self.in_favs = False
                    self.is_fav = False
                else:
                    # Fail to clear in_favorites during main flow
                    self.is_fav = False
                    self.in_favs = True
                return FakeResponse(204, b"")
            return super().request(method, path, **kwargs)

    client = DesyncClient(initial_favorite=False)
    res = runner.run_instance(client, "admin", seed)

    # Main flow failed on verify_unfavorite because in_favorites was True
    assert res["success"] is False
    assert "verify_unfavorite" in res["steps"]
    # But cleanup ran and restored in_favs to False!
    assert client.in_favs is False
    assert res["cleanup"]["status"] == "passed"






