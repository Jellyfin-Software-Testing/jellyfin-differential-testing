# G2-23A — Deterministic test replay and failure reproduction rate

## What this task measures

A captured record binds `test_id`, random `seed`, the exact HTTP request, a
reference/live environment fingerprint, and one observed normalized diff
signature. Replay checks the fingerprint before **each** attempt and counts a
failure as reproduced only when the same category, path, and value hashes
reappear. It does not assume that every failure is reproducible.

`failure_reproduction_rate = reproduced / (reproduced + not_reproduced)`.
Environment-invalid attempts are reported but excluded from the denominator.
When there are no valid attempts, the rate is `null`, not zero.

The CLI is deliberately limited to read-only `GET` requests. The core replay
function can accept a `reset_state` callback for mutating requests, but the CLI
rejects POST/PUT/PATCH/DELETE until a task-specific reset mechanism exists.
This prevents a second attempt from starting in the first attempt's altered
state. No container configuration, media, or database is deleted.

## Prerequisites (PowerShell)

Run commands from the root of this repository checkout. Start the existing Jellyfin
containers; do not create a second Compose stack from another worktree. The
servers must respond at `http://localhost:8096` (10.8.13) and
`http://localhost:8097` (10.9.0). Use the existing G1-06 initial-state report
with `status: equivalent` and the checked-in seed media.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -o addopts="" -q tests/test_G2_23A_replay_record.py tests/test_G2_23A_replay.py
```

If the local environment already has the dependencies, use it instead of
recreating the venv. `-o addopts=""` avoids the project's default xdist worker
count for this small test set. The admin password is read from the
`JELLYFIN_ADMIN_PASSWORD` environment variable (default: local development
password from G1-06); it is never accepted as a command-line argument or
written to records/reports.

## Capture an observed difference

The included request is intentionally a **demonstration**, not a Jellyfin bug:
the two versions naturally return different `Version` values. It proves the
capture/replay mechanism against live servers without claiming a defect.

```powershell
python scripts/G2_23A_replay.py capture `
  --test-id G2-23A-public-version-demo --seed 20261018 `
  --request-file docs/evidence/G2-23A/demo-public-info-request.json `
  --target-category VALUE_MISMATCH --target-path '$.Version' `
  --record docs/evidence/G2-23A/demo-public-info-record.json
```

Capture refuses to write a record when the selected difference was not
observed, when multiple differences match the target, or when the target file
already exists. For a real failed test, replace the request and target with the
actual failing case and label its evidence accordingly. Do not call a known
version difference a defect.

The request file may use `{"$choice": [value1, value2]}` for seeded input
generation. Capture stores both the template and resolved request. Loading the
record verifies that the same seed regenerates the exact request; the
`request_input_sha256` also binds TestID, seed, template, and payload. For a
fixed request such as the demo, the seed is retained as provenance and bound
to the request identity, but it does not alter the request.

Use `"$AUTH_USER"` as a query/body value if a test needs the administrator's
ID. Replay substitutes each server's own authenticated ID; no user ID or token
needs to be hardcoded in the request file.

## Replay and inspect the result

```powershell
python scripts/G2_23A_replay.py replay `
  --record docs/evidence/G2-23A/demo-public-info-record.json `
  --runs 5 `
  --report docs/evidence/G2-23A/demo-public-info-report.json
```

The report contains `reproduced`, `not_reproduced`, `invalid`, `valid_runs`,
`failure_reproduction_rate`, and each attempt's outcome. A successful command
means the measurement ran; the rate itself may be less than 100%. If all runs
are invalid, the command returns nonzero and the rate is unavailable. Record
and report files use create-only writes, so rerunning requires a new output
path; existing evidence is not silently overwritten.

The fingerprint includes Jellyfin versions, hashes of the seed manifest,
normalization rules and prior G1-06 evidence, plus a hash of the **live** seed
library/items and relevant G1-06 system configuration (semantic fields only).
The runner also verifies the checked-in
WAV hashes against the G1-06 report. It checks this before every replay
attempt. This is a scoped fingerprint for read-only seeded API tests; a future
stateful test must include its own state in the fingerprint and reset it between
attempts.

Only status and normalized body are compared. HTTP headers are excluded from
the signature to avoid transport noise. A matching category/path with
different normalized values is **not** counted as reproduced because each
value is represented by a SHA-256 digest in the signature. Raw response values,
credentials, and auth headers are not stored in evidence.
The recorder rejects common credential field names, but review any custom
request values before committing evidence; it cannot detect every secret hidden
under an unrelated field name.
