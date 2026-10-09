# Design: Configuration-Driven Semantic Normalizer

- **Topic:** Normalize Jellyfin JSON responses using `config/ignore-rules.json`
- **Date:** 2026-10-09
- **Status:** Approved

## 1. Purpose

Build an independent Python normalizer that removes or rewrites volatile values before differential comparison. The module must recursively handle JSON-compatible dictionaries and lists, preserve raw response evidence, and implement every action currently declared in `config/ignore-rules.json`.

The first version is successful when it:

- supports `DROP`, `REGEX_REPLACE`, and `MAP_STATE`;
- supports root fields, nested fields, and list wildcards such as `$.MediaSources[*].TranscodingUrl`;
- returns a normalized deep copy without mutating the input;
- fails immediately on invalid configuration;
- leaves unmatched paths and unsupported runtime value shapes unchanged; and
- passes the existing test suite plus focused normalizer tests.

Comparator integration, a CLI, logging, and full JSONPath support are outside this task.

## 2. Public API

Add an independent module at `normalizer/semantic_normalizer.py` with this usage contract:

```python
normalizer = SemanticNormalizer.from_file("config/ignore-rules.json")

normalized = normalizer.normalize(
    payload,
    state_mapping={
        "v108-user-id": "user:admin",
        "v109-user-id": "user:admin",
    },
)
```

`SemanticNormalizer.from_file(path)` reads and validates the configuration, parses paths, and compiles regular expressions once. `normalize(payload, state_mapping=None)` applies the compiled rules to one deep copy and returns that copy. The normalizer stores configuration but no mutable response state, so one instance can normalize both Jellyfin versions.

`state_mapping` is one flat mapping from raw IDs from either server to canonical logical IDs. A missing mapping leaves the original value visible to the future comparator.

## 3. Rule Model and Path Grammar

Each configured rule contains:

- `path`: target path;
- `action`: `DROP`, `REGEX_REPLACE`, or `MAP_STATE`;
- `pattern` and `replacement`: required only for `REGEX_REPLACE`; and
- optional descriptive fields, which do not affect execution.

The first version intentionally implements only the grammar needed by the current configuration:

```text
path       = "$" segment+
segment    = "." field | "[*]"
field      = one or more characters excluding ".", "[", and "]"
```

Examples:

- `$.AccessToken`
- `$.User.Id`
- `$.MediaSources[*].TranscodingUrl`

The parser converts a path into field and wildcard tokens. It does not support recursive descent, filters, unions, quoted field names, or specific list indexes. This avoids adding a JSONPath dependency for unused features.

## 4. Normalization Flow

Configuration loading performs these steps once:

1. Read and decode the JSON file.
2. Validate the root object and `rules` list.
3. Validate each rule and supported action.
4. Parse each path into traversal tokens.
5. Compile every `REGEX_REPLACE` pattern.
6. Preserve rule order in an immutable internal sequence.

Normalization performs these steps per payload:

1. Deep-copy the input once using `copy.deepcopy`.
2. Apply compiled rules in file order.
3. Traverse only the branches addressed by each rule.
4. Apply the action at every matching leaf.
5. Return the normalized copy.

Traversal semantics:

- A field token continues only when the current node is a dictionary containing that key.
- A wildcard token continues only when the current node is a list and visits every index.
- A missing field or incompatible container is a no-op.
- If an earlier rule removes a node, a later rule targeting that node is a no-op.

This ordered behavior makes precedence explicit without a separate priority mechanism.

## 5. Action Semantics

### 5.1 `DROP`

- For a dictionary leaf, delete the matching key.
- For a list leaf, replace the matching element with `None` rather than shifting indexes.

The distinction removes ignored object properties while preserving list position and cardinality.

### 5.2 `REGEX_REPLACE`

- Apply the precompiled expression with `re.sub` when the leaf is a string.
- Leave non-string values unchanged.
- Use the configured replacement verbatim.

### 5.3 `MAP_STATE`

- Look up a hashable leaf value in `state_mapping`.
- Replace a known value with its canonical ID.
- Leave missing or unhashable values unchanged.
- Treat an omitted `state_mapping` as an empty mapping.

Leaving unknown IDs unchanged ensures normalization does not hide an unmapped semantic difference.

## 6. Validation and Errors

Add `NormalizerConfigError`, derived from `ValueError`, for invalid normalizer configuration. Configuration loading fails for:

- unreadable files or invalid JSON;
- a non-object root;
- a missing or non-list `rules` field;
- a non-object rule;
- a missing, non-string, or unsupported path;
- an unsupported action;
- missing or non-string `pattern` or `replacement` fields for `REGEX_REPLACE`; or
- a regular expression that cannot be compiled.

Messages identify the rule index and include its path when available, for example:

```text
Invalid normalizer rule 3 ($.Items[*].Id): unsupported action 'MASK'
```

Payload shape differences are not configuration errors. A scalar payload is deep-copied and returned unchanged. Type mismatches encountered during traversal or action execution are no-ops. Programming errors and resource errors are not suppressed.

## 7. Testing

Add `tests/test_semantic_normalizer.py` using the existing pytest setup. Tests cover:

- loading the real `config/ignore-rules.json`;
- root and nested dictionary `DROP`;
- wildcard application across all list elements;
- direct list-element `DROP` preserving indexes with `None`;
- nested-list `REGEX_REPLACE` and non-string no-op behavior;
- mapping IDs from both Jellyfin versions to one canonical value;
- missing and unhashable mapping values remaining unchanged;
- missing paths and incompatible containers as no-ops;
- ordered interaction between multiple rules;
- input immutability;
- scalar payload behavior; and
- parameterized invalid configurations covering malformed roots, rules, paths, actions, required fields, and regular expressions.

Error tests assert that messages contain the relevant rule index and path.

The completion gate is:

```bash
python -m pytest -q
```

All existing and new tests must pass.

## 8. Deliverables and Scope Boundary

Deliverables:

- `normalizer/__init__.py`
- `normalizer/semantic_normalizer.py`
- `tests/test_semantic_normalizer.py`

No dependency changes are needed. The implementation uses only Python standard-library modules including `copy`, `json`, `re`, and `pathlib`.

Skipped: Comparator integration, response dispatch, CLI options, runtime logging, JSONPath extensions, and per-path mapping tables. Add those only when a consuming differential execution flow requires them.
