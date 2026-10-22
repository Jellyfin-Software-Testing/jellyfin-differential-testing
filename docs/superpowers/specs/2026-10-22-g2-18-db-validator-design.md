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

Add a small `scripts/db_validator.py` module. Call it only from the G2-15 lifecycle orchestration after each relevant API state read/transition; do not add DB validation to `read_state` or another shared helper, since G2-16 imports `read_state`.

Resolve the API user ID to exactly one `Users.Id` row in `jellyfin.db` and obtain `InternalId`. For the library lookup, open one `library.db` connection with SQLite URI `mode=ro` and begin one explicit read transaction. Keep that same connection and transaction for the complete sequence: resolve the API item ID to exactly one `TypedBaseItems.guid` row and obtain `UserDataKey`; verify that this key belongs to exactly one `TypedBaseItems` row; then query `UserDatas` for `(UserDataKey, InternalId)`. If multiple items use the key, fail with `USER_DATA_KEY_COLLISION`. Do not open a new library connection or transaction between these steps.

Query all `UserDatas` rows for the resolved pair. Zero rows means `isFavorite = false`; one row supplies the stored boolean; multiple rows fail. Do not use `fetchone()` for any lookup whose cardinality must be checked. Data queries use `SELECT` only; `BEGIN`/`COMMIT`/`ROLLBACK` may be used solely to manage the explicit read transaction. No DML, DDL, writable fallback, or `immutable` connection is allowed. If a consistent DB/WAL snapshot cannot be opened, fail the instance.

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

Unit tests use temporary SQLite databases to cover successful ID resolution, a missing `UserDatas` row mapping to false, true/false values, each ambiguous or duplicate case, `USER_DATA_KEY_COLLISION`, schema/read errors, and all three mismatch codes. They verify database files are opened read-only and remain unchanged, and that all library lookups in one validation share a single explicit read transaction/snapshot.

Integration verification runs the existing G2-15 lifecycle against both running instances and observes `false → true → false` through API and DB after each transition. Specifically verify that v10.9 `library.db` is readable with `mode=ro` while Jellyfin is running in WAL mode, including its required readable `-wal`/`-shm` sidecars. If those files are unavailable or SQLite cannot open a consistent read-only snapshot, fail the instance; do not create sidecars via a writable fallback or ignore WAL via `immutable`. SQLite read-only WAL support starts at 3.22.0; the current environment reports 3.45.1, so integration should focus on the live sidecar/snapshot behavior. Existing cleanup restores the original favorite state.

## Acceptance criteria

1. Every observed G2-15 favorite state is checked against both relevant API observations and SQLite.
2. User and item IDs are resolved explicitly, with ambiguity and `UserDataKey` collisions reported rather than guessed.
3. A missing `UserDatas` row is treated as false; duplicate rows and all other DB errors fail the instance.
4. SQLite data access uses `mode=ro` and `SELECT` only, with an explicit read transaction across the complete `library.db` item/key/user-data lookup; there is no writable or `immutable` fallback.
5. Evidence identifies the resolution/read stage, row counts, resolved keys, and precise mismatch/error code.
6. Tests cover false-to-true-to-false on both versions, including live reads from v10.9 `library.db` while WAL is active.
7. DB validation is called only by G2-15 lifecycle orchestration and does not change shared `read_state` behavior used by G2-16.
