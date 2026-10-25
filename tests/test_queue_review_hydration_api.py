"""Only the queue request opts into verified legacy graph count reads."""

from test_application import HEADERS, PREFIX, SYNTHETIC_COLLECTION, client, intake


def test_queue_hydration_does_not_spread_to_detail_or_asset_lookup(tmp_path, monkeypatch):
    with client(tmp_path) as http:
        specimen = intake(http)
        repository = http.app.state.workflow.repository
        search = repository.search
        calls = []

        def observed_search(*args, **kwargs):
            calls.append(kwargs.get("hydrate_review", False))
            return search(*args, **kwargs)

        monkeypatch.setattr(repository, "search", observed_search)
        queue = http.get(
            PREFIX + "/specimens",
            params={"collection_id": SYNTHETIC_COLLECTION},
            headers=HEADERS,
        )
        assert queue.status_code == 200, queue.text
        assert calls == [True]
        row = queue.json()["items"][0]
        assert row["specimen_id"] == specimen["specimen_id"]
        assert row["available_actions"] == []

        for route in (
            f"/specimens/{row['specimen_id']}",
            f"/assets/{row['asset_id']}/access",
            f"/runs/{row['active_run_id']}/events",
        ):
            calls.clear()
            response = http.get(PREFIX + route, headers=HEADERS)
            assert response.status_code == 200, response.text
            assert calls and not any(calls)

        calls.clear()
        workspace = http.get(
            PREFIX + f"/specimens/{row['specimen_id']}/workspace", headers=HEADERS
        )
        assert workspace.status_code == 200, workspace.text
        assert not any(calls)
