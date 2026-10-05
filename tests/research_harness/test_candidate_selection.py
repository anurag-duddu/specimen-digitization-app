"""Human selection resolves a retained field candidate, never a caller-supplied value.

Real SQLite job/effect/checkpoint fixtures; no network, model call or paid effect.
Tampering changes only detached copies of the persisted read document.
"""

import copy
import asyncio
import json

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.research_harness.candidate_selection import retained_candidate
from specimen_digitization.research_harness.contracts import FieldKey, SpecialistRole, digest
from specimen_digitization.research_harness.persistence import StaleWork
from specimen_digitization.research_harness.thread_view import candidate_selection_id
from test_thread_review import Rig, apo_ambiguous


class Retained:
    def __init__(self, tmp_path):
        self.rig = Rig(tmp_path)
        result, waiting = apo_ambiguous(self.rig)
        self.effect_id = self.rig.capture(result, FieldKey.COUNTRY)
        self.rig.commit(SpecialistRole.GEOGRAPHY, [waiting], [self.effect_id])
        self.document = self.rig.journal.store._read(self.rig.journal.scope)
        self.job_key = self.rig.journal.scope.key
        self.token = self.rig.field(FieldKey.COUNTRY).review.candidates[0].selection_id

    @property
    def job(self):
        return self.document.state["jobs"][self.job_key]

    @property
    def field(self):
        return self.job["fields"][str(FieldKey.COUNTRY)]

    @property
    def checkpoint(self):
        return self.field["checkpoint"]

    @property
    def effect(self):
        return self.document.state["effects"][self.effect_id]

    @property
    def payload(self):
        return self.effect["receipt"]["typed_payload"]

    def choose(self, token=None, field=FieldKey.COUNTRY):
        return retained_candidate(self.document, self.job_key, field, self.token if token is None else token)

    def edit_candidate(self, **changes):
        item = json.loads(self.payload["candidate_json"][0])
        item.update(changes)
        self.payload["candidate_json"][0] = json.dumps(item)
        return candidate_selection_id(self.job_key, FieldKey.COUNTRY, self.effect_id, item)


@pytest.fixture
def retained(tmp_path):
    return Retained(tmp_path)


def test_real_native_job_shape_resolves_exact_value_and_opaque_geographic_identity(retained):
    assert "identity" in retained.job and "scope" not in retained.job
    before = copy.deepcopy(retained.document.state)
    choice = retained.choose()
    assert choice["value"] == "Philippines"
    assert choice["source_candidate"]["match_name"] == "MOUNT APO"
    assert choice["authority_id"] == "geolocate:a863d52e6ff08fe2"
    assert choice["source_id"] == "geolocate"
    assert choice["field_key"] == "country" and choice["selection_id"] == retained.token
    assert choice["effect_id"] == retained.effect_id and choice["checkpoint_id"] == retained.checkpoint["id"]
    assert choice["source_result"] == retained.payload
    assert choice["capture"] == retained.effect["receipt"]["capture"]
    assert choice["evidence_id"] in retained.payload["coverage"]["receipt_ids"]
    assert {"decimal_latitude", "decimal_longitude"} <= choice["source_candidate"].keys()
    assert retained.document.state == before


@pytest.mark.parametrize("token", ["", "a" * 63, "A" * 64, "z" * 64, 7, {}, []])
def test_invalid_selection_tokens_are_rejected(retained, token):
    with pytest.raises(ValueError):
        retained.choose(token)


def test_unknown_well_formed_selection_is_not_a_candidate(retained):
    with pytest.raises(ValueError):
        retained.choose("f" * 64)


def test_a_country_choice_cannot_be_replayed_for_a_different_field(retained):
    with pytest.raises((StaleWork, ValueError)):
        retained.choose(field=FieldKey.PROVINCE_STATE)


