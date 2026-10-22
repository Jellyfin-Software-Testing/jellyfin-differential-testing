import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any
import pytest

from scripts.db_validator import validate_favorite_state


def create_fixture_dbs(tmp_path: Path):
    jellyfin_db = tmp_path / "jellyfin.db"
    library_db = tmp_path / "library.db"

    # Setup jellyfin.db
    with sqlite3.connect(str(jellyfin_db)) as con:
        con.execute(
            'CREATE TABLE Users ("Id" TEXT NOT NULL PRIMARY KEY, "InternalId" INTEGER NOT NULL)'
        )
        con.commit()

    # Setup library.db
    with sqlite3.connect(str(library_db)) as con:
        con.execute(
            "CREATE TABLE TypedBaseItems (guid GUID PRIMARY KEY NOT NULL, UserDataKey TEXT NULL)"
        )
        con.execute(
            "CREATE TABLE UserDatas (key TEXT NOT NULL, userId INTEGER NOT NULL, isFavorite BIT NOT NULL)"
        )
        con.commit()

    return jellyfin_db, library_db


def test_maps_api_ids_to_database_keys(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("user-uuid-1", 42))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute(
            "INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)",
            ("item-guid-1", "key-custom-1"),
        )
        con.execute(
            "INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)",
            ("key-custom-1", 42, 1),
        )
        con.commit()

    res = validate_favorite_state(
        jdb,
        ldb,
        user_id="user-uuid-1",
        item_id="item-guid-1",
        api_state={"is_favorite": True, "in_favorites": True},
    )

    assert res["passed"] is True
    assert res["internal_id"] == 42
    assert res["user_data_key"] == "key-custom-1"
    assert res["db_is_favorite"] is True
    assert res["row_counts"] == {
        "user_by_id": 1,
        "item_by_guid": 1,
        "items_by_user_data_key": 1,
        "user_data": 1,
    }
    assert res["mismatch_codes"] == []
    assert res["error"] is None


def test_true_and_false_rows_match_api(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "k1"))
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i2", "k2"))
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 1))
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k2", 1, 0))
        con.commit()

    res1 = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": True, "in_favorites": True}
    )
    assert res1["passed"] is True
    assert res1["db_is_favorite"] is True

    res2 = validate_favorite_state(
        jdb, ldb, "u1", "i2", {"is_favorite": False, "in_favorites": False}
    )
    assert res2["passed"] is True
    assert res2["db_is_favorite"] is False


def test_missing_user_data_is_false(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "k1"))
        con.commit()

    res = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is True
    assert res["db_is_favorite"] is False
    assert res["row_counts"]["user_data"] == 0
    assert res["error"] is None


def test_user_and_item_resolve_require_exactly_one_row(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)

    # Missing user
    res = validate_favorite_state(
        jdb, ldb, "nonexistent-user", "i1", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is False
    assert res["error"]["code"] == "USER_NOT_FOUND"
    assert res["row_counts"]["user_by_id"] == 0
    assert res["internal_id"] is None

    # Ambiguous user (duplicate)
    with sqlite3.connect(str(jdb)) as con:
        # SQLite doesn't allow duplicate PK, but can have duplicate if schema has no PK or matching candidates
        con.execute('DROP TABLE Users')
        con.execute('CREATE TABLE Users ("Id" TEXT, "InternalId" INTEGER)')
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("dup-user", 1))
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("dup-user", 2))
        con.commit()

    res = validate_favorite_state(
        jdb, ldb, "dup-user", "i1", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is False
    assert res["error"]["code"] == "USER_AMBIGUOUS"
    assert res["row_counts"]["user_by_id"] == 2

    # Reset valid user for item tests
    with sqlite3.connect(str(jdb)) as con:
        con.execute('DROP TABLE Users')
        con.execute('CREATE TABLE Users ("Id" TEXT PRIMARY KEY, "InternalId" INTEGER)')
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()

    # Missing item
    res = validate_favorite_state(
        jdb, ldb, "u1", "missing-item", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is False
    assert res["error"]["code"] == "ITEM_NOT_FOUND"
    assert res["row_counts"]["item_by_guid"] == 0
    assert res["user_data_key"] is None

    # Ambiguous item
    with sqlite3.connect(str(ldb)) as con:
        con.execute('DROP TABLE TypedBaseItems')
        con.execute('CREATE TABLE TypedBaseItems (guid GUID, UserDataKey TEXT)')
        con.execute('INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)', ("dup-item", "k1"))
        con.execute('INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)', ("dup-item", "k2"))
        con.commit()

    res = validate_favorite_state(
        jdb, ldb, "u1", "dup-item", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is False
    assert res["error"]["code"] == "ITEM_AMBIGUOUS"
    assert res["row_counts"]["item_by_guid"] == 2


def test_user_data_key_collision_fails(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        # Multiple different items have the same UserDataKey
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "shared-key"))
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i2", "shared-key"))
        con.commit()

    res = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is False
    assert res["error"]["code"] == "USER_DATA_KEY_COLLISION"
    assert res["row_counts"]["items_by_user_data_key"] == 2
    assert res["user_data_key"] == "shared-key"


def test_duplicate_or_invalid_user_data_fails(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "k1"))
        # Duplicate user data rows
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 0))
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 1))
        con.commit()

    res = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is False
    assert res["error"]["code"] == "USER_DATA_NOT_UNIQUE"
    assert res["row_counts"]["user_data"] == 2

    # Invalid stored bit value (e.g. 5)
    with sqlite3.connect(str(ldb)) as con:
        con.execute("DELETE FROM UserDatas")
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 5))
        con.commit()

    res2 = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": False, "in_favorites": False}
    )
    assert res2["passed"] is False
    assert res2["error"]["code"] == "USER_DATA_VALUE_INVALID"


