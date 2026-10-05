"""Human selection resolves a retained field candidate, never a caller-supplied value.

Real SQLite job/effect/checkpoint fixtures; no network, model call or paid effect.
Tampering changes only detached copies of the persisted read document.
"""

import copy
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