@pytest.mark.parametrize("change", [
    "paused", "locked", "missing_checkpoint", "field_revision", "generation", "retry",
    "checkpoint_binding", "checkpoint_field", "envelope_field", "envelope_revision", "envelope_id",
])
def test_no_choice_from_a_stale_or_inconsistent_current_field(retained, change):
    if change == "paused":
        retained.job["paused"] = True
    elif change == "locked":
        retained.field["locked"] = True
    elif change == "missing_checkpoint":
        retained.field["checkpoint"] = None
    elif change == "field_revision":
        retained.field["revision"] += 1
    elif change == "generation":
        retained.job["generation"] += 1
    elif change == "retry":
        retained.field["retry_command_id"] = digest("queued retry")
    elif change == "checkpoint_binding":
        retained.checkpoint["binding_digest"] = "f" * 64
    elif change == "checkpoint_field":
        retained.checkpoint["payload"]["field_key"] = "province_state"
        retained.checkpoint["payload"]["resolution"]["field_key"] = "province_state"
    elif change == "envelope_field":
        retained.checkpoint["field_key"] = "province_state"
    elif change == "envelope_revision":
        retained.checkpoint["revision"] += 1
    else:
        retained.checkpoint["id"] = "f" * 64
    with pytest.raises((StaleWork, ValueError, PermissionError)):
        retained.choose()


@pytest.mark.parametrize("key", ["organization_id", "collection_id", "specimen_id", "job_id", "input_digest", "profile_digest", "sensitive"])
def test_checkpoint_scope_cannot_be_substituted(retained, key):
    scoped = retained.checkpoint["payload"]["scope"]
    scoped[key] = True if key == "sensitive" else "f" * 64 if key.endswith("digest") else "another-scope"
    with pytest.raises((StaleWork, ValueError, PermissionError)):
        retained.choose()


@pytest.mark.parametrize("change", ["other_job", "other_field", "sending", "held_unknown", "not_lookup", "missing_receipt", "scope", "not_cited"])
def test_source_effect_must_be_completed_own_field_and_cited_by_checkpoint(retained, change):
    if change == "other_job":
        retained.effect["job_key"] = "another-job"
    elif change == "other_field":
        retained.effect["field_keys"] = ["province_state"]
    elif change in {"sending", "held_unknown"}:
        retained.effect["status"] = change
    elif change == "not_lookup":
        retained.effect["operation_key"] = "model:geography"
    elif change == "missing_receipt":
        retained.effect["receipt"] = None
    elif change == "scope":
        retained.effect["scope"]["specimen_id"] = "another-specimen"
    else:
        retained.checkpoint["receipt_ids"] = []
    with pytest.raises((StaleWork, ValueError, PermissionError)):
        retained.choose()


@pytest.mark.parametrize("status", [item.value for item in LookupStatus if item not in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}] + ["invented_status"])
def test_failed_unknown_and_nonmatching_source_results_are_not_selectable(retained, status):
    retained.payload["status"] = status
    with pytest.raises((StaleWork, ValueError, PermissionError)):
        retained.choose()


@pytest.mark.parametrize("change", ["result_field", "not_cited", "wrong_source", "wrong_version", "wrong_coverage_source", "wrong_coverage_version", "not_covered", "missing_evidence"])
def test_choice_requires_checkpoint_cited_source_matching_evidence(retained, change):
    if change == "result_field":
        retained.payload["coverage"]["field_key"] = "province_state"
    elif change == "not_cited":
        retained.payload["evidence"][0]["id"] = "uncited-evidence"
        retained.payload["coverage"]["receipt_ids"] = ["uncited-evidence"]
    elif change == "wrong_source":
        retained.payload["evidence"][0]["source_id"] = "other-source"
    elif change == "wrong_version":
        retained.payload["evidence"][0]["source_version"] = "other-version"
    elif change == "wrong_coverage_source":
        retained.payload["coverage"]["source_id"] = "another-source"
        retained.payload["evidence"][0]["source_id"] = "another-source"
    elif change == "wrong_coverage_version":
        retained.payload["coverage"]["source_version"] = "another-version"
        retained.payload["evidence"][0]["source_version"] = "another-version"
    elif change == "not_covered":
        retained.payload["coverage"]["receipt_ids"] = []
    else:
        retained.payload["evidence"] = []
    with pytest.raises((StaleWork, ValueError, PermissionError)):
        retained.choose()


@pytest.mark.parametrize("authority", [None, "", "Mount Apo", "geolocate:wrong", 7, {}, "geolocate:" + "a" * 64])
def test_geographic_authority_is_an_opaque_retained_geolocate_identifier(retained, authority):
    token = retained.edit_candidate(authority_id=authority)
    with pytest.raises((StaleWork, ValueError, PermissionError)):
        retained.choose(token)


