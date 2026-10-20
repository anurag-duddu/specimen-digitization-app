"""Optional monthly budget caps per organization and collection (TENANT_BUDGETS.md).

The lab is test_lane_costs.py's: the published profile's allowance and stage
reservations, readers that report their tokens, and the program's ledger in a
SQLite store. The store here also holds caps, as SqlConnectRepository.tenant_caps
returns them, and records every document it reads or writes.
"""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application import tenant_budget
from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT, create_app
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger
from specimen_digitization.application.lane_allowance import reserve_step as reserve_program
from specimen_digitization.application.lane_costs import record_model_usage, record_refused, settle_step
from specimen_digitization.application.profile_runtime import published_risk_registry
from specimen_digitization.application.storage import Conflict, LocalBlobs, Missing
from specimen_digitization.application.tenant_budget import (
    EXHAUSTED, ORGANIZATION, RECORD, UNAVAILABLE, TenantLedger, cap_positions, ledger_ident, month_of,
)
from specimen_digitization.application.workflow import LOST_READING

from test_lane_costs import QWEN, SCOPE, TokenAdapters, priced_registry, priced_run, seed_synthetic_ledger
from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER
from test_lane_trigger import RecordingDispatcher, action, intake, specimen_with

MOMENT = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
MONTH = "2026-10"
PARENT = "00000000-0000-4000-8000-0000000000a1"
SIBLING = "00000000-0000-4000-8000-0000000000a2"
TREE = [{"id": PARENT, "parent_id": None}, {"id": SYNTHETIC_COLLECTION, "parent_id": PARENT},
    {"id": SIBLING, "parent_id": PARENT}]
PRINCIPAL = Principal(user_id=USER, scope=SCOPE, role="reviewer")
# What the lab's paid steps hold once its run reaches parse (test_lane_costs.py):
# SAM 3's whole reservation (no instance report) and the two readings' costs.
SEGMENT = 164_121
LAB_TOTAL = SEGMENT + 550 + 900


class Capped(NonSensitiveMember):
    """A SQLite store that also holds caps, and records each document call."""

    def __init__(self, path, caps=(), collections=None, broken=None):
        super().__init__(path)
        self.caps = list(caps)
        self.collections = TREE if collections is None else collections
        self.broken = broken
        self.cap_reads = 0
        self.touched = []

    def tenant_caps(self, scope):
        self.cap_reads += 1
        assert scope == SCOPE  # Read as the actor in the run's own collection.
        if self.broken is not None:
            raise self.broken
        return {"caps": [{"collection_key": key, "monthly_cap_micros": micros} for key, micros in self.caps],
            "collections": self.collections}

    def document(self, scope, kind, ident):
        self.touched.append(("read", kind, ident))
        return super().document(scope, kind, ident)

    def put_document(self, scope, kind, ident, payload, expected):
        self.touched.append(("write", kind, ident))
        return super().put_document(scope, kind, ident, payload, expected)


class Counting(TokenAdapters):
    def __init__(self, *args):
        super().__init__(*args)
        self.segments = 0

    def segment(self, specimen):
        self.segments += 1
        return super().segment(specimen)


def without_allowance(registry):
    profiles = tuple(profile.model_copy(update={"processing": profile.processing.model_copy(
        update={"program_allowance": None})}) if profile.processing else profile for profile in registry.profiles)
    return registry.model_copy(update={"profiles": profiles})


