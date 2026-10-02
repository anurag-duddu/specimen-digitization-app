"""Actor lifetime tests exercise await, worker-thread copies, and cancellation."""

import asyncio

import pytest

from specimen_digitization.application.production import actor_uid, verified_actor_context


@pytest.mark.asyncio
async def test_distinct_async_actors_and_worker_threads_never_share_context():
    entered = asyncio.Event()
    count = 0

    async def task(uid):
        nonlocal count
        with verified_actor_context(uid):
            count += 1
            if count == 2:
                entered.set()
            await entered.wait()
            assert actor_uid.get() == uid
            assert await asyncio.to_thread(actor_uid.get) == uid
        assert actor_uid.get() is None

    assert actor_uid.get() is None
    await asyncio.gather(task("actor-one"), task("actor-two"))
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_error_resets_previous_actor_token():
    with verified_actor_context("outer"):
        with pytest.raises(RuntimeError):
            with verified_actor_context("inner"):
                assert await asyncio.to_thread(actor_uid.get) == "inner"
                raise RuntimeError("fixture failure")
        assert actor_uid.get() == "outer"
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_cancel_resets_context_and_late_thread_keeps_original_actor():
    import threading

    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    observed = []
    reset = []

    def read():
        started.set()
        release.wait(timeout=2)
        observed.append(actor_uid.get())
        finished.set()

    async def request():
        try:
            with verified_actor_context("cancelled-actor"):
                await asyncio.to_thread(read)
        finally:
            reset.append(actor_uid.get())

    pending = asyncio.create_task(request())
    try:
        await asyncio.to_thread(started.wait, 2)
        assert started.is_set()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert reset == [None]
        with verified_actor_context("next-actor"):
            assert await asyncio.to_thread(actor_uid.get) == "next-actor"
    finally:
        release.set()
    # Cancellation does not kill a worker thread; observe its completion.
    assert await asyncio.to_thread(finished.wait, 2)
    assert observed == ["cancelled-actor"]
    assert actor_uid.get() is None


@pytest.mark.parametrize("uid", [None, "", 123])
def test_unverified_context_is_rejected(uid):
    with pytest.raises(PermissionError):
        with verified_actor_context(uid):
            pytest.fail("invalid identity must not enter context")
    assert actor_uid.get() is None
