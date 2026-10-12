# G2-10: Stateful Differential Testing

## Prepare and test

Run from repository root. Create a local virtual environment and install the
existing test dependencies, including `pytest`.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Start both Jellyfin instances, then run G1-06 first. Its evidence must report
`equivalent` before G2-10 runs.

```bash
docker compose -f docker/docker-compose.yml up -d
python scripts/g1_06_setup_and_verify.py
```

```bash
python scripts/g2_10_stateful_differential.py
```

The runner compares Jellyfin v10.8.13 and v10.9.0 after every favorite-state
operation. It tests admin idempotency plus independent favorite state for two
test users. Evidence is written to `docs/evidence/G2-10-stateful-differential.json`.

It creates `g2-10-user-a` and `g2-10-user-b` when absent, but never deletes
users, media, libraries, or container configuration. Override their names with
`--user-a` and `--user-b`; set `JELLYFIN_ADMIN_PASSWORD` for a non-default admin
password.

Exit code `0` means every state invariant matched. On failure, inspect
`docs/evidence/G2-10-stateful-differential.json` for the first failed step.
