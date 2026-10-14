# Seed data for differential testing

Both Jellyfin containers mount this version-controlled directory read-only at
`/media`. Keep its fixtures deterministic and do not place production media here.

Run `python scripts/G1_06_setup_and_verify.py` from the repository root to create
the deterministic WAV fixtures specified in `../dataset-manifest.json`. The runner
checks the SHA-256 digest of every generated fixture before it starts Jellyfin setup.

The isolated G2-14 movie fixture and NFO are under `seed-filter-movies/`. Run
`python scripts/G2_14_seed_filters.py` to create and scan its dedicated movie library
on both Jellyfin instances. Its fixed metadata is Drama, 2020, and PG-13.
