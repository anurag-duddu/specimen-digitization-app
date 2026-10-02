"""Typed lookup producer cardinality at the actual projection writer boundary."""

import pytest

from specimen_digitization.application.domain import (
    Asset,
    Disposition,
    Evidence,
    FieldValue,
    LookupStatus,
    Observation,
    Principal,
    Profile,
    Region,
    Run,
    Scope,
    Specimen,
    ToolCallRecord,
    ValueState,
)
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.projection import writes
from specimen_digitization.application.storage import ProjectionResult, digest

from test_projection_writer import Session, repository


@pytest.fixture
def typed_lookup(tmp_path):
    session = Session()
    repo, blobs = repository(tmp_path, session)
    original = b"synthetic original fixture"
    asset = Asset(
        sensitive=False,
        sha256=blobs.put(original),
        blob_ref=blobs.put(original),
        media_type="image/png",
        size_bytes=len(original),
        width=200,
        height=100,
        filename="synthetic-producer-control.png",
        uploader="synthetic-worker",
    )
    region = Region(
        asset_id=asset.id, x=0, y=0, width=100, height=50, order=0,
        method="offline", version="producer-control-v1",
    )
    raw_reading = blobs.put(b'{"literal":"Synthetic Place"}')
    reading = Observation(
        region_id=region.id, route_id="offline-reader", model_id="offline-model",
        provider="offline-provider", prompt_version="producer-control-v1",
        input_sha256=asset.sha256, literal_text="Synthetic Place",
        raw_ref=raw_reading, raw_sha256=raw_reading,
        completion_state="validated_output",
    )
    raw_response = blobs.put(b'{"source":"synthetic-source","place":"synthetic-place"}')
    evidence = Evidence(
        kind="lookup", asset_id=asset.id, region_id=region.id,
        observation_ids=[reading.id], source="synthetic-source",
        locator="name/synthetic-place", excerpt="Synthetic Place",
        raw_ref=raw_response, digest=raw_response,
    )
    producer = ToolCallRecord(
        call_key="lookup:synthetic-source:producer-control:1",
        phase="lookup", tool="geography_lookup", tool_version="producer-control-v1",
        source="synthetic-source", field_keys=["city"], input_source="raw_reading",
        region_id=region.id, observation_id=reading.id, attempt=1,
        arguments={"q": "Synthetic Place"}, outcome=LookupStatus.SUCCESS,
        evidence_id=evidence.id,
        started_at="2026-09-30T00:00:00Z", completed_at="2026-09-30T00:00:01Z",
    )
    profile = Profile(id="synthetic-profile", version="producer-control-v1")
    snapshot = {"id": profile.id, "version": profile.version}
    run = Run(
        profile=profile, profile_snapshot=snapshot, profile_registry_version="registry-v1",
        dependencies={
            "profile_snapshot_sha256": digest(snapshot),
            "profile_registry_version": "registry-v1",
        },
        regions=[region], observations=[reading], evidence=[evidence],
        tool_calls=[producer], disposition=Disposition.REVIEW, reasons=["manual_control"],
        fields={"city": FieldValue(
            state=ValueState.SUPPORTED, literal="Synthetic Place",
            normalized="Synthetic Place", input_source="raw_reading",
            source_region_id=region.id, source_observation_id=reading.id,
            evidence_ids=[evidence.id], evidence_relations={evidence.id: "supports"},
        )},
    )
    specimen = Specimen(
        scope=Scope(
            organization_id="00000000-0000-0000-0000-000000000001",
            collection_id="00000000-0000-0000-0000-000000000002",
        ),
        asset=asset, run=run,
    )
    return specimen, repo, session, evidence.id


def validated(specimen):
    specimen = Specimen.model_validate(specimen.model_dump(mode="json"))
    assert type(specimen) is Specimen and type(specimen.run) is Run
    assert all(type(item) is Evidence for item in specimen.run.evidence)
    assert all(type(record) is ToolCallRecord for record in specimen.run.tool_calls)
    return specimen


def project(specimen, repo):
    token = actor_uid.set("synthetic-worker")
    try:
        return repo.write_projection(specimen.scope, specimen)
    finally:
        actor_uid.reset(token)


