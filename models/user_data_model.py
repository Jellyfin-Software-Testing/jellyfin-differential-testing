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

    @staticmethod
    def verify_action_invariants(
        action: FavoriteAction,
        status_code: int,
        response_data: Any,
        target_item_id: str,
        allowed_statuses: Iterable[int] = (200, 204),
    ) -> Tuple[bool, Optional[str]]:
        """Xác thực phản hồi trực tiếp (Tầng 1) của POST/DELETE FavoriteItems."""
        allowed_set = set(allowed_statuses)
        if status_code not in allowed_set:
            return False, f"HTTP status {status_code} not in allowed statuses {allowed_set}"

        expected_is_favorite = (action == FavoriteAction.MARK_FAVORITE)

        # Case 1: HTTP 204 No Content
        if status_code == 204:
            if response_data not in (None, "", b"", {}):
                return False, "HTTP 204 must have no body"
            return True, None

        # Case 2: HTTP 200 OK
        if status_code == 200:
            if not isinstance(response_data, dict) or not response_data:
                return False, "HTTP 200 rejects empty or invalid DTO body"

            if "IsFavorite" not in response_data:
                return False, "Response DTO missing required field 'IsFavorite'"

            actual_is_fav = response_data.get("IsFavorite")
            if actual_is_fav != expected_is_favorite:
                return False, f"Action {action.value} expected IsFavorite to be {expected_is_favorite}, got {actual_is_fav}"

            item_id_in_dto = response_data.get("ItemId")
            if item_id_in_dto is not None:
                if not UserDataTestModel.is_same_guid(item_id_in_dto, target_item_id):
                    return False, f"ItemId in DTO '{item_id_in_dto}' does not match target item '{target_item_id}'"

            play_count = response_data.get("PlayCount")
            if play_count is not None and (not isinstance(play_count, int) or play_count < 0):
                return False, f"Invalid PlayCount in DTO: {play_count}"

            return True, None

        # Case 3: Error statuses (401, 403, 404, etc.)
        return True, None

    @staticmethod
    def verify_item_persistence(
        expected_state: FavoriteState,
        item_response_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Xác thực trường UserData.IsFavorite từ endpoint GET /Users/{userId}/Items/{id}."""
        if not isinstance(item_response_data, dict):
            return False, "Item response data is not a dictionary"

        user_data = item_response_data.get("UserData")
        if not isinstance(user_data, dict):
            return False, "Item response data is missing 'UserData' dictionary"

        expected_bool = (expected_state == FavoriteState.FAVORITED)
        actual_bool = user_data.get("IsFavorite")
        if actual_bool != expected_bool:
            return False, f"Expected UserData.IsFavorite to be {expected_bool}, got {actual_bool}"

        return True, None

    @staticmethod
    def verify_collection_persistence(
        expected_state: FavoriteState,
        target_item_id: str,
        collection_response_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Xác thực sự hiện diện của item trong GET /Users/{userId}/Items?isFavorite=true."""
        if not isinstance(collection_response_data, dict):
            return False, "Collection response data is not a dictionary"

        items = collection_response_data.get("Items")
        if not isinstance(items, list):
            return False, "Collection response data is missing 'Items' list"

        item_present = any(
            UserDataTestModel.is_same_guid(item.get("Id"), target_item_id)
            for item in items
            if isinstance(item, dict)
        )

        if expected_state == FavoriteState.FAVORITED and not item_present:
            return False, f"Expected item {target_item_id} to be present in favorite collection, but was missing"

        if expected_state == FavoriteState.UNFAVORITED and item_present:
            return False, f"Expected item {target_item_id} to be ABSENT from favorite collection, but was present"

        return True, None

    @staticmethod
    def verify_two_way_isolation_step(
        step_name: str,
        user_a_state: FavoriteState,
        user_b_state: FavoriteState,
        user_a_item_data: Dict[str, Any],
        user_b_item_data: Dict[str, Any],
        target_item_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """Xác thực tính cô lập hai chiều giữa User A và User B tại mỗi bước của vòng đời."""
        ok_a, err_a = UserDataTestModel.verify_item_persistence(user_a_state, user_a_item_data)
        if not ok_a:
            return False, f"[{step_name}] User A isolation failure: {err_a}"

        ok_b, err_b = UserDataTestModel.verify_item_persistence(user_b_state, user_b_item_data)
        if not ok_b:
            return False, f"[{step_name}] User B isolation failure: {err_b}"

        return True, None

    @staticmethod
    def verify_schema_parity(
        v108_payload: Dict[str, Any],
        v109_payload: Dict[str, Any],
        required_fields: Optional[Set[str]] = None,
    ) -> Tuple[bool, List[str]]:
        """Pha 1: So sánh schema structural parity, phát hiện dropped fields hoặc type changes."""
        diffs: List[str] = []
        if not isinstance(v108_payload, dict) or not isinstance(v109_payload, dict):
            return False, ["One or both payloads are not dictionaries"]

        fields_to_check = required_fields or {"IsFavorite", "ItemId"}
        for f in fields_to_check:
            if f in v108_payload and f not in v109_payload:
                diffs.append(f"Field '{f}' dropped in v10.9 response")
            elif f not in v108_payload and f in v109_payload:
                diffs.append(f"New field '{f}' appeared in v10.9 response")
            elif f in v108_payload and f in v109_payload:
                t108 = type(v108_payload[f])
                t109 = type(v109_payload[f])
                if t108 != t109 and v108_payload[f] is not None and v109_payload[f] is not None:
                    diffs.append(f"Field '{f}' type mutation: v10.8 has {t108.__name__}, v10.9 has {t109.__name__}")

        return len(diffs) == 0, diffs

    @staticmethod
    def verify_semantic_parity(
        v108_result: Dict[str, Any],
        v109_result: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """Pha 2: So sánh logic nghiệp vụ và state transition semantics."""
        diffs: List[str] = []
        if v108_result.get("is_favorite") != v109_result.get("is_favorite"):
            diffs.append(
                f"Semantic state mismatch: v10.8 is_favorite={v108_result.get('is_favorite')}, "
                f"v10.9 is_favorite={v109_result.get('is_favorite')}"
            )
        return len(diffs) == 0, diffs

    @staticmethod
    def verify_normalized_payload_parity(
        v108_payload: Dict[str, Any],
        v109_payload: Dict[str, Any],
        ignored_fields: Optional[Set[str]] = None,
    ) -> Tuple[bool, Any]:
        """Pha 3: So sánh raw payload sau khi loại trừ các trường dynamic noise."""
        from deepdiff import DeepDiff

        ignore = ignored_fields or {"ServerId", "LastPlayedDate", "Key", "PlaybackPositionTicks"}
        filtered_108 = {k: v for k, v in v108_payload.items() if k not in ignore}
        filtered_109 = {k: v for k, v in v109_payload.items() if k not in ignore}

        diff = DeepDiff(filtered_108, filtered_109, ignore_string_case=True)
        return len(diff) == 0, diff

    @staticmethod
    def classify_differential_discrepancy(
        v108_resp: Dict[str, Any],
        v109_resp: Dict[str, Any],
        v108_persisted: FavoriteState,
        v109_persisted: FavoriteState,
        is_cross_user_attempt: bool = False,
    ) -> Optional[DiffCategory]:
        """Phân loại bản chất của sự sai lệch giữa v10.8 và v10.9."""
        status_108 = v108_resp.get("status_code")
        status_109 = v109_resp.get("status_code")

        # 1. Security Regression Check
        if is_cross_user_attempt:
            if status_108 in (401, 403) and status_109 in (200, 204):
                return DiffCategory.SECURITY_REGRESSION
            if status_109 in (401, 403) and status_108 in (200, 204):
                return DiffCategory.SECURITY_REGRESSION

        # 2. Semantic Regression Check
        if v108_persisted != v109_persisted:
            return DiffCategory.SEMANTIC_REGRESSION

        # 3. Schema Regression Check
        body_108 = v108_resp.get("body")
        body_109 = v109_resp.get("body")
        if isinstance(body_108, dict) and isinstance(body_109, dict):
            ok_schema, _ = UserDataTestModel.verify_schema_parity(body_108, body_109)
            if not ok_schema:
                return DiffCategory.SCHEMA_REGRESSION

        # 4. Benign Status Drift Check
        if status_108 != status_109 and {status_108, status_109}.issubset({200, 204}):
            if v108_persisted == v109_persisted:
                return DiffCategory.BENIGN_STATUS_DRIFT

        return None





