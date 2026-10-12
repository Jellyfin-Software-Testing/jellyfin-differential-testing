import json
from pathlib import Path

import pytest

from normalizer import SemanticNormalizer

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "normalization-cases.json"
CASES = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mutation_cases():
    cases = CASES
    assert len({case["name"] for case in cases}) == len(cases)
    assert {case["mutation_kind"] for case in cases} <= {
        "noise_only", "real_bug", "noise_and_real_bug"
    }
    return cases


@pytest.fixture(scope="module")
def normalizer():
    return SemanticNormalizer.from_file(ROOT / "config" / "normalization-rules.json")


@pytest.mark.parametrize("case_name", [case["name"] for case in CASES], ids=str)
def test_controlled_mutation_preserves_expected_signal(normalizer, mutation_cases, case_name):
    case = next(case for case in mutation_cases if case["name"] == case_name)
    assert case["base"] != case["mutated"]
    base = normalizer.normalize(
        case["base"], endpoint=case["endpoint"], state_mapping=case.get("state_mapping")
    )
    mutated = normalizer.normalize(
        case["mutated"], endpoint=case["endpoint"], state_mapping=case.get("state_mapping")
    )
    assert (base == mutated) is case["expected_equal_after_normalization"]
