"""
Test Model cho nhóm API User/UserData (POST/DELETE FavoriteItems)
Task Jira: G1-12
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import uuid


class FavoriteState(str, Enum):
    UNFAVORITED = "Unfavorited"
    FAVORITED = "Favorited"


class FavoriteAction(str, Enum):
    MARK_FAVORITE = "POST"
    UNMARK_FAVORITE = "DELETE"


class UserRole(str, Enum):
    OWNER = "Owner"
    OTHER_USER = "OtherUser"
    ADMIN = "Admin"
    ANONYMOUS = "Anonymous"


class OutcomeType(str, Enum):
    SUCCESS = "Success"
    IDEMPOTENT_SUCCESS = "IdempotentSuccess"
    REJECTED_UNAUTHENTICATED = "RejectedUnauthenticated"
    REJECTED_FORBIDDEN = "RejectedForbidden"
    REJECTED_NOT_FOUND = "RejectedNotFound"
    REJECTED_BAD_REQUEST = "RejectedBadRequest"


class DiffCategory(str, Enum):
    BENIGN_STATUS_DRIFT = "BenignStatusDrift"
    SCHEMA_REGRESSION = "SchemaRegression"
    SEMANTIC_REGRESSION = "SemanticRegression"
    SECURITY_REGRESSION = "SecurityRegression"


@dataclass(frozen=True)
class ExpectedOutcome:
    outcome_type: OutcomeType
    expected_post_state: Optional[FavoriteState]
    allowed_statuses: Tuple[int, ...]
    body_policy: str  # "REQUIRE_DTO", "NO_BODY", "ERROR_BODY_OPTIONAL"
    must_preserve_pre_state: bool


class UserDataTestModel:
    """Định nghĩa Partitions, Boundaries, State Machine, Invariants cho nhóm API User/UserData."""

    @staticmethod
    def is_same_guid(a: Any, b: Any) -> bool:
        """So sánh 2 giá trị theo bản chất ngữ nghĩa RFC 4122 UUID 128-bit.
        
        Trả về True khi và chỉ khi cả 2 giá trị parse thành công thành UUID
        và có cùng giá trị 128-bit. Trả về False an toàn cho None hoặc malformed.
        """
        if a is None or b is None:
            return False
        try:
            uuid_a = a if isinstance(a, uuid.UUID) else uuid.UUID(str(a))
            uuid_b = b if isinstance(b, uuid.UUID) else uuid.UUID(str(b))
            return uuid_a.int == uuid_b.int
        except (ValueError, AttributeError, TypeError):
            return False
