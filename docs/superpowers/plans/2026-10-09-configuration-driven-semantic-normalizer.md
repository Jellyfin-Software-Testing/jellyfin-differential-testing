# Configuration-Driven Semantic Normalizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python module that compiles `config/ignore-rules.json` and recursively normalizes JSON-compatible payloads with `DROP`, `REGEX_REPLACE`, and `MAP_STATE` rules.

**Architecture:** `SemanticNormalizer.from_file()` validates and compiles ordered rules into field/wildcard path tokens. `normalize()` deep-copies a payload once, follows only each rule's addressed branches, and applies an action at matching leaves without mutating raw evidence.

**Tech Stack:** Python 3.10+, standard library (`copy`, `json`, `pathlib`, `re`, `dataclasses`, `typing`), pytest 8.1.1

**Spec:** `docs/superpowers/specs/2026-10-09-configuration-driven-semantic-normalizer-design.md`

## Global Constraints

- Add no dependency; use only the Python standard library.
- Support only `$`, `.field`, and `[*]` path syntax.
- Preserve rule order exactly as declared in the configuration.
- Return a deep copy and never mutate the input payload.
- Keep unknown paths, incompatible runtime types, and unmapped IDs unchanged.
- Do not add Comparator integration, CLI behavior, logging, or broader JSONPath syntax.

## Review Focus

- An empty `rules` list is valid and returns an equal but distinct deep copy; pin this in Task 2.
- Wildcards may traverse lists containing dictionaries, scalars, and nested lists; incompatible elements are no-ops; pin this in Task 2.
- A regex replacement with an invalid group reference is invalid configuration and must fail during loading, not during a test run; pin this in Task 1.
- Unreadable files and malformed JSON must be wrapped as `NormalizerConfigError` with the source path; pin this in Task 1.
- Python mapping keys can be hashable non-strings; `MAP_STATE` must map known hashable values while preserving unhashable leaves; pin this in Task 2.

---

## File Structure

- `normalizer/__init__.py`: package exports for `SemanticNormalizer` and `NormalizerConfigError`.
- `normalizer/semantic_normalizer.py`: configuration validation, path compilation, recursive traversal, and action execution.
- `tests/test_semantic_normalizer.py`: unit and configuration integration tests for the complete public contract.

### Task 1: Configuration and Path Compiler

**Files:**

- Create: `normalizer/__init__.py`
- Create: `normalizer/semantic_normalizer.py`
- Create: `tests/test_semantic_normalizer.py`

**Interfaces:**

- Consumes: JSON configuration shaped as `{"rules": [rule, ...]}` and a `str | pathlib.Path` source path.
- Produces: `NormalizerConfigError(ValueError)` and `SemanticNormalizer.from_file(path: str | Path) -> SemanticNormalizer`; compiled rules remain private and ordered for Task 2.

- [ ] **Step 1: Write failing tests for valid configuration compilation**

Add tests named:

```python
def test_loads_real_ignore_rules():
    normalizer = SemanticNormalizer.from_file(ROOT / "config" / "ignore-rules.json")
    assert normalizer.rule_count == 6


def test_accepts_supported_field_and_wildcard_paths(tmp_path):
    normalizer = load_rules(tmp_path, [
        {"path": "$.AccessToken", "action": "DROP"},
        {"path": "$.User.Id", "action": "MAP_STATE"},
        {
            "path": "$.MediaSources[*].TranscodingUrl",
            "action": "REGEX_REPLACE",
            "pattern": "token=[^&]+",
            "replacement": "token=<MASKED>",
        },
    ])
    assert normalizer.rule_count == 3
```

`load_rules()` is a test-only helper that writes `{"rules": rules}` and calls `from_file()`.

- [ ] **Step 2: Run the valid-configuration tests and confirm the expected failure**

Run: `python -m pytest tests/test_semantic_normalizer.py::test_loads_real_ignore_rules tests/test_semantic_normalizer.py::test_accepts_supported_field_and_wildcard_paths -q`

Expected: FAIL during import because `normalizer` does not exist.

- [ ] **Step 3: Add package exports and the minimal compiler API**

In `normalizer/semantic_normalizer.py`, define:

```python
class NormalizerConfigError(ValueError): ...

class SemanticNormalizer:
    @classmethod
    def from_file(cls, path: str | Path) -> "SemanticNormalizer": ...

    @property
    def rule_count(self) -> int: ...
```

