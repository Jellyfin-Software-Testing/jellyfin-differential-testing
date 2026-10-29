import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

from models.user_data_model import FavoriteAction, FavoriteState
from scripts.G1_06_setup_and_verify import SetupError

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "G2_16_concurrency_differential.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("g2_16_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {RUNNER}")
    module = importlib.util.module_from_spec(spec)
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
        self.token = "fake-token"
        self.timeout = 5.0
        self.calls = []
        self._lock = threading.Lock()
        self.routed_responses = {}
        self.default_responses = []

    def queue_routed_response(self, path, resp):
        with self._lock:
            self.routed_responses.setdefault(path, []).append(resp)

    def queue_response(self, resp):
        with self._lock:
            self.default_responses.append(resp)

    def request(self, method, path, **kwargs):
        with self._lock:
            self.calls.append((method, path, kwargs.get("params"), kwargs.get("payload")))
            if path in self.routed_responses and self.routed_responses[path]:
                return self.routed_responses[path].pop(0)
            if self.default_responses:
                return self.default_responses.pop(0)
            return FakeResponse(204, b"")

    def json(self, method, path, **kwargs):
        resp = self.request(method, path, **kwargs)
        return resp.json()


def test_find_common_seed_items_resolves_and_paginates():
    runner = load_runner_module()
    manifest = {
        "library": {"name": "Differential Seed Music"},
    }

    client_108 = FakeClient("v10.8.13")
    client_109 = FakeClient("v10.9.0")

    vf_108 = [{"Name": "Differential Seed Music", "ItemId": "lib-id-108"}]
    vf_109 = [{"Name": "Differential Seed Music", "ItemId": "lib-id-109"}]

    client_108.queue_routed_response("/Library/VirtualFolders", FakeResponse(200, json_data=vf_108))
    client_109.queue_routed_response("/Library/VirtualFolders", FakeResponse(200, json_data=vf_109))

    # Page 1 for 108: 2 items, total 3
    client_108.queue_routed_response(
        "/Items",
        FakeResponse(
            200,
            json_data={
                "TotalRecordCount": 3,
                "Items": [
                    {"Id": "id-108-1", "Name": "01 - Reference Tone", "Type": "Audio"},
                    {"Id": "id-108-2", "Name": "02 - Comparison Tone", "Type": "Audio"},
                ],
            },
        ),
    )
    # Page 2 for 108: 1 item
    client_108.queue_routed_response(
        "/Items",
        FakeResponse(
            200,
            json_data={
                "TotalRecordCount": 3,
                "Items": [
                    {"Id": "id-108-3", "Name": "03 - Tone", "Type": "Audio"},
                ],
            },
        ),
    )

    # For 109: single page with 3 items in different order + 1 extra item not in 108
    client_109.queue_routed_response(
        "/Items",
        FakeResponse(
            200,
            json_data={
                "TotalRecordCount": 4,
                "Items": [
                    {"Id": "id-109-2", "Name": "02 - Comparison Tone", "Type": "Audio"},
                    {"Id": "id-109-extra", "Name": "99 - Unmatched", "Type": "Audio"},
                    {"Id": "id-109-1", "Name": "01 - Reference Tone", "Type": "Audio"},
                    {"Id": "id-109-3", "Name": "03 - Tone", "Type": "Audio"},
                ],
            },
        ),
    )

    result = runner.find_common_seed_items([client_108, client_109], manifest, "Audio")

    assert "v10.8.13" in result
    assert "v10.9.0" in result
    items_108 = result["v10.8.13"]
    items_109 = result["v10.9.0"]

    # Must be identically ordered by common name/type
    names_108 = [i["Name"] for i in items_108]
    names_109 = [i["Name"] for i in items_109]
    assert names_108 == names_109
    assert names_108 == ["01 - Reference Tone", "02 - Comparison Tone", "03 - Tone"]
    assert items_108[0]["Id"] == "id-108-1"
    assert items_109[0]["Id"] == "id-109-1"


