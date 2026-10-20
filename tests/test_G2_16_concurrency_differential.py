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


