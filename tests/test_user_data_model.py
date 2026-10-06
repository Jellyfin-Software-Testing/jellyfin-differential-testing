import uuid
import pytest
from models.user_data_model import (
    UserDataTestModel,
    FavoriteState,
    FavoriteAction,
    UserRole,
    OutcomeType,
    DiffCategory,
    ExpectedOutcome,
)


def test_enums_and_dataclasses_defined():
    assert FavoriteState.UNFAVORITED == "Unfavorited"
    assert FavoriteState.FAVORITED == "Favorited"
    assert FavoriteAction.MARK_FAVORITE == "POST"
    assert FavoriteAction.UNMARK_FAVORITE == "DELETE"
    assert UserRole.OWNER == "Owner"
    assert OutcomeType.SUCCESS == "Success"
    assert DiffCategory.BENIGN_STATUS_DRIFT == "BenignStatusDrift"


def test_is_same_guid_valid_equivalences():
    raw_32 = "758cdd3734433b1bc7c6213a5c7179f2"
    hyphenated = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    uppercase = "758CDD37-3443-3B1B-C7C6-213A5C7179F2"
    as_uuid = uuid.UUID(hyphenated)

    assert UserDataTestModel.is_same_guid(raw_32, hyphenated) is True
    assert UserDataTestModel.is_same_guid(hyphenated, uppercase) is True
    assert UserDataTestModel.is_same_guid(raw_32, as_uuid) is True


def test_is_same_guid_distinct_and_malformed():
    guid_a = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    guid_b = "b730f9fd-841b-9789-262f-9b84d119e58e"

    assert UserDataTestModel.is_same_guid(guid_a, guid_b) is False
    assert UserDataTestModel.is_same_guid(guid_a, "not-a-guid") is False
    assert UserDataTestModel.is_same_guid(guid_a, None) is False
    assert UserDataTestModel.is_same_guid(None, guid_a) is False
    assert UserDataTestModel.is_same_guid("", "") is False
    assert UserDataTestModel.is_same_guid(None, None) is False


def test_partitions_and_boundaries():
    users = UserDataTestModel.get_user_partitions()
    assert "VALID_OWNER" in users
    assert "VALID_OTHER_USER" in users
    assert "NON_EXISTENT_GUID" in users
    assert "MALFORMED_STRING" in users
    assert "EMPTY_OR_WHITESPACE" in users

    items = UserDataTestModel.get_item_partitions()
    assert "VALID_AUDIO_ITEM" in items
    assert "VALID_FOLDER_ITEM" in items
    assert "NON_EXISTENT_GUID" in items
    assert "RESTRICTED_ITEM" in items

    auth_matrix = UserDataTestModel.get_authorization_matrix()
    assert len(auth_matrix) >= 5
    # Verify User B modifying User A is marked as FORBIDDEN
    cross_user = next(
        entry for entry in auth_matrix
        if entry["actor"] == UserRole.OTHER_USER and entry["target_user"] == UserRole.OWNER
    )
    assert cross_user["expected_outcome"] == OutcomeType.REJECTED_FORBIDDEN

    boundaries = UserDataTestModel.get_path_and_method_boundaries()
    assert any(b["case"] == "TRAILING_SLASH" for b in boundaries)
    assert any(b["case"] == "METHOD_NOT_ALLOWED" for b in boundaries)


def test_state_machine_happy_path_and_idempotency():
    # Happy path: Unfavorited -> POST -> Favorited
    t1 = UserDataTestModel.get_transition(FavoriteState.UNFAVORITED, FavoriteAction.MARK_FAVORITE)
    assert t1.outcome_type == OutcomeType.SUCCESS
    assert t1.expected_post_state == FavoriteState.FAVORITED
    assert t1.allowed_statuses == (200, 204)
    assert t1.must_preserve_pre_state is False

    # Idempotent: Favorited -> POST -> Favorited
    t2 = UserDataTestModel.get_transition(FavoriteState.FAVORITED, FavoriteAction.MARK_FAVORITE)
    assert t2.outcome_type == OutcomeType.IDEMPOTENT_SUCCESS
    assert t2.expected_post_state == FavoriteState.FAVORITED
    assert t2.allowed_statuses == (200, 204)

    # Happy path: Favorited -> DELETE -> Unfavorited
    t3 = UserDataTestModel.get_transition(FavoriteState.FAVORITED, FavoriteAction.UNMARK_FAVORITE)
    assert t3.outcome_type == OutcomeType.SUCCESS
    assert t3.expected_post_state == FavoriteState.UNFAVORITED
    assert t3.allowed_statuses == (200, 204)

    # Idempotent: Unfavorited -> DELETE -> Unfavorited
    t4 = UserDataTestModel.get_transition(FavoriteState.UNFAVORITED, FavoriteAction.UNMARK_FAVORITE)
    assert t4.outcome_type == OutcomeType.IDEMPOTENT_SUCCESS
    assert t4.expected_post_state == FavoriteState.UNFAVORITED
    assert t4.allowed_statuses == (200, 204)


