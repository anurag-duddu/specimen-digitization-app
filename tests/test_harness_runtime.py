"""The field harness in the workflow's `parse` step (HARNESS.md section 14)."""

import json
from functools import partial
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_application import client, intake

from specimen_digitization.application import collection_runtime, harness_runtime
from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import (
    FieldValue,
    HarnessCall,
    Lookup,
    Principal,
    Profile,
    ReaderHandoff,
    Run,
    Scope,
    ToolCallRecord,
    Transcript,
)
from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.domain import ValueState as V
from specimen_digitization.application.harness_knowledge import insects
from specimen_digitization.application.harness_tools import (
    SourceCall,
    TaxonCandidate,
    ToolResult,
)
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    digest,
)
from specimen_digitization.application.taxonomy_tool import Verification
from specimen_digitization.application.workflow import (
    OperationalBlock,
    SyntheticAdapters,
    Workflow,
)
from specimen_digitization.model_gateway import HuggingFaceInferenceRoute
from specimen_digitization.prompts import PromptName, ResolvedPrompt

ROUTE = HuggingFaceInferenceRoute(
    "harness-test", "field_harness", "vendor/text", "deepinfra"
)
PROMPT = ResolvedPrompt(
    name=PromptName.FIELD_HARNESS,
    text="You are the field harness.",
    requested_label="test",
    served_label=None,
    version=None,
    resolution_reason="fixture",
)
KNOWLEDGE = {"id": "insects", "version": insects.KNOWLEDGE_VERSION}
DECIDED = "Chimaltenango, GUAT.\nEpipsocus sp."


def transcript(region, *handoffs, resolved=True, text=None):
    return Transcript(
        region_id=region,
        text=text,
        observation_ids=[h.observation_id for h in handoffs] or ["o-only"],
        alternatives=[],
        resolved=resolved,
        handoffs=list(handoffs),
    )


def handoff(observation, role, text, note=None):
    return ReaderHandoff(
        observation_id=observation, role=role, handed_text=text, note=note
    )


def run_for(transcripts, snapshot=None):
    return Run(
        profile=Profile(
            mandatory_fields=["taxon", "city"], harness_route=ROUTE.route_id
        ),
        profile_snapshot=snapshot
        if snapshot is not None
        else {
            "optional_fields": ["identified_by_irn"],
            "field_tools": {
                "taxon": ["taxonomy_verifier"],
                "city": ["geography_lookup"],
            },
            "date_rules": {"version": "date-rules-v1", "two_digit_year_century": 1900},
            "harness_knowledge": KNOWLEDGE,
        },
        transcripts=transcripts,
    )


def test_the_payload_hands_every_reading_and_the_profiles_plan():
    run = run_for(
        [
            transcript(
                "r1",
                handoff("o-muse", "decided_transcript", DECIDED),
                handoff("o-qwen", "raw_reading", "Chimaltenago", "misread"),
            ),
            transcript("r2", resolved=True, text="det. 1948"),  # No handoffs kept.
        ]
    )

    payload = harness_runtime.harness_payload(run)

    assert [
        (r["region_id"], r["observation_id"], r["role"], r["note"])
        for r in payload["readings"]
    ] == [
        ("r1", "o-muse", "decided_transcript", None),
        ("r1", "o-qwen", "raw_reading", "misread"),
        ("r2", "o-only", "decided_transcript", None),
    ]
    assert payload["plan"] == {
        "mandatory": ["taxon", "city"],
        "optional": ["identified_by_irn"],
        "tools": {"taxon": "taxonomy_verifier", "city": "geography_lookup"},
    }
    assert payload["knowledge"] == KNOWLEDGE
    assert payload["date_rules"]["two_digit_year_century"] == 1900


class Gateway:
    """The pinned route answered by a fake model."""

    def __init__(self, timeout_seconds=None):
        self.routes = {ROUTE.route_id: ROUTE}

    def route(self, route_id):
        return self.routes[route_id]

    def model_for(self, route_id):
        def respond(messages, info):
            answer = {
                "literals": [
                    {"field_key": "taxon", "reading": "1A", "literal": "Epipsocus"},
                    {"field_key": "city", "reading": "1A", "literal": "Chimaltenango"},
                ]
            }
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, json.dumps(answer))]
            )

        return FunctionModel(respond, model_name="fake-harness")


def taxon(literal, **kwargs):
    usage = TaxonCandidate(
        source="gbif", usage_key="8MQRG", name="Epipsocus Hagen, 1866"
    )
    calls = [
        SourceCall(
            source="gbif", query={"name": literal}, retrieved_at="t", outcome=S.SUCCESS
        )
    ]
    result = ToolResult(
        tool="taxonomy_verifier",
        tool_version="v1",
        outcome=S.SUCCESS,
        taxa=[usage],
        sub_calls=calls,
    )
    return Verification(
        result,
        Lookup(provider="gbif", adapter_version="v2", query={}, status=S.SUCCESS),
    )