def test_find_common_seed_items_rejects_duplicate_names():
    runner = load_runner_module()
    manifest = {"library": {"name": "Differential Seed Music"}}

    client_108 = FakeClient("v10.8.13")
    client_109 = FakeClient("v10.9.0")

    client_108.queue_routed_response("/Library/VirtualFolders", FakeResponse(200, json_data=[{"Name": "Differential Seed Music", "ItemId": "lib-1"}]))
    client_109.queue_routed_response("/Library/VirtualFolders", FakeResponse(200, json_data=[{"Name": "Differential Seed Music", "ItemId": "lib-2"}]))

    client_108.queue_routed_response(
        "/Items",
        FakeResponse(
            200,
            json_data={
                "TotalRecordCount": 2,
                "Items": [
                    {"Id": "1", "Name": "Duplicate Tone", "Type": "Audio"},
                    {"Id": "2", "Name": "Duplicate Tone", "Type": "Audio"},
                ],
            },
        ),
    )
    client_109.queue_routed_response(
        "/Items",
        FakeResponse(
            200,
            json_data={
                "TotalRecordCount": 1,
                "Items": [
                    {"Id": "3", "Name": "Duplicate Tone", "Type": "Audio"},
                ],
            },
        ),
    )

    with pytest.raises(SetupError, match="duplicate"):
        runner.find_common_seed_items([client_108, client_109], manifest, "Audio")


def test_find_common_seed_items_caps_at_100():
    runner = load_runner_module()
    manifest = {"library": {"name": "Differential Seed Music"}}

    client_108 = FakeClient("v10.8.13")
    client_109 = FakeClient("v10.9.0")

    client_108.queue_routed_response("/Library/VirtualFolders", FakeResponse(200, json_data=[{"Name": "Differential Seed Music", "ItemId": "lib-1"}]))
    client_109.queue_routed_response("/Library/VirtualFolders", FakeResponse(200, json_data=[{"Name": "Differential Seed Music", "ItemId": "lib-2"}]))

    items = [{"Id": f"id-{i}", "Name": f"Tone {i:03d}", "Type": "Audio"} for i in range(120)]
    client_108.queue_routed_response("/Items", FakeResponse(200, json_data={"TotalRecordCount": 120, "Items": items}))
    client_109.queue_routed_response("/Items", FakeResponse(200, json_data={"TotalRecordCount": 120, "Items": items}))

    res = runner.find_common_seed_items([client_108, client_109], manifest, "Audio")
    assert len(res["v10.8.13"]) == 100
    assert len(res["v10.9.0"]) == 100


def test_run_concurrent_batch_releases_together_and_routes_versioned():
    runner = load_runner_module()
    client_108 = FakeClient("v10.8.13")
    client_109 = FakeClient("v10.9.0")

    items_by_server = {
        "v10.8.13": [
            {"Id": "id-108-1", "Name": "Tone 1", "Type": "Audio"},
            {"Id": "id-108-2", "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": "id-109-1", "Name": "Tone 1", "Type": "Audio"},
            {"Id": "id-109-2", "Name": "Tone 2", "Type": "Audio"},
        ],
    }

    result = runner.run_concurrent_batch(
        [client_108, client_109],
        items_by_server,
        FavoriteAction.MARK_FAVORITE,
        concurrency=2,
    )

    assert "servers" in result
    servers = result["servers"]
    assert "v10.8.13" in servers
    assert "v10.9.0" in servers

    reqs_108 = servers["v10.8.13"]["requests"]
    reqs_109 = servers["v10.9.0"]["requests"]
    assert len(reqs_108) == 2
    assert len(reqs_109) == 2

    assert all(r["status"] == "passed" for r in reqs_108)
    assert all(r["status"] == "passed" for r in reqs_109)

    # Check versioned routes called
    paths_108 = [c[1] for c in client_108.calls]
    paths_109 = [c[1] for c in client_109.calls]
    assert "/Users/admin-id/FavoriteItems/id-108-1" in paths_108
    assert "/Users/admin-id/FavoriteItems/id-108-2" in paths_108
    assert "/UserFavoriteItems/id-109-1" in paths_109
    assert "/UserFavoriteItems/id-109-2" in paths_109


