"""The monthly caps in the cost report: GET /v1/organizations/{org}/costs (TENANT_BUDGETS.md, COST_METER.md).

test_cost_api.py's client, with a repository that also reads caps. The caps'
positions are for the current UTC month, whatever range is asked for; spent is
that month's cost entries, settled and held, rolled up the collection tree.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from specimen_digitization.application import tenant_budget
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.storage import Conflict

from test_cost_api import BEETLES, COLLECTIONS, GROUPS, HEADERS, INSECTS, ORG, client, membership

URL = f"/v1/organizations/{ORG}/costs"


@pytest.fixture(autouse=True)
def october(monkeypatch):
    monkeypatch.setattr(tenant_budget, "utc_now", lambda: datetime(2026, 10, 20, 12, tzinfo=timezone.utc))


def capped(caps, groups=GROUPS):
    repository = Mock(spec=["cost_totals", "tenant_caps"])
    repository.cost_totals.return_value = {"collections": COLLECTIONS, "groups": groups}
    repository.tenant_caps.return_value = {
        "caps": [{"collection_key": key, "monthly_cap_micros": micros} for key, micros in caps],
        "collections": [{"id": INSECTS, "parent_id": None}, {"id": BEETLES, "parent_id": INSECTS}]}
    return repository


def position(cap, spent):
    return {"monthly_cap_micros": cap, "month": "2026-10", "spent_micros": spent,
            "remaining_micros": max(0, cap - spent)}


def caps_of(body):
    return body["organization_cap"], {item["collection_id"]: item["cap"] for item in body["collections"]}


def test_each_cap_is_reported_with_the_current_month_s_spend_rolled_up_the_tree():
    repository = capped([("organization", 20_000), (INSECTS, 9_600), (BEETLES, 500)])
    http, _ = client([membership("viewer"), membership("admin", collection=BEETLES)], repository=repository)
    with http:
        response = http.get(URL, params={"from": "2026-10", "to": "2026-10"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    # Insects' own SAM 3 hold (9,000, held) and Beetles' reading (550, settled):
    # Insects' cap counts both, as its child's spend rolls up.
    assert caps_of(body) == (position(20_000, 9_550), {INSECTS: position(9_600, 9_550), BEETLES: position(500, 550)})
    assert body["caps_status"] == "ok"
    assert body["totals"]["cost_micros"] == 9_550  # The report itself is unchanged.
    repository.cost_totals.assert_called_once_with(ORG, "2026-10", "2026-10")
    # Read as the caller's administrator membership in the organization.
    repository.tenant_caps.assert_called_once_with(Scope(organization_id=ORG, collection_id=BEETLES))


def test_the_caps_are_read_as_an_active_administrator_membership():
    # An admin row that is not active sorts first (Insects before Beetles): the
    # caps are read as the active one, as PUT .../costs/caps sets them.
    repository = capped([(BEETLES, 1_000)])
    http, _ = client([dict(membership("admin"), active=False), membership("admin", collection=BEETLES)],
        repository=repository)
    with http:
        response = http.get(URL, params={"from": "2026-10", "to": "2026-10"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["caps_status"] == "ok"
    assert caps_of(response.json())[1][BEETLES] == position(1_000, 550)
    repository.tenant_caps.assert_called_once_with(Scope(organization_id=ORG, collection_id=BEETLES))


def test_a_range_without_the_current_month_reads_that_month_once_more():
    repository = capped([(BEETLES, 1_000)])
    september = [dict(group, month="2026-09") for group in GROUPS]
    repository.cost_totals.side_effect = [{"collections": COLLECTIONS, "groups": september},
                                          {"collections": COLLECTIONS, "groups": GROUPS}]
    http, _ = client([membership("admin")], repository=repository)
    with http:
        response = http.get(URL, params={"from": "2026-08", "to": "2026-09"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert caps_of(body) == (None, {INSECTS: None, BEETLES: position(1_000, 550)})
    assert [call.args for call in repository.cost_totals.call_args_list] == [
        (ORG, "2026-08", "2026-09"), (ORG, "2026-10", "2026-10")]
    assert body["totals"]["cost_micros"] == 9_550  # September's, as asked.


@pytest.mark.parametrize("caps", [[], [("organization", None), (INSECTS, None)]], ids=["no_rows", "cleared"])
def test_with_no_cap_set_every_cap_is_null_and_nothing_more_is_read(caps):
    repository = capped(caps, groups=[dict(group, month="2026-09") for group in GROUPS])
    http, _ = client([membership("admin")], repository=repository)
    with http:
        response = http.get(URL, params={"from": "2026-08", "to": "2026-09"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert caps_of(body) == (None, {INSECTS: None, BEETLES: None}) and body["caps_status"] == "ok"
    repository.cost_totals.assert_called_once_with(ORG, "2026-08", "2026-09")


@pytest.mark.parametrize("failure", [
    tenant_budget.TenantBudgetUnavailable(), Conflict("SQL Connect transaction rejected"),
    PermissionError("Verified actor context required"),
], ids=["untrusted", "refused", "denied"])
def test_caps_that_cannot_be_read_leave_the_costs_whole(failure):
    repository = capped([("organization", 20_000)])
    repository.tenant_caps.side_effect = failure
    http, _ = client([membership("admin")], repository=repository)
    with http:
        response = http.get(URL, params={"from": "2026-10", "to": "2026-10"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert caps_of(body) == (None, {INSECTS: None, BEETLES: None})
    assert body["caps_status"] == "unavailable" and body["totals"]["cost_micros"] == 9_550


def test_shared_cost_allocations_and_their_credits_are_not_a_cap_s_spend():
    # A month in Google's free tier: Beetles' SAM 3 credit is larger than its residual.
    allocations = [
        {**GROUPS[0], "source": "allocation", "kind": "allocation", "stage": "label_finding", "provider": "google_cloud",
         "resource": "specimen-sam", "cost_basis": "allocated", "cost_micros": "-2000", "list_cost_micros": "300",
         "entries": "2"},
        {**GROUPS[1], "source": "allocation", "kind": "allocation", "stage": "database", "provider": "google_cloud",
         "resource": "cloud-sql", "cost_basis": "allocated", "cost_micros": "700", "list_cost_micros": "700",
         "entries": "1"},
    ]
    repository = capped([(INSECTS, 9_600), (BEETLES, 500)], groups=GROUPS + allocations)
    http, _ = client([membership("admin")], repository=repository)
    with http:
        response = http.get(URL, params={"from": "2026-10", "to": "2026-10"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["caps_status"] == "ok"
    assert caps_of(body) == (None, {INSECTS: position(9_600, 9_550), BEETLES: position(500, 550)})
    assert body["totals"]["cost_micros"] == 9_550 - 2_000 + 700  # The report itself counts them.


def test_a_failed_read_of_the_current_month_leaves_the_costs_whole():
    repository = capped([("organization", 20_000)])
    repository.cost_totals.side_effect = [{"collections": COLLECTIONS, "groups": []}, Conflict("rejected")]
    http, _ = client([membership("admin")], repository=repository)
    with http:
        response = http.get(URL, params={"from": "2026-09", "to": "2026-09"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert (response.json()["organization_cap"], response.json()["caps_status"]) == (None, "unavailable")