@pytest.mark.parametrize("value", [None, "", "   ", "X" * 241, "Philippines\nchanged", 42])
def test_unrepresentable_exact_values_are_never_silently_replaced_or_truncated(retained, value):
    token = retained.edit_candidate(value=value)
    with pytest.raises((StaleWork, ValueError, PermissionError)):
        retained.choose(token)


def test_hidden_candidate_metadata_is_bound_to_the_selection_token(retained):
    retained.edit_candidate(decimal_longitude=120.0)
    with pytest.raises(ValueError):
        retained.choose()


def test_repeated_same_effect_reference_is_still_one_retained_choice(retained):
    retained.checkpoint["payload"]["effect_receipt_ids"].append(retained.effect_id)
    retained.checkpoint["receipt_ids"].append(retained.effect_id)
    retained.checkpoint["id"] = digest({"scope": retained.checkpoint["scope"], "field": "country",
                                       "revision": retained.field["revision"], "payload": retained.checkpoint["payload"]})
    assert retained.choose()["selection_id"] == retained.token


def derived_metadata(*, field_key="country", input_field="province_state", revision=2):
    """Explicit synthetic computation shape; not a source/adapter execution claim."""
    return {"field_key": field_key, "value": "Philippines", "input_fields": [input_field],
        "input_revisions": [[input_field, revision]], "evidence_ids": ["computed:" + "a" * 64],
        "authority_id": "boundary:PH", "dataset_ids": ["synthetic-boundary-v1"],
        "tool_call_id": "synthetic-tool-call", "value_layer": "derived",
        "human_review_required": True, "automatic_settlement_allowed": False,
        "rule_version": "retrospective-georeferencing-v1",
        "georeference": {"latitude": 6.9, "longitude": 125.2, "uncertainty_m": 1200.,
            "footprint_dataset": "synthetic-boundary-v1", "footprint_id": "fixture-unit",
            "authority_ids": ["geolocate:0000000000000001"], "input_fields": [input_field],
            "evidence_ids": ["computed:" + "a" * 64], "tool_call_id": "synthetic-tool-call",
            "simplification_margin_m": 100., "method": "Synthetic footprint computation fixture",
            "geodetic_datum": "EPSG:4326", "version": "retrospective-georeferencing-v1"}}


def make_derived(retained, metadata=None):
    """Alter a detached native read document; original durable evidence stays intact."""
    item = derived_metadata() if metadata is None else metadata
    retained.payload["candidate_json"] = [json.dumps(item)]
    retained.payload["status"] = "success"
    coverage = retained.payload["coverage"]
    coverage.update(source_id="georeference_spatial", source_version=item["rule_version"],
        qualification_digest=digest(item["rule_version"]), receipt_ids=["computed:" + "a" * 64])
    evidence = retained.payload["evidence"][0]
    evidence.update(id="computed:" + "a" * 64, kind="computed_derivation_result",
        source_id="georeference_spatial", source_version=item["rule_version"],
        response_digest="a" * 64, locator="computed://georeference_spatial/" + "a" * 64)
    retained.checkpoint["payload"]["resolution"]["question"]["coverage"] = [copy.deepcopy(coverage)]
    retained.checkpoint["payload"]["resolution"]["question"]["evidence_ids"] = [evidence["id"]]
    # A legacy waiting-policy fixture exercises selection without pretending a
    # computed result was an ambiguous provider response.
    retained.checkpoint["payload"]["resolution"].update(
        work_state="waiting_policy", question=None, source_coverage=[copy.deepcopy(coverage)],
        evidence_ids=[evidence["id"]])
    retained.field["work_state"] = "waiting_policy"
    retained.checkpoint["id"] = digest({"scope": retained.checkpoint["scope"], "field": "country",
        "revision": retained.field["revision"], "payload": retained.checkpoint["payload"]})
    retained.token = candidate_selection_id(retained.job_key, FieldKey.COUNTRY, retained.effect_id, item)
    return item


def test_derived_choice_requires_complete_retained_computation_metadata(retained):
    item = make_derived(retained)
    assert item["human_review_required"] is True and item["automatic_settlement_allowed"] is False
    assert "settlement_allowed" not in item and "validation_required" not in item
    assert retained.choose()["source_candidate"] == item


