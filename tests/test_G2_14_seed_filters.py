import pytest

from scripts.G1_06_setup_and_verify import Server, SetupError
from scripts.G2_14_seed_filters import (
    FILTER_LIBRARY_NAME,
    FILTER_LIBRARY_PATH,
    get_or_create_filter_library,
)


class FakeClient:
    def __init__(self, library):
        self.server = Server("test", "http://test")
        self.library = library
        self.manifest = None

    def get_or_create_library(self, manifest):
        self.manifest = manifest
        return self.library


def test_get_or_create_filter_library_uses_dedicated_movie_manifest():
    library = {
        "Name": FILTER_LIBRARY_NAME,
        "ItemId": "filters-library-id",
        "CollectionType": "movies",
        "Locations": [FILTER_LIBRARY_PATH],
    }
    client = FakeClient(library)

    assert get_or_create_filter_library(client) == library
    config = client.manifest["library"]

    assert config["name"] == FILTER_LIBRARY_NAME
    assert config["collectionType"] == "movies"
    assert config["paths"] == [FILTER_LIBRARY_PATH]


def test_get_or_create_filter_library_rejects_unexpected_path():
    client = FakeClient(
        {
            "Name": FILTER_LIBRARY_NAME,
            "ItemId": "filters-library-id",
            "CollectionType": "movies",
            "Locations": ["/media/unexpected"],
        }
    )

    with pytest.raises(SetupError, match="different locations"):
        get_or_create_filter_library(client)