Use private immutable dataclasses/tuples for compiled rules and tokens. Parse only the grammar from the spec, compile regex patterns once, and preserve file order. Export the two public classes from `normalizer/__init__.py`.

- [ ] **Step 4: Run the valid-configuration tests**

Run: `python -m pytest tests/test_semantic_normalizer.py::test_loads_real_ignore_rules tests/test_semantic_normalizer.py::test_accepts_supported_field_and_wildcard_paths -q`

Expected: `2 passed`.

- [ ] **Step 5: Write failing parameterized tests for invalid configuration**

Add tests covering:

```python
@pytest.mark.parametrize(("document", "message"), [
    ([], "root must be an object"),
    ({}, "missing 'rules' list"),
    ({"rules": {}}, "'rules' must be a list"),
    ({"rules": ["bad"]}, "rule 0"),
    ({"rules": [{"action": "DROP"}]}, "rule 0"),
    ({"rules": [{"path": "Items[*].Id", "action": "DROP"}]}, "Items[*].Id"),
    ({"rules": [{"path": "$.Items[0].Id", "action": "DROP"}]}, "$.Items[0].Id"),
    ({"rules": [{"path": "$.Id", "action": "MASK"}]}, "MASK"),
    ({"rules": [{"path": "$.Url", "action": "REGEX_REPLACE"}]}, "pattern"),
    ({"rules": [{"path": "$.Url", "action": "REGEX_REPLACE", "pattern": "[", "replacement": "x"}]}, "$.Url"),
])
def test_rejects_invalid_configuration(tmp_path, document, message): ...
```

Also add focused tests asserting:

- missing/non-string `replacement` fails;
- invalid replacement group reference such as `pattern="(x)"`, `replacement=r"\2"` fails during `from_file()`;
- malformed JSON is wrapped as `NormalizerConfigError` and includes the file path; and
- a missing file is wrapped as `NormalizerConfigError` and includes the file path.

- [ ] **Step 6: Run invalid-configuration tests and confirm failure**

Run: `python -m pytest tests/test_semantic_normalizer.py -k "rejects_invalid or invalid_replacement or malformed_json or missing_file" -q`

Expected: FAIL because validation and error wrapping are incomplete.

- [ ] **Step 7: Implement fail-fast validation and contextual errors**

Validate all root, rule, action, path, and regex requirements during `from_file()`. Validate replacement group references against the compiled pattern during loading. Wrap file I/O and JSON decoding failures in `NormalizerConfigError`; messages must include the source path, and rule errors must include the zero-based rule index plus path when available.

- [ ] **Step 8: Run Task 1 tests**

Run: `python -m pytest tests/test_semantic_normalizer.py -q`