def geocode(query, **kwargs):
    call = SourceCall(
        source="google-maps-geocoding",
        query={"address": "x"},
        retrieved_at="t",
        outcome=S.RATE_LIMITED,
    )
    # Like the real tool, it reports only assigned fields, never the
    # unassigned locality text ("GUAT." here).
    outcomes = {i.field_key: S.RATE_LIMITED for i in query.literals if i.field_key}
    return ToolResult(
        tool="geography_lookup",
        tool_version="v1",
        outcome=S.RATE_LIMITED,
        field_outcomes=outcomes,
        sub_calls=[call],
    )


@pytest.fixture
def child(monkeypatch, tmp_path):
    """harness_direct against the fake route and tools; returns (call, specimen)."""
    from specimen_digitization.application import geography_tool, taxonomy_tool

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setattr(harness_runtime, "HuggingFaceModelGateway", Gateway)
    monkeypatch.setattr(taxonomy_tool, "verify_taxon", taxon)
    monkeypatch.setattr(geography_tool, "geocode_locality", geocode)
    run = run_for([transcript("r1", handoff("o-muse", "decided_transcript", DECIDED))])
    run.dependencies = {
        "routes": {
            ROUTE.route_id: {"model_id": ROUTE.model_id, "provider": ROUTE.provider}
        },
        "prompts": {PROMPT.name.value: PROMPT.model_dump(mode="json")},
    }
    specimen = SimpleNamespace(asset=SimpleNamespace(id="asset-1"), run=run)
    adapter = SimpleNamespace(blobs=LocalBlobs(tmp_path / "blobs"))

    def call(payload=None):
        payload = payload or harness_runtime.harness_payload(run)
        return harness_runtime.harness_direct(adapter, specimen, payload)

    return call, specimen


def test_the_child_runs_the_harness_on_the_pinned_route_prompt_and_knowledge(child):
    call, _ = child

    value = call()

    assert value["fields"]["taxon"]["authority_id"] == "8MQRG"
    # Google rate-limited after its retries: the run blocks (QUE-005).
    assert value["blocker"] == "harness_geography_lookup_rate_limited"
    assert value["failure"] is None
    assert {c["tool"] for c in value["tool_calls"]} == {
        "taxonomy_verifier",
        "geography_lookup",
    }
    assert value["usage"]["requests"] == 1
    assert value["call"] == {
        "route_id": ROUTE.route_id,
        "model_id": ROUTE.model_id,
        "provider": ROUTE.provider,
        "geocoding_requests": 1,  # One Google attempt, rate-limited.
    }
    assert set(value["fields"]) == {"taxon", "city", "identified_by_irn"}


@pytest.mark.parametrize(
    "change, code",
    [
        (
            lambda run: run.dependencies.update(routes={}),
            "pinned_model_route_unavailable",
        ),
        (lambda run: run.dependencies.update(prompts={}), "pinned_prompt_unavailable"),
        (
            lambda run: run.profile_snapshot.pop("harness_knowledge"),
            "harness_knowledge_unavailable",
        ),
        (
            lambda run: run.profile_snapshot.update(
                harness_knowledge={"id": "insects", "version": "v0"}
            ),
            "harness_knowledge_unavailable",
        ),
    ],
    ids=["route", "prompt", "no-knowledge", "unknown-version"],
)
def test_the_child_refuses_what_the_run_did_not_pin(child, change, code):
    call, specimen = child
    change(specimen.run)

    with pytest.raises(OperationalBlock, match=code):
        call()


def test_the_child_needs_approved_inference(child, monkeypatch):
    call, _ = child
    monkeypatch.delenv("SPECIMEN_APPROVED_INFERENCE")

    with pytest.raises(
        OperationalBlock, match="provider_data_policy_and_spending_approval_required"
    ):
        call()


def test_every_place_query_names_the_profiles_knowledge(child, monkeypatch):
    # PLAN 4.8's filter reads the knowledge the profile names (HARNESS.md 7).
    from specimen_digitization.application import geography_tool

    call, _ = child
    queries = []

    def recorded(query, **kwargs):
        queries.append(query)
        return geocode(query, **kwargs)

    monkeypatch.setattr(geography_tool, "geocode_locality", recorded)

    call()

    (query,) = queries
    assert (query.knowledge_id, query.reading_texts) == ("insects", [DECIDED])


def outcome(fields, blocker=None, failure=None):
    return {
        "fields": {k: v.model_dump(mode="json") for k, v in fields.items()},
        "evidence": [],
        "findings": [],
        "tool_calls": [],
        "lookups": [
            Lookup(
                provider="gbif", adapter_version="v2", query={}, status=S.SUCCESS
            ).model_dump(mode="json")
        ],
        "blocker": blocker,
        "failure": failure,
        "usage": {"input_tokens": 1200, "output_tokens": 300, "requests": 2},
        "call": {
            "route_id": ROUTE.route_id,
            "model_id": ROUTE.model_id,
            "provider": ROUTE.provider,
            "geocoding_requests": 1,
        },
    }