@pytest.mark.parametrize("source", ["geolocate", "tgn", "wikidata", "nga", "georeference_history", "georeference_spatial"])
@pytest.mark.parametrize("markers", [{"settlement_allowed": False}, {"validation_required": "geolocate"},
    {"settlement_allowed": False, "validation_required": "geolocate"},
    {"settlement_allowed": True, "validation_required": "geolocate"}])
def test_context_candidates_remain_visible_but_never_accept_even_a_recomputed_token(retained, source, markers):
    from specimen_digitization.research_harness.contracts import FieldCheckpoint
    from specimen_digitization.research_harness.thread_view import _field_review

    if source == "georeference_spatial":
        make_derived(retained)
    item = json.loads(retained.payload["candidate_json"][0]) | markers
    retained.payload["candidate_json"] = [json.dumps(item)]
    retained.payload["coverage"]["source_id"] = source
    for evidence in retained.payload["evidence"]:
        evidence["source_id"] = source
    resolution = retained.checkpoint["payload"]["resolution"]
    resolution.update(work_state="waiting_policy", question=None,
        source_coverage=[copy.deepcopy(retained.payload["coverage"])],
        evidence_ids=[evidence["id"] for evidence in retained.payload["evidence"]])
    retained.field["work_state"] = "waiting_policy"
    retained.checkpoint["id"] = digest({"scope": retained.checkpoint["scope"], "field": "country",
        "revision": retained.field["revision"], "payload": retained.checkpoint["payload"]})
    review = _field_review(retained.document.state["effects"], retained.job_key, FieldKey.COUNTRY,
        FieldCheckpoint.model_validate(retained.checkpoint["payload"]))
    candidate, = review.candidates
    assert candidate.label == item.get("match_name", item["value"])
    assert candidate.source_id == source and review.evidence
    assert candidate.selection_id is None and candidate.selection_value is None
    token = candidate_selection_id(retained.job_key, FieldKey.COUNTRY, retained.effect_id, item)
    with pytest.raises(ValueError, match="Select one retained research candidate"):
        retained.choose(token)


def prepend_spatial_dataset_evidence(retained):
    make_derived(retained)
    dataset = {**retained.payload["evidence"][0], "id": "dataset:" + "b" * 64,
        "kind": "qualified_dataset", "locator": "fixture://spatial-dataset", "response_digest": "b" * 64}
    retained.payload["evidence"].insert(0, dataset)
    retained.payload["coverage"]["receipt_ids"].insert(0, dataset["id"])
    resolution = retained.checkpoint["payload"]["resolution"]
    resolution["source_coverage"][0]["receipt_ids"].insert(0, dataset["id"])
    resolution["evidence_ids"].insert(0, dataset["id"])
    retained.checkpoint["id"] = digest({"scope": retained.checkpoint["scope"], "field": "country",
        "revision": retained.field["revision"], "payload": retained.checkpoint["payload"]})


def test_spatial_selection_anchors_to_computation_after_dataset_without_reordering_evidence(retained):
    from specimen_digitization.research_harness.contracts import FieldCheckpoint
    from specimen_digitization.research_harness.thread_view import _field_review

    prepend_spatial_dataset_evidence(retained)
    before = copy.deepcopy(retained.document.state)
    choice = retained.choose()
    assert choice["evidence_id"] == "computed:" + "a" * 64
    review = _field_review(retained.document.state["effects"], retained.job_key, FieldKey.COUNTRY,
        FieldCheckpoint.model_validate(retained.checkpoint["payload"]))
    assert review.candidates[0].evidence_id == choice["evidence_id"]
    assert [item.kind for item in review.evidence] == ["qualified_dataset", "computed_derivation_result"]
    assert retained.document.state == before


