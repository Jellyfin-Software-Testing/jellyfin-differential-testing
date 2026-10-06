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

    @staticmethod
    def get_user_partitions() -> Dict[str, List[Any]]:
        return {
            "VALID_OWNER": ["admin"],
            "VALID_OTHER_USER": ["regular_user_b"],
            "NON_EXISTENT_GUID": ["00000000-0000-0000-0000-000000000000", "e4a1a3b2-9c12-4c22-b5e1-88c9910d9999"],
            "MALFORMED_STRING": ["invalid-user-guid", "12345", "../../admin"],
            "EMPTY_OR_WHITESPACE": ["", "   "],
        }

    @staticmethod
    def get_item_partitions() -> Dict[str, List[Any]]:
        return {
            "VALID_AUDIO_ITEM": ["01 - Reference Tone", "02 - Comparison Tone"],
            "VALID_FOLDER_ITEM": ["seed-music"],
            "NON_EXISTENT_GUID": ["ffffffff-ffff-ffff-ffff-ffffffffffff"],
            "RESTRICTED_ITEM": ["restricted-library-item-guid"],
            "MALFORMED_STRING": ["not-an-item", "null", "<script>"],
            "EMPTY_OR_WHITESPACE": ["", "   "],
        }

    @staticmethod
    def get_authorization_matrix() -> List[Dict[str, Any]]:
        return [
            {
                "actor": UserRole.OWNER,
                "target_user": UserRole.OWNER,
                "action": FavoriteAction.MARK_FAVORITE,
                "expected_outcome": OutcomeType.SUCCESS,
                "allowed_statuses": (200, 204),
            },
            {
                "actor": UserRole.OWNER,
                "target_user": UserRole.OWNER,
                "action": FavoriteAction.UNMARK_FAVORITE,
                "expected_outcome": OutcomeType.SUCCESS,
                "allowed_statuses": (200, 204),
            },
            {
                "actor": UserRole.OTHER_USER,
                "target_user": UserRole.OWNER,
                "action": FavoriteAction.MARK_FAVORITE,
                "expected_outcome": OutcomeType.REJECTED_FORBIDDEN,
                "allowed_statuses": (403, 401),
            },
            {
                "actor": UserRole.OTHER_USER,
                "target_user": UserRole.OWNER,
                "action": FavoriteAction.UNMARK_FAVORITE,
                "expected_outcome": OutcomeType.REJECTED_FORBIDDEN,
                "allowed_statuses": (403, 401),
            },
            {
                "actor": UserRole.ANONYMOUS,
                "target_user": UserRole.OWNER,
                "action": FavoriteAction.MARK_FAVORITE,
                "expected_outcome": OutcomeType.REJECTED_UNAUTHENTICATED,
                "allowed_statuses": (401,),
            },
        ]

    @staticmethod
    def get_path_and_method_boundaries() -> List[Dict[str, Any]]:
        return [
            {
                "case": "NORMAL_PATH",
                "template": "/Users/{userId}/FavoriteItems/{id}",
                "method": "POST",
                "expected_allowed": True,
            },
            {
                "case": "LOWERCASE_PATH",
                "template": "/users/{userId}/favoriteitems/{id}",
                "method": "POST",
                "expected_allowed": True,
            },
            {
                "case": "TRAILING_SLASH",
                "template": "/Users/{userId}/FavoriteItems/{id}/",
                "method": "POST",
                "expected_allowed": True,
            },
            {
                "case": "METHOD_NOT_ALLOWED",
                "template": "/Users/{userId}/FavoriteItems/{id}",
                "method": "GET",
                "allowed_statuses": (404, 405),
            },
        ]

    @staticmethod
    def get_guid_boundary_cases() -> List[Dict[str, Any]]:
        return [
            {"case": "RAW_32_HEX", "sample": "758cdd3734433b1bc7c6213a5c7179f2"},
            {"case": "HYPHENATED_36", "sample": "758cdd37-3443-3b1b-c7c6-213a5c7179f2"},
            {"case": "UPPERCASE_HYPHENATED", "sample": "758CDD37-3443-3B1B-C7C6-213A5C7179F2"},
            {"case": "LEADING_WHITESPACE", "sample": " 758cdd37-3443-3b1b-c7c6-213a5c7179f2"},
            {"case": "TRAILING_WHITESPACE", "sample": "758cdd37-3443-3b1b-c7c6-213a5c7179f2 "},
        ]

    @staticmethod
    def get_transition(
        pre_state: FavoriteState,
        action: FavoriteAction,
        actor: UserRole = UserRole.OWNER,
        target_user_exists: bool = True,
        target_item_exists: bool = True,
    ) -> ExpectedOutcome:
        """Tính toán ExpectedOutcome cho mọi trạng thái và hành động."""
        if not target_user_exists or not target_item_exists:
            return ExpectedOutcome(
                outcome_type=OutcomeType.REJECTED_NOT_FOUND,
                expected_post_state=pre_state,
                allowed_statuses=(404, 400),
                body_policy="ERROR_BODY_OPTIONAL",
                must_preserve_pre_state=True,
            )

        if actor == UserRole.ANONYMOUS:
            return ExpectedOutcome(
                outcome_type=OutcomeType.REJECTED_UNAUTHENTICATED,
                expected_post_state=pre_state,
                allowed_statuses=(401,),
                body_policy="ERROR_BODY_OPTIONAL",
                must_preserve_pre_state=True,
            )

        if actor == UserRole.OTHER_USER:
            return ExpectedOutcome(
                outcome_type=OutcomeType.REJECTED_FORBIDDEN,
                expected_post_state=pre_state,
                allowed_statuses=(403, 401),
                body_policy="ERROR_BODY_OPTIONAL",
                must_preserve_pre_state=True,
            )

        # Actor is OWNER or ADMIN acting on user's behalf
        if action == FavoriteAction.MARK_FAVORITE:
            is_idempotent = (pre_state == FavoriteState.FAVORITED)
            return ExpectedOutcome(
                outcome_type=OutcomeType.IDEMPOTENT_SUCCESS if is_idempotent else OutcomeType.SUCCESS,
                expected_post_state=FavoriteState.FAVORITED,
                allowed_statuses=(200, 204),
                body_policy="REQUIRE_DTO",
                must_preserve_pre_state=False,
            )
        else:  # UNMARK_FAVORITE (DELETE)
            is_idempotent = (pre_state == FavoriteState.UNFAVORITED)
            return ExpectedOutcome(
                outcome_type=OutcomeType.IDEMPOTENT_SUCCESS if is_idempotent else OutcomeType.SUCCESS,
                expected_post_state=FavoriteState.UNFAVORITED,
                allowed_statuses=(200, 204),
                body_policy="REQUIRE_DTO",
                must_preserve_pre_state=False,
            )

    @staticmethod
    def get_lifecycle_isolation_matrix() -> List[Dict[str, Any]]:
        return [
            {
                "step": 0,
                "name": "BASELINE",
                "action_user": None,
                "action": None,
                "expected_a": FavoriteState.UNFAVORITED,
                "expected_b": FavoriteState.UNFAVORITED,
            },
            {
                "step": 1,
                "name": "USER_A_MARKS_FAVORITE",
                "action_user": UserRole.OWNER,
                "action": FavoriteAction.MARK_FAVORITE,
                "expected_a": FavoriteState.FAVORITED,
                "expected_b": FavoriteState.UNFAVORITED,
            },
            {
                "step": 2,
                "name": "USER_B_MARKS_FAVORITE",
                "action_user": UserRole.OTHER_USER,
                "action": FavoriteAction.MARK_FAVORITE,
                "expected_a": FavoriteState.FAVORITED,
                "expected_b": FavoriteState.FAVORITED,
            },
            {
                "step": 3,
                "name": "USER_A_UNMARKS_FAVORITE",
                "action_user": UserRole.OWNER,
                "action": FavoriteAction.UNMARK_FAVORITE,
                "expected_a": FavoriteState.UNFAVORITED,
                "expected_b": FavoriteState.FAVORITED,
            },
            {
                "step": 4,
                "name": "USER_B_UNMARKS_FAVORITE",
                "action_user": UserRole.OTHER_USER,
                "action": FavoriteAction.UNMARK_FAVORITE,
                "expected_a": FavoriteState.UNFAVORITED,
                "expected_b": FavoriteState.UNFAVORITED,
            },
        ]


