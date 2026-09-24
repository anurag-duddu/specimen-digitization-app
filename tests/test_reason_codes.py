"""The policy's reason codes in the collection configuration (LANE.md)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from specimen_digitization.application import policy
from specimen_digitization.application.policy import REASON_CODES

from test_application import HEADERS, PREFIX
from test_lane_trigger import lane_client


def emitted_codes():
    """Every code policy.evaluate appends, before any `:detail`, in rule order."""
    source = Path(policy.__file__).read_text()
    layers = re.findall(r'\("([a-z_]+)", field\.', source)
    codes = []
    for code in re.findall(r'failures\.append\(\s*f?"([a-z_{}]+)', source):
        expanded = (
            [code.replace("{layer}", layer) for layer in layers]
            if "{layer}" in code
            else [code]
        )
        codes.extend(c for c in expanded if c not in codes)
    return codes


def test_the_catalog_lists_exactly_the_codes_the_policy_emits_in_order():
    assert len(REASON_CODES) == len(set(REASON_CODES))
    assert list(REASON_CODES) == emitted_codes()


def test_the_collection_configuration_publishes_the_codes(tmp_path):
    client = lane_client(tmp_path)
    response = client.get(PREFIX + "/collections", headers=HEADERS)
    assert response.status_code == 200, response.text
    for item in response.json()["items"]:
        assert item["reason_codes"] == list(REASON_CODES)
