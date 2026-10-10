# G2-06A Normalization Mutation Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add endpoint-scoped runtime normalization rules and deterministic mutation fixtures proving noise is removed without hiding real defects.

**Architecture:** `SemanticNormalizer` compiles an endpoint into every rule and applies only exact endpoint matches. A separate runtime config supplies `MASK_STRING`, `REGEX_REPLACE`, and `MAP_STATE` rules; a data-driven offline suite compares controlled fixture pairs before and after normalization.

**Tech Stack:** Python 3.10+, standard library (`copy`, `dataclasses`, `json`, `pathlib`, `re`), pytest

**Spec:** `docs/superpowers/specs/2026-10-09-g2-06a-normalization-mutation-validation-design.md`

## Global Constraints

- Do not modify `config/ignore-rules.json`; it remains G2-02 catalog/evidence.
- Add no dependency and require no network, Docker, or running Jellyfin instance.
- Require explicit endpoint context; do not add a global/default endpoint.
- Preserve `DROP` behavior and rule file ordering.
- `MASK_STRING` masks only Python `str`; missing, `None`, numbers, lists, and objects remain observable.
- Fixtures must be deterministic and must prove `base != mutated` before checking normalized equality.

## Review Focus

- Lowercase or whitespace-containing endpoint configuration must fail fast rather than silently create an unreachable rule; pinned in Task 1.
- Two valid endpoints sharing the same JSONPath must not affect each other; pinned in Task 1.
- `MASK_STRING` on direct wildcard leaves must preserve non-string elements; pinned in Task 2.
- Regex text that does not match must remain byte-for-byte unchanged; pinned in Task 3.
- Collection reordering must remain visible because no sorting rule exists; pinned in Task 3.

---

## File Structure

- Modify `normalizer/semantic_normalizer.py`: endpoint validation/filtering and `MASK_STRING` execution.
- Modify `tests/test_semantic_normalizer.py`: migrate unit tests to explicit endpoints and pin the new contract.
- Create `config/normalization-rules.json`: four auditable runtime rules covering authentication, playback, and item identity.
- Create `tests/fixtures/normalization-cases.json`: controlled noise-only, bug-only, and mixed mutations.
- Create `tests/test_normalization_mutations.py`: load production rules and execute the fixture oracle.

### Task 1: Endpoint-scoped rule contract

**Files:**
- Modify: `normalizer/semantic_normalizer.py:9-173`
- Modify: `tests/test_semantic_normalizer.py:9-377`

**Interfaces:**
- Consumes: Existing JSON root with a `rules` array and existing JSONPath/action semantics.
- Produces: `CompiledRule.endpoint: str`; `SemanticNormalizer.normalize(payload: Any, endpoint: str, state_mapping: Mapping[Any, Any] | None = None) -> Any`.

- [ ] **Step 1: Migrate the unit-test helper and calls to the explicit endpoint contract**

In `tests/test_semantic_normalizer.py`, define `TEST_ENDPOINT = "GET /Test"`; make `load_rules()` add that endpoint to inline rules; pass `endpoint=TEST_ENDPOINT` to every `normalize()` call. Change the real-config loading test to target `config/normalization-rules.json` but leave its final rule-count assertion for Task 2.

- [ ] **Step 2: Write failing endpoint validation and isolation tests**

Add tests with these assertions:

```python
@pytest.mark.parametrize("endpoint", [None, 123, "get /Items", "GET Items", "GET  /Items", "GET /Items with-space"])
def test_rejects_missing_or_invalid_endpoint(tmp_path, endpoint):
    # Write one DROP rule, omitting endpoint for None.
    with pytest.raises(NormalizerConfigError, match="endpoint"):
        SemanticNormalizer.from_file(config_file)

def test_only_rules_for_exact_endpoint_are_applied(tmp_path):
    # Two DROP rules use $.Token but endpoints GET /A and GET /B.
    assert normalizer.normalize({"Token": "x"}, endpoint="GET /A") == {}
    assert normalizer.normalize({"Token": "x"}, endpoint="GET /C") == {"Token": "x"}
```