def test_merge_keeps_the_outcome_and_returns_a_tool_block():
    run = run_for([])
    fields = {
        "taxon": FieldValue(state=V.SUPPORTED, literal="Epipsocus"),
        "city": FieldValue(),
        "identified_by_irn": FieldValue(),
    }

    block = harness_runtime.merge_harness(
        run, outcome(fields, "harness_taxonomy_verifier_timeout", "harness_usage_limit")
    )

    assert block == "harness_taxonomy_verifier_timeout"
    assert run.fields["taxon"].literal == "Epipsocus" and len(run.lookups) == 1
    assert (run.harness_failure, run.usage.tokens) == ("harness_usage_limit", 1500)
    # The model call as the lane's cost record reads it (S3's record_step).
    assert run.harness_calls == [
        HarnessCall(
            attempt=1,
            route_id=ROUTE.route_id,
            model_id=ROUTE.model_id,
            provider=ROUTE.provider,
            requests=2,
            input_tokens=1200,
            output_tokens=300,
            geocoding_requests=1,
        )
    ]


def test_merge_keeps_unreported_usage_unknown():
    # Tokens a provider did not report are unknown, not zero, so the lane
    # keeps the step reserved instead of settling it at nothing.
    run = run_for([])
    run.attempts["parse"] = 2
    fields = {key: FieldValue() for key in ("taxon", "city", "identified_by_irn")}
    value = outcome(fields)
    value["usage"] = {"input_tokens": 0, "output_tokens": 0, "requests": 2}

    harness_runtime.merge_harness(run, value)

    (call,) = run.harness_calls
    assert (call.attempt, call.requests, call.input_tokens, call.output_tokens) == (
        2,
        2,
        None,
        None,
    )


def test_merge_refuses_fields_the_plan_does_not_name():
    with pytest.raises(OperationalBlock, match="external_outcome_unknown"):
        harness_runtime.merge_harness(run_for([]), outcome({"taxon": FieldValue()}))


class HarnessAdapters(SyntheticAdapters):
    """A synthetic harness that verifies the taxon, then returns `block`."""

    def __init__(self, blobs, block=None):
        super().__init__(blobs, SYNTHETIC_TEXT)
        self.block, self.harnessed, self.looked_up = block, [], []

    def harness(self, specimen):
        run = specimen.run
        self.harnessed.append(run.id)
        run.tool_calls.append(
            ToolCallRecord(
                call_key="lookup:taxonomy_verifier:gbif:decided_transcript:r:-:0:1",
                phase="lookup",
                tool="taxonomy_verifier",
                tool_version="v1",
                source="gbif",
                field_keys=["taxon"],
                input_source="decided_transcript",
                attempt=1,
                arguments={"literal": "Epipsocus"},
                outcome=S.SUCCESS,
                started_at="t",
                completed_at="t",
            )
        )
        return self.block

    def lookup(self, name):
        self.looked_up.append(name)
        return super().lookup(name)


def drain(tmp_path, monkeypatch, adapters):
    # Classify rebuilds the run's profile from the published one, which does
    # not name a harness route until S3's profile wiring (HARNESS.md 14).
    monkeypatch.setattr(
        collection_runtime, "Profile", partial(Profile, harness_route=ROUTE.route_id)
    )
    row = intake(client(tmp_path))
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": True}))
    return Workflow(repo, adapters.blobs, adapters).drain(principal, specimen.id).run


def test_the_harness_runs_in_parse_and_its_taxonomy_lookup_is_not_repeated(
    tmp_path, monkeypatch
):
    adapters = HarnessAdapters(LocalBlobs(tmp_path / "blobs"))

    run = drain(tmp_path, monkeypatch, adapters)

    assert adapters.harnessed == [run.id]
    assert "parse" in run.completed_steps and "lookup" in run.completed_steps
    assert adapters.looked_up == []  # The harness verified the taxon.


def test_a_harness_tool_block_stops_the_run_after_the_model_call_settled(
    tmp_path, monkeypatch
):
    adapters = HarnessAdapters(
        LocalBlobs(tmp_path / "blobs"), "harness_taxonomy_verifier_rate_limited"
    )

    run = drain(tmp_path, monkeypatch, adapters)

    assert (run.stage, run.blocker) == (
        "processing_blocked",
        "harness_taxonomy_verifier_rate_limited",
    )
    assert "parse" not in run.completed_steps
    assert [c.tool for c in run.tool_calls] == ["taxonomy_verifier"]  # Kept for costs.
