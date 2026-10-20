"""The program ledger's head stays small as paid steps accumulate.

The storage review of 2026-10-20 found one head holding every effect, saved
whole as a version row (SaveDocumentV2) on every charge: 2,003 versions and
197 MB of JSON. Effects past HEAD_EFFECTS now move to archive documents, and
the ledger keeps its invariants across them: a reservation is made once, a
settlement is applied once, and the total changes only with an effect.
"""

import json
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest

from specimen_digitization.application.domain import Scope
from specimen_digitization.application.lane_allowance import (
    ARCHIVE_BATCH,
    HEAD_EFFECTS,
    LEDGER_KIND,
    ORDINARY,
    RESEARCH,
    UNAVAILABLE,
    ProgramLedger,
)
from specimen_digitization.application.storage import Conflict, SQLiteRepository, canonical_json
from specimen_digitization.application.workflow import Workflow

SCOPE = Scope(organization_id="00000000-0000-4000-8000-000000000001", collection_id="insects")
ALLOWANCE = 28_000_000


def ident(name):
    return str(uuid5(NAMESPACE_URL, name))  # Specimen and run ids are UUIDs in production.


def step(i):
    """The i-th paid step: twelve to a run, three runs to a specimen."""
    return {"specimen_id": ident(f"specimen-{i // 36}"), "run_id": ident(f"run-{i // 12}"),
            "step": f"step-{i % 12}", "attempt": 1}


def key(args):
    return canonical_json([args["specimen_id"], args["run_id"], args["step"], args["attempt"]])


class Versioned(SQLiteRepository):
    """The worker's membership (non-sensitive writes only), recording what each
    save stores as a version row in production: the whole document saved."""

    def __init__(self, path):
        super().__init__(path)
        self.versions = []

    def put_document(self, scope, kind, ident, payload, expected):
        if payload.get("sensitive", True) is not False:
            raise Conflict("SQL Connect transaction rejected")
        stored = super().put_document(scope, kind, ident, payload, expected)
        self.versions.append(len(json.dumps(stored, separators=(",", ":"))))
        return stored


def ledger_on(repository, total=0, **effects):
    ledger = ProgramLedger(repository, SCOPE)
    SQLiteRepository.put_document(repository, SCOPE, LEDGER_KIND, ledger.ident,
        {"sensitive": False, "reserved_total_micros": total, **effects}, 0)
    return ledger


def reserve(ledger, i, micros=1_000):
    assert ledger.reserve(ALLOWANCE, micros, **step(i)).issue is None


def charge(ledger, steps):
    for i in range(steps):
        reserve(ledger, i)
        assert ledger.settle(ALLOWANCE, 1_000, 900, **step(i)) is not None


def archive(repository, ledger, family, args_or_key):
    name = args_or_key if isinstance(args_or_key, str) else key(args_or_key)
    return repository.document(SCOPE, LEDGER_KIND, ledger.archive_id(family, name))


HELD = {"reserved_micros": 1_000, "allowance_micros": ALLOWANCE, "settled_micros": None}


def test_ledger_versions_grow_with_paid_steps_not_with_their_square(tmp_path):
    written = {}
    for steps in (100, 400):
        repository = Versioned(tmp_path / f"{steps}.sqlite3")
        ledger = ledger_on(repository)
        charge(ledger, steps)
        assert ledger.read()["reserved_total_micros"] == 900 * steps
        written[steps] = (sum(repository.versions), max(repository.versions))
    # A head keeping every effect makes each save larger than the last: 400
    # steps then store about 16 times what 100 do, and the last save is the
    # whole history (over 70,000 bytes at 400 steps).
    assert written[400][0] < 5 * written[100][0]
    assert max(written[100][1], written[400][1]) < 8_000


