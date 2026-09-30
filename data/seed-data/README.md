# Seed data for differential testing

Do not edit or add media manually in this directory. Both Jellyfin containers mount
this exact directory read-only at `/media`.

Run `python scripts/g1_06_setup_and_verify.py` from the repository root to create
the deterministic WAV fixtures specified in `../dataset-manifest.json`. The runner
checks the SHA-256 digest of every generated fixture before it starts Jellyfin setup.