@pytest.mark.parametrize("change", ["kind", "id", "locator", "uncited"])
def test_spatial_dataset_evidence_cannot_substitute_for_a_genuine_cited_computation(retained, change):
    from specimen_digitization.research_harness.contracts import FieldCheckpoint, SourceResult
    from specimen_digitization.research_harness.thread_view import candidate_selection_evidence

    prepend_spatial_dataset_evidence(retained)
    evidence = retained.payload["evidence"][1]
    if change == "kind":
        evidence["kind"] = "qualified_dataset"
    elif change == "id":
        previous = evidence["id"]
        evidence["id"] = "computed:" + "c" * 64
        resolution = retained.checkpoint["payload"]["resolution"]
        for identifiers in (retained.payload["coverage"]["receipt_ids"], resolution["evidence_ids"],
                            resolution["source_coverage"][0]["receipt_ids"]):
            identifiers[identifiers.index(previous)] = evidence["id"]
    elif change == "locator":
        evidence["locator"] = "computed://another-source/" + "a" * 64
    else:
        retained.checkpoint["payload"]["resolution"]["evidence_ids"].remove(evidence["id"])
        retained.checkpoint["payload"]["resolution"]["source_coverage"][0]["receipt_ids"].remove(evidence["id"])
    assert candidate_selection_evidence(SourceResult.model_validate(retained.payload),
        FieldCheckpoint.model_validate(retained.checkpoint["payload"])) is None


@pytest.mark.parametrize("change", [
    "source", "field", "layer", "missing_trace", "model_coords", "input_revision", "input_duplicate",
    "input_keys", "self_input", "trace_inputs", "trace_tool", "trace_version", "uncited",
    "ambiguous", "evidence_kind", "qualification", "unknown_key", "auto_settle", "no_review", "numeric_review",
])
def test_derived_choice_rejects_forged_or_incomplete_metadata(retained, change):
    item = make_derived(retained)
    if change == "source":
        retained.payload["coverage"]["source_id"] = "geolocate"
    elif change == "field":
        item["field_key"] = "city"
    elif change == "layer":
        item["value_layer"] = "settled"
    elif change == "missing_trace":
        item.pop("georeference")
    elif change == "model_coords":
        item["latitude"] = 6.9
    elif change == "input_revision":
        item["input_revisions"][0][1] = True
    elif change == "input_duplicate":
        item["input_fields"].append("province_state")
    elif change == "input_keys":
        item["input_revisions"][0][0] = "city"
    elif change == "self_input":
        item["field_key"] = "province_state"
    elif change == "trace_inputs":
        item["georeference"]["input_fields"] = ["city"]
    elif change == "trace_tool":
        item["georeference"]["tool_call_id"] = "another-tool"
    elif change == "trace_version":
        item["georeference"]["version"] = "another-rule"
    elif change == "uncited":
        item["evidence_ids"] = ["forged-evidence"]
    elif change == "ambiguous":
        retained.payload["status"] = "ambiguous"
    elif change == "evidence_kind":
        retained.payload["evidence"][0]["kind"] = "model_claim"
    elif change == "qualification":
        retained.payload["coverage"]["qualification_digest"] = "f" * 64
    elif change == "auto_settle":
        item["automatic_settlement_allowed"] = True
    elif change == "no_review":
        item["human_review_required"] = False
    elif change == "numeric_review":
        item["human_review_required"] = 1
    else:
        item["unknown_key"] = "model claim"
    retained.payload["candidate_json"] = [json.dumps(item)]
    token = candidate_selection_id(retained.job_key, FieldKey.COUNTRY, retained.effect_id, item)
    with pytest.raises((ValueError, StaleWork)):
        retained.choose(token)


def test_non_spatial_source_cannot_mark_a_candidate_derived(retained):
    token = retained.edit_candidate(value_layer="derived", input_fields=["city"])
    with pytest.raises(ValueError, match="Only the georeferencing source"):
        retained.choose(token)