def test_run_concurrent_batch_handles_request_exception():
    runner = load_runner_module()
    client_108 = FakeClient("v10.8.13")
    client_109 = FakeClient("v10.9.0")

    # Fail one request on 108
    def failing_request(method, path, **kwargs):
        if "id-108-2" in path:
            raise SetupError("Network glitch on 108-2")
        return FakeResponse(204, b"")

    client_108.request = failing_request

    items_by_server = {
        "v10.8.13": [
            {"Id": "id-108-1", "Name": "Tone 1", "Type": "Audio"},
            {"Id": "id-108-2", "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": "id-109-1", "Name": "Tone 1", "Type": "Audio"},
            {"Id": "id-109-2", "Name": "Tone 2", "Type": "Audio"},
        ],
    }

    result = runner.run_concurrent_batch(
        [client_108, client_109],
        items_by_server,
        FavoriteAction.MARK_FAVORITE,
        concurrency=2,
    )

    reqs_108 = result["servers"]["v10.8.13"]["requests"]
    assert reqs_108[0]["status"] == "passed"
    assert reqs_108[1]["status"] == "failed"
    assert "Network glitch" in reqs_108[1]["error"]

    reqs_109 = result["servers"]["v10.9.0"]["requests"]
    assert all(r["status"] == "passed" for r in reqs_109)


def test_run_concurrent_batch_pre_barrier_worker_setup_aborts():
    runner = load_runner_module()
    client_108 = FakeClient("v10.8.13")
    client_109 = FakeClient("v10.9.0")

    # Only 1 item for 109 when concurrency=2 -> causes setup/submit error
    items_by_server = {
        "v10.8.13": [
            {"Id": "id-108-1", "Name": "Tone 1", "Type": "Audio"},
            {"Id": "id-108-2", "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": "id-109-1", "Name": "Tone 1", "Type": "Audio"},
        ],
    }

    result = runner.run_concurrent_batch(
        [client_108, client_109],
        items_by_server,
        FavoriteAction.MARK_FAVORITE,
        concurrency=2,
    )

    # None of the workers should hang; all should complete
    servers = result["servers"]
    assert len(servers["v10.8.13"]["requests"]) == 2
    assert len(servers["v10.9.0"]["requests"]) == 2
    # The aborted barrier or setup error marks items as failed
    assert any(r["status"] == "failed" for r in servers["v10.8.13"]["requests"])
    assert servers["v10.9.0"]["requests"][1]["status"] == "failed"


class StatefulItemClient:
    """Fake client maintaining per-item favorite states."""
    def __init__(self, label="v10.8.13", user_id="admin-id", initial_states=None):
        self.server = type("Server", (), {"label": label, "base_url": f"http://{label}"})()
        self.user_id = user_id
        self.token = "fake-token"
        self.timeout = 5.0
        self.states = dict(initial_states or {})
        self.mutations = []
        self._lock = threading.Lock()
        self.fail_cleanup_ids = set()

    def request(self, method, path, **kwargs):
        with self._lock:
            # Extract item_id from path
            # /Users/{user_id}/FavoriteItems/{item_id} or /UserFavoriteItems/{item_id}
            item_id = path.rstrip("/").split("/")[-1]
            if method in ("POST", "DELETE"):
                self.mutations.append((method, item_id))
                if item_id in self.fail_cleanup_ids:
                    raise SetupError(f"Simulated cleanup write failure for {item_id}")
                is_fav = (method == "POST")
                self.states[item_id] = {"is_favorite": is_fav, "in_favorites": is_fav}
                return FakeResponse(204, b"")
            return FakeResponse(204, b"")

    def json(self, method, path, **kwargs):
        with self._lock:
            # Check if this is read_state collection query
            params = kwargs.get("params") or {}
            if path == "/Items" and params.get("isFavorite") == "true":
                item_id = params.get("ids")
                st = self.states.get(item_id, {"is_favorite": False, "in_favorites": False})
                items = [{"Id": item_id}] if st.get("in_favorites") else []
                return {"Items": items}
            # Otherwise single item query
            item_id = path.rstrip("/").split("/")[-1]
            st = self.states.get(item_id, {"is_favorite": False, "in_favorites": False})
            return {"Id": item_id, "UserData": {"IsFavorite": st.get("is_favorite")}}


