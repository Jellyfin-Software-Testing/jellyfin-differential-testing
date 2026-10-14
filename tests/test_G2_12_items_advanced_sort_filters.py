import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "G2_12_items_advanced_sort_filters.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("g2_12_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_semantic_keys_extracts_name_and_type():
    runner = load_runner_module()
    items = [
        {"Name": "Song A", "Type": "Audio", "SortName": "Song A"},
        {"Name": "Song B", "Type": "Audio", "SortName": "Song B"},
    ]
    assert runner.semantic_keys(items, "v10.8.13") == [("Song A", "Audio"), ("Song B", "Audio")]


def test_semantic_keys_raises_setup_error_on_missing_field():
    runner = load_runner_module()
    bad_items = [
        {"Name": "Song A", "SortName": "Song A"},  # missing Type
    ]
    with pytest.raises(runner.SetupError, match="v10.8.13.*missing.*Type"):
        runner.semantic_keys(bad_items, "v10.8.13")


def test_verify_server_results_success_ascending():
    runner = load_runner_module()
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    item_b = {"Name": "Song B", "Type": "Audio", "SortName": "B"}
    baseline = {"Items": [item_a, item_b], "StartIndex": 0, "TotalRecordCount": 2}
    pages = {
        0: {"Items": [item_a], "StartIndex": 0, "TotalRecordCount": 2},
        1: {"Items": [item_b], "StartIndex": 1, "TotalRecordCount": 2},
    }
    keys = runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)
    assert keys == [("Song A", "Audio"), ("Song B", "Audio")]


def test_verify_server_results_success_descending():
    runner = load_runner_module()
    item_b = {"Name": "Song B", "Type": "Audio", "SortName": "B"}
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    baseline = {"Items": [item_b, item_a], "StartIndex": 0, "TotalRecordCount": 2}
    pages = {
        0: {"Items": [item_b], "StartIndex": 0, "TotalRecordCount": 2},
        1: {"Items": [item_a], "StartIndex": 1, "TotalRecordCount": 2},
    }
    keys = runner.verify_server_results("v10.8.13", "Descending", baseline, pages, limit=1)
    assert keys == [("Song B", "Audio"), ("Song A", "Audio")]


def test_verify_server_results_rejects_incomplete_baseline():
    runner = load_runner_module()
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    # len(Items) != TotalRecordCount
    baseline = {"Items": [item_a], "StartIndex": 0, "TotalRecordCount": 2}
    pages = {0: {"Items": [item_a], "StartIndex": 0, "TotalRecordCount": 2}}
    with pytest.raises(runner.SetupError, match="baseline length"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)

    # StartIndex != 0
    baseline2 = {"Items": [item_a], "StartIndex": 1, "TotalRecordCount": 1}
    with pytest.raises(runner.SetupError, match="baseline StartIndex"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline2, pages, limit=1)


def test_verify_server_results_rejects_wrong_order():
    runner = load_runner_module()
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    item_b = {"Name": "Song B", "Type": "Audio", "SortName": "B"}
    # Expected Ascending, but given B then A
    baseline = {"Items": [item_b, item_a], "StartIndex": 0, "TotalRecordCount": 2}
    pages = {
        0: {"Items": [item_b], "StartIndex": 0, "TotalRecordCount": 2},
        1: {"Items": [item_a], "StartIndex": 1, "TotalRecordCount": 2},
    }
    with pytest.raises(runner.SetupError, match="not in Ascending order"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)


def test_verify_server_results_rejects_page_count_mismatch_with_baseline():
    runner = load_runner_module()
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    item_b = {"Name": "Song B", "Type": "Audio", "SortName": "B"}
    baseline = {"Items": [item_a, item_b], "StartIndex": 0, "TotalRecordCount": 2}
    pages = {0: {"Items": [item_a], "StartIndex": 0, "TotalRecordCount": 99}}
    with pytest.raises(runner.SetupError, match="TotalRecordCount mismatch"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)


def test_verify_server_results_rejects_page_slice_mismatch():
    runner = load_runner_module()
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    item_b = {"Name": "Song B", "Type": "Audio", "SortName": "B"}
    baseline = {"Items": [item_a, item_b], "StartIndex": 0, "TotalRecordCount": 2}
    # Page 0 returns item_b instead of item_a
    pages = {
        0: {"Items": [item_b], "StartIndex": 0, "TotalRecordCount": 2},
        1: {"Items": [item_b], "StartIndex": 1, "TotalRecordCount": 2},
    }
    with pytest.raises(runner.SetupError, match="slice mismatch"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)


def test_verify_server_results_rejects_page_exceeding_limit():
    runner = load_runner_module()
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    item_b = {"Name": "Song B", "Type": "Audio", "SortName": "B"}
    baseline = {"Items": [item_a, item_b], "StartIndex": 0, "TotalRecordCount": 2}
    pages = {
        0: {"Items": [item_a, item_b], "StartIndex": 0, "TotalRecordCount": 2},
    }
    with pytest.raises(runner.SetupError, match="exceeds limit"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)