Expected: all tests currently defined in the file PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add normalizer/__init__.py normalizer/semantic_normalizer.py tests/test_semantic_normalizer.py
git commit -m "[G2-06] Compile semantic normalizer rules"
```

### Task 2: Recursive Normalization Engine

**Files:**

- Modify: `normalizer/semantic_normalizer.py`
- Modify: `tests/test_semantic_normalizer.py`

**Interfaces:**

- Consumes: Task 1's ordered compiled rules, any JSON-compatible payload, and optional `Mapping[Any, Any]` canonical state mapping.
- Produces: `SemanticNormalizer.normalize(payload: Any, state_mapping: Mapping[Any, Any] | None = None) -> Any`.

- [ ] **Step 1: Write failing tests for deep-copy and `DROP` behavior**

Add tests asserting:

```python
def test_drop_removes_root_and_nested_dictionary_fields(tmp_path): ...
def test_drop_through_wildcard_applies_to_every_dictionary(tmp_path): ...
def test_drop_direct_list_elements_replaces_them_with_none(tmp_path): ...
def test_normalize_does_not_mutate_input(tmp_path): ...
def test_empty_rules_return_equal_distinct_deep_copy(tmp_path): ...
```

Use exact expectations including:

- `$.AccessToken` removes only the root key;
- `$.Users[*].Id` transforms `{"Users": [{"Id": "a", "Name": "A"}, {"Id": "b"}]}` to `{"Users": [{"Name": "A"}, {}]}`;
- `$.Values[*]` transforms `{"Values": [1, 2]}` to `{"Values": [None, None]}`; and
- nested input containers are different objects in the returned value.

- [ ] **Step 2: Run `DROP` tests and confirm failure**

Run: `python -m pytest tests/test_semantic_normalizer.py -k "drop or deep_copy or empty_rules" -q`

Expected: FAIL because `normalize()` is absent.

- [ ] **Step 3: Implement deep-copy traversal and `DROP`**

Add the exact public signature:

```python
def normalize(
    self,
    payload: Any,
    state_mapping: Mapping[Any, Any] | None = None,
) -> Any: ...
```

Deep-copy once, then recursively follow field/wildcard tokens. At a matching leaf, delete dictionary keys or assign `None` to list indexes. Missing keys, wrong container types, and mixed wildcard element types are no-ops.

- [ ] **Step 4: Run `DROP` tests**

Run: `python -m pytest tests/test_semantic_normalizer.py -k "drop or deep_copy or empty_rules" -q`

Expected: all selected tests PASS.

- [ ] **Step 5: Write failing tests for `REGEX_REPLACE` and traversal no-ops**

Add tests asserting:

- `$.MediaSources[*].TranscodingUrl` replaces every matching `SessionId` substring using the real rule shape;
- non-string leaves remain unchanged;
- a wildcard list containing dictionaries, scalars, and nested lists only changes compatible dictionary branches;
- absent paths remain absent; and
- field/wildcard container mismatches leave the payload unchanged.

- [ ] **Step 6: Run regex and traversal tests and confirm failure**

Run: `python -m pytest tests/test_semantic_normalizer.py -k "regex or wildcard_mixed or missing_path or incompatible_container" -q`

Expected: FAIL because `REGEX_REPLACE` is not implemented.

- [ ] **Step 7: Implement `REGEX_REPLACE` leaf behavior**

Use the precompiled pattern's `sub()` method only for string leaves. Reuse the traversal from Step 3; do not add a second tree walker.

- [ ] **Step 8: Run regex and traversal tests**

Run: `python -m pytest tests/test_semantic_normalizer.py -k "regex or wildcard_mixed or missing_path or incompatible_container" -q`

Expected: all selected tests PASS.

- [ ] **Step 9: Write failing tests for `MAP_STATE` and ordered rules**

Add tests asserting:

```python
def test_map_state_converges_version_ids_to_one_canonical_id(tmp_path): ...
def test_map_state_preserves_missing_and_unhashable_values(tmp_path): ...
def test_map_state_supports_known_hashable_non_string_values(tmp_path): ...
def test_rules_apply_in_file_order(tmp_path): ...
def test_scalar_payload_is_deep_copied_without_change(tmp_path): ...
```

Use one mapping such as `{"v108-id": "user:admin", "v109-id": "user:admin", 42: "item:42"}`. Prove order with `REGEX_REPLACE` on `$.Token` followed by `DROP` on `$.Token`, expecting the key to be absent. Use a list or dictionary leaf for the unhashable no-op case.

- [ ] **Step 10: Run mapping and ordering tests and confirm failure**

Run: `python -m pytest tests/test_semantic_normalizer.py -k "map_state or file_order or scalar_payload" -q`

Expected: FAIL because `MAP_STATE` is not implemented.

- [ ] **Step 11: Implement `MAP_STATE` and ordered action dispatch**

Treat `None` as an empty mapping. For hashable leaves, replace only keys present in the supplied mapping; preserve missing and unhashable values. Keep action dispatch private and apply compiled rules in their stored order.

- [ ] **Step 12: Run the normalizer test file**

Run: `python -m pytest tests/test_semantic_normalizer.py -q`

Expected: all normalizer tests PASS.

- [ ] **Step 13: Run the full regression suite**

Run: `python -m pytest -q`

Expected: all existing and new tests PASS with no collection errors.

- [ ] **Step 14: Check formatting and unintended changes**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; the normalizer package and test file are the only implementation changes shown. The approved spec and plan are hidden by the existing `docs/superpowers/*` ignore rule; leave that rule unchanged. Ignore pre-existing `.codegraph/` workspace metadata and do not stage it.

- [ ] **Step 15: Commit Task 2 and approved documentation**

```bash
git add normalizer/ tests/test_semantic_normalizer.py
git add -f docs/superpowers/specs/2026-10-09-configuration-driven-semantic-normalizer-design.md docs/superpowers/plans/2026-10-09-configuration-driven-semantic-normalizer.md
git commit -m "[G2-06] Add configuration-driven semantic normalizer"
```

