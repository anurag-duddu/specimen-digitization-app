"""A request that carries hand-over candidates survives the engine's narrowing (review B1 of #265).

``ResearchEngine.run`` re-validates each role's request with ``field_keys`` narrowed to what is left to do: to
the one retried field (``retry_fields``), minus the protected fields (a human decision), and to the fields
still pending. The dump it re-validates keeps every candidate of the role, so the request contract must judge a
candidate by the role's fields, not by the narrowed ``field_keys``. Before the fix the first narrowing raised
a ValidationError out of ``engine.run``, and a role whose fields were retried, protected or partly settled
could not run again (the retry consumer ends such a command ``retry_worker_failed``).

These tests run the real ResearchEngine (the engine's own scheduler tests' journal and harness stand-ins) on
requests built from the real request factory's graph of an abstract label.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/ (the engine tests' stand-ins)

from test_organiser_handover import STORED, FieldSpec, RegionSpec, build  # noqa: E402
from test_research_harness_engine import Harness, Journal, inputs  # noqa: E402

from specimen_digitization.application.domain import FieldValue  # noqa: E402
from specimen_digitization.research_harness.contracts import (  # noqa: E402
    ROLE_FIELDS, FieldKey, FieldResolution, SpecialistRequest, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.engine import ResearchEngine  # noqa: E402
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory  # noqa: E402
from specimen_digitization.research_harness.prompts import resolve_prompt  # noqa: E402

DIGEST = "e" * 64


class RetryJournal(Journal):
    def __init__(self, protected=()):
        super().__init__()
        self.protected = tuple(protected)

    async def retry_eligible(self, scope, field_key):
        return True

    async def protected_fields(self, scope):
        return self.protected


def requests_with_candidates():
    """The six roles' requests from the real graph of a label whose stored values give every role candidates."""
    profile, scope, _ = inputs()
    built = build(fields=(*STORED, FieldSpec("taxon", "Syntheticland"), FieldSpec("date_identified", "12 June 1948")))
    fragments, events, assemblies, evidence, decisions, candidates = NativeGenerationRequestFactory._build_graph(
        built.specimen, scope)
    requests = {}
    for role, keys in ROLE_FIELDS.items():
        requests[role] = SpecialistRequest(scope=scope, role=role, field_keys=keys,
            prompt=resolve_prompt(role, profile_digest=scope.profile_digest, source_registry_digest="b" * 64,
                toolset_digest="c" * 64, model_route="harness-deepseek", output_schema_digest="d" * 64),
            fragments=fragments, events=events, assemblies=assemblies, evidence=evidence,
            accepted_decisions=decisions, organiser_candidates=tuple(c for c in candidates if c.field_key in keys),
            field_revisions={key: 0 for key in keys})
    return profile, requests


def failed(request, keys):
    return tuple(FieldResolution(field_key=key, work_state=WorkState.OPERATIONAL_FAILED, value=FieldValue(),
        reason="specialist_operational_failure") for key in keys)


def engine_for(profile, requests, journal, seen):
    return ResearchEngine(profile=profile, requests=requests, journal=journal,
        harness_factory=lambda selected: Harness(selected, seen),
        validate=lambda request, resolution, sources: resolution, model_settings_digest=DIGEST)


def test_every_role_the_fixture_gives_candidates_has_some():
    profile, requests = requests_with_candidates()
    assert {role for role, request in requests.items() if request.organiser_candidates} == set(SpecialistRole)


@pytest.mark.parametrize(("role", "field"), (
    (SpecialistRole.COLLECTION, FieldKey.HABITAT),
    (SpecialistRole.COLLECTION, FieldKey.VERBATIM_DTS),
    (SpecialistRole.PARTIES, FieldKey.IDENTIFIED_BY_IRN),
    (SpecialistRole.GEOGRAPHY, FieldKey.COUNTY),
    (SpecialistRole.TEMPORAL, FieldKey.DATE_VISITED_TO),
    (SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_TO_M),
    (SpecialistRole.TAXONOMY, FieldKey.TAXON),
))
def test_a_single_field_retry_runs_a_role_whose_request_carries_candidates(role, field):
    """FAILS before the fix: ValidationError out of engine.run, for the retried field of every role that carries a
    candidate for a field other than the retried one."""
    profile, requests = requests_with_candidates()
    journal, seen = RetryJournal(), []
    asyncio.run(journal.commit(requests[role], failed(requests[role], ROLE_FIELDS[role]), receipt_ids=(),
        model_settings_digest=DIGEST))
    handed = []

    def factory(selected):
        handed.append(selected)
        return Harness(selected, seen)
    engine = ResearchEngine(profile=profile, requests=requests, journal=journal, harness_factory=factory,
        validate=lambda request, resolution, sources: resolution, model_settings_digest=DIGEST)
    result = asyncio.run(engine.run(retry_fields=(field,), retry_command_id="a" * 64))
    assert seen == [role] and result.fields[field].work_state == WorkState.WAITING_SOURCE
    [selected] = handed
    narrowed = selected[role]
    # The request the specialist runs holds the one field, and still holds the role's candidates.
    assert narrowed.field_keys == (field,)
    assert narrowed.organiser_candidates == requests[role].organiser_candidates


def test_a_protected_field_narrows_the_request_and_the_role_still_runs():
    profile, requests = requests_with_candidates()
    journal, seen = RetryJournal(protected=(FieldKey.HABITAT, FieldKey.COLLECTORS)), []
    result = asyncio.run(engine_for(profile, requests, journal, seen).run())
    assert SpecialistRole.COLLECTION in seen and SpecialistRole.PARTIES in seen
    assert result.fields[FieldKey.FMNH_INS_NUMBER].work_state == WorkState.WAITING_SOURCE


def test_a_role_with_some_fields_already_settled_runs_for_the_pending_ones():
    """After a partial run only the PENDING fields are asked for again (engine._pending): the narrowed request
    must still validate."""
    profile, requests = requests_with_candidates()
    journal, seen = RetryJournal(), []
    done = FieldResolution(field_key=FieldKey.FMNH_INS_NUMBER, work_state=WorkState.WAITING_SOURCE, value=FieldValue(),
        reason="qualified_source_prerequisite")
    asyncio.run(journal.commit(requests[SpecialistRole.COLLECTION], (done,), receipt_ids=(), model_settings_digest=DIGEST))
    result = asyncio.run(engine_for(profile, requests, journal, seen).run())
    assert SpecialistRole.COLLECTION in seen
    assert result.fields[FieldKey.HABITAT].work_state == WorkState.WAITING_SOURCE


def test_a_candidate_of_another_role_is_still_refused_whatever_the_narrowing():
    profile, requests = requests_with_candidates()
    foreign = next(item for item in requests[SpecialistRole.COLLECTION].organiser_candidates
                   if item.field_key == FieldKey.HABITAT)
    request = requests[SpecialistRole.PARTIES]
    with pytest.raises(ValueError, match="owned field of the role"):
        SpecialistRequest.model_validate({**request.model_dump(mode="json"), "field_keys": (FieldKey.COLLECTORS,),
            "field_revisions": {FieldKey.COLLECTORS: 0}, "organiser_candidates": [*request.model_dump(mode="json")["organiser_candidates"],
                foreign.model_dump(mode="json")]})
