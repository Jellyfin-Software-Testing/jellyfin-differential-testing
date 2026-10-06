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