@pytest.fixture
def retained_v2(tmp_path):
    """Real V2 broker retains the request and two original publisher response bodies."""
    from types import SimpleNamespace
    from specimen_digitization.application.domain import FieldValue
    from specimen_digitization.research_harness.contracts import ExactSpecimenJoin, FieldResolution, WorkState
    from specimen_digitization.research_harness.journal import DurableResearchJournal
    from specimen_digitization.research_harness.sources import MUSEUM_DATASET
    from test_source_capture_v2 import make_capture_rig, query_once, saved_envelope

    rig = make_capture_rig(tmp_path, source_id="field_museum_ipt",
        join=ExactSpecimenJoin(dataset_id=MUSEUM_DATASET, occurrence_id="fixture-exact-guid"))
    result = query_once(rig)
    effect, envelope = saved_envelope(rig, result)
    journal = DurableResearchJournal(rig.store, rig.durable_scope, rig.lease)
    waiting = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_POLICY,
        value=FieldValue(state="unresolved"), source_coverage=(result.coverage,),
        evidence_ids=tuple(item.id for item in result.evidence), reason="Offline reviewer policy fixture")
    asyncio.run(journal.commit(rig.request, (waiting,), receipt_ids=(effect["effect_id"],),
        model_settings_digest=digest(rig.pins.settings)))
    document = rig.store._read(rig.durable_scope)
    job = document.state["jobs"][rig.durable_scope.key]
    effect = document.state["effects"][effect["effect_id"]]
    item = json.loads(result.candidate_json[0])
    token = candidate_selection_id(rig.durable_scope.key, FieldKey.TAXON, effect["effect_id"], item)
    return SimpleNamespace(rig=rig, journal=journal, document=document, job=job, effect=effect,
        envelope=envelope, token=token, checkpoint=job["fields"]["taxon"]["checkpoint"],
        choose=lambda: retained_candidate(document, rig.durable_scope.key, FieldKey.TAXON, token))


def test_real_v2_capture_is_selectable_and_visible_with_the_same_retained_token(retained_v2):
    from specimen_digitization.research_harness.source_capture_v2 import OPERATION_PREFIX
    from specimen_digitization.research_harness.thread_view import ResearchThreadReader

    value = retained_v2
    before = copy.deepcopy(value.document.state)
    choice = value.choose()
    assert value.effect["operation_key"] == OPERATION_PREFIX + digest(value.envelope.logical_request)
    assert value.envelope.query.source_id == choice["source_id"] == "field_museum_ipt"
    assert choice["value"] == "Danaus plexippus" and choice["authority_id"] == "occurrence:fixture-exact-guid"
    assert len(value.envelope.responses) == len(value.rig.calls) == 2
    thread = asyncio.run(ResearchThreadReader(value.journal).read(value.rig.scope))
    field = next(item for item in thread.fields if item.field_key == FieldKey.TAXON)
    candidate, = field.review.candidates
    assert candidate.selection_id == choice["selection_id"] == value.token
    assert candidate.selection_value == choice["value"]
    assert value.document.state == before


@pytest.mark.parametrize("change", ["operation", "request_digest", "unregistered_source", "denied_policy",
    "policy_source", "qualification", "missing_raw", "raw_locator", "raw_size", "attempt", "effect_id"])
def test_v2_capture_requires_exact_registered_source_and_original_capture_provenance(retained_v2, change):
    from specimen_digitization.research_harness.contracts import FieldCheckpoint
    from specimen_digitization.research_harness.thread_view import _field_review

    value = retained_v2
    policy = value.job["pins"]["sources"]["capture_policies"]["field_museum_ipt"]
    if change == "operation":
        value.effect["operation_key"] = "source_capture_v2:" + "f" * 64
    elif change == "request_digest":
        value.effect["request_digest"] = "f" * 64
    elif change == "unregistered_source":
        value.job["pins"]["sources"]["capture_policies"] = {}
    elif change == "denied_policy":
        policy["kind"] = "denied"
    elif change == "policy_source":
        policy["source_id"] = "geolocate"
    elif change == "qualification":
        value.effect["receipt"]["typed_payload"]["coverage"]["qualification_digest"] = "f" * 64
    elif change == "missing_raw":
        value.effect["receipt"].pop("raw_capture")
    elif change == "raw_locator":
        value.effect["receipt"]["raw_capture"]["locator"] = "another-capture"
    elif change == "raw_size":
        value.effect["receipt"]["raw_capture"]["byte_size"] = 0
    elif change == "attempt":
        value.effect["receipt"]["attempt_id"] = "another-attempt"
    else:
        value.effect["effect_id"] = "f" * 64
    with pytest.raises(ValueError):
        value.choose()
    projection = _field_review(value.document.state["effects"], value.rig.durable_scope.key,
        FieldKey.TAXON, FieldCheckpoint.model_validate(value.checkpoint["payload"]), job=value.job)
    assert projection.candidates == ()