def lab(tmp_path, repository=None, *, allowance=True, program_total=0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    blobs = LocalBlobs(tmp_path / "blobs")
    repository = repository if repository is not None else Capped(tmp_path / "state.sqlite3")
    if allowance:
        seed_synthetic_ledger(repository, program_total)
    app = create_app(
        mode="emulator", repository=repository, blobs=blobs, adapters=Counting(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check: USER,
        memberships=lambda user: [{"organization_id": SYNTHETIC_ORG, "collection_id": SYNTHETIC_COLLECTION,
            "role": "reviewer", "can_view_sensitive": True}],
        profile_registry=priced_registry() if allowance else without_allowance(priced_registry()),
        risk_registry=published_risk_registry(), worker_dispatcher=RecordingDispatcher(),
    )
    app.state.workflow.clock = lambda: MOMENT
    specimen_id = intake(TestClient(app, raise_server_exceptions=False))["specimen_id"]
    if isinstance(repository, Capped):
        repository.touched.clear()
    return app, specimen_id


def capped(tmp_path, caps, **options):
    return Capped(tmp_path / "state.sqlite3", caps, **options)


def drain(app, specimen_id):
    return app.state.workflow.drain(PRINCIPAL, specimen_id).run


def ledger(repository, key, month=MONTH):
    return TenantLedger(repository, SCOPE, key, month)


def stored(repository, key, month=MONTH):
    """The ledger document as stored; Missing when no reservation created it."""
    return NonSensitiveMember.document(repository, SCOPE, LEDGER_KIND, ledger_ident(SYNTHETIC_ORG, key, month))


def seed(repository, key, total, month=MONTH):
    """The month's reserved and settled spend before this run, as earlier runs left it."""
    NonSensitiveMember.put_document(repository, SCOPE, LEDGER_KIND, ledger_ident(SYNTHETIC_ORG, key, month), {
        "sensitive": False, "organization_id": SYNTHETIC_ORG, "collection_key": key, "month": month,
        "reserved_total_micros": total, "ordinary_effects": {}}, 0)


def program_total(repository):
    return ProgramLedger(repository, SCOPE).read()["reserved_total_micros"]


def tenant_idents(month=MONTH):
    return {ledger_ident(SYNTHETIC_ORG, key, month) for key in (ORGANIZATION, SYNTHETIC_COLLECTION, PARENT, SIBLING)}


def summary(run):
    """What a run did, without its identity and its wall-clock stamps and seconds."""
    def plain(value):
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items() if k not in {"at", "seconds", "active_seconds"}}
        if isinstance(value, list):
            return [plain(v) for v in value]
        return value

    data = run.model_dump(mode="json")
    text = json.dumps(plain({key: data[key] for key in ("stage", "blocker", "disposition", "completed_steps",
        "attempts", "usage", "paid_calls", "program_allowance", "reasons")}))
    for index, region in enumerate(data["regions"]):  # Region ids are random per run.
        text = text.replace(region["id"], f"region-{index}")
    return json.loads(text)


# ---- no cap set: nothing changes -------------------------------------------------

@pytest.mark.parametrize("caps", [(), ((ORGANIZATION, None), (SYNTHETIC_COLLECTION, None))],
    ids=["no_rows", "cleared_rows"])
def test_with_no_cap_set_no_ledger_is_read_or_written_and_the_run_is_unchanged(tmp_path, caps):
    plain_app, plain_id = lab(tmp_path / "plain", NonSensitiveMember(tmp_path / "plain.sqlite3"))
    repository = capped(tmp_path, caps)
    app, specimen_id = lab(tmp_path / "capped", repository)
    before, run = drain(plain_app, plain_id), drain(app, specimen_id)
    assert "parse" in run.completed_steps, run.blocker
    assert summary(run) == summary(before)
    assert run.usage.reserved_cost_micros == LAB_TOTAL == program_total(repository)
    # One caps read per paid reservation, and no tenant ledger read or written.
    assert repository.cap_reads == len({(c["step"], c["attempt"]) for c in run.paid_calls}) > 0
    assert not {ident for _, _, ident in repository.touched} & tenant_idents()
    assert RECORD not in run.dependencies
    for key in (ORGANIZATION, SYNTHETIC_COLLECTION):
        with pytest.raises(Missing):
            stored(repository, key)


def test_with_no_cap_set_not_even_the_runs_record_is_read(tmp_path):
    specimen = specimen_with(priced_run())
    specimen.run.dependencies[RECORD] = "unreadable"
    assert tenant_budget.reserve_step(capped(tmp_path, []), PRINCIPAL, specimen, QWEN, 20_000) is None
    assert tenant_budget.reserve_step(capped(tmp_path, [(ORGANIZATION, 1_000_000)]), PRINCIPAL, specimen, QWEN,
        20_000) == UNAVAILABLE


def test_a_store_that_cannot_hold_caps_reads_none(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    specimen = specimen_with(priced_run())
    assert tenant_budget.read_caps(repository, SCOPE) is None
    assert tenant_budget.reserve_step(repository, PRINCIPAL, specimen, QWEN, 20_000) is None
    assert repository.documents(SCOPE, LEDGER_KIND) == []


# ---- caps that apply block before any call ---------------------------------------

def test_an_organization_cap_the_month_cannot_cover_blocks_before_any_call(tmp_path):
    repository = capped(tmp_path, [(ORGANIZATION, 1_000_000)])
    seed(repository, ORGANIZATION, 1_000_000 - SEGMENT + 1)
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert (run.stage, run.blocker, run.disposition) == ("processing_blocked", EXHAUSTED, None)
    assert app.state.workflow.adapters.segments == 0 and run.paid_calls == []
    # Refused on the read-only check: nothing is held, here or on the program's ledger.
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 1_000_000 - SEGMENT + 1
    assert program_total(repository) == 0 and RECORD not in run.dependencies


def test_a_cap_that_the_reservation_exactly_fills_admits_the_step(tmp_path):
    repository = capped(tmp_path, [(ORGANIZATION, 1_000_000)])
    seed(repository, ORGANIZATION, 1_000_000 - SEGMENT)
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    # SAM 3 fit exactly; the first reading then found nothing left.
    assert app.state.workflow.adapters.segments == 1 and "segment" in run.completed_steps
    assert (run.stage, run.blocker) == ("processing_blocked", EXHAUSTED)
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 1_000_000


def test_a_collection_cap_blocks_the_collections_run(tmp_path):
    repository = capped(tmp_path, [(SYNTHETIC_COLLECTION, SEGMENT - 1)])
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert (run.stage, run.blocker) == ("processing_blocked", EXHAUSTED)
    assert app.state.workflow.adapters.segments == 0
    with pytest.raises(Missing):
        stored(repository, SYNTHETIC_COLLECTION)


def test_a_parent_collections_cap_applies_to_a_childs_run(tmp_path):
    repository = capped(tmp_path, [(PARENT, SEGMENT - 1)])
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert (run.stage, run.blocker) == ("processing_blocked", EXHAUSTED)
    assert app.state.workflow.adapters.segments == 0


def test_a_siblings_cap_does_not_apply(tmp_path):
    repository = capped(tmp_path, [(SIBLING, 1)])
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert "parse" in run.completed_steps, run.blocker
    assert not {ident for _, _, ident in repository.touched} & tenant_idents()


def test_a_tenant_refusal_comes_before_the_program_allowance_and_holds_nothing(tmp_path):
    # Both would refuse: the cap is checked first, and nothing is reserved anywhere.
    repository = capped(tmp_path, [(ORGANIZATION, 1)])
    app, specimen_id = lab(tmp_path, repository, program_total=28_000_000)
    assert drain(app, specimen_id).blocker == EXHAUSTED
    assert program_total(repository) == 28_000_000


def test_the_program_allowance_refusing_parks_no_tenant_hold(tmp_path):
    repository = capped(tmp_path, [(ORGANIZATION, 5_000_000)])
    app, specimen_id = lab(tmp_path, repository, program_total=28_000_000 - 1)
    run = drain(app, specimen_id)
    assert run.blocker == "program_allowance_exhausted"
    # The program ledger was read before any tenant hold: the cap's ledger was never created.
    with pytest.raises(Missing):
        stored(repository, ORGANIZATION)
    assert RECORD not in run.dependencies


# ---- settlement ------------------------------------------------------------------

def test_each_ledger_settles_to_what_the_steps_cost(tmp_path):
    repository = capped(tmp_path, [(ORGANIZATION, 5_000_000), (PARENT, 4_000_000), (SYNTHETIC_COLLECTION, 3_000_000)])
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert "parse" in run.completed_steps, run.blocker
    # Each paid step reserved its worst case on every applicable ledger and settled
    # to its calls' cost; SAM 3's unknown cost stays held in full.
    for key in (ORGANIZATION, PARENT, SYNTHETIC_COLLECTION):
        assert ledger(repository, key).read()["reserved_total_micros"] == LAB_TOTAL == program_total(repository)
    entries = ledger(repository, ORGANIZATION).read()["ordinary_effects"]
    settled = sorted(entry["settled_micros"] for entry in entries.values() if entry["settled_micros"] is not None)
    assert settled == [550, 900] and len(entries) == 3
    records = run.dependencies[RECORD]
    assert set(records) == {f"{c['step']}:{c['attempt']}" for c in run.paid_calls}
    assert all(record == {"month": MONTH, "keys": [ORGANIZATION, SYNTHETIC_COLLECTION, PARENT],
        "ledger_collection": SYNTHETIC_COLLECTION} for record in records.values())


def capped_specimen(repository, cap=1_000_000, clock=lambda: MOMENT):
    """A reading reserved on an organization cap's ledger, as the workflow reserves it."""
    repository.caps = [(ORGANIZATION, cap)]
    run = priced_run()
    specimen = specimen_with(run)
    assert tenant_budget.reserve_step(repository, PRINCIPAL, specimen, QWEN, 20_000, clock) is None
    run.usage.reserved_cost_micros += 20_000
    run.attempts[QWEN] = 1
    run.completed_steps.append(QWEN)
    return specimen


def test_a_refused_call_settles_to_zero(tmp_path):
    repository = capped(tmp_path, [])
    specimen = capped_specimen(repository)
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 20_000
    record_refused(specimen.run, QWEN, "model", route_id="handwriting-qwen", failure_code="rate_limited")
    settle_step(repository, PRINCIPAL, specimen, QWEN, 20_000)
    current = ledger(repository, ORGANIZATION).read()
    assert current["reserved_total_micros"] == 0
    assert [entry["settled_micros"] for entry in current["ordinary_effects"].values()] == [0]


def test_reservation_and_settlement_replay_exactly_once(tmp_path):
    repository = capped(tmp_path, [])
    specimen = capped_specimen(repository)
    run = specimen.run
    # A worker that stopped before saving its intent reserves the same attempt again.
    run.attempts[QWEN] = 0
    assert tenant_budget.reserve_step(repository, PRINCIPAL, specimen, QWEN, 20_000, lambda: MOMENT) is None
    run.attempts[QWEN] = 1
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 20_000
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    settle_step(repository, PRINCIPAL, specimen, QWEN, 20_000)
    settle_step(repository, PRINCIPAL, specimen, QWEN, 20_000)
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 550
    key = ProgramLedger._ordinary_key(specimen.id, run.id, QWEN, 1)
    one = ledger(repository, ORGANIZATION)
    # A different amount for a settled attempt, or a different reservation, changes nothing.
    assert one.settle(20_000, 600, specimen_id=specimen.id, run_id=run.id, step=QWEN, attempt=1) is None
    assert one.reserve(1_000_000, 30_000, specimen_id=specimen.id, run_id=run.id, step=QWEN,
        attempt=1).issue == UNAVAILABLE
    assert one.read()["reserved_total_micros"] == 550 and one.settled(key, 20_000) == 550


def test_a_cost_above_its_reservation_counts_in_full(tmp_path):
    repository = capped(tmp_path, [])
    specimen = capped_specimen(repository)
    record_model_usage(specimen.run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500,
        billed_micros=25_000)
    settle_step(repository, PRINCIPAL, specimen, QWEN, 20_000)
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 25_000


def test_a_refusal_after_the_check_keeps_its_holds_and_the_attempt_replays_them(tmp_path, monkeypatch):
    # Another worker fills the collection's ledger between this one's check and
    # its reservation: the organization's hold stays, on the run's record.
    repository = capped(tmp_path, [(ORGANIZATION, 1_000_000), (SYNTHETIC_COLLECTION, 30_000)])
    seed(repository, SYNTHETIC_COLLECTION, 20_000)
    monkeypatch.setattr(TenantLedger, "admits", lambda self, cap, micros, key: None)
    run = priced_run()
    specimen = specimen_with(run)
    clock = lambda: MOMENT
    assert tenant_budget.reserve_step(repository, PRINCIPAL, specimen, QWEN, 20_000, clock) == EXHAUSTED
    assert run.dependencies[RECORD][f"{QWEN}:1"]["keys"] == [ORGANIZATION]
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 20_000
    # Once the cap allows it, the same attempt holds once on each ledger.
    repository.caps = [(ORGANIZATION, 1_000_000), (SYNTHETIC_COLLECTION, 40_000)]
    assert tenant_budget.reserve_step(repository, PRINCIPAL, specimen, QWEN, 20_000, clock) is None
    assert run.dependencies[RECORD][f"{QWEN}:1"]["keys"] == [ORGANIZATION, SYNTHETIC_COLLECTION]
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == 20_000
    assert ledger(repository, SYNTHETIC_COLLECTION).read()["reserved_total_micros"] == 40_000


def test_a_cap_changed_while_an_attempt_is_held_keeps_the_hold_readable(tmp_path):
    repository = capped(tmp_path, [])
    specimen = capped_specimen(repository)
    run = specimen.run
    one = ledger(repository, ORGANIZATION)
    # The cap is lowered below what the month holds: the hold replays (as over
    # the cap), and settles, rather than becoming unreadable.
    replay = one.reserve(10_000, 20_000, specimen_id=specimen.id, run_id=run.id, step=QWEN, attempt=1)
    assert (replay.issue, replay.held) == (EXHAUSTED, True)
    # Settlement reads the run's record, never the caps: a cap removed or
    # unreadable since does not keep the hold.
    repository.broken = Conflict("caps unreadable")
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    settle_step(repository, PRINCIPAL, specimen, QWEN, 20_000)
    assert one.read()["reserved_total_micros"] == 550


def test_a_reservation_in_october_settles_on_octobers_ledger_in_november(tmp_path):
    repository = capped(tmp_path, [])
    late = datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)
    specimen = capped_specimen(repository, clock=lambda: late)
    run = specimen.run
    assert run.dependencies[RECORD][f"{QWEN}:1"]["month"] == "2026-10"
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    settle_step(repository, PRINCIPAL, specimen, QWEN, 20_000,
        clock=lambda: datetime(2026, 11, 1, 0, 0, 1, tzinfo=timezone.utc))
    assert ledger(repository, ORGANIZATION, "2026-10").read()["reserved_total_micros"] == 550
    with pytest.raises(Missing):
        stored(repository, ORGANIZATION, "2026-11")
    # A new reservation in November opens November's ledger at zero.
    run.attempts[QWEN] = 1
    november = lambda: datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert tenant_budget.reserve_step(repository, PRINCIPAL, specimen, QWEN, 20_000, november) is None
    assert ledger(repository, ORGANIZATION, "2026-11").read()["reserved_total_micros"] == 20_000


def test_the_month_is_the_utc_month():
    from datetime import timedelta

    chicago = timezone(timedelta(hours=-5))
    assert month_of(datetime(2026, 10, 31, 20, 30, tzinfo=chicago)) == "2026-11"
    assert month_of(datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)) == "2026-11"
    assert month_of(datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)) == "2026-10"


