import importlib.util
import sys
from pathlib import Path

import pytest

from models.user_data_model import FavoriteAction, FavoriteState


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "g2_10_stateful_differential.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("g2_10_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    status_code = 204
    content = b""


class FakeClient:
    def __init__(self, label):
        self.server = type("Server", (), {"label": label})()
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("params")))
        return FakeResponse()


def test_favorite_request_maps_versioned_routes():
    runner = load_runner_module()
    legacy = FakeClient("v10.8.13")
    current = FakeClient("v10.9.0")

    runner.favorite_request(legacy, FavoriteAction.MARK_FAVORITE, "user", "item")
    runner.favorite_request(current, FavoriteAction.UNMARK_FAVORITE, "user", "item")

    assert legacy.calls == [("POST", "/Users/user/FavoriteItems/item", None)]
    assert current.calls == [("DELETE", "/UserFavoriteItems/item", {"userId": "user"})]


def test_consistent_states_rejects_cross_version_mismatch():
    runner = load_runner_module()
    expected = {"user_a": FavoriteState.FAVORITED}

    with pytest.raises(runner.SetupError, match="semantic state mismatch"):
        runner.assert_consistent_states(
            expected,
            {"user_a": FavoriteState.FAVORITED},
            {"user_a": FavoriteState.UNFAVORITED},
        )