def test_api_mismatches_have_distinct_codes(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "k1"))
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 0))
        con.commit()

    # 1. API item says True, API collection says False, DB is False
    # item != db -> API_ITEM_DB_MISMATCH
    # item != coll -> API_INTERNAL_MISMATCH
    res1 = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": True, "in_favorites": False}
    )
    assert res1["passed"] is False
    assert "API_ITEM_DB_MISMATCH" in res1["mismatch_codes"]
    assert "API_INTERNAL_MISMATCH" in res1["mismatch_codes"]
    assert "API_COLLECTION_DB_MISMATCH" not in res1["mismatch_codes"]

    # 2. API item says False, API collection says True, DB is False
    # coll != db -> API_COLLECTION_DB_MISMATCH
    # item != coll -> API_INTERNAL_MISMATCH
    res2 = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": False, "in_favorites": True}
    )
    assert res2["passed"] is False
    assert "API_COLLECTION_DB_MISMATCH" in res2["mismatch_codes"]
    assert "API_INTERNAL_MISMATCH" in res2["mismatch_codes"]
    assert "API_ITEM_DB_MISMATCH" not in res2["mismatch_codes"]


def test_reports_multiple_mismatch_codes_together(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "k1"))
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 0))
        con.commit()

    # Both API item and collection say True, but DB is False
    res = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": True, "in_favorites": True}
    )
    assert res["passed"] is False
    assert set(res["mismatch_codes"]) == {"API_ITEM_DB_MISMATCH", "API_COLLECTION_DB_MISMATCH"}


def test_readonly_connection_error_is_reported(tmp_path: Path):
    nonexistent = tmp_path / "does_not_exist.db"
    valid_db = tmp_path / "valid.db"
    with sqlite3.connect(str(valid_db)) as con:
        con.execute("CREATE TABLE foo (x INT)")
        con.commit()

    res = validate_favorite_state(
        nonexistent, valid_db, "u1", "i1", {"is_favorite": False, "in_favorites": False}
    )
    assert res["passed"] is False
    assert res["error"]["code"] in ("DB_OPEN_ERROR", "DB_READ_ERROR", "DB_SNAPSHOT_ERROR")


def test_opens_databases_readonly_and_leaves_files_unchanged(tmp_path: Path, monkeypatch):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "k1"))
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 1))
        con.commit()

    jdb_bytes_before = jdb.read_bytes()
    ldb_bytes_before = ldb.read_bytes()

    opened_uris = []
    real_connect = sqlite3.connect

    def spy_connect(*args, **kwargs):
        if args and isinstance(args[0], str):
            opened_uris.append(args[0])
        conn = real_connect(*args, **kwargs)
        return conn

    monkeypatch.setattr(sqlite3, "connect", spy_connect)

    res = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": True, "in_favorites": True}
    )
    assert res["passed"] is True

    # Assert URIs had mode=ro
    assert len(opened_uris) == 2
    for uri in opened_uris:
        assert "mode=ro" in uri
        # Test that writing through a connection to this URI is rejected
        test_conn = real_connect(uri, uri=True)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            test_conn.execute("CREATE TABLE write_test (a INT)")
        test_conn.close()

    # Compare file bytes before and after
    assert jdb.read_bytes() == jdb_bytes_before
    assert ldb.read_bytes() == ldb_bytes_before


