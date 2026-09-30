# G1-06: Setup Wizard and initial-state seeding

## Goal

Make Jellyfin v10.8.13 (`http://localhost:8096`) and v10.9.0
(`http://localhost:8097`) start with equivalent test state before differential
requests are sent. Version and server IDs are intentionally not compared.

## Design

- Both containers mount the single canonical directory `data/seed-data` read-only
  at `/media`; therefore their input bytes cannot drift.
- `data/dataset-manifest.json` describes two deterministic PCM/WAV fixtures, the
  first-run wizard configuration and the seed music library.
- `scripts/g1_06_setup_and_verify.py` creates (or verifies) the fixtures, completes
  the Setup Wizard on a fresh server, creates the library, requests a scan and
  compares a normalised state.
- Before comparing the two responses, the runner also validates each response
  against the manifest. Thus, two identically misconfigured instances cannot be
  reported as equivalent.
- The comparison includes wizard completion, selected system configuration, the
  admin name and role, library semantics, item names/types/paths/sizes/durations
  and SHA-256 for the mounted seed files. Database IDs, access tokens and version
  values are deliberately excluded because they must differ.

## Run

Start the services from the repository root:

```powershell
docker compose -f docker/docker-compose.yml up -d
py -3 -m pip install -r requirements.txt
py -3 scripts/g1_06_setup_and_verify.py
```

The runner uses the existing development credential `admin` / `admin123456` by
default. To avoid putting an alternative credential on the command line, set
`JELLYFIN_ADMIN_PASSWORD` first. This account is only appropriate for isolated
local test containers.

On success it writes `docs/evidence/G1-06-initial-state-parity.json` with status
`equivalent`. A status of `different` is a hard stop for differential test runs.

## Resetting a failed first-run attempt

The runner intentionally never removes Jellyfin configuration. To start fresh,
stop the containers and have an operator explicitly remove only the two task-owned
directories `docker/v10.8/config`, `docker/v10.8/cache`, `docker/v10.9/config`,
and `docker/v10.9/cache`; then run the commands above again. Do not remove
`data/seed-data`, because it is the canonical shared input.