def test_an_archived_reservation_is_neither_reserved_again_nor_changed(tmp_path):
    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = ledger_on(repository)
    for i in range(HEAD_EFFECTS + 1):
        reserve(ledger, i)
    head = ledger.read()
    assert head[ORDINARY] == {}
    assert archive(repository, ledger, ORDINARY, step(0))["effect"] == HELD
    assert ledger.reserve(ALLOWANCE, 1_000, **step(0)).issue is None
    assert ledger.reserve(ALLOWANCE, 2_000, **step(0)).issue == UNAVAILABLE
    assert ledger.read()["revision"] == head["revision"]  # Neither call saved the head.
    assert ledger.read()["reserved_total_micros"] == 1_000 * (HEAD_EFFECTS + 1)


def test_an_archived_reservation_settles_exactly_once(tmp_path):
    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = ledger_on(repository)
    for i in range(HEAD_EFFECTS + 1):
        reserve(ledger, i)
    total = 1_000 * (HEAD_EFFECTS + 1)
    assert ledger.settle(ALLOWANCE, 1_000, 400, **step(0))["reserved_total_micros"] == total - 600
    settled = {**HELD, "settled_micros": 400}
    assert ledger.read()[ORDINARY] == {key(step(0)): settled}
    assert ledger.settle(ALLOWANCE, 1_000, 400, **step(0))["reserved_total_micros"] == total - 600
    assert ledger.settle(ALLOWANCE, 1_000, 500, **step(0)) is None
    for i in range(HEAD_EFFECTS + 1, 2 * HEAD_EFFECTS + 1):
        reserve(ledger, i)
    assert ledger.read()[ORDINARY] == {}
    moved = archive(repository, ledger, ORDINARY, step(0))
    assert (moved["effect"], moved["revision"]) == (settled, 2)  # Held, then settled.
    assert ledger.settle(ALLOWANCE, 1_000, 400, **step(0)) is not None
    assert ledger.settle(ALLOWANCE, 1_000, 500, **step(0)) is None
    assert ledger.reserve(ALLOWANCE, 1_000, **step(0)).issue is None
    assert ledger.read()["reserved_total_micros"] == total - 600 + 1_000 * HEAD_EFFECTS


def test_an_archived_research_attempt_replays_and_settles_once(tmp_path):
    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = ledger_on(repository)
    keys = [f"research:research-run:{ident(f'run-{i}')}:effect:1" for i in range(HEAD_EFFECTS + 1)]
    for name in keys:
        ledger.research_effect(ALLOWANCE, name, 5_000)
    # A research charge runs inside its send's lease and never waits on
    # archiving; the next ordinary save archives both families.
    assert len(ledger.read()[RESEARCH]) == HEAD_EFFECTS + 1
    assert len(repository.versions) == HEAD_EFFECTS + 1
    reserve(ledger, 0)
    head = ledger.read()
    assert head[RESEARCH] == head[ORDINARY] == {}
    ledger.research_effect(ALLOWANCE, keys[0], 5_000)
    with pytest.raises(ValueError, match="reservation changed"):
        ledger.research_effect(ALLOWANCE, keys[0], 6_000)
    ledger.research_effect(ALLOWANCE, keys[0], 4_200, settle=True, historical=True)
    ledger.research_effect(ALLOWANCE, keys[0], 4_200, settle=True, historical=True)
    with pytest.raises(ValueError, match="settlement changed"):
        ledger.research_effect(ALLOWANCE, keys[0], 4_300, settle=True)
    after = ledger.read()
    assert after["reserved_total_micros"] == 5_000 * len(keys) + 1_000 - 800
    assert after["revision"] == head["revision"] + 1  # Only the settlement saved the head.
    assert ledger.effect(RESEARCH, keys[0]) == {"micros": 4_200, "status": "settled"}