- [ ] **Step 3: Run the endpoint tests and verify failure**

Run: `python -m pytest tests/test_semantic_normalizer.py -q`

Expected: FAIL because rules do not compile `endpoint` and `normalize()` does not require/filter it.

- [ ] **Step 4: Implement endpoint compilation and exact filtering**

In `normalizer/semantic_normalizer.py`:

- Add `endpoint: str` to `CompiledRule`.
- Validate with `_ENDPOINT_RE = re.compile(r"^[A-Z]+ /\S+$")`; missing, non-string, or non-matching values raise `NormalizerConfigError` containing rule index and `endpoint`.
- Change `normalize()` to the exact signature in Interfaces.
- In its rule loop, call `_apply_rule` only when `rule.endpoint == endpoint`.

- [ ] **Step 5: Run the migrated unit suite**

Run: `python -m pytest tests/test_semantic_normalizer.py -q`

Expected: all tests except the Task 2 real-config rule-count assertion pass.

- [ ] **Step 6: Commit endpoint scoping**

```bash
git add normalizer/semantic_normalizer.py tests/test_semantic_normalizer.py
git commit -m "feat(G2-06A): scope normalization rules by endpoint"
```

### Task 2: Schema-preserving string masking and runtime rules

**Files:**
- Create: `config/normalization-rules.json`
- Modify: `normalizer/semantic_normalizer.py:11-234`
- Modify: `tests/test_semantic_normalizer.py`

**Interfaces:**
- Consumes: Task 1 endpoint-scoped `CompiledRule` and `normalize()`.
- Produces: `MASK_STRING` action with required `replacement: str`; production `SemanticNormalizer` containing exactly four rules.

- [ ] **Step 1: Write failing `MASK_STRING` configuration and behavior tests**

Add tests proving:

Add `test_mask_string_requires_string_replacement`, parametrized over missing, `None`, integer, and list replacements; each load must raise `NormalizerConfigError` matching `replacement`.

Add `test_mask_string_preserves_schema_and_type_defects`. With replacement `<TOKEN>`, assert a string becomes `<TOKEN>`, while `None`, integer, object, and a missing field remain unchanged.

