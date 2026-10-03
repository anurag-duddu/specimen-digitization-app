"""A real-shaped label with no `field_key: value` line, through the production composer.

On the ten recorded production specimens no reading line carries a field key, so
initial_requests._graph builds no event and no assembly, and fifteen fields (the
twelve literals, county, city and taxon) have no accepted assembly and, for the
twelve, no ready source. A specialist can only abstain on them. This test runs
that label through compose_production_research_workflow with the offline rig of
production_e2e_support (imported, not edited) and a scripted specialist that
abstains the way the v3 prompts tell a model to:

- waiting_policy on a field the committed profile declares missing policy
  "unstructured_label_event_unqualified" when no assembly or source can ground it;
- waiting_source only for a source that failed.

Without the declaration, waiting_policy is an operational block like
waiting_source, so the record ends processing_blocked with no disposition. With
it, the record lands in needs_human_review with mandatory_unresolved:{field}
reasons and no operational reason, while a failed source still blocks.

The label text is synthetic: only its shape (plain lines, no colon prefixes,
the locality, a date, a collector, habitat and method lines) comes from the
recorded snapshots. The scripted specialist is not a model: whether a real model
follows the prompt is not tested here, and its geography values cite the reading
they came from (see reading_provenance).
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import OperationalBlock, SyntheticAdapters, Workflow
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, ResearchScope, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import dts_policy_resolution, missing_irn_resolution
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, ImmutableFileBlobs, SqliteStateBackend,
)
from specimen_digitization.research_harness.sources import FixtureSourceTransport
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

from production_e2e_support import (
    COLLECTION, FIXTURES, ORG, WORKER, FakeDataConnect, GenerationBlobs, research_state,
    specimen_before_adjudication, worker_principal,
)

# Plain lines, no `key:` prefix. The locality is the public Chicago fixture the
# GEOLocate answer was recorded for; every other word is a placeholder.
LABEL_LINES = (
    "Synthetic specimen slide",
    "Chicago, Cook County",
    "Illinois, United States",
    "12 June 1948",
    "Synthetic Collector",
    "oak woodland margin",
    "light trap",
)
UNKEYED_LABEL = "\n".join(LABEL_LINES)
NAMED_TAXON_LABEL = "\n".join((*LABEL_LINES, "Danaus plexippus"))
POLICY = "unstructured_label_event_unqualified"
# The fields the committed profile declares missing policy: the twelve literals,
# county, city and taxon. The scripted specialist reads this set, not the source.
LITERALS = ("date_visited_from", "date_visited_to", "date_identified", "elevation_from_m", "elevation_to_m",
    "elevation_from_ft", "elevation_to_ft", "collectors", "fmnh_ins_number", "collection_code", "habitat",
    "collection_method")
DECLARED = frozenset(FieldKey(key) for key in (*LITERALS, "county", "city", "taxon"))
# The label names a locality, so GEOLocate grounds these five; the rest wait on policy.
GEOGRAPHY = (FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY, FieldKey.CITY,
    FieldKey.PRECISE_LOCATION)
GROUNDED_BY_GEOLOCATE = frozenset(GEOGRAPHY)
LOCALITY = {"country": "United States", "state": "Illinois", "county": "Cook", "locality": "Chicago",
    "place": "Chicago", **support.PLACEMENT}
VALUE = {FieldKey.COUNTRY: "United States", FieldKey.PROVINCE_STATE: "Illinois", FieldKey.COUNTY: "Cook",
    FieldKey.CITY: "Chicago", FieldKey.PRECISE_LOCATION: "Chicago, Cook County"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the offline test performs no HTTP")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


def build_rig(tmp_path, monkeypatch, label):
    # specimen_before_adjudication reads the module's LABEL_TEXT for the readings.
    monkeypatch.setattr(support, "LABEL_TEXT", label)
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    members = {WORKER: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
        "can_view_sensitive": False}]}
    backend.grant(DurabilityScope(ORG, COLLECTION, "membership", "membership", 1, WORKER, False))
    fake = FakeDataConnect(backend, members=members)
    blobs = GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    ordinary = Workflow(repository, blobs, SyntheticAdapters(blobs, label))
    token = actor_uid.set(WORKER)
    principal = worker_principal()
    created = repository.create(principal, specimen_before_adjudication(blobs), "e2e-intake", "e2e-intake")
    rig = SimpleNamespace(fake=fake, backend=backend, repository=repository, ordinary=ordinary,
        principal=principal, specimen_id=created.id, research_blobs=ImmutableFileBlobs(tmp_path / "research"),
        model_calls=[], source_urls=[])
    return rig, token


@pytest.fixture
def unkeyed(tmp_path, monkeypatch):
    rig, token = build_rig(tmp_path, monkeypatch, UNKEYED_LABEL)
    yield rig
    actor_uid.reset(token)


@pytest.fixture
def named_taxon(tmp_path, monkeypatch):
    rig, token = build_rig(tmp_path, monkeypatch, NAMED_TAXON_LABEL)
    yield rig
    actor_uid.reset(token)


def abstention(key, state, reason):
    """What the v3 prompts tell a specialist to return for a field it cannot ground."""
    if state == WorkState.WAITING_POLICY:
        return FieldResolution(field_key=key, work_state=state, value=FieldValue(state=ValueState.UNRESOLVED),
            reason=f"missing_policy:{POLICY} {reason}")
    return FieldResolution(field_key=key, work_state=state, value=FieldValue(), reason=reason)


def reading_provenance(request):
    """The decided reading a value was read from.

    A lookup in a request with no assembly has no producer unless the value that cites it names its
    reading; without these fields the publication ends native_publication_requires_reconciliation
    (a separate finding, independent of the missing-policy declaration, that no v3 prompt text
    addresses). The scripted geography specialist supplies them so this test isolates the
    disposition of the declared fields."""
    fragment = next(item for item in request.fragments if item.input_source == "decided_transcript")
    return dict(input_source=fragment.input_source, source_region_id=fragment.region_id,
        source_observation_id=fragment.observation_id,
        verbatim_by_observation={fragment.observation_id: fragment.observation_text},
        input_source_by_observation={fragment.observation_id: fragment.input_source},
        settled_observation_ids=[fragment.observation_id])


def geolocated(request, key, results):
    for result in results:
        if (result.coverage.source_id != "geolocate" or result.coverage.field_key != key
                or result.status != LookupStatus.SUCCESS):
            continue
        [candidate] = [json.loads(raw) for raw in result.candidate_json]
        evidence = tuple(item.id for item in result.evidence)
        return FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
            value_layer="verbatim" if key == FieldKey.PRECISE_LOCATION else "settled",
            value=FieldValue(state=ValueState.SUPPORTED, normalized=candidate["value"],
                authority_id=candidate["authority_id"], evidence_ids=list(evidence),
                evidence_relations=dict.fromkeys(evidence, "supports"), **reading_provenance(request)),
            evidence_ids=evidence, reason=f"Label writes {candidate['value']}; GEOLocate confirms it")
    raise AssertionError(f"no GEOLocate success for {key}")


def specialist_factory(log, *, abstain, source_first=False):
    """A scripted specialist for the unkeyed label.

    ``abstain`` is the work state it returns for a declared field nothing can ground:
    waiting_policy (the v3 prompts) or waiting_source (the v2 prompts). With
    ``source_first`` the taxonomy specialist queries GBIF for the taxon the label
    names and returns waiting_source when that lookup fails."""
    def factory(request, binding):
        role = request.role

        def respond(messages, info):
            log.append((str(role), 1 + sum(isinstance(message, ModelResponse) for message in messages)))
            results, attempted = support._results(messages)
            if role == SpecialistRole.TAXONOMY and source_first and not attempted:
                return ModelResponse(parts=[ToolCallPart("lookup_source", {"query": {
                    "source_id": "gbif", "field_key": "taxon", "query_text": "Danaus plexippus"}},
                    tool_call_id="unkeyed-gbif")], usage=support.USAGE)
            if role == SpecialistRole.GEOGRAPHY and not attempted:
                return ModelResponse(parts=[ToolCallPart("lookup_source", {"query": {
                    "source_id": "geolocate", "field_key": str(key),
                    "query_text": json.dumps({**LOCALITY, "value": VALUE[key]})}},
                    tool_call_id=f"unkeyed-geolocate-{key}") for key in GEOGRAPHY], usage=support.USAGE)
            resolutions = []
            for key in request.field_keys:
                if key == FieldKey.IDENTIFIED_BY_IRN:
                    resolutions.append(missing_irn_resolution())
                elif key == FieldKey.VERBATIM_DTS:
                    resolutions.append(dts_policy_resolution(None))
                elif key in GROUNDED_BY_GEOLOCATE:
                    resolutions.append(geolocated(request, key, results))
                elif key == FieldKey.TAXON and source_first:
                    # The lookup ended without a result to resolve from: a failed source, not an absence.
                    assert results and results[0].status != LookupStatus.SUCCESS
                    resolutions.append(abstention(key, WorkState.WAITING_SOURCE, "the GBIF lookup failed"))
                else:
                    state = abstain if key in DECLARED else WorkState.WAITING_SOURCE
                    resolutions.append(abstention(key, state, "no assembly and no source can ground it"))
            output = SpecialistOutput(role=role, resolutions=tuple(resolutions))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"),
                tool_call_id=f"unkeyed-{role.value}-output")], usage=support.USAGE)

        return FunctionModel(respond)
    return factory


def transport(log, *, gbif_status=None):
    """The recorded Chicago GEOLocate answer; GBIF answers ``gbif_status`` (a failure) when given."""
    manifest = json.loads((FIXTURES / "sources.json").read_text())
    chicago = (FIXTURES / manifest["geolocate"]["body"]).read_bytes()

    async def read(url, policy):
        log.append(url)
        if policy.id == "geolocate":
            assert url == manifest["geolocate"]["url"], url
            return 200, chicago
        assert policy.id == "gbif" and gbif_status is not None, f"unexpected request {policy.id} {url}"
        return gbif_status, b"{}"
    return FixtureSourceTransport(read)


def compose(rig, factory, source_transport):
    return compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=WORKER, state_backend=rig.backend,
        model_factory=factory, source_transport=source_transport, blobs=rig.research_blobs)


def supervised():
    return WorkerDeadline(time.monotonic() + 600).scope()


def to_plan(workflow, rig):
    with supervised():
        workflow.step(rig.principal, rig.specimen_id)
        parsed = workflow.step(rig.principal, rig.specimen_id)
    assert rig.ordinary.next_step(parsed.run) == "plan" and len(parsed.run.fields) == 20
    return parsed


def run_research(rig, factory, source_transport):
    """Plan to research: the specimen as the worker's plan tick leaves it, or the hold it raised."""
    workflow = compose(rig, factory, source_transport)
    parsed = to_plan(workflow, rig)
    try:
        with supervised():
            return parsed, workflow.step(rig.principal, rig.specimen_id), None
    except OperationalBlock as hold:
        return parsed, rig.repository.get(rig.principal.scope, rig.specimen_id), hold