def test_state_machine_rejected_transitions_preserve_state():
    # Cross-user forbidden attempt must preserve pre-state
    t_forbidden = UserDataTestModel.get_transition(
        FavoriteState.UNFAVORITED,
        FavoriteAction.MARK_FAVORITE,
        actor=UserRole.OTHER_USER,
    )
    assert t_forbidden.outcome_type == OutcomeType.REJECTED_FORBIDDEN
    assert t_forbidden.expected_post_state == FavoriteState.UNFAVORITED
    assert t_forbidden.must_preserve_pre_state is True

    # Anonymous attempt must preserve pre-state
    t_anon = UserDataTestModel.get_transition(
        FavoriteState.FAVORITED,
        FavoriteAction.UNMARK_FAVORITE,
        actor=UserRole.ANONYMOUS,
    )
    assert t_anon.outcome_type == OutcomeType.REJECTED_UNAUTHENTICATED
    assert t_anon.expected_post_state == FavoriteState.FAVORITED
    assert t_anon.must_preserve_pre_state is True


def test_verify_action_invariants_status_200_valid_dto():
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    valid_dto = {
        "ItemId": "758cdd3734433b1bc7c6213a5c7179f2",
        "IsFavorite": True,
        "PlayCount": 0,
        "PlaybackPositionTicks": 0,
        "Played": False,
        "Key": "02 - Comparison Tone",
    }
    ok, err = UserDataTestModel.verify_action_invariants(
        action=FavoriteAction.MARK_FAVORITE,
        status_code=200,
        response_data=valid_dto,
        target_item_id=target_id,
    )
    assert ok is True
    assert err is None


def test_verify_action_invariants_status_200_empty_body_contract_violation():
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    ok, err = UserDataTestModel.verify_action_invariants(
        action=FavoriteAction.MARK_FAVORITE,
        status_code=200,
        response_data={},  # Empty body on 200 is a contract violation
        target_item_id=target_id,
    )
    assert ok is False
    assert "empty or invalid dto body" in err.lower()



def test_verify_action_invariants_status_204_no_body():
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    # 204 with None or empty string body passes
    ok, err = UserDataTestModel.verify_action_invariants(
        action=FavoriteAction.MARK_FAVORITE,
        status_code=204,
        response_data=None,
        target_item_id=target_id,
    )
    assert ok is True
    assert err is None


def test_verify_action_invariants_status_204_with_body_contract_violation():
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    ok, err = UserDataTestModel.verify_action_invariants(
        action=FavoriteAction.MARK_FAVORITE,
        status_code=204,
        response_data={"IsFavorite": True},  # 204 must NOT contain body
        target_item_id=target_id,
    )
    assert ok is False
    assert "204 must have no body" in err.lower()


def test_verify_action_invariants_inverted_is_favorite():
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    invalid_dto = {
        "ItemId": target_id,
        "IsFavorite": False,  # Should be True for MARK_FAVORITE
        "PlayCount": 0,
    }
    ok, err = UserDataTestModel.verify_action_invariants(
        action=FavoriteAction.MARK_FAVORITE,
        status_code=200,
        response_data=invalid_dto,
        target_item_id=target_id,
    )
    assert ok is False
    assert "expected IsFavorite to be True" in err


def test_verify_item_persistence():
    item_fav = {"Id": "item-1", "UserData": {"IsFavorite": True}}
    item_unfav = {"Id": "item-1", "UserData": {"IsFavorite": False}}

    assert UserDataTestModel.verify_item_persistence(FavoriteState.FAVORITED, item_fav)[0] is True
    assert UserDataTestModel.verify_item_persistence(FavoriteState.UNFAVORITED, item_unfav)[0] is True
    assert UserDataTestModel.verify_item_persistence(FavoriteState.FAVORITED, item_unfav)[0] is False


def test_verify_collection_persistence():
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    coll_containing = {
        "Items": [{"Id": "758cdd3734433b1bc7c6213a5c7179f2", "Name": "Tone"}],
        "TotalRecordCount": 1,
    }
    coll_empty = {"Items": [], "TotalRecordCount": 0}

    # FAVORITED must contain item
    assert UserDataTestModel.verify_collection_persistence(FavoriteState.FAVORITED, target_id, coll_containing)[0] is True
    assert UserDataTestModel.verify_collection_persistence(FavoriteState.FAVORITED, target_id, coll_empty)[0] is False

    # UNFAVORITED must NOT contain item
    assert UserDataTestModel.verify_collection_persistence(FavoriteState.UNFAVORITED, target_id, coll_empty)[0] is True
    assert UserDataTestModel.verify_collection_persistence(FavoriteState.UNFAVORITED, target_id, coll_containing)[0] is False


def test_verify_two_way_lifecycle_isolation():
    target_id = "758cdd37-3443-3b1b-c7c6-213a5c7179f2"
    # Step 3: A unmarks (A=False), but B is still marked (B=True)
    user_a_data = {"Id": target_id, "UserData": {"IsFavorite": False}}
    user_b_data = {"Id": target_id, "UserData": {"IsFavorite": True}}

    ok, err = UserDataTestModel.verify_two_way_isolation_step(
        step_name="USER_A_UNMARKS_FAVORITE",
        user_a_state=FavoriteState.UNFAVORITED,
        user_b_state=FavoriteState.FAVORITED,
        user_a_item_data=user_a_data,
        user_b_item_data=user_b_data,
        target_item_id=target_id,
    )
    assert ok is True
    assert err is None




