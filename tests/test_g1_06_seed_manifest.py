import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "g1_06_setup_and_verify.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("g1_06_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_generates_deterministic_seed_media(tmp_path):
    runner = load_runner_module()
    manifest = json.loads((ROOT / "data" / "dataset-manifest.json").read_text())

    first = runner.prepare_seed_media(manifest, tmp_path / "first")
    second = runner.prepare_seed_media(manifest, tmp_path / "second")

    assert first == second
    assert len(first) == len(manifest["files"])
    assert all(int(item["bytes"]) > 44 for item in first)
