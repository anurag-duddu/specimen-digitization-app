"""Offline HTTP proof of canonical candidate saves and read-only retained reports.

Only native binding discovery is a fixture. Specimens, effects, checkpoints,
candidate resolution, application evidence, canonical CAS and reopen are real.
"""

import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT, create_app,
)
from specimen_digitization.application.domain import FieldValue, Scope, ValueState
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.research_harness.canonical_binding import (
    BindingUnavailable, CanonicalIdentity,
)
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, EvidenceItem, FieldKey, FieldProfile,
    FieldResolution, HumanQuestion, ResearchScope, SourceCoverageReceipt,
    SourceResult, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.human_review import REPORT_KEY
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, CapturedResult, DurabilityScope, DurableEffectBroker,
    ImmutableFileBlobs, ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import runtime_pins
from specimen_digitization.research_harness.thread_view import ResearchThreadReader
from test_decisions_batch import BATCH, HEADERS, PREFIX, REASON, client, processed
from test_derivation_proposal_reads import build_computed


class RetainedResearch:
    """Real offline journal matching the canonical specimen's actual identity."""

    def __init__(self, root, specimen):
        profile = CollectionProfile(id="fixture-insects", version="1",
            organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION,
            ancestry=(SYNTHETIC_ORG, SYNTHETIC_COLLECTION), knowledge_version="fixture",
            fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
        self.scope = ResearchScope(organization_id=SYNTHETIC_ORG,
            collection_id=SYNTHETIC_COLLECTION, specimen_id=specimen.id,
            job_id="offline-review", generation=1, input_digest=specimen.asset.sha256,
            profile_digest=digest(profile), sensitive=specimen.asset.sensitive)
        requests = {role: SpecialistRequest(scope=self.scope, role=role, field_keys=keys,
            prompt=resolve_prompt(role, profile_digest=self.scope.profile_digest,
                source_registry_digest="b" * 64, toolset_digest="c" * 64,
                model_route="harness-deepseek", output_schema_digest="d" * 64))
            for role, keys in ROLE_FIELDS.items()}
        settings = {"max_tokens": 128}
        pins = runtime_pins(profile, requests,
            model={role: {"route": "harness-deepseek"} for role in requests}, settings=settings)
        self.durable = DurabilityScope(SYNTHETIC_ORG, SYNTHETIC_COLLECTION,
            specimen.id, self.scope.job_id, 1, "synthetic-reviewer", specimen.asset.sensitive)
        backend = SqliteStateBackend(root / "research.sqlite3")
        backend.grant(self.durable, can_view_sensitive=True)
        self.store = ResearchStore(backend, "offline-review-budget")
        self.store.initialize(self.durable, BudgetPolicy(100))
        self.store.create_job(self.durable, pins, list(ALL_FIELDS),
            record_revision=specimen.version)
        lease = self.store.claim(self.durable, "offline-worker")
        self.journal = DurableResearchJournal(self.store, self.durable, lease)
        broker = DurableEffectBroker(self.store, ImmutableFileBlobs(root / "captures"))
        resolutions, effects = [], []
        for ordinal, (key, value) in enumerate((
            (FieldKey.COUNTRY, "Philippines"), (FieldKey.PROVINCE_STATE, "Davao del Sur"),
        ), 1):
            evidence_id = "source:" + digest(str(key))
            coverage = SourceCoverageReceipt(source_id="geolocate", field_key=key,
                state="searched", source_version="offline-fixture-v1", receipt_ids=(evidence_id,),
                candidate_count=1, coverage_limit="Synthetic capture only",
                reason="ambiguous: multiple places share the displayed name")
            result = SourceResult(status="ambiguous", coverage=coverage,
                evidence=(EvidenceItem(id=evidence_id, kind="qualified_source", source_id="geolocate",
                    source_version=coverage.source_version, locator="fixture/apo",
                    response_digest=digest(value), publisher_assertion_id="offline-fixture",
                    excerpt="Synthetic retained source candidate"),),
                candidate_json=(json.dumps({"value": value, "match_name": "MOUNT APO",
                    "authority_id": f"geolocate:{ordinal:016x}", "rank": 1,
                    "latitude": 6.99, "longitude": 125.27}),))

            async def capture(*_, payload=result.model_dump(mode="json")):
                return CapturedResult(payload, 0)

            effect = asyncio.run(broker.execute(self.durable, lease,
                "source_lookup:" + digest(str(key)), {"field": str(key)}, 1, capture,
                execution_class="offline", field_keys=(str(key),)))
            effects.append(effect.effect_id)
            resolutions.append(FieldResolution(field_key=key, work_state=WorkState.WAITING_HUMAN,
                value=FieldValue(state=ValueState.AMBIGUOUS, literal=specimen.run.fields[str(key)].literal),
                question=HumanQuestion(field_key=key, question="Which retained place is intended?",
                    reason="semantic_ambiguity", coverage=(coverage,), evidence_ids=(evidence_id,)),
                reason="Retained alternatives need a reviewer"))
        asyncio.run(self.journal.commit(requests[SpecialistRole.GEOGRAPHY], tuple(resolutions),
            receipt_ids=tuple(effects), model_settings_digest=digest(settings)))
        self.thread = asyncio.run(ResearchThreadReader(self.journal).read(self.scope))
        self.candidates = {str(field.field_key): field.review.candidates[0]
            for field in self.thread.fields if field.review and field.review.candidates}


class BoundDiscovery:
    """Explicit fixture for native binding only, with a real canonical revision check."""

    def __init__(self, repository, specimen, research):
        self.repository, self.research = repository, research
        self.scope = specimen.scope
        canonical = CanonicalIdentity(organization_id=SYNTHETIC_ORG,
            collection_id=SYNTHETIC_COLLECTION, specimen_id=specimen.id,
            sensitive=specimen.asset.sensitive, canonical_run_id=specimen.run.id,
            record_revision=specimen.version, record_version_id=str(uuid4()),
            host_record_version_id=f"{specimen.run.id}:{specimen.version}",
            snapshot_sha256=digest(specimen.model_dump(mode="json")))
        self.snapshot = SimpleNamespace(canonical=canonical,
            field_mapping={key: str(key) for key in FieldKey}, research_locks=set(),
            research_scope=lambda: research.scope)
        self.snapshot.same_snapshot = lambda other: other is self.snapshot
        self.drift = False

    async def binding(self, principal, specimen_id):
        current = self.repository.get(principal.scope, specimen_id)
        if current.version != self.snapshot.canonical.record_revision:
            raise BindingUnavailable("canonical_binding_stale")
        return SimpleNamespace() if self.drift else self.snapshot

    async def bound_state(self, principal, specimen_id):
        await self.binding(principal, specimen_id)
        document = self.research.store._read(self.research.durable)
        return (self.snapshot, self.research.store, self.research.durable, document,
            document.state["jobs"][self.research.durable.key])

    async def discover(self, principal, specimen_id):
        from specimen_digitization.research_harness.discovery import DiscoveryCapabilities
        from specimen_digitization.research_harness.discovery_v2 import ResearchDiscoveryResultV2

        await self.binding(principal, specimen_id)
        return ResearchDiscoveryResultV2(canonical=self.snapshot.canonical,
            scope=self.research.scope, human_locked_fields=(),
            capabilities=DiscoveryCapabilities(read=True, retry=False, review=False))

    async def service(self, principal, locator):
        from specimen_digitization.research_harness.persistence import StaleWork
        from specimen_digitization.research_harness.service import ResearchService

        await self.binding(principal, locator.specimen_id)
        async def resolve(actor, requested):
            if (actor.user_id != principal.user_id or requested.specimen_id != self.research.scope.specimen_id
                    or requested.job_id != self.research.scope.job_id
                    or requested.generation != self.research.scope.generation):
                raise StaleWork("research_state_changed")
            return self.research.durable
        return ResearchService(store=self.research.store, resolve_scope=resolve,
            retry_admission=self.research.store.admit_retry)


@pytest.fixture
def review(tmp_path):
    with client(tmp_path) as intake:
        record = processed(intake, 1)
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    specimen = repository.get(scope, record["specimen_id"])
    blobs = LocalBlobs(tmp_path / "blobs")
    research = RetainedResearch(tmp_path, specimen)
    access = SimpleNamespace(role="reviewer", sensitive=True, member=True)
    app = create_app(mode="emulator", repository=repository, blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        research_version="v2",
        identity_verifier=lambda *_: "synthetic-reviewer",
        memberships=lambda _: [{"organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION, "role": access.role,
            "can_view_sensitive": access.sensitive}] if access.member else [])
    discovery = BoundDiscovery(repository, specimen, research)
    app.state.research_discovery.current = discovery
    with TestClient(app, raise_server_exceptions=False) as http:
        yield SimpleNamespace(client=http, app=app, root=tmp_path, record=record, original=specimen,
            repository=repository, scope=scope, blobs=blobs, research=research,
            discovery=discovery, access=access)


def choice(review, field="country", **changes):
    record = review.record
    return dict({"specimen_id": record["specimen_id"], "expected_revision": record["revision"],
        "base_record_version_id": record["record_version_id"], "kind": "research_candidate",
        "target_id": field, "after": {"selection_id": review.research.candidates[field].selection_id}},
        **changes)


def post(review, decisions, request_key="candidate-batch"):
    response = review.client.post(BATCH, headers=dict(HEADERS, **{"Idempotency-Key": request_key}),
        json={"reason": REASON, "decisions": decisions})
    assert response.status_code == 200, response.text
    return response.json()


def reopen(review):
    response = review.client.get(PREFIX + f"/specimens/{review.record['specimen_id']}/workspace",
        headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def research_base(review):
    return (PREFIX + f"/collections/{SYNTHETIC_COLLECTION}/specimens/{review.record['specimen_id']}"
        + "/research")


def current_thread(review):
    return review.client.get(research_base(review) + "/jobs/offline-review/generations/1/thread",
        headers=HEADERS)


def test_current_report_offers_only_qualified_choices_then_saves_and_reopens(review):
    current = review.client.get(research_base(review) + "/current", headers=HEADERS)
    assert current.status_code == 200, current.text
    assert current.json()["scope"]["job_id"] == "offline-review"
    response = current_thread(review)
    assert response.status_code == 200, response.text
    thread = response.json()
    assert thread.get("historical") is not True
    by_field = {field["field_key"]: field for field in thread["fields"]}
    choices = []
    for key in ("country", "province_state"):
        field = by_field[key]
        assert field["work_state"] == "waiting_human"
        assert field["actions"] == ["review_proposal"]
        candidate, = field["review"]["candidates"]
        assert candidate["selection_id"] == review.research.candidates[key].selection_id
        assert candidate["selection_value"] == review.research.candidates[key].selection_value
        assert candidate["evidence_id"] == field["review"]["evidence"][0]["evidence_id"]
        choices.append(choice(review, key, after={"selection_id": candidate["selection_id"]}))
    assert all("review_proposal" not in field["actions"] for key, field in by_field.items()
               if key not in {"country", "province_state"})
    result = post(review, choices)
    assert (result["applied"], result["refused"], result["skipped"]) == (2, 0, 0)
    saved = reopen(review)
    assert saved["revision"] == review.record["revision"] + 1
    assert saved["fields"]["country"]["normalized"] == "Philippines"
    assert saved["fields"]["province_state"]["normalized"] == "Davao del Sur"
    after = current_thread(review)
    assert after.status_code == 200 and after.json()["historical"] is True
    assert all(not field["actions"] for field in after.json()["fields"])
    assert all(candidate["selection_id"] is None for field in after.json()["fields"]
               if field["review"] for candidate in field["review"]["candidates"])


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_current_report_keeps_source_context_but_no_choice_for_non_reviewers(review, role):
    review.access.role = role
    response = current_thread(review)
    assert response.status_code == 200, response.text
    country = next(item for item in response.json()["fields"] if item["field_key"] == "country")
    assert country["review"]["evidence"] and country["review"]["candidates"]
    assert "review_proposal" not in country["actions"]
    assert all(item["selection_id"] is None and item["selection_value"] is None
               for item in country["review"]["candidates"])


@pytest.mark.parametrize("failure", ["unknown_effect", "uncited_capture", "missing_capture"])
def test_current_report_cannot_advertise_a_source_choice_that_post_would_refuse(review, failure):
    original = review.discovery.bound_state

    async def damaged(*args):
        binding, store, scope, document, job = await original(*args)
        effect = next(item for item in document.state["effects"].values()
                      if item["field_keys"] == ["country"])
        if failure == "unknown_effect":
            effect["status"] = "held_unknown"
        elif failure == "uncited_capture":
            effect["receipt"]["typed_payload"]["coverage"]["receipt_ids"] = []
        else:
            effect["receipt"].pop("capture")
        return binding, store, scope, document, job

    review.discovery.bound_state = damaged
    response = current_thread(review)
    assert response.status_code == 200, response.text
    country = next(item for item in response.json()["fields"] if item["field_key"] == "country")
    assert country["review"]["candidates"] and country["review"]["evidence"]
    assert country["review"]["candidates"][0]["selection_id"] is None
    assert country["review"]["candidates"][0]["selection_value"] is None
    assert "review_proposal" not in country["actions"]
    province = next(item for item in response.json()["fields"] if item["field_key"] == "province_state")
    assert province["actions"] == ["review_proposal"]


@pytest.mark.parametrize("failure", ["missing_typed_payload", "non_mapping_receipt"])
def test_malformed_secondary_receipt_keeps_other_current_choices_readable(review, failure):
    baseline = current_thread(review)
    assert baseline.status_code == 200
    assert next(item for item in baseline.json()["fields"] if item["field_key"] == "country")[
        "actions"] == ["review_proposal"]
    original = review.discovery.bound_state

    async def damaged(*args):
        binding, store, scope, document, job = await original(*args)
        existing = next(item for item in document.state["effects"].values()
                        if item["field_keys"] == ["country"])
        secondary_id = digest({"malformed_secondary_country": failure})
        secondary = copy.deepcopy(existing)
        secondary["effect_id"] = secondary_id
        secondary["operation_key"] = "source_lookup:" + secondary_id
        secondary["receipt"] = ({"effect_id": secondary_id}
            if failure == "missing_typed_payload" else ["not a receipt mapping"])
        document.state["effects"][secondary_id] = secondary
        stored = job["fields"]["country"]["checkpoint"]
        stored["payload"]["effect_receipt_ids"].append(secondary_id)
        stored["receipt_ids"].append(secondary_id)
        stored["id"] = digest({"scope": stored["scope"], "field": "country",
            "revision": stored["revision"], "payload": stored["payload"]})
        return binding, store, scope, document, job

    review.discovery.bound_state = damaged
    response = current_thread(review)
    assert response.status_code == 200, response.text
    country = next(item for item in response.json()["fields"] if item["field_key"] == "country")
    province = next(item for item in response.json()["fields"] if item["field_key"] == "province_state")
    assert country["review"]["candidates"] and country["review"]["evidence"]
    assert country["review"]["candidates"][0]["selection_id"] is None
    assert "review_proposal" not in country["actions"]
    assert province["actions"] == ["review_proposal"]
    assert province["review"]["candidates"][0]["selection_id"]


@pytest.mark.parametrize("failure, status", [
    (PermissionError("research_access_denied"), 403),
    (OSError("unavailable-private-research-store"), 503),
])
def test_proposal_qualification_does_not_hide_auth_or_storage_failure(review, failure, status):
    async def unavailable(*_):
        raise failure

    review.discovery.bound_state = unavailable
    response = current_thread(review)
    assert response.status_code == status
    assert "unavailable-private-research-store" not in response.text


def test_current_report_refuses_revoked_membership_and_wrong_job_without_a_choice(review):
    review.access.member = False
    denied = current_thread(review)
    assert denied.status_code == 403
    assert denied.json() == {"detail": "research_access_denied"}
    review.access.member = True
    wrong = review.client.get(research_base(review) + "/jobs/old-job/generations/1/thread",
        headers=HEADERS)
    assert wrong.status_code == 409
    assert wrong.json() == {"detail": "research_state_changed"}


@pytest.fixture
def derived_review(tmp_path):
    """Real saved human proofs and local computed receipts; discovery is explicit fixture."""
    from specimen_digitization.application.domain import AuditEvent, Principal
    from specimen_digitization.application.production import actor_uid
    from specimen_digitization.research_harness.derivation_contracts import (
        DerivationCommand, derivation_input_digest,
    )
    from specimen_digitization.research_harness.human_review import CandidateReviewContext
    from specimen_digitization.research_harness.thread_view import candidate_selection_id
    from test_derivation_contracts import command_data
    from test_derivation_inputs import Case

    actor = actor_uid.set("B")
    try:
        case = Case(tmp_path / "canonical")
        case.manual()
        while case.current.version < 5:
            pending = case.current.model_copy(deep=True)
            pending.run.fields["city"] = FieldValue(literal="Original city reading", state="unresolved")
            case.save(pending)
        inputs = case.collect()
        info = case.repo.version_info(case.current.scope, case.current.id, case.current.version)
        command = DerivationCommand.model_validate(command_data() | {
            "canonical_run_id": case.current.run.id, "source_snapshot_sha256": info["sha256"],
            "inputs": inputs, "input_digest": derivation_input_digest(inputs)})
        queued = case.current.model_copy(deep=True)
        queued.run.dependencies["research_derivation_request"] = command.model_dump(mode="json")
        queued.audit.append(AuditEvent(actor="A", action="review_derive_rest", reason="Queue fixture",
            after={"request_id": command.id}))
        case.save(queued)
        rig, document, job, result, effect = build_computed(tmp_path / "computed", command)
        job["record_revision"] = command.queued_revision
        job["dependencies"].update(derivation_request_id=command.id,
            derivation_result={**result, "request_id": command.id, "status": "completed"})
        payload = document.state["effects"][effect]["receipt"]["typed_payload"]
        item = json.loads(payload["candidate_json"][0])
        token = candidate_selection_id(rig.journal.scope.key, FieldKey.CITY, effect, item)
        decision = SimpleNamespace(kind="research_candidate", target_id="city",
            after={"selection_id": token}, evidence_ids=[], before={})
        binding = SimpleNamespace(canonical=SimpleNamespace(record_revision=case.current.version,
            canonical_run_id=case.current.run.id), field_mapping={key: str(key) for key in FieldKey},
            research_locks={FieldKey.COUNTRY}, research_scope=lambda: rig.scope)

        async def bound_state(*_):
            return binding, rig.journal.store, rig.journal.scope, document, job

        discovery = SimpleNamespace(bound_state=bound_state)
        principal = Principal(user_id="B", role="reviewer", scope=case.current.scope)

        def load(decisions=None, **changes):
            return asyncio.run(CandidateReviewContext.load(discovery, principal, case.current,
                [decision] if decisions is None else decisions,
                **({"repository": case.repo, "blobs": case.blobs, "capture_blobs": rig.capture_blobs} | changes)))

        yield SimpleNamespace(case=case, command=command, job=job, document=document,
            metadata=item, payload=payload, binding=binding, decision=decision, load=load,
            capture_blobs=rig.capture_blobs)
    finally:
        actor_uid.reset(actor)


def test_genuine_derived_choice_preserves_original_literal_and_exact_source_metadata(derived_review):
    from specimen_digitization.application.domain import AuditEvent
    from specimen_digitization.application.projection import _human_research_choices

    review = derived_review
    context = review.load()
    pending = review.case.current.model_copy(deep=True)
    literal = pending.run.fields["city"].literal
    after = context.apply(pending, "city", review.case.blobs, "Reviewed deterministic proposal")
    field = pending.run.fields["city"]
    assert field.literal == literal
    assert field.normalized == field.parsed == review.metadata["value"]
    assert field.layer == after["value_layer"] == "derived"
    assert field.derived_from == after["derived_from"] == ["country"]
    assert after["derivation_metadata"] == review.metadata
    assert field.source_observation_id is None and field.settled_observation_ids == []
    evidence = next(e for e in pending.run.evidence if e.id == after["evidence_ids"][0])
    retained = json.loads(review.case.blobs.get(evidence.raw_ref))
    assert retained["source_candidate"] == review.metadata
    assert "derivation_metadata" not in retained  # Original source envelope remains stable.
    pending.audit.append(AuditEvent(actor="A", action="review_research_candidate", reason="Reviewed", after=after))
    saved = review.case.save(pending)
    proofs, _ = review.case.repo._review_proofs(saved.scope, saved)
    assert _human_research_choices(saved, proofs)["city"] == after


@pytest.mark.parametrize("attack", ["no_repository", "no_blobs", "no_capture_blobs", "missing_command", "queued_revision",
    "source_snapshot", "request_id", "record_revision", "unfinished", "checkpoint", "stale_input",
    "forged_proof", "target", "metadata_revision", "metadata_evidence", "sensitive", "blocked",
    "extra_checkpoint", "command_reason"])
def test_derived_choices_fail_before_application_when_saved_input_or_request_proof_changes(derived_review, attack):
    from specimen_digitization.application.storage import Conflict
    from specimen_digitization.research_harness.derivation_contracts import derivation_input_digest
    from specimen_digitization.research_harness.thread_view import candidate_selection_id

    review = derived_review
    command = review.case.current.run.dependencies["research_derivation_request"]
    changes = {}
    if attack in {"no_repository", "no_blobs", "no_capture_blobs"}:
        changes[attack.removeprefix("no_")] = None
    elif attack == "missing_command":
        review.case.current.run.dependencies.pop("research_derivation_request")
    elif attack == "queued_revision":
        review.case.current.version += 1
        review.binding.canonical.record_revision += 1
    elif attack == "source_snapshot":
        command["source_snapshot_sha256"] = "f" * 64
    elif attack == "request_id":
        review.job["dependencies"]["derivation_request_id"] = "f" * 64
    elif attack == "record_revision":
        review.job["record_revision"] += 1
    elif attack == "unfinished":
        review.job["dependencies"]["derivation_result"]["status"] = "running"
    elif attack == "checkpoint":
        review.job["dependencies"]["derivation_result"]["checkpoint_ids"] = []
    elif attack == "extra_checkpoint":
        review.job["dependencies"]["derivation_result"]["checkpoint_ids"].append("f" * 64)
    elif attack == "blocked":
        command["status"] = "blocked"
    elif attack == "command_reason":
        command["reason"] = "Another request with the same saved inputs"
    elif attack == "stale_input":
        review.case.current.run.fields["country"].normalized = "Changed since request"
    elif attack == "sensitive":
        review.case.current.asset.sensitive = True
    elif attack == "forged_proof":
        command["inputs"][0]["provenance_blob_ref"] = review.case.blobs.put(b"forged proof")
        command["input_digest"] = derivation_input_digest(command["inputs"])
    elif attack == "target":
        command["requested_fields"] = ["county"]
    else:
        if attack == "metadata_revision":
            review.metadata["input_revisions"][0][1] -= 1
        else:
            review.metadata["evidence_ids"].append("invented-input-evidence")
        review.payload["candidate_json"] = [json.dumps(review.metadata)]
        effect = next(key for key, value in review.document.state["effects"].items()
                      if value.get("receipt", {}).get("typed_payload") is review.payload)
        review.decision.after["selection_id"] = candidate_selection_id(
            next(iter(review.document.state["jobs"])), FieldKey.CITY, effect, review.metadata)
    before = review.case.current.model_dump(mode="json")
    with pytest.raises((ValueError, Conflict)):
        review.load(**changes)
    assert review.case.current.model_dump(mode="json") == before


@pytest.mark.parametrize("derived_first", [True, False])
def test_a_derived_group_cannot_change_its_own_input_in_either_decision_order(derived_review, derived_first):
    review = derived_review
    edit = SimpleNamespace(kind="field", target_id="country")
    decisions = [review.decision, edit] if derived_first else [edit, review.decision]
    with pytest.raises(ValueError, match="Save derivation input changes separately"):
        review.load(decisions)


def test_two_candidates_are_one_canonical_cas_with_server_retained_values_and_provenance(review):
    result = post(review, [choice(review), choice(review, "province_state")])
    assert (result["applied"], result["refused"], result["skipped"]) == (2, 0, 0), result
    expected_revision = review.record["revision"] + 1
    assert {row["revision"] for row in result["results"]} == {expected_revision}
    saved = reopen(review)
    assert saved["revision"] == expected_revision
    for field, value in (("country", "Philippines"), ("province_state", "Davao del Sur")):
        candidate = review.research.candidates[field]
        assert candidate.label == "MOUNT APO" and candidate.selection_value == value
        materialized = saved["fields"][field]
        assert materialized["literal"] == review.record["fields"][field]["literal"]
        assert materialized["parsed"] == materialized["normalized"] == value
        assert materialized["authority_id"] == candidate.authority_id
        assert "latitude" not in materialized and "longitude" not in materialized
    assert saved["run"]["observations"] == review.record["run"]["observations"]
    assert saved["run"]["transcripts"] == review.record["run"]["transcripts"]
    assert saved["run"]["human_approved"] is False
    assert set(saved["run"]["dependencies"]["human_review_field_locks"]) == {"country", "province_state"}
    events = [event for event in saved["decisions"] if event["action"] == "review_research_candidate"]
    assert len(events) == 2
    assert {event["actor"] for event in events} == {"synthetic-reviewer"}
    assert {event["reason"] for event in events} == {REASON}
    selected_evidence = [item for item in saved["evidence"] if item["kind"] == "authority_selection"]
    assert len(selected_evidence) == 2
    for item in selected_evidence:
        copied = json.loads(review.blobs.get(item["raw_ref"]))
        assert copied["source_candidate"]["match_name"] == "MOUNT APO"
        assert copied["capture"] and copied["checkpoint_id"] and copied["effect_id"]
    assert review.research.store.budget(review.research.durable)["settled_micro_usd"] == 0


@pytest.mark.parametrize("candidate_first", [False, True])
def test_candidate_and_normal_pending_field_edit_commit_together(review, candidate_first):
    field = dict(review.record["fields"]["habitat"])
    field.pop("value_state", None)
    evidence = field.pop("evidence_ids")
    field["reason"] = "Reviewer retained the original habitat reading"
    edit = choice(review, kind="field", target_id="habitat", after=field, evidence_ids=evidence)
    entries = [choice(review), edit] if candidate_first else [edit, choice(review)]
    result = post(review, entries)
    assert (result["applied"], result["refused"]) == (2, 0), result
    saved = reopen(review)
    assert saved["revision"] == review.record["revision"] + 1
    assert saved["fields"]["country"]["normalized"] == "Philippines"
    assert saved["fields"]["habitat"]["reason"] == field["reason"]


@pytest.mark.parametrize("attack", ["unknown_token", "caller_value", "wrong_field", "stale_revision", "snapshot_drift"])
def test_invalid_candidate_group_never_partially_saves(review, attack):
    good, bad = choice(review), choice(review, "province_state")
    if attack == "unknown_token":
        bad["after"] = {"selection_id": "f" * 64}
    elif attack == "caller_value":
        bad["after"]["value"] = "Forged scientific result"
    elif attack == "wrong_field":
        bad["after"] = dict(good["after"])
    elif attack == "stale_revision":
        for entry in (good, bad):
            entry["expected_revision"] += 1
            entry["base_record_version_id"] = f"{review.original.run.id}:{entry['expected_revision']}"
    else:
        review.discovery.drift = True
    result = post(review, [good, bad])
    assert (result["applied"], result["refused"], result["skipped"]) == (0, 1, 1), result
    saved = reopen(review)
    assert saved["revision"] == review.record["revision"]
    assert saved["fields"] == review.record["fields"]
    assert REPORT_KEY not in saved["run"]["dependencies"]
    assert not any(event["action"] == "review_research_candidate" for event in saved["decisions"])


def test_invalid_ordinary_edit_rolls_back_preceding_candidate_in_same_save(review):
    invalid = choice(review, kind="field", target_id="not-a-real-field", after={})
    result = post(review, [choice(review), invalid])
    assert (result["applied"], result["refused"], result["skipped"]) == (0, 1, 1)
    assert reopen(review)["revision"] == review.record["revision"]


def test_idempotent_candidate_replay_keeps_one_revision_and_one_human_event(review):
    entries = [choice(review)]
    first = post(review, entries)
    replay = post(review, entries)
    assert first == replay
    saved = reopen(review)
    assert saved["revision"] == review.record["revision"] + 1
    assert len([event for event in saved["decisions"] if event["action"] == "review_research_candidate"]) == 1


def test_single_candidate_endpoint_uses_the_same_retained_selection_and_cas(review):
    entry = choice(review)
    entry.pop("specimen_id")
    entry["reason"] = REASON
    response = review.client.post(PREFIX + f"/specimens/{review.record['specimen_id']}/decisions",
        headers=HEADERS, json=entry)
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == review.record["revision"] + 1
    assert reopen(review)["fields"]["country"]["normalized"] == "Philippines"


def test_actual_canonical_cas_race_preserves_competing_save_without_partial_selection(review, monkeypatch):
    save = review.repository.save

    def competing_save(principal, pending, expected, key, request_digest):
        if key.startswith("research-review:"):
            current = review.repository.get(principal.scope, pending.id)
            current.run.fields["habitat"].reason = "Concurrent reviewer edit"
            save(principal, current, current.version, "competing-review", digest("competing-review"))
        return save(principal, pending, expected, key, request_digest)

    monkeypatch.setattr(review.repository, "save", competing_save)
    result = post(review, [choice(review), choice(review, "province_state")])
    assert (result["applied"], result["refused"], result["skipped"]) == (0, 1, 1)
    assert result["results"][0]["error"]["status"] == 409
    saved = reopen(review)
    assert saved["revision"] == review.record["revision"] + 1
    assert saved["fields"]["habitat"]["reason"] == "Concurrent reviewer edit"
    assert saved["fields"]["country"] == review.record["fields"]["country"]
    assert REPORT_KEY not in saved["run"]["dependencies"]


def test_restart_reopens_saved_values_and_history_without_native_binding_fixture(review):
    assert post(review, [choice(review)])["applied"] == 1
    with client(review.root) as restarted:
        workspace = restarted.get(PREFIX + f"/specimens/{review.record['specimen_id']}/workspace",
            headers=HEADERS)
        assert workspace.status_code == 200, workspace.text
        assert workspace.json()["fields"]["country"]["normalized"] == "Philippines"
        current = restarted.get(research_base(review) + "/current", headers=HEADERS)
        assert current.status_code == 200, current.text
        assert current.json()["historical"] is True
        assert current.json()["capabilities"] == {"read": True, "retry": False, "review": False}


def test_corrupt_retained_report_fails_closed_without_exposing_unverified_history(review, monkeypatch):
    assert post(review, [choice(review)])["applied"] == 1
    saved = review.repository.get(review.scope, review.record["specimen_id"])
    report_ref = saved.run.dependencies[REPORT_KEY]["blob_ref"]
    get_bounded = review.blobs.get_bounded

    def altered_report(ref, bound):
        raw = get_bounded(ref, bound)
        return raw + b" " if ref == report_ref else raw

    monkeypatch.setattr(review.blobs, "get_bounded", altered_report)
    response = review.client.get(research_base(review) + "/current", headers=HEADERS)
    assert response.status_code == 503
    assert response.json() == {"detail": "research_service_unavailable"}


def test_saved_research_reopens_as_explicit_read_only_history_and_rejects_retry(review):
    result = post(review, [choice(review)])
    assert result["applied"] == 1, result
    base = research_base(review)
    current = review.client.get(base + "/current", headers=HEADERS)
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["historical"] is True
    assert body["canonical_revision"] == review.record["revision"]
    assert body["review_saved_revision"] == review.record["revision"] + 1
    assert body["capabilities"] == {"read": True, "retry": False, "review": False}
    thread_url = base + "/jobs/offline-review/generations/1"
    thread = review.client.get(thread_url + "/thread", headers=HEADERS)
    assert thread.status_code == 200, thread.text
    assert thread.json()["historical"] is True
    assert all(field["actions"] == [] for field in thread.json()["fields"])
    choices = [candidate for field in thread.json()["fields"] if field["review"]
        for candidate in field["review"]["candidates"]]
    assert choices and all(candidate["selection_id"] is None for candidate in choices)
    retry = review.client.post(thread_url + "/fields/country/retry", headers=HEADERS,
        json={"expected_checkpoint_revision": 1})
    assert retry.status_code == 409, retry.text


def test_historical_discovery_keeps_source_proof_and_names_the_current_saved_host(review):
    source = review.client.get(research_base(review) + "/current", headers=HEADERS)
    assert source.status_code == 200, source.text
    source_identity = source.json()["canonical"]
    assert post(review, [choice(review)])["applied"] == 1

    current = reopen(review)
    for step in range(2):
        response = review.client.get(research_base(review) + "/current", headers=HEADERS)
        assert response.status_code == 200, response.text
        history = response.json()
        assert history["historical"] is True
        assert history["canonical"] == source_identity
        assert history["canonical_revision"] == source_identity["record_revision"]
        assert history["review_saved_revision"] == source_identity["record_revision"] + 1
        assert history["current_host"] == {
            "organization_id": review.scope.organization_id,
            "collection_id": review.scope.collection_id,
            "specimen_id": current["specimen_id"],
            "canonical_run_id": current["active_run_id"],
            "record_revision": current["revision"],
            "host_record_version_id": current["record_version_id"],
            "sensitive": current["asset"].get("sensitive", True),
        }
        assert history["capabilities"] == {"read": True, "retry": False, "review": False}
        thread = current_thread(review)
        assert thread.status_code == 200 and thread.json()["historical"] is True
        assert all(not field["actions"] for field in thread.json()["fields"])
        if step == 0:
            current, _ = post_ordinary_field(review, current)


@pytest.mark.parametrize("damage", ["scope", "run", "source_revision", "source_host", "sensitive", "saved_revision", "token"])
def test_historical_discovery_rejects_retained_identity_or_revision_damage(review, monkeypatch, damage):
    assert post(review, [choice(review)])["applied"] == 1
    saved = review.repository.get(review.scope, review.record["specimen_id"])
    metadata = saved.run.dependencies[REPORT_KEY]
    payload = json.loads(review.blobs.get(metadata["blob_ref"]))
    if damage == "scope":
        payload["canonical"]["collection_id"] = str(uuid4())
    elif damage == "run":
        payload["canonical"]["canonical_run_id"] = str(uuid4())
    elif damage == "source_revision":
        payload["canonical"]["record_revision"] += 1
    elif damage == "source_host":
        payload["canonical"]["host_record_version_id"] = "old-run:1"
    elif damage == "sensitive":
        payload["canonical"]["sensitive"] = not payload["canonical"]["sensitive"]
    elif damage == "saved_revision":
        metadata["review_saved_revision"] += 1
        payload["thread"]["review_saved_revision"] += 1
    else:
        country = next(field for field in payload["thread"]["fields"] if field["field_key"] == "country")
        country["review"]["candidates"][0]["selection_id"] = "a" * 64
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    metadata.update(blob_ref=review.blobs.put(raw), sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw))
    original_get = review.repository.get
    monkeypatch.setattr(review.repository, "get", lambda scope, ident:
        saved if scope == saved.scope and ident == saved.id else original_get(scope, ident))

    response = review.client.get(research_base(review) + "/current", headers=HEADERS)
    assert response.status_code == 503, response.text
    assert response.json() == {"detail": "research_service_unavailable"}


@pytest.mark.parametrize("access_change", ["membership", "sensitive"])
def test_retained_historical_report_still_obeys_current_acl(review, access_change):
    assert post(review, [choice(review)])["applied"] == 1
    if access_change == "membership":
        review.access.member = False
    else:
        review.access.sensitive = False
    base = research_base(review)
    for suffix in ("/current", "/jobs/offline-review/generations/1/thread"):
        response = review.client.get(base + suffix, headers=HEADERS)
        assert response.status_code == 403, response.text
        assert response.json() == {"detail": "research_access_denied"}


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_candidate_save_requires_genuine_reviewer_role(review, role):
    review.access.role = role
    result = post(review, [choice(review)])
    assert result["applied"] == 0
    assert result["results"][0]["error"]["status"] == 403
    assert reopen(review)["revision"] == review.record["revision"]


@pytest.mark.parametrize("failure", ["partial_projection", "lost_ack"])
def test_candidate_replay_reenters_repository_save_to_recover_incomplete_transport(review, monkeypatch, failure):
    # Exercise the API's re-entry into the real canonical receipt path. The
    # incomplete projection/transport is deliberately simulated here; native
    # projection proof belongs to the production adapter's separate tests.
    save = review.repository.save
    attempts, projected = [], {}

    def interrupted_save(principal, pending, expected, key, request_digest):
        committed = save(principal, pending, expected, key, request_digest)
        if key.startswith("research-review:"):
            attempts.append((expected, key, request_digest, committed.version))
            events = [event for event in committed.audit if event.action == "review_research_candidate"]
            if len(attempts) == 1:
                projected[events[0].id] = events[0].model_dump(mode="json")
                if failure == "lost_ack":
                    raise ConnectionError("offline transport lost the committed reply")
            else:
                projected.update({event.id: event.model_dump(mode="json") for event in events})
        return committed

    monkeypatch.setattr(review.repository, "save", interrupted_save)
    entries = [choice(review), choice(review, "province_state")]
    first = post(review, entries)
    if failure == "lost_ack":
        assert (first["applied"], first["refused"], first["skipped"]) == (0, 1, 1)
        assert first["results"][0]["error"]["status"] == 503
    else:
        assert first["applied"] == 2
    saved_before_retry = reopen(review)
    assert saved_before_retry["revision"] == review.record["revision"] + 1
    assert len(projected) == 1

    retry = post(review, entries)

    assert (retry["applied"], retry["refused"], retry["skipped"]) == (2, 0, 0), retry
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert {row["revision"] for row in retry["results"]} == {saved_before_retry["revision"]}
    saved_after_retry = reopen(review)
    assert saved_after_retry["revision"] == saved_before_retry["revision"]
    original_events = {event["id"]: event for event in saved_before_retry["decisions"]
        if event["action"] == "review_research_candidate"}
    assert projected == original_events
    assert saved_after_retry["decisions"] == saved_before_retry["decisions"]


def post_ordinary_field(review, current, field="country", request_key="later-field-edit"):
    # The reviewer explicitly restores the original retained reading, with its
    # actual original evidence ids, rather than supplying source provenance.
    value = dict(review.record["fields"][field])
    value.pop("value_state", None)
    evidence_ids = value.pop("evidence_ids")
    value["reason"] = "Reviewer restores the original supported reading"
    entry = {"expected_revision": current["revision"],
        "base_record_version_id": current["record_version_id"],
        "kind": "field", "target_id": field, "after": value,
        "evidence_ids": evidence_ids, "reason": REASON}
    response = review.client.post(PREFIX + f"/specimens/{review.record['specimen_id']}/decisions",
        headers=dict(HEADERS, **{"Idempotency-Key": request_key}), json=entry)
    assert response.status_code == 200, response.text
    return response.json(), evidence_ids


def test_later_explicit_field_edit_supersedes_marker_and_audits_real_field_evidence(review):
    assert post(review, [choice(review), choice(review, "province_state")])["applied"] == 2
    selected = reopen(review)
    report = selected["run"]["dependencies"][REPORT_KEY]
    retained_report_bytes = review.blobs.get(report["blob_ref"])
    prior_events = [event for event in selected["decisions"] if event["action"] == "review_research_candidate"]

    edited, evidence_ids = post_ordinary_field(review, selected)

    assert edited["revision"] == selected["revision"] + 1
    assert set(edited["run"]["dependencies"]["human_review_field_locks"]) == {"province_state"}
    assert edited["fields"]["country"]["literal"] == review.record["fields"]["country"]["literal"]
    assert edited["fields"]["country"]["evidence_ids"] == evidence_ids
    latest = [event for event in edited["decisions"] if event["action"] == "review_field"][-1]
    assert latest["after"]["field_key"] == "country"
    assert latest["after"]["evidence_ids"] == evidence_ids
    assert latest["after"]["superseded_research_selection_id"] == review.research.candidates["country"].selection_id
    assert edited["run"]["dependencies"][REPORT_KEY] == report
    assert review.blobs.get(report["blob_ref"]) == retained_report_bytes
    assert [event for event in edited["decisions"] if event["action"] == "review_research_candidate"] == prior_events


def test_candidate_replay_after_later_save_returns_original_immutable_result(review):
    entry = choice(review)
    entry.pop("specimen_id")
    entry["reason"] = REASON
    url = PREFIX + f"/specimens/{review.record['specimen_id']}/decisions"
    headers = dict(HEADERS, **{"Idempotency-Key": "original-candidate-choice"})
    first = review.client.post(url, headers=headers, json=entry)
    assert first.status_code == 200, first.text
    original_result = first.json()
    later, _ = post_ordinary_field(review, original_result)
    assert later["revision"] == original_result["revision"] + 1
    assert later["fields"]["country"]["normalized"] != "Philippines"

    replay = review.client.post(url, headers=headers, json=entry)

    assert replay.status_code == 200, replay.text
    assert replay.json() == original_result
    current = reopen(review)
    assert current["revision"] == later["revision"]
    assert current["fields"]["country"] == later["fields"]["country"]
    assert not current["run"]["dependencies"].get("human_review_field_locks")


def test_transcription_edit_clears_source_dependent_markers_preserving_report_and_choice_audit(review):
    assert post(review, [choice(review), choice(review, "province_state")])["applied"] == 2
    selected = reopen(review)
    report = selected["run"]["dependencies"][REPORT_KEY]
    prior_events = [event for event in selected["decisions"] if event["action"] == "review_research_candidate"]
    transcript = selected["run"]["transcripts"][0]
    corrected_text = transcript["text"] + "\nExplicit reviewer transcription correction"
    response = review.client.post(PREFIX + f"/specimens/{review.record['specimen_id']}/decisions",
        headers=dict(HEADERS, **{"Idempotency-Key": "later-transcription-edit"}),
        json={"expected_revision": selected["revision"],
            "base_record_version_id": selected["record_version_id"], "reason": REASON,
            "kind": "transcription", "target_id": transcript["region_id"],
            "after": {"text": corrected_text, "state": "supported"}})
    assert response.status_code == 200, response.text
    saved = reopen(review)
    assert saved["revision"] == selected["revision"] + 1
    assert not saved["run"]["dependencies"].get("human_review_field_locks")
    assert saved["run"]["dependencies"][REPORT_KEY] == report
    assert [event for event in saved["decisions"] if event["action"] == "review_research_candidate"] == prior_events
    latest = [event for event in saved["decisions"] if event["action"] == "review_transcription"][-1]
    assert latest["after"]["region_id"] == transcript["region_id"]
    assert latest["after"]["superseded_research_fields"] == ["country", "province_state"]
    assert next(item for item in saved["run"]["transcripts"] if item["region_id"] == transcript["region_id"])["text"] == corrected_text
    historical = review.client.get(research_base(review) + "/current", headers=HEADERS)
    assert historical.status_code == 200, historical.text
    assert historical.json()["historical"] is True
    assert historical.json()["human_locked_fields"] == []


def test_reprocess_cannot_discard_human_candidate_markers_and_is_not_advertised(review):
    assert post(review, [choice(review)])["applied"] == 1
    selected = reopen(review)
    assert "reprocess" not in selected["available_actions"]
    response = review.client.post(PREFIX + f"/runs/{selected['active_run_id']}/actions",
        headers=dict(HEADERS, **{"Idempotency-Key": "reprocess-refused"}),
        json={"expected_revision": selected["revision"], "reason": REASON, "action": "reprocess"})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "revision_or_idempotency_conflict"
    unchanged = reopen(review)
    assert unchanged["revision"] == selected["revision"]
    assert unchanged["run"] == selected["run"]


@pytest.mark.parametrize("kind,field_key", [
    ("authority_resolution", "country"), ("taxonomy_resolution", "taxon"),
])
def test_explicit_authority_choice_supersedes_prior_research_marker_and_audits_evidence(review, kind, field_key):
    import hashlib

    from specimen_digitization.application.authority_registry import AuthorityCandidate, AuthorityResult
    from specimen_digitization.application.domain import AuditEvent, Principal

    specimen = review.repository.get(review.scope, review.record["specimen_id"])
    field = specimen.run.fields[field_key]
    prior_selection_id = "a" * 64
    # Seed only the prior-choice state for this legacy-endpoint regression.
    # The existing processed specimen supplies genuine retained field evidence.
    specimen.run.dependencies["human_review_field_locks"] = {
        field_key: {"selection_id": prior_selection_id, "evidence_id": field.evidence_ids[0]},
        "province_state": {"selection_id": "b" * 64,
            "evidence_id": specimen.run.fields["province_state"].evidence_ids[0]},
    }
    specimen.audit.append(AuditEvent(actor="synthetic-reviewer", action="review_research_candidate",
        reason="Offline prior-choice fixture", after={"field_key": field_key,
            "selection_id": prior_selection_id, "evidence_ids": list(field.evidence_ids)}))
    if kind == "authority_resolution":
        identifier, value = "fixture:country:2", "Retained synthetic country"
        raw = json.dumps({"identifier": identifier, "name": value}).encode()
        result = AuthorityResult(source_id="fixture-authority", source_version="1",
            adapter_version="fixture-v1", operation="retained_lookup", status="ambiguous",
            literal=field.literal, evidence_ids=tuple(field.evidence_ids), query_json="{}",
            input_sha256=hashlib.sha256(b"{}").hexdigest(), retrieved_at="2026-10-04T00:00:00Z",
            candidates=(AuthorityCandidate(identifier=identifier, name=value, source_version="1",
                relation="unresolved", reason="Retained fixture choice", evidence_ids=tuple(field.evidence_ids)),),
            raw_ref=review.blobs.put(raw), response_sha256=hashlib.sha256(raw).hexdigest())
        artifact = result.model_dump_json().encode()
        specimen.run.authority_results["fixture-country"] = {"tool_id": "fixture-geography",
            "field_key": field_key, "source_id": result.source_id, "status": result.status.value,
            "blob_ref": review.blobs.put(artifact), "sha256": hashlib.sha256(artifact).hexdigest()}
        after = {"tool_id": "fixture-geography", "identifier": identifier}
    else:
        candidate = specimen.run.lookups[-1].candidates[0]
        identifier, value = candidate["key"], candidate["scientificName"]
        after = {"authority_id": identifier}
    seeded = review.repository.save(Principal(user_id="synthetic-reviewer", scope=review.scope, role="reviewer"),
        specimen, specimen.version, "prior-marker-fixture", digest(kind))

    response = review.client.post(PREFIX + f"/specimens/{seeded.id}/decisions",
        headers=dict(HEADERS, **{"Idempotency-Key": "explicit-authority-supersession"}),
        json={"expected_revision": seeded.version, "base_record_version_id": f"{seeded.run.id}:{seeded.version}",
            "kind": kind, "target_id": field_key, "after": after, "reason": REASON})

    assert response.status_code == 200, response.text
    saved = reopen(review)
    assert set(saved["run"]["dependencies"]["human_review_field_locks"]) == {"province_state"}
    materialized = saved["fields"][field_key]
    assert materialized["normalized"] == value and materialized["authority_id"] == identifier
    event = [event for event in saved["decisions"] if event["action"] == "review_" + kind][-1]
    assert event["after"]["field_key"] == field_key
    assert event["after"]["value"] == value and event["after"]["authority_id"] == identifier
    assert event["after"]["evidence_ids"] == materialized["evidence_ids"]
    assert event["after"]["superseded_research_selection_id"] == prior_selection_id
    evidence = {item["id"]: item for item in saved["evidence"]}
    selected = [evidence[ident] for ident in event["after"]["evidence_ids"]
        if evidence[ident]["kind"] == "authority_selection"]
    assert selected and selected[-1]["locator"] == "candidate:" + identifier


def test_internally_consistent_other_rule_cannot_be_accepted(derived_review, monkeypatch):
    from specimen_digitization.research_harness import derivation_contracts

    monkeypatch.setattr(derivation_contracts, "DERIVATION_RULE_VERSION", "retrospective-georeferencing-next")
    before = derived_review.case.current.model_dump(mode="json")
    with pytest.raises(ValueError):
        derived_review.load()
    assert derived_review.case.current.model_dump(mode="json") == before


def test_derived_acceptance_requires_intact_original_capture_bytes(derived_review):
    class CorruptCapture:
        def get(self, reference):
            return derived_review.capture_blobs.get(reference) + b"corrupt"

    before = derived_review.case.current.model_dump(mode="json")
    with pytest.raises(ValueError, match="retained_spatial_derivation_capture_unproved"):
        derived_review.load(capture_blobs=CorruptCapture())
    assert derived_review.case.current.model_dump(mode="json") == before
