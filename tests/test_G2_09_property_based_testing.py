# tests/test_G2_09_property_based_testing.py

import pytest
from hypothesis import given, strategies as st, settings, Verbosity, HealthCheck, note
from normalizer.G2_07_diff_engine import SemanticDiffEngine

# 1. Định nghĩa Strategies chuẩn theo 6 yêu cầu Jira (G2-09)
unicode_strategy = st.text(alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S')), min_size=1, max_size=20)
special_chars_strategy = st.sampled_from(["!@#$%^&*()_+-=[]{}|;:',.<>?/`~"])
injection_strategy = st.sampled_from(["system' OR '1'='1", "<script>alert('xss')</script>", "1; DROP TABLE users;"])
long_string_strategy = st.text(min_size=200, max_size=500)
empty_string_strategy = st.just("")
boundary_strategy = st.one_of(st.just(0), st.just(-1), st.just(2147483647), st.just(-2147483648))

fuzz_input_strategy = st.one_of(
    unicode_strategy,
    special_chars_strategy,
    injection_strategy,
    long_string_strategy,
    empty_string_strategy,
    boundary_strategy
)

HYPOTHESIS_SETTINGS = settings(
    max_examples=30,
    verbosity=Verbosity.quiet,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)

# --------------------------------------------------------------------------
# TEST CASE 1: In log chứng minh sinh dữ liệu ngẫu nhiên đa dạng thành công
# --------------------------------------------------------------------------
@HYPOTHESIS_SETTINGS
@given(val=fuzz_input_strategy)
def test_property_identical_inputs_never_fail(val):
    engine = SemanticDiffEngine()
    
    # In log input ra màn hình Terminal bằng note() của Hypothesis
    note(f"[GENERATED INPUT]: {repr(val)}")
    
    v1 = {"status": 200, "headers": {}, "body": {"query": val}}
    v2 = {"status": 200, "headers": {}, "body": {"query": val}}

    diffs = engine.compare_responses(
        v1_status=v1["status"], v2_status=v2["status"],
        v1_headers=v1["headers"], v2_headers=v2["headers"],
        v1_body=v1["body"], v2_body=v2["body"]
    )

    assert len(diffs) == 0, f"False Positive detected for input: {repr(val)}"


# --------------------------------------------------------------------------
# TEST CASE 2: Chứng minh cơ chế MINIMAL FAILURE SHRINKING khi gặp lỗi
# (Giả lập bug: Nếu chuỗi chứa từ 'DROP' hoặc ký tự 'x' thì cố tình báo lỗi)
# --------------------------------------------------------------------------
@pytest.mark.xfail(reason="Cố tình fail để minh họa cơ chế Shrinking của Hypothesis")
@HYPOTHESIS_SETTINGS
@given(val=st.text())
def test_demonstrate_hypothesis_shrinking(val):
    # Giả định hệ thống bị bug khi xuất hiện chữ 'x'
    if "x" in val:
        assert False, f"Bug triggered by input containing 'x': {repr(val)}"