ID_1 = "758cdd37-3443-3b1b-c7c6-213a5c7179f1"
ID_2 = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"


def test_run_case_mark_favorite_lifecycle():
    runner = load_runner_module()
    # Item 1 initially favorited, Item 2 initially unfavorited
    init_108 = {
        ID_1: {"is_favorite": True, "in_favorites": True},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    init_109 = {
        ID_1: {"is_favorite": True, "in_favorites": True},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    items_by_server = {
        "v10.8.13": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
    }

    res = runner.run_case([c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=2)

    assert res["status"] == "passed"
    assert res["parity"] is True
    assert res["error"] is None

    # Check that after run_case finishes, original state is restored in StatefulItemClient
    assert c108.states[ID_1]["is_favorite"] is True
    assert c108.states[ID_2]["is_favorite"] is False
    assert c109.states[ID_1]["is_favorite"] is True
    assert c109.states[ID_2]["is_favorite"] is False

    # Check items record
    items_record = res["servers"]["v10.8.13"]["items"]
    assert items_record[ID_1]["cleanup"] == "passed"
    assert items_record[ID_1]["final"]["is_favorite"] is True
    assert items_record[ID_1]["original"]["is_favorite"] is True


def test_run_case_unmark_favorite_lifecycle():
    runner = load_runner_module()
    # Mixed original states
    init_108 = {
        ID_1: {"is_favorite": True, "in_favorites": True},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    init_109 = {
        ID_1: {"is_favorite": True, "in_favorites": True},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    items_by_server = {
        "v10.8.13": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
    }

    res = runner.run_case([c108, c109], items_by_server, FavoriteAction.UNMARK_FAVORITE, concurrency=2)

    assert res["status"] == "passed"
    assert res["parity"] is True
    assert res["error"] is None

    # Check original states restored
    assert c108.states[ID_1]["is_favorite"] is True
    assert c108.states[ID_2]["is_favorite"] is False
    assert c109.states[ID_1]["is_favorite"] is True
    assert c109.states[ID_2]["is_favorite"] is False

    # Check final in-batch states were unfavorited
    items_record = res["servers"]["v10.8.13"]["items"]
    assert items_record[ID_1]["final"]["is_favorite"] is False
    assert items_record[ID_2]["final"]["is_favorite"] is False


def test_run_case_continues_verifying_after_item_readback_error(monkeypatch):
    runner = load_runner_module()
    initial = {
        ID_1: {"is_favorite": False, "in_favorites": False},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    c108 = StatefulItemClient("v10.8.13", initial_states=initial)
    c109 = StatefulItemClient("v10.9.0", initial_states=initial)
    items_by_server = {
        "v10.8.13": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
    }

    original_read_state = runner.read_state
    original_run_batch = runner.run_concurrent_batch
    batch_finished = False
    failed_reads = set()

    def run_batch_then_mark_finished(*args, **kwargs):
        nonlocal batch_finished
        result = original_run_batch(*args, **kwargs)
        batch_finished = True
        return result

    def fail_first_post_batch_read_for_first_item(client, user_id, item_id):
        key = (client.server.label, item_id)
        if batch_finished and item_id == ID_1 and key not in failed_reads:
            failed_reads.add(key)
            raise SetupError("simulated post-batch readback failure")
        return original_read_state(client, user_id, item_id)

    monkeypatch.setattr(runner, "run_concurrent_batch", run_batch_then_mark_finished)
    monkeypatch.setattr(runner, "read_state", fail_first_post_batch_read_for_first_item)

    result = runner.run_case(
        [c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=2
    )

    assert result["status"] == "failed"
    for label in ("v10.8.13", "v10.9.0"):
        item_records = result["servers"][label]["items"]
        assert "simulated post-batch readback failure" in item_records[ID_1]["verification_error"]
        assert item_records[ID_2]["final"] == {
            "is_favorite": True,
            "in_favorites": True,
        }
        assert item_records[ID_2]["verification_error"] is None
        assert all(item["cleanup"] == "passed" for item in item_records.values())


def test_run_case_preflight_inconsistency_aborts_without_writes():
    runner = load_runner_module()
    # Inconsistent initial state on ID_1
    init_108 = {
        ID_1: {"is_favorite": True, "in_favorites": False},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    init_109 = {
        ID_1: {"is_favorite": True, "in_favorites": True},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    items_by_server = {
        "v10.8.13": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
    }

    res = runner.run_case([c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=2)

    assert res["status"] == "failed"
    assert "inconsistent" in res["error"].lower()
    # Zero writes attempted
    assert len(c108.mutations) == 0
    assert len(c109.mutations) == 0

    # Cleanup must be not_needed
    item_rep = res["servers"]["v10.8.13"]["items"][ID_1]
    assert item_rep["cleanup"] == "not_needed"


def test_run_case_cleanup_failure_continues_restoring_later_items():
    runner = load_runner_module()
    init_108 = {
        ID_1: {"is_favorite": False, "in_favorites": False},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    init_109 = {
        ID_1: {"is_favorite": False, "in_favorites": False},
        ID_2: {"is_favorite": False, "in_favorites": False},
    }
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    # Make ID_1 fail during cleanup
    c108.fail_cleanup_ids.add(ID_1)

    items_by_server = {
        "v10.8.13": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
        "v10.9.0": [
            {"Id": ID_1, "Name": "Tone 1", "Type": "Audio"},
            {"Id": ID_2, "Name": "Tone 2", "Type": "Audio"},
        ],
    }

    res = runner.run_case([c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=2)

    assert res["status"] == "failed"
    items_108 = res["servers"]["v10.8.13"]["items"]
    assert items_108[ID_1]["cleanup"] == "failed"
    assert "Simulated cleanup write failure" in items_108[ID_1]["cleanup_error"]

    # ID_2 must still have been restored!
    assert items_108[ID_2]["cleanup"] == "passed"


def test_main_full_success(monkeypatch, tmp_path):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"

    # Mock client and find_common_seed_items and run_case
    c108 = StatefulItemClient("v10.8.13")
    c109 = StatefulItemClient("v10.9.0")

    monkeypatch.setattr(runner, "JellyfinClient", lambda server, timeout: c108 if "10.8" in server.label else c109)
    # Give them authenticate method
    c108.authenticate = lambda u, p: None
    c109.authenticate = lambda u, p: None

    # Provide 100 fake items
    seed_items = {
        "v10.8.13": [{"Id": f"id-108-{i}", "Name": f"Tone {i:03d}", "Type": "Audio"} for i in range(100)],
        "v10.9.0": [{"Id": f"id-109-{i}", "Name": f"Tone {i:03d}", "Type": "Audio"} for i in range(100)],
    }
    monkeypatch.setattr(runner, "find_common_seed_items", lambda clients, manifest, item_type: seed_items)

    executed_cases = []
    def fake_run_case(clients, items_by_server, action, concurrency):
        executed_cases.append((action, concurrency))
        return {
            "action": action.name,
            "concurrency": concurrency,
            "status": "passed",
            "parity": True,
            "error": None,
            "servers": {c.server.label: {"requests": [], "items": {}} for c in clients},
        }

    monkeypatch.setattr(runner, "run_case", fake_run_case)

    exit_code = runner.main([
        "--v108-url", "http://fake-108",
        "--v109-url", "http://fake-109",
        "--report", str(report_file),
    ])

    assert exit_code == 0
    assert report_file.exists()
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["task"] == "G2-16"
    assert report["status"] == "passed"
    assert report["parity"] is True
    # 4 levels x 2 actions = 8 cases
    assert len(executed_cases) == 8
    assert len(report["cases"]) == 8


def test_main_insufficient_items_skips_and_exits_nonzero(monkeypatch, tmp_path):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"

    c108 = StatefulItemClient("v10.8.13")
    c109 = StatefulItemClient("v10.9.0")
    c108.authenticate = lambda u, p: None
    c109.authenticate = lambda u, p: None

    monkeypatch.setattr(runner, "JellyfinClient", lambda server, timeout: c108 if "10.8" in server.label else c109)

    # Only 50 items available
    seed_items = {
        "v10.8.13": [{"Id": f"id-108-{i}", "Name": f"Tone {i:03d}", "Type": "Audio"} for i in range(50)],
        "v10.9.0": [{"Id": f"id-109-{i}", "Name": f"Tone {i:03d}", "Type": "Audio"} for i in range(50)],
    }
    monkeypatch.setattr(runner, "find_common_seed_items", lambda clients, manifest, item_type: seed_items)

    executed_cases = []
    def fake_run_case(clients, items_by_server, action, concurrency):
        executed_cases.append((action, concurrency))
        return {
            "action": action.name,
            "concurrency": concurrency,
            "status": "passed",
            "parity": True,
            "error": None,
            "servers": {c.server.label: {"requests": [], "items": {}} for c in clients},
        }

    monkeypatch.setattr(runner, "run_case", fake_run_case)

    exit_code = runner.main(["--report", str(report_file)])

    assert exit_code != 0
    assert report_file.exists()
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["status"] == "failed"

    # Level 100 must be marked skipped_insufficient_items and not executed
    assert (FavoriteAction.MARK_FAVORITE, 100) not in executed_cases
    assert (FavoriteAction.UNMARK_FAVORITE, 100) not in executed_cases

    skipped = [c for c in report["cases"] if c.get("status") == "skipped_insufficient_items"]
    assert len(skipped) == 2  # MARK and UNMARK for level 100


def test_main_auth_failure_writes_error_report(monkeypatch, tmp_path):
    runner = load_runner_module()
    report_file = tmp_path / "evidence.json"

    c108 = StatefulItemClient("v10.8.13")
    c108.authenticate = lambda u, p: (_ for _ in ()).throw(SetupError("Invalid credentials"))
    monkeypatch.setattr(runner, "JellyfinClient", lambda server, timeout: c108)

    exit_code = runner.main(["--report", str(report_file)])

    assert exit_code == 1
    assert report_file.exists()
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert "Invalid credentials" in report["error"]


def test_main_report_write_error_returns_nonzero(monkeypatch, tmp_path):
    runner = load_runner_module()
    c108 = StatefulItemClient("v10.8.13")
    c109 = StatefulItemClient("v10.9.0")
    c108.authenticate = lambda u, p: None
    c109.authenticate = lambda u, p: None

    monkeypatch.setattr(runner, "JellyfinClient", lambda server, timeout: c108 if "10.8" in server.label else c109)
    monkeypatch.setattr(runner, "find_common_seed_items", lambda clients, manifest, item_type: {
        "v10.8.13": [{"Id": f"id-{i}", "Name": f"Tone {i}", "Type": "Audio"} for i in range(100)],
        "v10.9.0": [{"Id": f"id-{i}", "Name": f"Tone {i}", "Type": "Audio"} for i in range(100)],
    })
    monkeypatch.setattr(runner, "run_case", lambda clients, items, action, level: {
        "action": action.name, "concurrency": level, "status": "passed", "parity": True, "error": None,
        "servers": {c.server.label: {"requests": [], "items": {}} for c in clients},
    })
    monkeypatch.setattr(runner, "write_report", lambda path, data: (_ for _ in ()).throw(IOError("Disk full")))

    exit_code = runner.main(["--report", str(tmp_path / "never.json")])
    assert exit_code != 0


def test_run_case_request_error_and_cleanup_error_coexist():
    runner = load_runner_module()
    init_108 = {
        ID_1: {"is_favorite": False, "in_favorites": False},
    }
    init_109 = {
        ID_1: {"is_favorite": False, "in_favorites": False},
    }
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    # Fail request on 108
    def failing_req(method, path, **kwargs):
        if "FavoriteItems" in path:
            raise SetupError("Batch mutation exploded")
        return FakeResponse(204, b"")

    c108.request = failing_req
    # Also fail cleanup
    c108.fail_cleanup_ids.add(ID_1)

    items_by_server = {
        "v10.8.13": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
        "v10.9.0": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
    }

    res = runner.run_case([c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=1)
    assert res["status"] == "failed"
    reqs_108 = res["servers"]["v10.8.13"]["requests"]
    assert reqs_108[0]["status"] == "failed"
    assert "Batch mutation exploded" in reqs_108[0]["error"]

    items_108 = res["servers"]["v10.8.13"]["items"]
    assert items_108[ID_1]["cleanup"] == "failed"
    assert items_108[ID_1]["cleanup_error"] is not None


def test_run_case_cleanup_readback_mismatch_fails():
    runner = load_runner_module()
    init_108 = {
        ID_1: {"is_favorite": False, "in_favorites": False},
    }
    init_109 = {
        ID_1: {"is_favorite": False, "in_favorites": False},
    }
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    c108.in_cleanup = False
    original_json = c108.json
    def broken_cleanup_json(method, path, **kwargs):
        data = original_json(method, path, **kwargs)
        if getattr(c108, "in_cleanup", False):
            if "UserData" in data:
                data["UserData"]["IsFavorite"] = True
            elif "Items" in data:
                data["Items"] = [{"Id": ID_1}]
        return data

    c108.json = broken_cleanup_json

    # When request is DELETE (which happens in cleanup to restore False):
    original_request = c108.request
    def tracking_request(method, path, **kwargs):
        if method == "DELETE" and len(c108.mutations) > 0:
            c108.in_cleanup = True
        return original_request(method, path, **kwargs)

    c108.request = tracking_request

    items_by_server = {
        "v10.8.13": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
        "v10.9.0": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
    }

    res = runner.run_case([c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=1)
    assert res["status"] == "failed"
    item_108 = res["servers"]["v10.8.13"]["items"][ID_1]
    assert item_108["cleanup"] == "failed"
    assert "Restored state mismatch" in item_108["cleanup_error"]


def test_run_case_cleanup_error_appended_when_verification_error_present():
    runner = load_runner_module()
    init_108 = {ID_1: {"is_favorite": False, "in_favorites": False}}
    init_109 = {ID_1: {"is_favorite": False, "in_favorites": False}}
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    # During batch, don't update state to True -> causes post-batch verification failure
    # During cleanup, raise error -> causes cleanup failure
    def mock_request(method, path, **kwargs):
        if method == "POST":
            return FakeResponse(204, b"")
        if method == "DELETE":
            raise SetupError("Cleanup restore exploded")
        return FakeResponse(204, b"")

    c108.request = mock_request

    items_by_server = {
        "v10.8.13": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
        "v10.9.0": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
    }

    res = runner.run_case([c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=1)
    assert res["status"] == "failed"
    assert res["error"] is not None
    # Must contain both the verification failure and the cleanup failure
    assert "verification" in res["error"].lower()
    assert "cleanup failed" in res["error"].lower()
    assert "cleanup restore exploded" in res["error"].lower()


def test_run_case_populates_error_on_batch_request_failure():
    runner = load_runner_module()
    init_108 = {ID_1: {"is_favorite": False, "in_favorites": False}}
    init_109 = {ID_1: {"is_favorite": False, "in_favorites": False}}
    c108 = StatefulItemClient("v10.8.13", initial_states=init_108)
    c109 = StatefulItemClient("v10.9.0", initial_states=init_109)

    # Mock batch runner to return failed request, but verification somehow passes
    original_run_batch = runner.run_concurrent_batch
    def failed_batch(clients, items, action, concurrency):
        return {
            "servers": {
                "v10.8.13": {"requests": [{"item_id": ID_1, "item_name": "Tone 1", "status": "failed", "response": None, "error": "HTTP 500"}]},
                "v10.9.0": {"requests": [{"item_id": ID_1, "item_name": "Tone 1", "status": "passed", "response": None, "error": None}]},
            }
        }
    runner.run_concurrent_batch = failed_batch

    items_by_server = {
        "v10.8.13": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
        "v10.9.0": [{"Id": ID_1, "Name": "Tone 1", "Type": "Audio"}],
    }

    try:
        # Pre-set states to True so verification passes
        c108.states[ID_1] = {"is_favorite": True, "in_favorites": True}
        c109.states[ID_1] = {"is_favorite": True, "in_favorites": True}
        res = runner.run_case([c108, c109], items_by_server, FavoriteAction.MARK_FAVORITE, concurrency=1)
        assert res["status"] == "failed"
        assert res["error"] is not None
        assert "request" in res["error"].lower() or "batch" in res["error"].lower()
    finally:
        runner.run_concurrent_batch = original_run_batch