# ---- compare-and-set ---------------------------------------------------------------

class Contended(Capped):
    """Another worker creates or advances the ledger between this one's read and write."""

    def __init__(self, *args, times=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.times = times

    def put_document(self, scope, kind, ident, payload, expected):
        if kind == LEDGER_KIND and payload.get("collection_key") and self.times:
            self.times -= 1
            NonSensitiveMember.put_document(self, scope, kind, ident, {
                "sensitive": False, "organization_id": SYNTHETIC_ORG, "collection_key": payload["collection_key"],
                "month": payload["month"], "reserved_total_micros": 1_000 * (expected + 1),
                "ordinary_effects": {}}, expected)
            raise Conflict("Stale document revision")
        return super().put_document(scope, kind, ident, payload, expected)


def test_a_concurrent_create_is_retried_on_a_fresh_read(tmp_path):
    repository = Contended(tmp_path / "state.sqlite3")
    one = ledger(repository, ORGANIZATION)
    reservation = one.reserve(1_000_000, 20_000, specimen_id="s", run_id="r", step=QWEN, attempt=1)
    assert (reservation.issue, reservation.held) == (None, True)
    # The other worker created the month's ledger at 1,000; this reservation is on top.
    assert one.read()["reserved_total_micros"] == 21_000 and one.read()["revision"] == 2


def test_a_ledger_that_keeps_losing_its_compare_and_set_is_unavailable(tmp_path):
    repository = Contended(tmp_path / "state.sqlite3", times=99)
    one = ledger(repository, ORGANIZATION)
    reservation = one.reserve(1_000_000, 20_000, specimen_id="s", run_id="r", step=QWEN, attempt=1)
    assert (reservation.issue, reservation.held) == (UNAVAILABLE, False)
    assert not any(entry for entry in one.read().get("ordinary_effects", {}).values())


def test_a_run_whose_ledger_stays_busy_blocks_unavailable(tmp_path):
    repository = Contended(tmp_path / "state.sqlite3", [(ORGANIZATION, 5_000_000)], times=99)
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert (run.stage, run.blocker) == ("processing_blocked", UNAVAILABLE)
    assert app.state.workflow.adapters.segments == 0 and program_total(repository) == 0


# ---- fail closed ------------------------------------------------------------------

@pytest.mark.parametrize("options", [
    {"broken": Conflict("SQL Connect transaction rejected")},
    {"broken": ValueError("malformed answer")},
    {"caps": [(ORGANIZATION, -1)]},
    {"caps": [(ORGANIZATION, "a lot")]},
    {"caps": [(ORGANIZATION, 5_000_000), (ORGANIZATION, 6_000_000)]},
    {"caps": [("not-a-collection", 5_000_000)]},
    {"caps": [(PARENT, 5_000_000)], "collections": [{"id": SYNTHETIC_COLLECTION, "parent_id": PARENT},
        {"id": PARENT, "parent_id": SYNTHETIC_COLLECTION}]},
    {"caps": [(PARENT, 5_000_000)], "collections": [{"id": PARENT, "parent_id": None}]},
], ids=["refused", "malformed", "negative", "not_a_number", "duplicate", "bad_key", "cycle", "unknown_collection"])
def test_caps_that_cannot_be_read_or_trusted_block_before_any_call(tmp_path, options):
    repository = capped(tmp_path, options.get("caps", ()), collections=options.get("collections"),
        broken=options.get("broken"))
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert (run.stage, run.blocker) == ("processing_blocked", UNAVAILABLE)
    assert app.state.workflow.adapters.segments == 0 and program_total(repository) == 0


def test_a_connector_that_cannot_be_reached_is_not_read_as_no_cap(tmp_path):
    # Like a program ledger read that cannot reach the connector, the step stops
    # before any reservation or call, and the drain ends its execution.
    from specimen_digitization.application.workflow import OperationalBlock

    repository = capped(tmp_path, [], broken=OperationalBlock("sql_connect_unavailable_or_connector_not_published"))
    with pytest.raises(OperationalBlock):
        tenant_budget.reserve_step(repository, PRINCIPAL, specimen_with(priced_run()), QWEN, 20_000)
    assert repository.documents(SCOPE, LEDGER_KIND) == []


def test_an_answer_too_long_to_be_complete_is_unavailable():
    rows = [{"collection_key": ORGANIZATION, "monthly_cap_micros": 1}] + [
        {"collection_key": f"00000000-0000-4000-8000-{n:012x}", "monthly_cap_micros": None} for n in range(1000)]
    with pytest.raises(tenant_budget.TenantBudgetUnavailable):
        tenant_budget.applicable({"caps": rows, "collections": TREE}, SYNTHETIC_COLLECTION)
    assert tenant_budget.applicable({"caps": rows[:1000], "collections": TREE}, SYNTHETIC_COLLECTION) == [
        (ORGANIZATION, 1)]


class ForeignLedger(Capped):
    """The month's ledger was created by another actor (GetDocumentV2's createdBy check)."""

    def document(self, scope, kind, ident):
        if ident in tenant_idents():
            raise Conflict("SQL Connect transaction rejected")
        return super().document(scope, kind, ident)


def test_a_ledger_that_cannot_be_read_blocks_before_any_call(tmp_path):
    repository = ForeignLedger(tmp_path / "state.sqlite3", [(ORGANIZATION, 5_000_000)])
    app, specimen_id = lab(tmp_path, repository)
    run = drain(app, specimen_id)
    assert (run.stage, run.blocker) == ("processing_blocked", UNAVAILABLE)
    assert app.state.workflow.adapters.segments == 0


@pytest.mark.parametrize("field", [{"month": "2026-09"}, {"collection_key": SIBLING},
    {"organization_id": "00000000-0000-4000-8000-0000000000b7"}], ids=["month", "collection", "organization"])
def test_a_ledger_naming_another_tenant_or_month_is_not_trusted(tmp_path, field):
    repository = capped(tmp_path, [(ORGANIZATION, 5_000_000)])
    seed(repository, ORGANIZATION, 0)
    current = stored(repository, ORGANIZATION)
    assert ledger(repository, ORGANIZATION).admits(5_000_000, 1, "key") is None
    NonSensitiveMember.put_document(repository, SCOPE, LEDGER_KIND, ledger_ident(SYNTHETIC_ORG, ORGANIZATION, MONTH),
        {**current, **field}, current["revision"])
    assert ledger(repository, ORGANIZATION).admits(5_000_000, 1, "key") == UNAVAILABLE


# ---- a blocked run is retried like any money block ---------------------------------

def test_a_capped_run_resumes_on_retry_once_the_cap_allows_it(tmp_path):
    repository = capped(tmp_path, [(ORGANIZATION, SEGMENT - 1)])
    app, specimen_id = lab(tmp_path, repository)
    blocked = drain(app, specimen_id)
    assert (blocked.stage, blocked.blocker, blocked.dead_letter) == ("processing_blocked", EXHAUSTED, False)
    # An administrator raises the cap; a person retries the run.
    repository.caps = [(ORGANIZATION, 5_000_000)]
    response = action(TestClient(app, raise_server_exceptions=False), specimen_id, "retry", "cap-raised")
    assert response.status_code == 200, response.text
    resumed = repository.get(SCOPE, specimen_id).run
    assert (resumed.id, resumed.stage, resumed.blocker) == (blocked.id, "pending", None)
    run = drain(app, specimen_id)
    assert "parse" in run.completed_steps, run.blocker
    assert ledger(repository, ORGANIZATION).read()["reserved_total_micros"] == LAB_TOTAL


# ---- lost results ------------------------------------------------------------------

@pytest.mark.parametrize("allowance", [False, True], ids=["caps_only", "with_program_allowance"])
def test_a_reading_settled_before_its_worker_stopped_keeps_that_cost(tmp_path, monkeypatch, allowance):
    from test_lost_reading import drain_days, muse_calls, stopped_after_settling
    from test_reader_failures_recoverable import step_of

    repository = capped(tmp_path, [(ORGANIZATION, 5_000_000)])
    app, specimen_id = lab(tmp_path, repository, allowance=allowance)
    stopped = stopped_after_settling(monkeypatch)
    runs = drain_days(app, PRINCIPAL, specimen_id)
    done = runs[-1]
    step = step_of(done, 1)
    assert stopped and done.stage == "finalized" and done.attempts[step] == 2
    # The stopped worker had settled the cap's ledger: the next one settles the
    # lost attempt at that cost, with or without the program's ledger.
    assert muse_calls(done)[0] == (1, "failed", LOST_READING, "computed")
    assert [c["cost_micros"] for c in done.paid_calls if c["step"] == step][0] == 900
    # drain_days steps a day at a time from today: the months the run reserved in.
    months = {record["month"] for record in done.dependencies[RECORD].values()}
    assert sum(ledger(repository, ORGANIZATION, month).read()["reserved_total_micros"]
        for month in months) == done.usage.reserved_cost_micros
    if allowance:
        assert program_total(repository) == done.usage.reserved_cost_micros


def test_a_lost_reading_the_cap_ledger_did_not_settle_stays_held(tmp_path):
    repository = capped(tmp_path, [])
    specimen = capped_specimen(repository)
    assert tenant_budget.settled_micros(repository, PRINCIPAL, specimen, QWEN, 1, 20_000) is None
    assert tenant_budget.settled_micros(repository, PRINCIPAL, specimen, QWEN, 1, 19_999) is None
    # And a run that reserved on no tenant ledger has nothing to report.
    assert tenant_budget.settled_micros(repository, PRINCIPAL, specimen_with(priced_run()), QWEN, 1, 20_000) is None


# ---- the read-only checks ------------------------------------------------------------

def test_admits_and_remaining_read_the_least_any_cap_has_left(tmp_path):
    repository = capped(tmp_path, [(ORGANIZATION, 1_000_000), (PARENT, 300_000)])
    seed(repository, PARENT, 100_000)
    specimen = specimen_with(priced_run())
    clock = lambda: MOMENT
    assert tenant_budget.remaining(repository, PRINCIPAL, specimen, clock) == 200_000
    assert tenant_budget.admits(repository, PRINCIPAL, specimen, 200_000, clock) is None
    assert tenant_budget.admits(repository, PRINCIPAL, specimen, 200_001, clock) == EXHAUSTED
    repository.broken = Conflict("refused")
    assert tenant_budget.admits(repository, PRINCIPAL, specimen, 1, clock) == UNAVAILABLE
    with pytest.raises(tenant_budget.TenantBudgetUnavailable):
        tenant_budget.remaining(repository, PRINCIPAL, specimen, clock)
    repository.broken, repository.caps = None, []
    assert tenant_budget.remaining(repository, PRINCIPAL, specimen, clock) is None
    assert tenant_budget.admits(repository, PRINCIPAL, specimen, 10**12, clock) is None


# ---- the research broker ("on" mode) -------------------------------------------------

def broker(repository):
    from specimen_digitization.research_harness.program_budget import ProgramEffectBroker

    return ProgramEffectBroker(SimpleNamespace(program_key="program"), None, repository=repository, scope=SCOPE,
        run=priced_run())


def test_the_research_broker_sends_nothing_while_a_cap_applies(tmp_path):
    from specimen_digitization.research_harness.persistence import HeldUnknown

    intent = {"effect_id": "effect", "attempts": [], "reservation_micro_usd": 1_000}
    repository = capped(tmp_path, [(ORGANIZATION, 5_000_000)])
    with pytest.raises(HeldUnknown, match=UNAVAILABLE):
        asyncio.run(broker(repository).before_send(SCOPE, intent))
    repository.caps, repository.broken = [], Conflict("refused")
    with pytest.raises(HeldUnknown, match=UNAVAILABLE):
        asyncio.run(broker(repository).before_send(SCOPE, intent))
    repository.broken = None
    asyncio.run(broker(repository).before_send(SCOPE, intent))  # No cap: as before.
    asyncio.run(broker(NonSensitiveMember(tmp_path / "plain.sqlite3")).before_send(SCOPE, intent))


# ---- the cost meter's positions ------------------------------------------------------

def test_cap_positions_roll_spend_up_the_tree():
    collections = {PARENT: None, SYNTHETIC_COLLECTION: PARENT, SIBLING: PARENT}
    positions = cap_positions({ORGANIZATION: 1_000, PARENT: 500, SIBLING: None, SYNTHETIC_COLLECTION: 50},
        collections, MONTH, {SYNTHETIC_COLLECTION: 120, SIBLING: 30})
    assert positions["organization"] == {"monthly_cap_micros": 1_000, "month": MONTH, "spent_micros": 150,
        "remaining_micros": 850}
    assert positions["collections"][PARENT] == {"monthly_cap_micros": 500, "month": MONTH, "spent_micros": 150,
        "remaining_micros": 350}
    assert positions["collections"][SYNTHETIC_COLLECTION]["remaining_micros"] == 0  # Overspend floors at zero.
    assert positions["collections"][SYNTHETIC_COLLECTION]["spent_micros"] == 120
    assert positions["collections"][SIBLING] is None
    assert cap_positions({}, collections, MONTH, {})["organization"] is None
    with pytest.raises(ValueError):
        cap_positions({}, {PARENT: SIBLING, SIBLING: PARENT}, MONTH, {})
    with pytest.raises(ValueError):
        cap_positions({}, collections, MONTH, {SYNTHETIC_COLLECTION: -1})
