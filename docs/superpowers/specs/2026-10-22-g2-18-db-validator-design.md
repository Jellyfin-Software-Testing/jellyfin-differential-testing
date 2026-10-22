# G2-18: DB Validator — Persistent State Consistency

## Goal

Verify that Jellyfin's persistent favorite state in SQLite agrees with both API-level observations after each favorite transition. The first version is limited to favorites for Jellyfin 10.8.13 and 10.9.0.

## Scope

- Read each instance's `jellyfin.db` and `library.db` from its existing Docker config directory.
- Resolve API user and item IDs to database keys explicitly.
- Compare `UserDatas.isFavorite` with `UserData.IsFavorite` and favorite collection membership from the API.
- Run the validation from the existing G2-15 favorite lifecycle and include results in its evidence.
- Keep all SQLite access read-only. Writing the existing JSON evidence file is allowed; SQLite databases and their WAL state must never be modified by the validator.

Out of scope: validating non-favorite state, comparing raw database IDs across versions, schema discovery/generalization, and changing Jellyfin state through SQL.

## Design

Add a small `scripts/db_validator.py` module and call it from G2-15 after each API state read. It opens the instance's two database files with SQLite URI `mode=ro` and issues `SELECT` queries only. It must not fall back to a writable connection. If it cannot read a consistent database/WAL snapshot, the instance validation fails.

For each observation, resolve the API user ID to exactly one `Users.Id` row in `jellyfin.db` and obtain `InternalId`. Resolve the API item ID to exactly one `TypedBaseItems.guid` row in `library.db` and obtain `UserDataKey`. Then verify that this `UserDataKey` belongs to exactly one row in `TypedBaseItems`; if multiple items use it, fail with `USER_DATA_KEY_COLLISION`.

Query all `UserDatas` rows for the resolved `(UserDataKey, InternalId)` pair. Zero rows means `isFavorite = false`; one row supplies the stored boolean; multiple rows fail. Do not use `fetchone()` for any lookup whose cardinality must be checked.

## Failure handling

Any SQLite/read/snapshot error, missing required table or column, unresolved or ambiguous user/item ID, invalid resolved key, duplicate user-data row, or key collision fails that instance. A missing `UserDatas` row is the sole zero-row case treated as valid `false`.

Use distinct mismatch codes:

- `API_ITEM_DB_MISMATCH`: API item `UserData.IsFavorite` differs from DB `isFavorite`.
- `API_COLLECTION_DB_MISMATCH`: API favorite collection membership differs from DB `isFavorite`.
- `API_INTERNAL_MISMATCH`: the API item flag and API collection membership disagree with each other.

Database error codes should identify the stage, including user resolution, item resolution, key collision, user-data lookup, schema validation, and snapshot read. Errors must not be silently ignored.

## Evidence

Extend G2-15 evidence with each validation result and transition. Record:

- instance and lifecycle step;
- API item favorite flag and collection membership;
- resolved `InternalId` and `UserDataKey` when available;
- row counts for user resolution, item-by-GUID resolution, item-by-key ownership, and user-data lookup;
- DB favorite value when available;
- pass/fail and the specific mismatch or database error code.

If resolution fails before a value is available, record that field as unavailable and retain the failing stage and row count.

## Verification

Unit tests use temporary SQLite databases to cover successful ID resolution, a missing `UserDatas` row mapping to false, true/false values, each ambiguous or duplicate case, `USER_DATA_KEY_COLLISION`, schema/read errors, and all three mismatch codes. They also verify database files are opened read-only and remain unchanged.

Integration verification runs the existing G2-15 lifecycle against both running instances and observes `false → true → false` through API and DB after each transition. It must also demonstrate that v10.9 state remains readable while Jellyfin is running with WAL active. Failure to read a consistent DB/WAL snapshot fails the instance. Existing cleanup restores the original favorite state.

## Acceptance criteria

1. Every observed G2-15 favorite state is checked against both relevant API observations and SQLite.
2. User and item IDs are resolved explicitly, with ambiguity and `UserDataKey` collisions reported rather than guessed.
3. A missing `UserDatas` row is treated as false; duplicate rows and all other DB errors fail the instance.
4. SQLite access uses `mode=ro`, runs only `SELECT`, and has no writable fallback.
5. Evidence identifies the resolution/read stage, row counts, resolved keys, and precise mismatch/error code.
6. Tests cover false-to-true-to-false on both versions, including live reads while the v10.9 WAL is active.
