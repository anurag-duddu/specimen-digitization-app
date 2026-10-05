"""A retained canonical commit must precede a freshly bound paid window."""
import asyncio
from types import SimpleNamespace
import pytest

from specimen_digitization.research_harness.native_worker import (
    NativeResearchWorker, NativeResearchWorkerOutcomeV2,
)
from test_production_bridge import RESEARCH_SCOPE, principal


@pytest.mark.parametrize("publication_only", [False, True])
def test_retained_publication_reopens_binding_before_the_next_provider_window(publication_only):
    state = {"revision": 7, "retained": True, "pending": True}
    opened, released, provider_revisions = [], [], []

    class Factory:
        async def retained_publication_locators(self, *_):
            return ()

        async def open(self, *_args, **_kwargs):
            revision = state["revision"]
            opened.append(revision)

            async def run(*, role_limit):
                assert revision == state["revision"]
                provider_revisions.append(revision)
                state["pending"] = False

            return SimpleNamespace(
                binding=SimpleNamespace(research_scope=lambda: RESEARCH_SCOPE),
                scope="scope", lease=revision, role_window=1,
                publication_only=publication_only,
                engine=SimpleNamespace(run=run),
                store=SimpleNamespace(
                    _read=lambda _: SimpleNamespace(state={"outbox": {}}),
                    release=lambda _scope, lease, **_: released.append(lease),
                    job=lambda _: {"fields": {"country": {
                        "work_state": "pending" if state["pending"] else "resolved", "locked": False}}}),
            )

    class Worker(NativeResearchWorker):
        async def _publish_committed(self, *_args, publication_progress=None):
            if state["retained"]:
                state.update(retained=False, revision=8)
                publication_progress.append("retained-receipt")
            return NativeResearchWorkerOutcomeV2(scope=RESEARCH_SCOPE,
                status="pending" if state["pending"] else "completed",
                publication_receipt_ids=("retained-receipt",))

    result = asyncio.run(Worker(Factory()).run_registered(principal(),
        RESEARCH_SCOPE.specimen_id, owner="worker"))
    assert opened == [7, 8] and released == [7, 8]
    assert provider_revisions == ([] if publication_only else [8])
    assert result.status == ("blocked" if publication_only else "completed")
    assert result.reason_code == ("research_program_headroom_unavailable" if publication_only else None)
    assert result.publication_receipt_ids == ("retained-receipt",)
