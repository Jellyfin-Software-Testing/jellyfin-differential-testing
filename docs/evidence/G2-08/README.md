# G2-08: Unit tests for Normalizer and DiffEngine

G2-08 verifies the core modules after G2-06A (PR #35) and G2-07 (PR #33)
were merged into `develop`. The tests use in-memory response pairs and the
checked-in normalization rules; Jellyfin and Docker are not required.

## Reproduce

From the repository root, install the dependencies from `requirements.txt` in
your Python environment, then run:

```powershell
python -m pytest -q tests/test_G2_08_diff_engine.py tests/test_G2_08_normalizer_diff_integration.py
python -m pytest -q
```

The recorded result is in [pytest-output.txt](pytest-output.txt). The G2-08
tests contributed 25 cases; the complete suite passed 112 cases on 2026-10-10.

## Coverage added in G2-08

| Module | Behaviors verified |
| --- | --- |
| DiffEngine | Equal nested responses; status code; headers removed, added, changed, ignored, and matched without regard to name casing; explicit empty ignore list; missing and additional fields; type and value changes; array length and nested paths; `DiffItem.to_dict()` |
| Normalizer + DiffEngine | Authentication tokens and mapped IDs converge; real user-name changes survive normalization; rules stay scoped to their endpoint; token type defects survive masking; item IDs and nested session URLs converge |

The tests exposed three header comparison defects in `G2_07_diff_engine.py`:
v2-only headers were missed, header name casing caused false differences, and
an explicit empty `ignore_headers` list was treated as the default ignore list.
The fix compares header names case insensitively in both directions and uses
the default ignore list only when the argument is `None`.
