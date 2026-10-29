#!/usr/bin/env python3
"""SQLite persistent favorite state validator for Jellyfin."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any


def _get_guid_candidates(val: str | bytes) -> list[Any]:
    candidates = [val]
    if isinstance(val, str):
        try:
            u = uuid.UUID(val)
            candidates.extend([
                str(u),
                str(u).upper(),
                str(u).lower(),
                u.hex,
                u.hex.upper(),
                u.hex.lower(),
                u.bytes_le,
                u.bytes,
            ])
        except (ValueError, AttributeError):
            pass
    elif isinstance(val, bytes):
        try:
            u_le = uuid.UUID(bytes_le=val)
            candidates.extend([str(u_le), u_le.hex, val])
        except Exception:
            pass
        try:
            u_be = uuid.UUID(bytes=val)
            candidates.extend([str(u_be), u_be.hex])
        except Exception:
            pass

    seen = set()
    result = []
    for c in candidates:
        key = c if isinstance(c, (str, bytes)) else str(c)
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


def _open_ro(path: Path, timeout: float = 0.5) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True, isolation_level=None, timeout=timeout)



def validate_favorite_state(
    jellyfin_db_path: Path,
    library_db_path: Path,
    user_id: str,
    item_id: str,
    api_state: dict[str, bool],
) -> dict[str, Any]:
    """Validate that API favorite observations match persistent UserDatas in SQLite."""
    return _do_validate_favorite_state(
        jellyfin_db_path,
        library_db_path,
        user_id,
        item_id,
        api_state,
    )


def _do_validate_favorite_state(
    jellyfin_db_path: Path,
    library_db_path: Path,
    user_id: str,
    item_id: str,
    api_state: dict[str, bool],
) -> dict[str, Any]:
    row_counts: dict[str, int | None] = {
        "user_by_id": None,
        "item_by_guid": None,
        "items_by_user_data_key": None,
        "user_data": None,
    }
    internal_id: int | None = None
    user_data_key: str | None = None
    db_is_favorite: bool | None = None
    mismatch_codes: list[str] = []

    # 1. Open jellyfin.db and resolve user
    try:
        con_user = _open_ro(jellyfin_db_path)
    except (sqlite3.DatabaseError, OSError) as exc:
        return {
            "passed": False,
            "internal_id": None,
            "user_data_key": None,
            "row_counts": row_counts,
            "db_is_favorite": None,
            "mismatch_codes": [],
            "error": {
                "code": "DB_OPEN_ERROR",
                "stage": "db_open",
                "message": f"Failed to open jellyfin.db: {exc}",
            },
        }

    try:
        user_cands = _get_guid_candidates(user_id)
        placeholders = ",".join("?" * len(user_cands))
        cur = con_user.cursor()
        cur.execute(f'SELECT "Id", "InternalId" FROM Users WHERE "Id" IN ({placeholders})', user_cands)
        user_rows = cur.fetchall()
        row_counts["user_by_id"] = len(user_rows)

        if len(user_rows) == 0:
            return {
                "passed": False,
                "internal_id": None,
                "user_data_key": None,
                "row_counts": row_counts,
                "db_is_favorite": None,
                "mismatch_codes": [],
                "error": {
                    "code": "USER_NOT_FOUND",
                    "stage": "user_resolution",
                    "message": f"User {user_id} not found in Users table (0 rows)",
                },
            }
        if len(user_rows) > 1:
            return {
                "passed": False,
                "internal_id": None,
                "user_data_key": None,
                "row_counts": row_counts,
                "db_is_favorite": None,
                "mismatch_codes": [],
                "error": {
                    "code": "USER_AMBIGUOUS",
                    "stage": "user_resolution",
                    "message": f"User {user_id} ambiguous in Users table ({len(user_rows)} rows)",
                },
            }

        internal_id = user_rows[0][1]
    except sqlite3.OperationalError as exc:
        err_msg = str(exc).lower()
        code = "DB_SCHEMA_ERROR" if "no such" in err_msg else "DB_READ_ERROR"
        return {
            "passed": False,
            "internal_id": None,
            "user_data_key": None,
            "row_counts": row_counts,
            "db_is_favorite": None,
            "mismatch_codes": [],
            "error": {"code": code, "stage": "user_resolution", "message": str(exc)},
        }
    except Exception as exc:
        return {
            "passed": False,
            "internal_id": None,
            "user_data_key": None,
            "row_counts": row_counts,
            "db_is_favorite": None,
            "mismatch_codes": [],
            "error": {"code": "DB_READ_ERROR", "stage": "user_resolution", "message": str(exc)},
        }
    finally:
        con_user.close()

    # 2. Open library.db once with single read transaction
    try:
        con_lib = _open_ro(library_db_path)
    except (sqlite3.DatabaseError, OSError) as exc:
        return {
            "passed": False,
            "internal_id": internal_id,
            "user_data_key": None,
            "row_counts": row_counts,
            "db_is_favorite": None,
            "mismatch_codes": [],
            "error": {
                "code": "DB_OPEN_ERROR",
                "stage": "db_open",
                "message": f"Failed to open library.db: {exc}",
            },
        }

    in_transaction = False
    read_stage = "snapshot_begin"
    try:
        con_lib.execute("BEGIN")
        in_transaction = True
        read_stage = "snapshot_read"

        # Item GUID lookup
        item_cands = _get_guid_candidates(item_id)
        placeholders_item = ",".join("?" * len(item_cands))
        cur = con_lib.cursor()
        cur.execute(
            f"SELECT guid, UserDataKey FROM TypedBaseItems WHERE guid IN ({placeholders_item})",
            item_cands,
        )
        item_rows = cur.fetchall()
        row_counts["item_by_guid"] = len(item_rows)
        read_stage = "library_lookup"

        if len(item_rows) == 0:
            return {
                "passed": False,
                "internal_id": internal_id,
                "user_data_key": None,
                "row_counts": row_counts,
                "db_is_favorite": None,
                "mismatch_codes": [],
                "error": {
                    "code": "ITEM_NOT_FOUND",
                    "stage": "item_resolution",
                    "message": f"Item {item_id} not found in TypedBaseItems (0 rows)",
                },
            }
        if len(item_rows) > 1:
            return {
                "passed": False,
                "internal_id": internal_id,
                "user_data_key": None,
                "row_counts": row_counts,
                "db_is_favorite": None,
                "mismatch_codes": [],
                "error": {
                    "code": "ITEM_AMBIGUOUS",
                    "stage": "item_resolution",
                    "message": f"Item {item_id} ambiguous in TypedBaseItems ({len(item_rows)} rows)",
                },
            }

        user_data_key = item_rows[0][1]
        if user_data_key is None or (isinstance(user_data_key, str) and not user_data_key.strip()):
            return {
                "passed": False,
                "internal_id": internal_id,
                "user_data_key": None,
                "row_counts": row_counts,
                "db_is_favorite": None,
                "mismatch_codes": [],
                "error": {
                    "code": "USER_DATA_KEY_INVALID",
                    "stage": "key_validation",
                    "message": f"Item {item_id} has invalid or null UserDataKey: {user_data_key!r}",
                },
            }

        # Key ownership collision check
        cur.execute("SELECT guid FROM TypedBaseItems WHERE UserDataKey = ?", (user_data_key,))
        owner_rows = cur.fetchall()
        row_counts["items_by_user_data_key"] = len(owner_rows)

        if len(owner_rows) != 1:
            code = "USER_DATA_KEY_COLLISION" if owner_rows else "USER_DATA_KEY_ORPHANED"
            return {
                "passed": False,
                "internal_id": internal_id,
                "user_data_key": user_data_key,
                "row_counts": row_counts,
                "db_is_favorite": None,
                "mismatch_codes": [],
                "error": {
                    "code": code,
                    "stage": "key_ownership",
                    "message": (
                        f"UserDataKey {user_data_key} must have exactly one owner; "
                        f"found {len(owner_rows)}"
                    ),
                },
            }

        # UserDatas lookup
        cur.execute(
            "SELECT key, userId, isFavorite FROM UserDatas WHERE key = ? AND userId = ?",
            (user_data_key, internal_id),
        )
        ud_rows = cur.fetchall()
        row_counts["user_data"] = len(ud_rows)

        if len(ud_rows) == 0:
            db_is_favorite = False
        elif len(ud_rows) > 1:
            return {
                "passed": False,
                "internal_id": internal_id,
                "user_data_key": user_data_key,
                "row_counts": row_counts,
                "db_is_favorite": None,
                "mismatch_codes": [],
                "error": {
                    "code": "USER_DATA_NOT_UNIQUE",
                    "stage": "user_data_lookup",
                    "message": f"Multiple UserDatas rows ({len(ud_rows)}) found for key {user_data_key} and userId {internal_id}",
                },
            }
        else:
            raw_fav = ud_rows[0][2]
            if raw_fav in (1, True):
                db_is_favorite = True
            elif raw_fav in (0, False):
                db_is_favorite = False
            else:
                return {
                    "passed": False,
                    "internal_id": internal_id,
                    "user_data_key": user_data_key,
                    "row_counts": row_counts,
                    "db_is_favorite": None,
                    "mismatch_codes": [],
                    "error": {
                        "code": "USER_DATA_VALUE_INVALID",
                        "stage": "user_data_lookup",
                        "message": f"Invalid UserDatas.isFavorite value: {raw_fav!r}",
                    },
                }

        con_lib.execute("COMMIT")
        in_transaction = False

    except sqlite3.OperationalError as exc:
        err_msg = str(exc).lower()
        if "no such" in err_msg:
            code, stage = "DB_SCHEMA_ERROR", "library_lookup"
        elif "locked" in err_msg or read_stage != "library_lookup":
            code, stage = "DB_SNAPSHOT_ERROR", read_stage
        else:
            code, stage = "DB_READ_ERROR", "library_lookup"
        return {
            "passed": False,
            "internal_id": internal_id,
            "user_data_key": user_data_key,
            "row_counts": row_counts,
            "db_is_favorite": None,
            "mismatch_codes": [],
            "error": {"code": code, "stage": stage, "message": str(exc)},
        }
    except Exception as exc:
        return {
            "passed": False,
            "internal_id": internal_id,
            "user_data_key": user_data_key,
            "row_counts": row_counts,
            "db_is_favorite": None,
            "mismatch_codes": [],
            "error": {
                "code": "DB_SNAPSHOT_ERROR" if read_stage != "library_lookup" else "DB_READ_ERROR",
                "stage": read_stage,
                "message": str(exc),
            },
        }
    finally:
        if con_lib is not None:
            if in_transaction:
                try:
                    con_lib.execute("ROLLBACK")
                except Exception:
                    pass
            try:
                con_lib.close()
            except Exception:
                pass


    # Compare API observations with DB
    api_is_fav = api_state.get("is_favorite")
    api_in_fav = api_state.get("in_favorites")

    if api_is_fav != db_is_favorite:
        mismatch_codes.append("API_ITEM_DB_MISMATCH")
    if api_in_fav != db_is_favorite:
        mismatch_codes.append("API_COLLECTION_DB_MISMATCH")
    if api_is_fav != api_in_fav:
        mismatch_codes.append("API_INTERNAL_MISMATCH")

    passed = len(mismatch_codes) == 0

    return {
        "passed": passed,
        "internal_id": internal_id,
        "user_data_key": user_data_key,
        "row_counts": row_counts,
        "db_is_favorite": db_is_favorite,
        "mismatch_codes": mismatch_codes,
        "error": None,
    }
