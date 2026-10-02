"""Focused additional boundary checks after the initial regression repairs."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from specimen_digitization.research_harness.contracts import FieldKey, SpecialistRequest, SpecialistRole, WorkState
from specimen_digitization.research_harness.engine import ResearchEngine
from specimen_digitization.research_harness.journal import DurableResearchJournal
from test_research_harness_boundaries import admitted, resolved, waiting


def test_journal_revalidates_role_ownership_even_for_model_copy_request(tmp_path):
    _, _, requests, journal, settings = admitted(tmp_path)
    request = requests[SpecialistRole.TAXONOMY].model_copy(update={"field_keys":(FieldKey.COUNTRY,)})
    # Establish that this is an invalid envelope, not an unsupported valid role.
    with pytest.raises(ValidationError):
        SpecialistRequest.model_validate(request.model_dump(mode="json"))
    with pytest.raises((ValueError, PermissionError), match="Specialist|field|role|coverage"):
        asyncio.run(journal.commit(request, (waiting(FieldKey.COUNTRY),),
            receipt_ids=(), model_settings_digest=settings))


def test_two_same_revision_engine_runs_cannot_replace_a_newly_settled_field(tmp_path):
    profile, scope, requests, original, settings = admitted(tmp_path)
    request = requests[SpecialistRole.GEOGRAPHY].model_copy(update={"field_keys":(FieldKey.COUNTRY,)})

    async def exercise():
        first_started, second_started = asyncio.Event(), asyncio.Event()
        release_first, first_committed = asyncio.Event(), asyncio.Event()
        started = []

        class ObservedJournal(DurableResearchJournal):
            async def commit(self, request, resolutions, **kwargs):
                saved = await super().commit(request, resolutions, **kwargs)
                if resolutions[0].value.normalized == "First accepted value":
                    first_committed.set()
                return saved

        journal = ObservedJournal(original.store, original.scope, original.lease)

        class Harness:
            async def run_specialist(self, _role):
                index = len(started)
                started.append(index)
                if index == 0:
                    first_started.set()
                    await release_first.wait()
                    text = "First accepted value"
                else:
                    second_started.set()
                    await first_committed.wait()
                    text = "Late stale value"
                return SimpleNamespace(resolutions=(resolved(FieldKey.COUNTRY, text),),
                    source_results=(), model_effect_ids=())

        def engine():
            return ResearchEngine(profile=profile, requests={request.role:request},
                journal=journal, harness_factory=lambda _selected:Harness(),
                model_settings_digest=settings, validate=lambda _request, resolution, _sources:resolution)

        first = asyncio.create_task(engine().run())
        await asyncio.wait_for(first_started.wait(), timeout=5)
        second = asyncio.create_task(engine().run())
        began = asyncio.create_task(second_started.wait())
        # Permit either safe implementation: fence a second investigation at
        # admission or let it finish but reject its now-stale commit. A small
        # bounded wait also permits serialization before any second dispatch.
        await asyncio.wait((began, second), timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
        release_first.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
        began.cancel()
        persisted, = await journal.load(scope)
        assert persisted.resolution.value.normalized == "First accepted value"
        assert persisted.revision == 1

    asyncio.run(exercise())