def test_assert_version_parity_success_and_failure():
    runner = load_runner_module()
    v108 = {
        "Ascending": [("Song A", "Audio"), ("Song B", "Audio")],
        "Descending": [("Song B", "Audio"), ("Song A", "Audio")],
    }
    v109_matching = {
        "Ascending": [("Song A", "Audio"), ("Song B", "Audio")],
        "Descending": [("Song B", "Audio"), ("Song A", "Audio")],
    }
    # Should not raise
    runner.assert_version_parity(v108, v109_matching)

    v109_mismatch = {
        "Ascending": [("Song X", "Audio"), ("Song B", "Audio")],
        "Descending": [("Song B", "Audio"), ("Song A", "Audio")],
    }
    with pytest.raises(runner.SetupError, match="Cross-version parity mismatch"):
        runner.assert_version_parity(v108, v109_mismatch)


class FakeRunnerClient:
    def __init__(self, label: str):
        self.server = type("Server", (), {"label": label, "url": f"http://fake-{label}"})()
        self.user_id = f"user_{label}"
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def authenticate(self, username, password):
        pass

    def json(self, method: str, path: str, **kwargs):
        params = kwargs.get("params")
        self.calls.append((method, path, params))
        if path == "/Library/VirtualFolders":
            return [{"Name": "Differential Seed Music", "ItemId": "lib_seed_01"}]
        if path == "/Items":
            order = params.get("SortOrder")
            item_a = {"Name": "01 - Song A", "Type": "Audio", "SortName": "01 - Song A"}
            item_b = {"Name": "02 - Song B", "Type": "Audio", "SortName": "02 - Song B"}
            items = [item_a, item_b] if order == "Ascending" else [item_b, item_a]

            start_idx = params.get("StartIndex", 0)
            limit = params.get("Limit")
            if limit is None:
                page_items = items
            else:
                page_items = items[start_idx : start_idx + limit]

            return {
                "Items": page_items,
                "StartIndex": start_idx,
                "TotalRecordCount": len(items),
            }
        return {}


def test_runner_queries_seed_music_baseline_and_pages():
    runner = load_runner_module()
    clients = [FakeRunnerClient("v10.8.13"), FakeRunnerClient("v10.9.0")]
    report = runner.run_differential_sorting(clients)

    assert report["status"] == "equivalent"
    for client in clients:
        item_calls = [c for c in client.calls if c[1] == "/Items"]
        # 2 orders (Ascending, Descending) * 3 requests each (baseline, page 0, page 1) = 6 calls
        assert len(item_calls) == 6
        for _, _, params in item_calls:
            assert params["UserId"] == client.user_id
            assert params["ParentId"] == "lib_seed_01"
            assert params["Recursive"] == "true"
            assert params["IncludeItemTypes"] == "Audio"
            assert params["SortBy"] == "SortName"
            assert params["Fields"] == "SortName"

        # Check baseline vs pages limit and startIndex
        baseline_calls = [c for c in item_calls if "Limit" not in c[2]]
        assert len(baseline_calls) == 2
        for _, _, p in baseline_calls:
            assert p["StartIndex"] == 0

        page_calls = [c for c in item_calls if "Limit" in c[2]]
        assert len(page_calls) == 4
        for _, _, p in page_calls:
            assert p["Limit"] == 1
            assert p["StartIndex"] in (0, 1)


def test_runner_starts_when_called_as_a_script():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "G2-12" in result.stdout


def test_verify_server_results_rejects_wrong_page_start_index():
    runner = load_runner_module()
    item_a = {"Name": "Song A", "Type": "Audio", "SortName": "A"}
    item_b = {"Name": "Song B", "Type": "Audio", "SortName": "B"}
    baseline = {"Items": [item_a, item_b], "StartIndex": 0, "TotalRecordCount": 2}
    # Page offset is 0, but response StartIndex is 1
    pages = {0: {"Items": [item_a], "StartIndex": 1, "TotalRecordCount": 2}}
    with pytest.raises(runner.SetupError, match="returned StartIndex 1"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)


def test_run_differential_sorting_rejects_identical_wrong_pages():
    runner = load_runner_module()
    # Both clients return identical corrupted page that does not match baseline
    class BadPageClient(FakeRunnerClient):
        def json(self, method: str, path: str, **kwargs):
            res = super().json(method, path, **kwargs)
            if path == "/Items" and kwargs.get("params", {}).get("Limit") is not None:
                # Corrupt the page slice to return unexpected item
                res["Items"] = [{"Name": "Wrong Item", "Type": "Audio", "SortName": "Wrong"}]
            return res

    clients = [BadPageClient("v10.8.13"), BadPageClient("v10.9.0")]
    with pytest.raises(runner.SetupError, match="slice mismatch"):
        runner.run_differential_sorting(clients)


def test_verify_server_results_rejects_empty_seed_library():
    runner = load_runner_module()
    baseline = {"Items": [], "StartIndex": 0, "TotalRecordCount": 0}
    pages = {0: {"Items": [], "StartIndex": 0, "TotalRecordCount": 0}}
    with pytest.raises(runner.SetupError, match="at least 2 items"):
        runner.verify_server_results("v10.8.13", "Ascending", baseline, pages, limit=1)


def test_run_differential_sorting_requires_at_least_two_clients():
    runner = load_runner_module()
    single_client = [FakeRunnerClient("v10.8.13")]
    with pytest.raises(runner.SetupError, match="requires at least two servers"):
        runner.run_differential_sorting(single_client)


def test_assert_version_parity_rejects_missing_order_keys():
    runner = load_runner_module()
    v108 = {}
    v109 = {}
    with pytest.raises(runner.SetupError, match="Missing sort order"):
        runner.assert_version_parity(v108, v109)