Add `test_leaf_wildcard_mask_string_only_masks_strings`. For `{"Values": ["a", None, 1, {"x": 1}]}`, assert the result is `{"Values": ["<MASKED>", None, 1, {"x": 1}]}`. Use `TEST_ENDPOINT` in every call.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m pytest tests/test_semantic_normalizer.py -q -k 'mask_string'`

Expected: FAIL with unsupported action `MASK_STRING`.

- [ ] **Step 3: Implement minimal `MASK_STRING` support**

Add `MASK_STRING` to `_SUPPORTED_ACTIONS`. Require a string `replacement` during compilation. In `_apply_action`, return the replacement only when `val` is a `str`; otherwise return `(False, val)`.

- [ ] **Step 4: Create the four-rule runtime config**

Create `config/normalization-rules.json` with these exact rules, in order:

1. `POST /Users/AuthenticateByName`, `$.AccessToken`, `MASK_STRING`, `<SESSION_TOKEN>`.
2. `POST /Users/AuthenticateByName`, `$.User.Id`, `MAP_STATE`.
3. `GET /Items`, `$.Items[*].Id`, `MAP_STATE`.
4. `GET /Items`, `$.Items[*].MediaSources[*].TranscodingUrl`, `REGEX_REPLACE`, pattern `(?<=SessionId=)[a-zA-Z0-9]+`, replacement `<MASKED_SESSION>`.

Set `test_loads_real_normalization_rules` to assert `rule_count == 4`.

- [ ] **Step 5: Run the full normalizer unit suite**

Run: `python -m pytest tests/test_semantic_normalizer.py -q`

Expected: PASS.

- [ ] **Step 6: Commit masking and runtime configuration**

```bash
git add config/normalization-rules.json normalizer/semantic_normalizer.py tests/test_semantic_normalizer.py
git commit -m "feat(G2-06A): add schema-preserving runtime rules"
```

### Task 3: Mutation fixture validation

**Files:**
- Create: `tests/fixtures/normalization-cases.json`
- Create: `tests/test_normalization_mutations.py`

**Interfaces:**
- Consumes: `SemanticNormalizer.from_file(ROOT / "config" / "normalization-rules.json")` and Task 1 `normalize()` signature.
- Produces: Data-driven regression oracle for runtime rules; no product API.

- [ ] **Step 1: Write the fixture loader and failing oracle test**

Create `tests/test_normalization_mutations.py` with a module-scoped fixture loader and one parametrized test named `test_controlled_mutation_preserves_expected_signal`. For each case:

```python
assert case["base"] != case["mutated"]
base = normalizer.normalize(case["base"], endpoint=case["endpoint"], state_mapping=case.get("state_mapping"))
mutated = normalizer.normalize(case["mutated"], endpoint=case["endpoint"], state_mapping=case.get("state_mapping"))
assert (base == mutated) is case["expected_equal_after_normalization"]
```

Assert fixture names are unique and `mutation_kind` is one of `noise_only`, `real_bug`, `noise_and_real_bug`.

- [ ] **Step 2: Add deterministic authentication cases**

In `tests/fixtures/normalization-cases.json`, add cases for token noise convergence, token versus missing/`null`/number/object divergence, mapped user IDs convergence, unknown user IDs divergence, changed admin policy divergence, and token noise plus changed admin policy divergence.

- [ ] **Step 3: Add deterministic playback cases**

Add cases for SessionId-only convergence; SessionId plus codec divergence; two unequal URLs with no regex match remaining unchanged and divergent; nested wildcard noise across two items converging; and endpoint `GET /Other` preventing the `GET /Items` URL rule from firing.

- [ ] **Step 4: Add deterministic item collection cases**

Add cases for mapped item IDs convergence, unknown IDs divergence, changed `Name` divergence, field addition/removal divergence, item addition/removal divergence, and reordered items divergence.

- [ ] **Step 5: Run mutation validation**

Run: `python -m pytest tests/test_normalization_mutations.py -q`

Expected: PASS with every JSON case collected; failures display the case `name` via pytest parameter IDs.

- [ ] **Step 6: Commit mutation fixtures**

```bash
git add tests/fixtures/normalization-cases.json tests/test_normalization_mutations.py
git commit -m "test(G2-06A): validate normalization with controlled mutations"
```

### Task 4: Full offline regression gate

**Files:**
- Verify: `normalizer/semantic_normalizer.py`
- Verify: `config/normalization-rules.json`
- Verify: `tests/test_semantic_normalizer.py`
- Verify: `tests/test_normalization_mutations.py`

**Interfaces:**
- Consumes: Tasks 1-3 completed commits.
- Produces: Evidence that G2-06A and the repository test suite pass without live services.

- [ ] **Step 1: Run focused G2-06A tests**

Run: `python -m pytest tests/test_semantic_normalizer.py tests/test_normalization_mutations.py -q`

Expected: PASS.

- [ ] **Step 2: Run the complete offline test suite**

Run: `python -m pytest -q`

Expected: PASS; no test requires Docker, network, or live Jellyfin.

- [ ] **Step 3: Check repository diff hygiene**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intentional G2-06A changes, plan tracking, or pre-existing untracked `.codegraph/` appear.

- [ ] **Step 4: Commit any test-only corrections required by the full gate**

If Step 2 required corrections, commit only those corrections:

```bash
git add <corrected-files>
git commit -m "test(G2-06A): complete offline regression coverage"
```

If no correction was needed, do not create an empty commit.