def test_library_lookups_share_one_read_transaction(tmp_path: Path, monkeypatch):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES (?, ?)', ("u1", 1))
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES (?, ?)", ("i1", "k1"))
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES (?, ?, ?)", ("k1", 1, 1))
        con.commit()

    events = []
    real_connect = sqlite3.connect

    class ConnectionProxy:
        def __init__(self, conn, is_library: bool):
            self._conn = conn
            self._is_lib = is_library

        def execute(self, sql, *args):
            if self._is_lib:
                events.append(("execute", sql.strip().split()[0].upper()))
            return self._conn.execute(sql, *args)

        def commit(self):
            if self._is_lib:
                events.append(("commit",))
            return self._conn.commit()

        def rollback(self):
            if self._is_lib:
                events.append(("rollback",))
            return self._conn.rollback()

        def cursor(self):
            cur = self._conn.cursor()
            if not self._is_lib:
                return cur
            class CursorProxy:
                def __init__(self, real_cur):
                    self._cur = real_cur
                def execute(self, sql, *args):
                    events.append(("execute", sql.strip().split()[0].upper()))
                    return self._cur.execute(sql, *args)
                def fetchall(self):
                    return self._cur.fetchall()
                def __getattr__(self, name):
                    return getattr(self._cur, name)
            return CursorProxy(cur)

        def close(self):
            if self._is_lib:
                events.append(("close",))
            return self._conn.close()

        def __getattr__(self, name):
            return getattr(self._conn, name)

    lib_connect_count = 0

    def spy_connect(*args, **kwargs):
        uri = args[0] if args else kwargs.get("database", "")
        conn = real_connect(*args, **kwargs)
        if "library.db" in str(uri):
            nonlocal lib_connect_count
            lib_connect_count += 1
            return ConnectionProxy(conn, True)
        return ConnectionProxy(conn, False)

    monkeypatch.setattr(sqlite3, "connect", spy_connect)

    res = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": True, "in_favorites": True}
    )
    assert res["passed"] is True
    assert lib_connect_count == 1, "library.db must be opened exactly once"

    # Verify transaction lifecycle: BEGIN -> SELECTs -> COMMIT
    op_types = [e[1] if e[0] == "execute" else e[0] for e in events]
    assert "BEGIN" in op_types
    begin_idx = op_types.index("BEGIN")
    select_indices = [i for i, op in enumerate(op_types) if op == "SELECT"]
    assert len(select_indices) >= 3, "At least 3 queries: item resolve, key check, user data"
    for s_idx in select_indices:
        assert s_idx > begin_idx, "Queries must be executed after BEGIN"
    if "COMMIT" in op_types:
        commit_idx = op_types.index("COMMIT")
        for s_idx in select_indices:
            assert s_idx < commit_idx, "Queries must be executed before COMMIT"


def test_locked_non_wal_db_retries_with_nolock(tmp_path: Path):
    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES ("u1", 10)')
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("PRAGMA journal_mode = DELETE;")
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES ('i1', 'k1')")
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES ('k1', 10, 1)")
        con.commit()

    wal_file = ldb.parent / f"{ldb.name}-wal"
    assert not wal_file.exists(), "Must be non-WAL database"

    # Hold an exclusive lock on library.db
    lock_conn = sqlite3.connect(str(ldb), isolation_level=None)
    try:
        lock_conn.execute("PRAGMA locking_mode = EXCLUSIVE;")
        lock_conn.execute("BEGIN EXCLUSIVE;")

        res = validate_favorite_state(
            jdb, ldb, "u1", "i1", {"is_favorite": True, "in_favorites": True}
        )
        assert res["passed"] is True
        assert res["db_is_favorite"] is True
        assert res["error"] is None
    finally:
        try:
            lock_conn.execute("ROLLBACK;")
        except Exception:
            pass
        lock_conn.close()


def test_locked_wal_db_does_not_retry_with_nolock(tmp_path: Path, monkeypatch):
    import scripts.db_validator

    jdb, ldb = create_fixture_dbs(tmp_path)
    with sqlite3.connect(str(jdb)) as con:
        con.execute('INSERT INTO Users ("Id", "InternalId") VALUES ("u1", 10)')
        con.commit()
    with sqlite3.connect(str(ldb)) as con:
        con.execute("PRAGMA journal_mode = WAL;")
        con.execute("INSERT INTO TypedBaseItems (guid, UserDataKey) VALUES ('i1', 'k1')")
        con.execute("INSERT INTO UserDatas (key, userId, isFavorite) VALUES ('k1', 10, 1)")
        con.commit()

    # Ensure WAL file exists on disk
    wal_file = ldb.parent / f"{ldb.name}-wal"
    wal_file.write_bytes(b"mock-wal-sidecar")

    real_open_ro = scripts.db_validator._open_ro

    class LockingConnectionProxy:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args, **kwargs):
            if str(sql).strip().upper() == "BEGIN":
                raise sqlite3.OperationalError("database is locked")
            return self._conn.execute(sql, *args, **kwargs)

        def close(self):
            return self._conn.close()

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def mock_open_ro(path):
        conn = real_open_ro(path)
        if "library.db" in str(path):
            return LockingConnectionProxy(conn)
        return conn

    monkeypatch.setattr(scripts.db_validator, "_open_ro", mock_open_ro)

    res = validate_favorite_state(
        jdb, ldb, "u1", "i1", {"is_favorite": True, "in_favorites": True}
    )
    assert res["passed"] is False
    assert res["error"]["code"] == "DB_READ_ERROR"
    assert "locked" in res["error"]["message"].lower()