def test_the_unkeyed_label_gives_the_request_fragments_and_no_event_or_assembly(unkeyed):
    """The premise, read from the graph the production request factory builds from the ordinary
    snapshot: every line of every reading is a fragment, and nothing is an event or an assembly."""
    parsed = to_plan(compose(unkeyed, specialist_factory([], abstain=WorkState.WAITING_POLICY), transport([])),
        unkeyed)
    assert not [key for key, value in parsed.run.fields.items() if value.state == "supported"]
    scope = ResearchScope(organization_id=ORG, collection_id=COLLECTION, specimen_id=unkeyed.specimen_id,
        job_id="job", generation=1, input_digest="e" * 64, profile_digest="f" * 64, sensitive=False)
    fragments, events, assemblies, _, _ = NativeGenerationRequestFactory._graph(parsed, scope)
    assert len(fragments) >= len(LABEL_LINES) and events == () and assemblies == ()


def test_an_unkeyed_label_lands_in_needs_human_review_on_the_declared_fields(unkeyed):
    """FAILS on origin/main: the profile declares only verbatim_dts, so every waiting_policy
    field below blocks the record (processing_blocked, no disposition, an operational hold)."""
    parsed, specimen, hold = run_research(unkeyed, specialist_factory(unkeyed.model_calls,
        abstain=WorkState.WAITING_POLICY), transport(unkeyed.source_urls))
    assert hold is None, f"the record is held: {hold}"
    assert specimen.run.stage == "finalized" and specimen.run.disposition == "needs_human_review"
    reasons = set(specimen.run.reasons)
    unresolved = {f"mandatory_unresolved:{key}" for key in (*LITERALS, "taxon", "verbatim_dts")}
    assert {reason for reason in reasons if reason.startswith("mandatory_unresolved:")} == unresolved
    assert not [reason for reason in reasons if reason.startswith(("research_work:", "canonical_"))]
    receipts = sorted(unkeyed.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    progress = receipts[-1]["causal_proof"]["progress_receipt"]
    # No operational reason. The rig never confirms label coverage, a review reason of its own.
    assert tuple(progress["operational_reason_codes"]) == ()
    assert unresolved <= set(progress["human_reason_codes"]) <= unresolved | {"label_coverage_unconfirmed"}
    assert progress["disposition"] == "needs_human_review" and progress["wire_status"] == "completed"
    # The five geography fields GEOLocate grounded publish; no declared field does.
    published = {row["causal_proof"]["changed_field"] for row in receipts}
    assert published == {*map(str, GEOGRAPHY), "identified_by_irn"}
    assert unkeyed.fake.specimens[unkeyed.specimen_id]["state"] != "processing_blocked"
    _, state = research_state(unkeyed.fake, unkeyed.specimen_id)
    job = list(state["jobs"].values())[0]
    assert {key for key, row in job["fields"].items() if row["work_state"] == "waiting_policy"} == {
        *map(str, DECLARED - {FieldKey.COUNTY, FieldKey.CITY}), "verbatim_dts"}


def test_parties_runs_last_so_the_always_terminal_irn_publishes_the_final_state(unkeyed):
    """FAILS on origin/main: COLLECTION is last, nothing in it is terminal, and the last publication
    (identified_by_irn) predates its result, so the record cannot finalize."""
    assert list(SpecialistRole)[-2:] == [SpecialistRole.COLLECTION, SpecialistRole.PARTIES]
    parsed, specimen, hold = run_research(unkeyed, specialist_factory(unkeyed.model_calls,
        abstain=WorkState.WAITING_POLICY), transport(unkeyed.source_urls))
    roles = [role for role, _ in unkeyed.model_calls]
    assert roles == ["specimen_taxonomy", "specimen_geography", "specimen_geography", "specimen_temporal",
        "specimen_measurement", "specimen_collection", "specimen_parties"]
    receipts = sorted(unkeyed.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    assert receipts[-1]["causal_proof"]["changed_field"] == "identified_by_irn"
    assert hold is None and specimen.run.stage == "finalized"


def test_waiting_source_on_a_declared_field_still_blocks_the_record(unkeyed):
    """The v2 prompts' abstention: the declaration holds only waiting_policy, so a field a specialist
    reports as waiting on a source blocks the record, as it does on origin/main."""
    parsed, specimen, hold = run_research(unkeyed, specialist_factory(unkeyed.model_calls,
        abstain=WorkState.WAITING_SOURCE), transport(unkeyed.source_urls))
    assert isinstance(hold, OperationalBlock) and str(hold) == "native_research_operational_hold"
    assert specimen.run.stage == "processing_blocked" and specimen.run.disposition is None
    blocking = {reason for reason in specimen.run.reasons if reason.startswith("research_work:")}
    assert blocking == {f"research_work:{key}:waiting_source" for key in (*LITERALS, "taxon")}
    assert unkeyed.fake.specimens[unkeyed.specimen_id]["state"] == "processing_blocked"


@pytest.mark.parametrize("status", [503, 429])
def test_a_failed_source_still_blocks_while_the_other_declared_fields_wait_on_policy(named_taxon, status):
    """The label names a taxon; GBIF fails (503) or rate-limits (429). The specialist returns
    waiting_source for taxon, which blocks the record even though taxon is a declared field,
    while the twelve literals and verbatim_dts are held for review."""
    parsed, specimen, hold = run_research(named_taxon, specialist_factory(named_taxon.model_calls,
        abstain=WorkState.WAITING_POLICY, source_first=True), transport(named_taxon.source_urls, gbif_status=status))
    assert any("gbif" in url for url in named_taxon.source_urls)
    assert isinstance(hold, OperationalBlock) and str(hold) == "native_research_operational_hold"
    assert specimen.run.stage == "processing_blocked" and specimen.run.disposition is None
    reasons = set(specimen.run.reasons)
    assert {reason for reason in reasons if reason.startswith("research_work:")} == {"research_work:taxon:waiting_source"}
    assert {f"mandatory_unresolved:{key}" for key in (*LITERALS, "verbatim_dts")} <= reasons
    assert "mandatory_unresolved:taxon" not in reasons
    _, state = research_state(named_taxon.fake, named_taxon.specimen_id)
    assert list(state["jobs"].values())[0]["fields"]["taxon"]["work_state"] == "waiting_source"
