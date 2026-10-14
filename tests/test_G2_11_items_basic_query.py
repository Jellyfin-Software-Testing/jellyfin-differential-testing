import os
from pathlib import Path

import pytest

from models.g1_10_items_model import ItemsTestModel
from normalizer import SemanticNormalizer
from normalizer.G2_07_diff_engine import SemanticDiffEngine
from scripts.G1_06_setup_and_verify import JellyfinClient, Server


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "config" / "normalization-rules.json"
ENDPOINT = "GET /Items"


@pytest.fixture(scope="module")
def clients():
    username = os.getenv("JELLYFIN_ADMIN_USERNAME", "admin")
    password = os.getenv("JELLYFIN_ADMIN_PASSWORD", "admin123456")

    servers = [
        Server("v10.8.13", "http://localhost:8096"),
        Server("v10.9.0", "http://localhost:8097"),
    ]

    result = []
    for server in servers:
        client = JellyfinClient(server, timeout=10)
        client.authenticate(username, password)
        result.append(client)

    return result


def get_items(client, query):
    params = {
        "userId": client.user_id,
        "recursive": "true",
        "includeItemTypes": "Audio",
        "sortBy": "SortName",
        "sortOrder": "Ascending",
        **query,
    }

    response = client.request(
        "GET",
        "/Items",
        params=params,
        authenticate=True,
        expected=(200,),
    )
    body = response.json()

    model_params = {**query, "includeItemTypes": ["Audio"]}
    valid, reason = ItemsTestModel.verify_invariants(model_params, body)
    assert valid, f"{client.server.label}: {reason}"
    assert all(item.get("Type") == "Audio" for item in body["Items"])

    return response, body


def comparable_body(body):
    return {
        "TotalRecordCount": body.get("TotalRecordCount"),
        "Items": [
            {
                key: item[key]
                for key in ("Id", "Name", "Type", "RunTimeTicks")
                if key in item
            }
            for item in body["Items"]
        ],
    }


def item_id_mapping(*bodies):
    mapping = {}
    for body in bodies:
        for item in body["Items"]:
            item_id = item.get("Id")
            name = item.get("Name")
            if isinstance(item_id, str) and isinstance(name, str):
                mapping[item_id] = f"item:{name}"
    return mapping


@pytest.mark.items_basic_query
@pytest.mark.parametrize(
    ("query", "expected_name"),
    [
        ({"startIndex": 0, "limit": 2}, None),
        ({"startIndex": 1, "limit": 1}, None),
        (
            {"startIndex": 0, "limit": 2, "searchTerm": "Reference Tone"},
            "01 - Reference Tone",
        ),
    ],
    ids=["first-page", "second-page", "search-seed-item"],
)
def test_items_basic_query_is_equivalent(clients, query, expected_name):
    response108, body108 = get_items(clients[0], query)
    response109, body109 = get_items(clients[1], query)

    if expected_name is not None:
        for client, body in zip(clients, (body108, body109)):
            names = [item.get("Name") for item in body["Items"]]
            assert expected_name in names, (
                f"{client.server.label}: không tìm thấy {expected_name!r}: {names}"
            )

    normalizer = SemanticNormalizer.from_file(RULES_PATH)
    mapping = item_id_mapping(body108, body109)

    normalized108 = normalizer.normalize(
        comparable_body(body108), endpoint=ENDPOINT, state_mapping=mapping
    )
    normalized109 = normalizer.normalize(
        comparable_body(body109), endpoint=ENDPOINT, state_mapping=mapping
    )

    diffs = SemanticDiffEngine().compare_responses(
        v1_status=response108.status_code,
        v2_status=response109.status_code,
        v1_headers={},
        v2_headers={},
        v1_body=normalized108,
        v2_body=normalized109,
    )

    assert not diffs, [diff.to_dict() for diff in diffs]