def test_a_legacy_head_drains_into_archives_keeping_every_effect_and_the_total(tmp_path):
    # The production head of 2026-10-20 held 913 ordinary and 99 research effects.
    ordinary = {key(step(i)): {**HELD, "settled_micros": None if i % 3 else 700} for i in range(913)}
    research = {f"research:research-run:{ident(f'legacy-{i}')}:effect:1":
                {"micros": 2_000, "status": "held" if i % 2 else "settled"} for i in range(99)}
    total = sum(e["settled_micros"] or e["reserved_micros"] for e in ordinary.values()) + 2_000 * 99
    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = ledger_on(repository, total, **{ORDINARY: ordinary, RESEARCH: research})
    charges = 0
    while len(ledger.read()[ORDINARY]) + len(ledger.read()[RESEARCH]) > HEAD_EFFECTS:
        reserve(ledger, 10_000 + charges, micros=1)
        charges += 1
        assert charges <= -(-1_012 // ARCHIVE_BATCH)
    assert ledger.read()["reserved_total_micros"] == total + charges
    for family, effects in ((ORDINARY, ordinary), (RESEARCH, research)):
        for name, effect in effects.items():
            assert ledger.effect(family, name) == effect
    assert repository.versions[-1] < 8_000
    # A legacy hold still settles once; a legacy settlement still replays.
    assert ledger.settle(ALLOWANCE, 1_000, 650, **step(1))["reserved_total_micros"] == total + charges - 350
    assert ledger.settle(ALLOWANCE, 1_000, 650, **step(1)) is not None
    assert ledger.reserve(ALLOWANCE, 1_000, **step(0)).issue is None
    assert ledger.read()["reserved_total_micros"] == total + charges - 350


def test_malformed_effects_stay_in_the_head_without_holding_the_rest_back(tmp_path):
    # More than a batch of them, ahead of every well-formed effect.
    malformed = {key(step(1_000 + i)): "not an envelope" for i in range(ARCHIVE_BATCH + 1)}
    ledger = ledger_on(Versioned(tmp_path / "state.sqlite3"), 0, **{ORDINARY: malformed})
    for i in range(HEAD_EFFECTS + 1):
        reserve(ledger, i)
    assert ledger.read()[ORDINARY] == malformed
    assert ledger.effect(ORDINARY, key(step(0))) == HELD
    assert ledger.reserve(ALLOWANCE, 1_000, **step(1_000)).issue == UNAVAILABLE
    assert ledger.reserve(ALLOWANCE, 1_000, **step(0)).issue is None
    assert ledger.read()["reserved_total_micros"] == 1_000 * (HEAD_EFFECTS + 1)


def test_a_stale_archive_write_cannot_move_an_effect_back(tmp_path):
    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = ledger_on(repository)
    for i in range(HEAD_EFFECTS + 1):
        reserve(ledger, i)
    assert ledger.settle(ALLOWANCE, 1_000, 400, **step(0)) is not None
    settled = ledger.effect(ORDINARY, key(step(0)))
    assert ledger._archive_one(ORDINARY, key(step(0)), settled)
    # A writer that read the head before the settlement, or another amount.
    assert not ledger._archive_one(ORDINARY, key(step(0)), HELD)
    assert not ledger._archive_one(ORDINARY, key(step(0)), {**settled, "settled_micros": 500})
    assert archive(repository, ledger, ORDINARY, step(0))["effect"] == settled


class ArchiveRefused(Versioned):
    def put_document(self, scope, kind, ident, payload, expected):
        if "ledger" in payload:  # Only archives name their ledger.
            raise Conflict("SQL Connect transaction rejected")
        return super().put_document(scope, kind, ident, payload, expected)


def test_an_effect_leaves_the_head_only_once_its_archive_holds_it(tmp_path):
    ledger = ledger_on(ArchiveRefused(tmp_path / "state.sqlite3"))
    charge(ledger, HEAD_EFFECTS + 4)  # Every charge still lands.
    head = ledger.read()
    assert len(head[ORDINARY]) == HEAD_EFFECTS + 4
    assert head["reserved_total_micros"] == 900 * (HEAD_EFFECTS + 4)


class SettledMeanwhile(Versioned):
    """Another worker settles one archived hold before this pass drops it."""

    def __init__(self, path, target):
        super().__init__(path)
        self.target = target

    def put_document(self, scope, kind, ident, payload, expected):
        if self.target and "ledger" not in payload:
            current = self.document(scope, kind, ident)
            if len(payload.get(ORDINARY, {})) < len(current.get(ORDINARY, {})):
                name, self.target = key(self.target), None
                effects = {**current[ORDINARY], name: {**current[ORDINARY][name], "settled_micros": 400}}
                super().put_document(scope, kind, ident, {**current, ORDINARY: effects,
                    "reserved_total_micros": current["reserved_total_micros"] - 600}, current["revision"])
        return super().put_document(scope, kind, ident, payload, expected)


def test_the_head_keeps_an_effect_that_changed_after_it_was_archived(tmp_path):
    repository = SettledMeanwhile(tmp_path / "state.sqlite3", step(3))
    ledger = ledger_on(repository)
    for i in range(HEAD_EFFECTS + 1):
        reserve(ledger, i)
    settled = {**HELD, "settled_micros": 400}
    head = ledger.read()
    assert head[ORDINARY] == {key(step(3)): settled}
    assert head["reserved_total_micros"] == 1_000 * (HEAD_EFFECTS + 1) - 600
    assert archive(repository, ledger, ORDINARY, step(3))["effect"] == HELD  # Behind the head.
    assert ledger.effect(ORDINARY, key(step(3))) == settled
    assert ledger.settle(ALLOWANCE, 1_000, 400, **step(3)) is not None
    assert ledger.read()["reserved_total_micros"] == 1_000 * (HEAD_EFFECTS + 1) - 600


class Racing(Versioned):
    """Another worker reserves the same attempt, archives it and drops it from
    the head while this one reserves: between its head read and its archive
    lookup, or between that lookup and its save."""

    def __init__(self, path, moment, target):
        super().__init__(path)
        self.moment, self.target, self.raced = moment, target, False
        self.rival = ProgramLedger(Versioned(path), SCOPE)

    def race(self):
        self.raced = True
        assert self.rival.reserve(ALLOWANCE, 1_000, **self.target).issue is None
        assert key(self.target) not in self.rival.read()[ORDINARY]

    def document(self, scope, kind, ident):
        if (self.moment == "lookup" and not self.raced
                and ident == self.rival.archive_id(ORDINARY, key(self.target))):
            self.race()
        return super().document(scope, kind, ident)

    def put_document(self, scope, kind, ident, payload, expected):
        if (self.moment == "save" and not self.raced and ident == self.rival.ident
                and key(self.target) in payload.get(ORDINARY, {})):
            self.race()
        return super().put_document(scope, kind, ident, payload, expected)


@pytest.mark.parametrize(("moment", "marked"), [("lookup", True), ("save", True), ("save", False)],
    ids=["lookup", "save", "save_from_an_unmarked_head"])
def test_a_reservation_racing_an_archive_pass_is_charged_once(tmp_path, moment, marked):
    path = tmp_path / "state.sqlite3"
    ledger = ledger_on(Versioned(path))
    if marked:
        for i in range(100, 100 + HEAD_EFFECTS + 1):
            reserve(ledger, i)  # One pass has archived, so the head is marked.
        assert ledger.read()["archives"] is True and ledger.read()[ORDINARY] == {}
    for i in range(1, HEAD_EFFECTS + 1):
        reserve(ledger, i)  # The rival's reservation is the one past HEAD_EFFECTS.
    # Unmarked, this worker reads no archive; the rival's pass marks the head,
    # so this worker's save conflicts and its retry finds the archive.
    assert ("archives" in ledger.read()) is marked
    racing = Racing(path, moment, step(0))
    assert ProgramLedger(racing, SCOPE).reserve(ALLOWANCE, 1_000, **step(0)).issue is None
    assert racing.raced
    earlier = HEAD_EFFECTS + 1 if marked else 0
    assert ledger.read()["reserved_total_micros"] == 1_000 * (earlier + HEAD_EFFECTS + 1)
    assert ledger.effect(ORDINARY, key(step(0))) == HELD


def test_a_head_that_never_archived_reads_no_archive(tmp_path):
    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = ledger_on(repository)
    reads = []
    document = repository.document
    repository.document = lambda scope, kind, ident: reads.append(ident) or document(scope, kind, ident)
    for i in range(HEAD_EFFECTS):
        reserve(ledger, i)
    assert "archives" not in ledger.read()
    assert set(reads) == {ledger.ident}  # Only the head, never an archive.
    reserve(ledger, HEAD_EFFECTS)  # Past the threshold: archived, and the head marked.
    assert ledger.read()["archives"] is True
    reads.clear()
    assert ledger.effect(ORDINARY, key(step(0))) == HELD
    assert reads == [ledger.ident, ledger.archive_id(ORDINARY, key(step(0)))]


def test_a_lost_attempt_settled_before_archiving_is_read_from_its_archive(tmp_path):
    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = ledger_on(repository)
    reserve(ledger, 0)
    assert ledger.settle(ALLOWANCE, 1_000, 400, **step(0)) is not None
    for i in range(1, HEAD_EFFECTS + 1):
        reserve(ledger, i)
    assert key(step(0)) not in ledger.read()[ORDINARY]
    target = step(0)
    execution = SimpleNamespace(program_allowance_micros=ALLOWANCE, program_ledger_collection=SCOPE.collection_id)
    run = SimpleNamespace(id=target["run_id"], attempts={target["step"]: 1},
        profile=SimpleNamespace(execution=execution))
    specimen = SimpleNamespace(id=target["specimen_id"], run=run)
    principal = SimpleNamespace(scope=SCOPE)
    workflow = SimpleNamespace(repository=repository, clock=None)
    assert Workflow._ledger_settlement(workflow, principal, specimen, target["step"], 1_000) == 400
    assert Workflow._ledger_settlement(workflow, principal, specimen, target["step"], 2_000) is None


def test_a_monthly_cap_ledger_archives_as_the_program_ledger_does(tmp_path):
    from specimen_digitization.application.tenant_budget import TenantLedger

    repository = Versioned(tmp_path / "state.sqlite3")
    ledger = TenantLedger(repository, SCOPE, "organization", "2026-10")
    for i in range(400):
        assert ledger.reserve(ALLOWANCE, 1_000, **step(i)).issue is None
        assert ledger.settle(1_000, 900, **step(i)) is not None
    head = ledger.read()
    assert head["reserved_total_micros"] == 900 * 400
    # One cap ledger keeping every effect would end with a save of over 30,000 bytes.
    assert len(head[ORDINARY]) <= HEAD_EFFECTS + 1 and max(repository.versions) < 8_000
    assert ledger.settled(key(step(0)), 1_000) == 900
    assert ledger.reserve(ALLOWANCE, 1_000, **step(0)).held
    assert ledger.settle(1_000, 500, **step(0)) is None
    assert ledger.read()["reserved_total_micros"] == 900 * 400


def test_a_replay_of_an_archived_attempt_is_admitted_at_the_allowance(tmp_path):
    from specimen_digitization.application.tenant_budget import _program_admits

    allowance = 1_000 * (HEAD_EFFECTS + 1)
    ledger = ledger_on(Versioned(tmp_path / "state.sqlite3"))
    for i in range(HEAD_EFFECTS + 1):
        assert ledger.reserve(allowance, 1_000, **step(i)).issue is None
    assert ledger.read()[ORDINARY] == {} and ledger.read()["reserved_total_micros"] == allowance
    target = step(0)
    execution = SimpleNamespace(program_allowance_micros=allowance, program_ledger_collection=SCOPE.collection_id)
    specimen = SimpleNamespace(id=target["specimen_id"], run=SimpleNamespace(id=target["run_id"],
        profile=SimpleNamespace(execution=execution)))
    principal = SimpleNamespace(scope=SCOPE)
    # The program ledger replays the attempt, so the cap's pre-check must too.
    assert ledger.reserve(allowance, 1_000, **target).issue is None
    assert _program_admits(ledger.repository, principal, specimen, target["step"], 1_000, 1, None) is None
    assert _program_admits(ledger.repository, principal, specimen, "new-step", 1_000, 1, None) == (
        "program_allowance_exhausted")