@pytest.mark.parametrize(
    "outcomes",
    [
        (),
        (LookupStatus.SUCCESS, LookupStatus.NO_MATCH),
        (LookupStatus.NO_MATCH, LookupStatus.SUCCESS),
        (LookupStatus.SUCCESS, LookupStatus.SUCCESS),
        (LookupStatus.NO_MATCH, LookupStatus.NO_MATCH),
    ],
    ids=["orphan", "success-first", "success-last", "duplicate-success", "duplicate-failure"],
)
def test_invalid_producer_count_stops_before_any_connector_write(typed_lookup, outcomes):
    specimen, repo, session, _ = typed_lookup
    original = specimen.run.tool_calls[0]
    specimen.run.tool_calls = [
        ToolCallRecord.model_validate({
            **original.model_dump(mode="json"),
            "call_key": f"{original.call_key}:producer-{index}",
            "attempt": index,
            "outcome": outcome,
        })
        for index, outcome in enumerate(outcomes, 1)
    ]
    specimen = validated(specimen)
    before = specimen.model_dump(mode="json")

    with pytest.raises(ValueError, match="^lookup_evidence_producer_invalid$"):
        writes(specimen, repo.locate, repo._sized, "synthetic-worker")
    assert project(specimen, repo) == ProjectionResult(False, "not_computed")
    assert session.calls == []
    assert specimen.model_dump(mode="json") == before


@pytest.mark.parametrize("outcome", [LookupStatus.SUCCESS, LookupStatus.NO_MATCH])
def test_one_producer_keeps_its_outcome_and_link_eligibility(typed_lookup, outcome):
    specimen, repo, session, evidence_id = typed_lookup
    specimen.run.tool_calls[0].outcome = outcome
    specimen.run.evidence[0].locator = (
        "name/synthetic-place" if outcome == LookupStatus.SUCCESS else None
    )
    specimen = validated(specimen)

    assert project(specimen, repo).complete
    row, = [
        variables for operation, variables in session.calls
        if operation == "AppendEvidenceItemV2" and variables["id"] == evidence_id
    ]
    assert row["outcome"] == outcome.value
    assert row["locator"] == specimen.run.evidence[0].locator
    links = [
        variables for operation, variables in session.calls
        if operation == "AppendCandidateEvidenceV2" and variables["evidenceId"] == evidence_id
    ]
    assert len(links) == (1 if outcome == LookupStatus.SUCCESS else 0)


def test_nonlookup_recorded_evidence_needs_no_lookup_producer(typed_lookup):
    specimen, repo, session, evidence_id = typed_lookup
    specimen.run.evidence[0].kind = "validation"
    specimen.run.tool_calls = []
    specimen = validated(specimen)

    assert project(specimen, repo).complete
    row, = [
        variables for operation, variables in session.calls
        if operation == "AppendEvidenceItemV2" and variables["id"] == evidence_id
    ]
    assert row["outcome"] == "recorded"
    assert any(
        operation == "AppendCandidateEvidenceV2" and variables["evidenceId"] == evidence_id
        for operation, variables in session.calls
    )


def test_unstored_lookup_stays_in_snapshot_without_a_projection_row(typed_lookup):
    specimen, repo, session, evidence_id = typed_lookup
    specimen.run.evidence[0].raw_ref = None
    specimen.run.evidence[0].digest = None
    specimen.run.tool_calls = []
    specimen = validated(specimen)

    assert project(specimen, repo).complete
    assert not any(
        (operation == "AppendEvidenceItemV2" and variables["id"] == evidence_id)
        or (operation == "AppendCandidateEvidenceV2" and variables["evidenceId"] == evidence_id)
        for operation, variables in session.calls
    )


def test_canonical_create_succeeds_when_lookup_projection_cannot_compute(typed_lookup):
    specimen, repo, session, evidence_id = typed_lookup
    specimen.run.tool_calls = []
    specimen = validated(specimen)
    principal = Principal(user_id="synthetic-worker", scope=specimen.scope, role="operator")
    token = actor_uid.set(principal.user_id)
    try:
        saved = repo.create(principal, specimen, "producer-guard-control", "d" * 64)
    finally:
        actor_uid.reset(token)

    assert saved.id == specimen.id and saved.version == 1
    assert saved.run.evidence[0].id == evidence_id and saved.run.tool_calls == []
    assert [operation for operation, _ in session.calls] == ["GetReceipt", "CreateSpecimenV3"]
    _, payload = session.calls[-1]
    assert payload["id"] == specimen.id
    assert payload["snapshotSha256"] == digest(payload["snapshot"])