def test_model_receipt_in_the_same_checkpoint_is_skipped_before_source_parsing(retained_v2):
    value = retained_v2
    model = copy.deepcopy(value.effect)
    model_id = "f" * 64
    model.update(effect_id=model_id, operation_key="model:geography")
    model["receipt"].update(effect_id=model_id, typed_payload={"model_output": "not source evidence"})
    value.document.state["effects"][model_id] = model
    value.checkpoint["payload"]["effect_receipt_ids"].insert(0, model_id)
    value.checkpoint["receipt_ids"].insert(0, model_id)
    value.checkpoint["id"] = digest({"scope": value.checkpoint["scope"], "field": "taxon",
        "revision": value.checkpoint["revision"], "payload": value.checkpoint["payload"]})
    assert value.choose()["selection_id"] == value.token


def local_v2_policy_fixture(retained_v2, kind):
    """Detached metadata fixture only; does not execute a dataset/computation adapter."""
    from specimen_digitization.research_harness.contracts import SourceResult
    from specimen_digitization.research_harness.derivation_contracts import DERIVATION_RULE_VERSION

    job, effect = copy.deepcopy(retained_v2.job), copy.deepcopy(retained_v2.effect)
    source_id = "georeference_spatial" if kind == "computed" else "georeference_history"
    policy = copy.deepcopy(job["pins"]["sources"]["capture_policies"]["field_museum_ipt"])
    policy.update(kind=kind, source_id=source_id)
    job["pins"]["sources"]["capture_policies"] = {source_id: policy}
    job["binding_digest"] = effect["binding_digest"] = digest(job["pins"])
    effect["effect_id"] = digest({key: effect[key]
        for key in ("scope", "operation_key", "request_digest", "binding_digest")})
    effect["receipt"]["effect_id"] = effect["effect_id"]
    payload = copy.deepcopy(effect["receipt"]["typed_payload"])
    payload["coverage"].update(source_id=source_id, source_version=DERIVATION_RULE_VERSION,
        qualification_digest=digest(DERIVATION_RULE_VERSION))
    return job, effect, SourceResult.model_validate(payload)


@pytest.mark.parametrize("kind", ["computed", "pinned_dataset"])
def test_local_v2_policy_uses_the_registered_rule_qualification_without_hiding_capture(retained_v2, kind):
    from specimen_digitization.research_harness.thread_view import candidate_source_capture

    job, effect, result = local_v2_policy_fixture(retained_v2, kind)
    policy = job["pins"]["sources"]["capture_policies"][result.coverage.source_id]
    assert result.coverage.qualification_digest != policy["source_policy_digest"]
    assert candidate_source_capture(effect, result, job)


@pytest.mark.parametrize("kind", ["computed", "pinned_dataset"])
@pytest.mark.parametrize("change", ["policy_digest_as_qualification", "rule_version", "wrong_source_kind",
                                    "raw_capture", "operation", "pin"])
def test_local_v2_capture_keeps_kind_specific_source_rule_and_common_receipt_fences(retained_v2, kind, change):
    from specimen_digitization.research_harness.thread_view import candidate_source_capture

    job, effect, result = local_v2_policy_fixture(retained_v2, kind)
    policy = job["pins"]["sources"]["capture_policies"][result.coverage.source_id]
    if change == "policy_digest_as_qualification":
        result = result.model_copy(update={"coverage": result.coverage.model_copy(
            update={"qualification_digest": policy["source_policy_digest"]})})
    elif change == "rule_version":
        result = result.model_copy(update={"coverage": result.coverage.model_copy(
            update={"source_version": "unregistered-rule", "qualification_digest": digest("unregistered-rule")})})
    elif change == "wrong_source_kind":
        policy["kind"] = "pinned_dataset" if kind == "computed" else "computed"
        job["binding_digest"] = effect["binding_digest"] = digest(job["pins"])
        effect["effect_id"] = digest({key: effect[key]
            for key in ("scope", "operation_key", "request_digest", "binding_digest")})
    elif change == "raw_capture":
        effect["receipt"]["raw_capture"] = None
    elif change == "operation":
        effect["operation_key"] = "source_capture_v2:" + "f" * 64
    else:
        policy["source_policy_digest"] = "f" * 64
    assert not candidate_source_capture(effect, result, job)
