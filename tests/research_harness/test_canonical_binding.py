"""Source contract tests; fixture identities do not grant native/live authority."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.research_harness.canonical_binding import (
    BindingUnavailable, CanonicalBindingSnapshot, CanonicalResearchBinding,
)
from specimen_digitization.research_harness.contracts import FieldKey, digest
from specimen_digitization.research_harness.persistence import StaleWork

ORG = "11111111-1111-4111-8111-111111111111"
COLLECTION = "22222222-2222-4222-8222-222222222222"
SPECIMEN = "33333333-3333-4333-8333-333333333333"
VERSION = "44444444-4444-4444-8444-444444444444"
RUN = "55555555-5555-4555-8555-555555555555"
BINDING = "66666666-6666-4666-8666-666666666666"


def registration():
    pins = {"input_digest": "a" * 64, "profile": {"approved": "fixture"},
            "prompts": {}, "sources": {}, "model": {}, "settings": {},
            "engine_version": "source-fixture"}
    policy = {"hold_reason": "fixture_unknown"}
    canonical = {"organization_id": ORG, "collection_id": COLLECTION,
                 "specimen_id": SPECIMEN, "record_revision": 7,
                 "record_version_id": VERSION, "canonical_run_id": RUN,
                 "host_record_version_id": RUN + ":7", "snapshot_sha256": "9" * 64,
                 "sensitive": True}
    identity = {"organization_id": ORG, "collection_id": COLLECTION,
                "specimen_id": SPECIMEN, "job_id": "journal-job-opaque"}
    job = {"identity": identity, "record_revision": 7, "generation": 2, "sensitive": True,
           "pins": pins, "binding_digest": digest(pins), "paused": False,
           "trace_context": None, "history": [], "dependencies": {},
           "fields": {str(key): {"revision": 0, "locked": False, "checkpoint": None,
                                "reuse": None} for key in FieldKey}}
    version_tuple = {key: canonical[key] for key in ("record_revision", "record_version_id",
        "canonical_run_id", "host_record_version_id", "snapshot_sha256")}
    row = {"binding_id": BINDING, "active": True, "registration_revision": 1,
           "base_canonical": deepcopy(version_tuple), "current_canonical": deepcopy(version_tuple),
           "job_id": "journal-job-opaque", "job_key": digest(identity), "generation": 2,
           "input_digest": pins["input_digest"], "profile_digest": digest(pins["profile"]),
           "runtime_binding_digest": digest(pins), "program_key": "fixture-existing-program",
           "policy_digest": "c" * 64, "source_sha256": "e" * 64,
           "canonical_profile_digest": "f" * 64, "semantic_mapping_digest": "d" * 64,
           "field_mapping": {str(key): str(key) for key in FieldKey},
           "human_locks": {str(key): False for key in FieldKey},
           "publication_transition": None, "job": deepcopy(job),
           "read_bundle": {"state_revision": 3, "observed_at": "2026-10-01T00:00:00Z",
                           "job": deepcopy(job), "effects": {}, "outbox": {}, "halted": False,
                           "hold_reasons": ["legacy_live_import_not_confirmed"]}}
    row["semantic_mapping"] = {"field_mapping": deepcopy(row["field_mapping"]),
        "journal_budget_policy_digest": "b" * 64, "research_policy_origin": "fixture-owner-reviewed"}
    row["semantic_mapping_digest"] = digest(row["semantic_mapping"])
    row["journal_budget_policy_digest"] = "b" * 64
    row["journal_budget_policy_origin"] = "verified_owner_registration_not_SQL_recomputed"
    row["research_policy_origin"] = "fixture-owner-reviewed"
    row["read_bundle"].pop("observed_at")
    row["read_bundle"].update(server_time=100.0, job_key=row["job_key"], paused=False)
    return row, job, policy


def envelope(canonical, rows):
    # Explicit synthetic native joins, never application defaults.
    canonical = {"organization_id": ORG, "collection_id": COLLECTION,
                 "specimen_id": SPECIMEN, "sensitive": True, **canonical}
    return {"canonical": canonical, "active_registration_count": sum(row["active"] for row in rows),
            "registrations": rows, "projection": [],
            "snapshot": {"snapshot": {"fixture": "private"}, "sha256": canonical["snapshot_sha256"],
                         "revision": canonical["record_revision"], "contractVersion": "fixture-source"}}


def native_response(canonical, rows):
    value = envelope(canonical, rows)
    return {"organizationMember": {"active": True},
            "collectionMember": {"active": True, "role": "viewer", "canViewSensitive": True},
            "specimen": {"sensitive": value["canonical"]["sensitive"]}, "binding": value}


def current(snapshot):
    return snapshot.current(organization_id=ORG, collection_id=COLLECTION, specimen_id=SPECIMEN)


def bound_registration(row):
    return current(CanonicalBindingSnapshot.model_validate(envelope(row["current_canonical"], [row])))


def test_native_uuid_numeric_opaque_and_journal_job_remain_distinct():
    row, job, policy = registration()
    bound = bound_registration(row)
    assert bound.canonical.record_revision == 7
    assert bound.canonical.record_version_id == VERSION
    assert bound.canonical.canonical_run_id == RUN
    assert bound.canonical.host_record_version_id == RUN + ":7"
    assert bound.job_id == "journal-job-opaque"
    bound.validate_job(job, program_key=row["program_key"])


@pytest.mark.parametrize("key,value", [("record_revision", True), ("record_revision", "7"), ("record_revision", 0),
                                       ("record_version_id", RUN + ":7"), ("sensitive", 1)])
def test_invalid_native_identity_is_not_coerced(key, value):
    row, _, _ = registration()
    row["current_canonical"][key] = value
    with pytest.raises(ValidationError):
        CanonicalResearchBinding.model_validate(row)


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_multiple_active_registration_is_unavailable(count):
    row, _, _ = registration()
    snapshot = CanonicalBindingSnapshot.model_validate(envelope(row["current_canonical"], [row] * count))
    with pytest.raises(BindingUnavailable):
        current(snapshot)


def test_different_second_active_registration_cannot_be_filtered_to_one():
    row, _, _ = registration()
    other = deepcopy(row)
    other["current_canonical"]["record_version_id"] = RUN
    other["base_canonical"] = deepcopy(other["current_canonical"])
    snapshot = CanonicalBindingSnapshot.model_validate(envelope(row["current_canonical"], [row, other]))
    with pytest.raises(BindingUnavailable):
        current(snapshot)


@pytest.mark.parametrize("key,value", [("record_version_id", RUN),
    ("canonical_run_id", VERSION), ("host_record_version_id", "different-opaque"),
    ("record_revision", 8), ("sensitive", False)])
def test_same_numeric_revision_cannot_hide_changed_native_or_opaque_identity(key, value):
    row, _, _ = registration()
    pointer = deepcopy(row["current_canonical"])
    pointer[key] = value
    snapshot = CanonicalBindingSnapshot.model_validate(envelope(pointer, [row]))
    with pytest.raises(BindingUnavailable):
        current(snapshot)


@pytest.mark.parametrize("change", ["generation", "input", "profile", "runtime", "program"])
def test_journal_binding_changes_require_fresh_registration(change):
    row, job, policy = registration()
    bound = bound_registration(row)
    program = row["program_key"]
    if change == "generation":
        job["generation"] += 1
    elif change == "input":
        job["pins"]["input_digest"] = "b" * 64
    elif change == "profile":
        job["pins"]["profile"] = {"different": True}
    elif change == "runtime":
        job["pins"]["settings"] = {"changed": True}
    elif change == "program":
        program = "another-program"
    with pytest.raises(StaleWork):
        bound.validate_job(job, program_key=program)


def test_wrong_collection_actor_is_denied():
    row, _, _ = registration()
    principal = Principal(user_id="verified", role="viewer",
                          scope=Scope(organization_id=ORG, collection_id=SPECIMEN))
    with pytest.raises(PermissionError):
        bound_registration(row).durability_scope(principal)


def test_explicit_published_transition_keeps_original_journal_base():
    row, job, _ = registration()
    row["current_canonical"]["record_revision"] = 8
    row["current_canonical"]["record_version_id"] = "77777777-7777-4777-8777-777777777777"
    row["current_canonical"]["host_record_version_id"] = "retained-result-opaque"
    row["current_canonical"]["snapshot_sha256"] = "8" * 64
    row["publication_transition"] = {
        "receipt_id": "88888888-8888-4888-8888-888888888888", "operation_digest": "1" * 64,
        "publication_digest": "2" * 64, "binding_id": row["binding_id"], "job_key": row["job_key"],
        "base_canonical": deepcopy(row["base_canonical"]),
        "current_canonical": deepcopy(row["current_canonical"]), "job_id": row["job_id"],
        "generation": row["generation"], "input_digest": row["input_digest"],
        "profile_digest": row["profile_digest"], "runtime_binding_digest": row["runtime_binding_digest"],
    }
    bound = bound_registration(row)
    bound.validate_job(job, program_key=row["program_key"])
    assert job["record_revision"] == 7
    assert bound.canonical.record_revision == 8


@pytest.mark.parametrize("missing", ["field_mapping", "source_sha256", "canonical_profile_digest",
                                     "semantic_mapping_digest", "job_key", "base_canonical"])
def test_mapping_and_distinct_source_pins_have_no_defaults(missing):
    row, _, _ = registration()
    del row[missing]
    with pytest.raises(ValidationError):
        CanonicalResearchBinding.model_validate(row)


def test_explicit_nonidentity_mapping_translates_canonical_human_lock():
    row, _, _ = registration()
    row["field_mapping"]["taxon"] = "country"
    row["field_mapping"]["country"] = "taxon"
    row["human_locks"]["country"] = True
    row["semantic_mapping"]["field_mapping"] = deepcopy(row["field_mapping"])
    row["semantic_mapping_digest"] = digest(row["semantic_mapping"])
    bound = bound_registration(row)
    assert bound.research_locks == (FieldKey.TAXON,)


@pytest.mark.parametrize("change", ["missing", "wrong_job", "wrong_input", "wrong_current"])
def test_current_advance_without_exact_causal_receipt_is_rejected(change):
    row, _, _ = registration()
    row["current_canonical"]["record_revision"] = 8
    if change != "missing":
        row["publication_transition"] = {
            "receipt_id": "88888888-8888-4888-8888-888888888888", "operation_digest": "1" * 64,
            "publication_digest": "2" * 64, "binding_id": row["binding_id"], "job_key": row["job_key"],
            "base_canonical": deepcopy(row["base_canonical"]),
            "current_canonical": deepcopy(row["current_canonical"]), "job_id": row["job_id"],
            "generation": row["generation"], "input_digest": row["input_digest"],
            "profile_digest": row["profile_digest"], "runtime_binding_digest": row["runtime_binding_digest"],
        }
        if change == "wrong_job":
            row["publication_transition"]["job_id"] = "another-job"
        elif change == "wrong_input":
            row["publication_transition"]["input_digest"] = "b" * 64
        else:
            row["publication_transition"]["current_canonical"]["host_record_version_id"] = "wrong"
    with pytest.raises(ValidationError):
        CanonicalResearchBinding.model_validate(row)


def test_real_sql_repository_uses_fixed_query_and_verified_actor():
    from specimen_digitization.application.production import SqlConnectRepository, verified_actor_context

    row, _, _ = registration()
    data = native_response(row["current_canonical"], [row])

    class Response:
        status_code = 200

        def json(self):
            return {"data": data}

    class Session:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    session = Session()
    repository = SqlConnectRepository(session=session)
    scope = Scope(organization_id=ORG, collection_id=COLLECTION)
    with verified_actor_context("verified-actor"):
        snapshot = repository.current_research_binding(scope, SPECIMEN)
    assert current(snapshot).job_id == row["job_id"]
    assert len(session.calls) == 1
    url, request = session.calls[0]
    assert url.endswith(":impersonateQuery")
    assert request["json"] == {"operationName": "GetCanonicalResearchBindingV1", "variables": {
        "organizationId": ORG, "collectionId": COLLECTION, "specimenId": SPECIMEN,
        "actorUid": "verified-actor"}}
    assert request["timeout"] == 30


@pytest.mark.parametrize("status", [401, 403, 404])
def test_native_denial_vs_uninstalled_query(status):
    from specimen_digitization.application.production import SqlConnectRepository, verified_actor_context

    class Response:
        status_code = status

    class Session:
        def post(self, *args, **kwargs):
            return Response()

    repository = SqlConnectRepository(session=Session())
    with verified_actor_context("verified-actor"):
        expected = PermissionError if status in {401, 403} else BindingUnavailable
        with pytest.raises(expected):
            repository.current_research_binding(Scope(organization_id=ORG, collection_id=COLLECTION), SPECIMEN)


@pytest.mark.parametrize("data", [{}, {"canonical": None, "registrations": []},
                                  {"binding": None}, {"binding": {"canonical": None}}])
def test_native_response_aliases_are_exact_no_legacy_fallback(data):
    with pytest.raises(BindingUnavailable):
        CanonicalBindingSnapshot.from_native_response(data)


def test_native_clock_changes_do_not_change_stable_scientific_state():
    row, _, _ = registration()
    first = CanonicalResearchBinding.model_validate(row)
    later = deepcopy(row)
    later["read_bundle"]["server_time"] += 1
    second = CanonicalResearchBinding.model_validate(later)
    assert first.same_snapshot(second)
    assert first.read_bundle.server_time != second.read_bundle.server_time
    later["read_bundle"]["state_revision"] += 1
    assert not first.same_snapshot(CanonicalResearchBinding.model_validate(later))


@pytest.mark.parametrize("corrupt", ["command", "scope", "foreign"])
def test_scoped_outbox_metadata_is_typed_before_lookup(corrupt):
    row, _, _ = registration()
    command = {"scope": {**row["job"]["identity"], "generation": 2}}
    if corrupt == "command":
        command = 1
    elif corrupt == "scope":
        command["scope"] = 1
    else:
        command["scope"]["job_id"] = "foreign-job"
    row["read_bundle"]["outbox"]["retry/x"] = {"kind": "research_field_retry", "command": command}
    with pytest.raises(ValidationError):
        CanonicalResearchBinding.model_validate(row)



def test_partial_version_tuple_requires_authoritative_native_scope_joins():
    row, _, _ = registration()
    assert set(row["base_canonical"]) == {"record_revision", "record_version_id",
        "canonical_run_id", "host_record_version_id", "snapshot_sha256"}
    raw = CanonicalResearchBinding.model_validate(row)
    with pytest.raises(BindingUnavailable):
        _ = raw.canonical
    assert bound_registration(row).canonical.organization_id == ORG
    assert bound_registration(row).canonical.sensitive is True


def test_native_job_scope_mismatch_cannot_be_filled_from_requested_scope():
    row, _, _ = registration()
    row["job"]["identity"]["collection_id"] = SPECIMEN
    row["read_bundle"]["job"] = deepcopy(row["job"])
    row["job_key"] = digest(row["job"]["identity"])
    row["read_bundle"]["job_key"] = row["job_key"]
    snapshot = CanonicalBindingSnapshot.model_validate(envelope(row["current_canonical"], [row]))
    with pytest.raises(PermissionError):
        current(snapshot)


def test_raw_registration_cannot_supply_private_authoritative_identity():
    row, _, _ = registration()
    data = native_response(row["current_canonical"], [row])
    row["authoritative_canonical"] = deepcopy(data["binding"]["canonical"])
    with pytest.raises(BindingUnavailable):
        CanonicalBindingSnapshot.from_native_response(data)


@pytest.mark.parametrize("fault", ["missing_history", "wrong_binding", "bool_generation",
                                 "bool_history_scope", "foreign_scope"])
def test_old_effect_requires_exact_retained_same_job_scope_and_pins(fault):
    row, _, _ = registration()
    old_scope = {**row["job"]["identity"], "generation": 1}
    old_pins = {**row["job"]["pins"], "input_digest": "7" * 64}
    old_binding = digest(old_pins)
    history = [{"scope": old_scope, "generation": 1, "pins": old_pins, "binding_digest": old_binding}]
    row["job"]["history"] = deepcopy(history)
    row["read_bundle"]["job"] = deepcopy(row["job"])
    effect = {"scope": deepcopy(old_scope), "job_key": row["job_key"], "binding_digest": old_binding}
    if fault == "missing_history":
        row["job"]["history"] = []
        row["read_bundle"]["job"] = deepcopy(row["job"])
    elif fault == "wrong_binding":
        effect["binding_digest"] = "5" * 64
    elif fault == "bool_generation":
        effect["scope"]["generation"] = True
    elif fault == "bool_history_scope":
        row["job"]["history"][0]["scope"]["generation"] = True
        row["read_bundle"]["job"] = deepcopy(row["job"])
    else:
        effect["scope"]["specimen_id"] = COLLECTION
    row["read_bundle"]["effects"]["old-sent"] = effect
    with pytest.raises(ValidationError):
        CanonicalResearchBinding.model_validate(row)


def test_exact_retained_old_generation_effect_is_read_only_and_accepted():
    row, _, _ = registration()
    old_scope = {**row["job"]["identity"], "generation": 1}
    old_pins = {**row["job"]["pins"], "input_digest": "7" * 64}
    old_binding = digest(old_pins)
    row["job"]["history"] = [{"scope": old_scope, "generation": 1,
        "pins": old_pins, "binding_digest": old_binding}]
    row["read_bundle"]["job"] = deepcopy(row["job"])
    row["read_bundle"]["effects"]["old-sent"] = {"scope": old_scope,
        "job_key": row["job_key"], "binding_digest": old_binding, "status": "held_unknown"}
    assert bound_registration(row).read_bundle.effects["old-sent"]["status"] == "held_unknown"



@pytest.mark.parametrize("change", ["null_organization", "inactive_organization", "null_collection",
                                    "inactive_collection", "sensitive_denied"])
def test_explicit_fresh_native_access_denial_precedes_missing_binding(change):
    row, _, _ = registration()
    data = native_response(row["current_canonical"], [row])
    data["binding"] = None
    if change == "null_organization":
        data["organizationMember"] = None
    elif change == "inactive_organization":
        data["organizationMember"]["active"] = False
    elif change == "null_collection":
        data["collectionMember"] = None
    elif change == "inactive_collection":
        data["collectionMember"]["active"] = False
    else:
        data["collectionMember"]["canViewSensitive"] = False
    with pytest.raises(PermissionError):
        CanonicalBindingSnapshot.from_native_response(data)


@pytest.mark.parametrize("change", ["unknown_alias", "bad_org_bool", "bad_collection_bool",
                                    "unknown_role", "bad_sensitivity_bool", "missing_specimen"])
def test_unknown_native_authorization_shape_is_unavailable_not_false_denial(change):
    row, _, _ = registration()
    data = native_response(row["current_canonical"], [row])
    if change == "unknown_alias":
        data["capabilities"] = {"read": True}
    elif change == "bad_org_bool":
        data["organizationMember"]["active"] = "true"
    elif change == "bad_collection_bool":
        data["collectionMember"]["canViewSensitive"] = 1
    elif change == "unknown_role":
        data["collectionMember"]["role"] = "unknown"
    elif change == "bad_sensitivity_bool":
        data["specimen"]["sensitive"] = 1
    else:
        data["specimen"] = None
    with pytest.raises(BindingUnavailable):
        CanonicalBindingSnapshot.from_native_response(data)


@pytest.mark.parametrize("count", [0, 2, 3, True, 1.0, "1", None])
def test_native_active_count_cannot_be_guessed_from_select_first_one_row(count):
    row, _, _ = registration()
    data = native_response(row["current_canonical"], [row])
    data["binding"]["active_registration_count"] = count
    with pytest.raises(BindingUnavailable):
        current(CanonicalBindingSnapshot.from_native_response(data))


def test_extra_inactive_row_does_not_satisfy_exact_v4_registration_array():
    row, _, _ = registration()
    inactive = deepcopy(row)
    inactive["active"] = False
    data = native_response(row["current_canonical"], [row, inactive])
    with pytest.raises(BindingUnavailable):
        current(CanonicalBindingSnapshot.from_native_response(data))


def test_http200_graphql_error_text_never_grants_authorization_classification():
    from specimen_digitization.application.production import SqlConnectRepository, verified_actor_context

    class Response:
        status_code = 200

        def json(self):
            return {"errors": [{"message": "permission denied"}]}

    class Session:
        def post(self, *args, **kwargs):
            return Response()

    with verified_actor_context("verified-actor"), pytest.raises(BindingUnavailable):
        SqlConnectRepository(session=Session()).current_research_binding(
            Scope(organization_id=ORG, collection_id=COLLECTION), SPECIMEN)


@pytest.mark.parametrize("holds", [["program_halted", "program_halted"],
                                   ["ledger_import_uninstalled"], [True], "program_halted"])
def test_native_dynamic_holds_are_unique_typed_and_exact_v4_codes(holds):
    row, _, _ = registration()
    row["read_bundle"]["hold_reasons"] = holds
    with pytest.raises(ValidationError):
        CanonicalResearchBinding.model_validate(row)


def test_fresh_public_sensitivity_does_not_create_historic_tuple_sensitivity():
    row, _, _ = registration()
    row["job"]["sensitive"] = False
    row["read_bundle"]["job"] = deepcopy(row["job"])
    data = native_response({**row["current_canonical"], "sensitive": False}, [row])
    data["collectionMember"]["canViewSensitive"] = False
    binding = current(CanonicalBindingSnapshot.from_native_response(data))
    assert binding.canonical.sensitive is False
    assert "sensitive" not in binding.base_canonical.model_dump()
    assert "sensitive" not in binding.current_canonical.model_dump()



def retry_event(row, status="queued", *, generation=None, binding_digest=None, delivered=False):
    """Synthetic persisted outbox row; never an admission or worker substitute."""
    generation = row["generation"] if generation is None else generation
    command_id = digest({"fixture": "retry-outbox", "status": status, "generation": generation})
    command = {"id": command_id, "kind": "retry_field", "status": status,
        "scope": {**row["job"]["identity"], "generation": generation},
        "expected_generation": generation, "field_key": "country",
        "binding_digest": row["runtime_binding_digest"] if binding_digest is None else binding_digest}
    row["read_bundle"]["outbox"]["retry/" + command_id] = {
        "kind": "research_field_retry", "command": command, "delivered": delivered}
    return command


@pytest.mark.parametrize("status", ["queued", "running", "blocked", "completed"])
def test_current_retry_commands_require_exact_scope_and_current_binding(status):
    row, _, _ = registration()
    command = retry_event(row, status, delivered=status in {"blocked", "completed"})
    result = bound_registration(row)
    assert result.read_bundle.outbox["retry/" + command["id"]]["command"]["scope"] == {
        **row["job"]["identity"], "generation": 2}
    assert result.runtime_binding_digest == command["binding_digest"]


@pytest.mark.parametrize("fault", ["bool", "float", "string", "extra", "missing", "stale", "future", "foreign", "empty_job"])
def test_native_outbox_rejects_malformed_or_unproved_command_scope(fault):
    row, _, _ = registration()
    # Generation1 is deliberate: bool True must not alias its valid scalar.
    row["generation"] = row["job"]["generation"] = 1
    row["read_bundle"]["job"] = deepcopy(row["job"])
    command = retry_event(row)
    if fault in {"bool", "float", "string"}:
        command["scope"]["generation"] = {"bool": True, "float": 1.0, "string": "1"}[fault]
    elif fault == "extra":
        command["scope"]["actor_uid"] = "unscoped-extra"
    elif fault == "missing":
        del command["scope"]["generation"]
    elif fault == "stale":
        command["scope"]["generation"] = 0
    elif fault == "future":
        command["scope"]["generation"] = 2
    elif fault == "foreign":
        command["scope"]["job_id"] = "another-job"
    else:
        command["scope"]["job_id"] = ""
    with pytest.raises(ValidationError):
        bound_registration(row)


@pytest.mark.parametrize("bad", [True, 2.0, "2", None, 1])
def test_retry_expected_generation_cannot_coerce_or_disagree(bad):
    row, _, _ = registration()
    command = retry_event(row)
    command["expected_generation"] = bad
    with pytest.raises(ValidationError):
        bound_registration(row)


@pytest.mark.parametrize("status", ["blocked", "completed"])
def test_exact_terminal_old_generation_command_is_retained_read_only(status):
    row, _, _ = registration()
    old_scope = {**row["job"]["identity"], "generation": 1}
    old_pins = {**row["job"]["pins"], "input_digest": "7" * 64}
    old_binding = digest(old_pins)
    row["job"]["history"] = [{"scope": old_scope, "generation": 1,
        "pins": old_pins, "binding_digest": old_binding}]
    row["read_bundle"]["job"] = deepcopy(row["job"])
    command = retry_event(row, status, generation=1, binding_digest=old_binding, delivered=True)
    result = bound_registration(row)
    assert result.generation == 2
    assert result.read_bundle.outbox["retry/" + command["id"]]["command"]["scope"] == old_scope
    assert result.read_bundle.outbox["retry/" + command["id"]]["delivered"] is True


@pytest.mark.parametrize("fault", ["queued", "running", "undelivered", "missing_history", "bool_history", "float_history", "string_history", "extra_history", "missing_history_key", "wrong_pins", "duplicate_history", "wrong_binding"])
def test_historical_retry_requires_exact_terminal_unique_pinned_lineage(fault):
    row, _, _ = registration()
    old_scope = {**row["job"]["identity"], "generation": 1}
    old_pins = {**row["job"]["pins"], "input_digest": "7" * 64}
    old_binding = digest(old_pins)
    history = {"scope": deepcopy(old_scope), "generation": 1,
        "pins": old_pins, "binding_digest": old_binding}
    row["job"]["history"] = [history]
    command = retry_event(row, "blocked", generation=1, binding_digest=old_binding, delivered=True)
    event = row["read_bundle"]["outbox"]["retry/" + command["id"]]
    if fault in {"queued", "running"}:
        command["status"] = fault
    elif fault == "undelivered":
        event["delivered"] = False
    elif fault == "missing_history":
        row["job"]["history"] = []
    elif fault in {"bool_history", "float_history", "string_history"}:
        history["scope"]["generation"] = {"bool_history": True, "float_history": 1.0, "string_history": "1"}[fault]
    elif fault == "extra_history":
        history["scope"]["actor_uid"] = "extra"
    elif fault == "missing_history_key":
        del history["scope"]["job_id"]
    elif fault == "wrong_pins":
        history["pins"]["input_digest"] = "8" * 64
    elif fault == "duplicate_history":
        row["job"]["history"].append(deepcopy(history))
    else:
        command["binding_digest"] = "6" * 64
    row["read_bundle"]["job"] = deepcopy(row["job"])
    with pytest.raises(ValidationError):
        bound_registration(row)
