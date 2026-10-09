"""Research attempts share G30's existing ordinary model allowance.

Two ledgers are deliberately ordered: reserve the run first, then the program,
then send. A crash between them may retain an unused hold, never an uncharged
request. Durable captures make settlement idempotent after any restart.
"""
from __future__ import annotations

import asyncio
import copy

from specimen_digitization.application.domain import Scope
from specimen_digitization.application.lane_allowance import LegacyLedgerUnavailable, ProgramLedger

from .persistence import DurableEffectBroker, HeldUnknown

# G9: the owner's USD 25 ceiling, cumulative. The research broker below refuses a larger
# allowance; lane.queue, ProgramLedger.reserve and ProgramAllowance do not check it.
MAX_PROGRAM_ALLOWANCE_MICROS = 25_000_000


class ProgramEffectBroker(DurableEffectBroker):
    def __init__(self, store, blobs, *, repository, scope, run, binding_guard=None, send_authorization=None):
        super().__init__(store, blobs)
        self.binding_guard = binding_guard
        self.authorization = copy.deepcopy(send_authorization)
        policy = run.profile.execution
        self.allowance = policy.program_allowance_micros
        self.ledger = None if self.allowance is None else ProgramLedger(repository, Scope(
            organization_id=scope.organization_id, collection_id=policy.program_ledger_collection))
        # This broker refuses an allowance above G9's USD 25. The pilot's own allowance
        # (G30, USD 15 in the published profile) sits inside it.
        if self.allowance is not None and self.allowance > MAX_PROGRAM_ALLOWANCE_MICROS:
            raise HeldUnknown("program_allowance_ledger_unavailable")

    def charge(self, key, amount, *, settle=False, historical=False):
        if self.ledger is None:
            return  # An explicitly synthetic fixture has no production allowance.
        try:
            self.ledger.research_effect(self.allowance, key, amount, settle=settle, historical=historical)
        except LegacyLedgerUnavailable as error:
            raise HeldUnknown(str(error)) from None

    def _key(self, effect_id, attempt_number):
        return f"research:{self.store.program_key}:{effect_id}:{attempt_number}"

    def reconcile(self, scope):
        """Carry all historical paid and unknown attempts before another send.

        Old research versions did not update the program ledger. Retain those
        costs on first encounter; already represented attempts replay unchanged.
        """
        if self.ledger is None:
            return
        for effect in self.store._read(scope).state["effects"].values():
            receipts = {row["attempt_id"]: row for row in effect.get("previous_receipts", [])}
            if effect.get("receipt"):
                receipts[effect["receipt"]["attempt_id"]] = effect["receipt"]
            for number, attempt in enumerate(effect["attempts"], 1):
                receipt = receipts.get(attempt["attempt_id"])
                actual = receipt.get("actual_micro_usd") if receipt else None
                self.charge(self._key(effect["effect_id"], number),
                    effect["reservation_micro_usd"] if actual is None else actual,
                    settle=actual is not None, historical=True)

    def send_authorization(self, execution_class):
        return copy.deepcopy(self.authorization) if execution_class == "live" else None

    async def before_send(self, scope, intent):
        if self.binding_guard is not None:
            await self.binding_guard()
        await asyncio.to_thread(self.charge,
            self._key(intent["effect_id"], len(intent["attempts"]) + 1), intent["reservation_micro_usd"])

    async def execute(self, scope, lease, operation_key, request, reservation_micro_usd, dispatch,
                      *, execution_class="offline", field_keys=()):
        if execution_class == "live" and (self.ledger is None or self.binding_guard is None or self.authorization is None):
            raise HeldUnknown("program_allowance_ledger_unavailable")
        async def guarded_dispatch(attempt, key):
            if self.binding_guard is not None:
                await self.binding_guard()
            return await dispatch(attempt, key)
        receipt = await super().execute(scope, lease, operation_key, request, reservation_micro_usd,
            guarded_dispatch, execution_class=execution_class, field_keys=field_keys)
        if receipt.actual_micro_usd is not None:
            effect = await asyncio.to_thread(self.store.effect, scope, receipt.effect_id)
            number = next(index for index, attempt in enumerate(effect["attempts"], 1)
                if attempt["attempt_id"] == receipt.attempt_id)
            await asyncio.to_thread(self.charge, self._key(receipt.effect_id, number),
                receipt.actual_micro_usd, settle=True, historical=True)
        return receipt


def research_liability_micros(repository, principal, specimen, *, state_backend=None):
    """The retained research offset for an ordinary pre-call budget check.

    Read by run identity, including all old jobs/generations. Only an absent
    state means no prior research. Malformed/unreadable state blocks the call.
    Does not add the returned offset to the ordinary usage counter.
    """
    from .persistence import CONTRACT_VERSION, DurabilityScope, SqlConnectStateBackend
    from .production_runtime import research_program_key

    scope = DurabilityScope(principal.scope.organization_id, principal.scope.collection_id,
        specimen.id, "ordinary-budget-read", 1, principal.user_id, specimen.asset.sensitive)
    backend = state_backend if state_backend is not None else SqlConnectStateBackend(repository)
    try:
        document = backend.load(scope, research_program_key(specimen.run.id))
        if document is None:
            return 0
        state = document.state
        if (state["contract_version"] != CONTRACT_VERSION
            or state["program_key"] != research_program_key(specimen.run.id)):
            raise ValueError("unsupported research state")
        ordinary = specimen.run.usage.reserved_cost_micros
        seed = state["budget_policy"]["external_settled_micro_usd"]
        highwater = state.get("ordinary_cost_micros", seed)
        values = [state["budget_policy"]["external_held_micro_usd"], max(seed, highwater) - ordinary]
        values[1] = max(0, values[1])
        for effect in state["effects"].values():
            actual = effect["actual_micro_usd"]
            values.extend((effect["held_micro_usd"], 0 if actual is None else actual))
        if any(type(value) is not int or value < 0 for value in [seed, highwater, ordinary, *values]):
            raise ValueError("invalid research liability")
        return sum(values)
    except Exception as error:
        raise HeldUnknown("research_budget_state_unavailable") from error


def reserve_ordinary_liability(repository, principal, specimen, step, cost, *, attempt=None, state_backend=None):
    """Before an ordinary provider send, atomically share the run's USD1 cap.

    Initializes the committed budget at the first ordinary call, so research
    provisioning cannot race a missing-state read. No canonical save failure or
    restart releases an unconfirmed hold.
    """
    from dataclasses import replace
    from .persistence import BudgetExceeded, DurabilityScope, ResearchStore, SqlConnectStateBackend
    from .production_runtime import research_budget_policy, research_program_key

    try:
        scope = DurabilityScope(principal.scope.organization_id, principal.scope.collection_id,
            specimen.id, "ordinary-budget-reserve", 1, principal.user_id, specimen.asset.sensitive)
        key = research_program_key(specimen.run.id)
        backend = state_backend if state_backend is not None else SqlConnectStateBackend(repository)
        store = ResearchStore(backend, key)
        policy = research_budget_policy(specimen.run.profile_snapshot, specimen.run.usage.reserved_cost_micros)
        existing = backend.load(scope, key)
        if existing is not None:
            policy = replace(policy, external_settled_micro_usd=existing.state["budget_policy"]["external_settled_micro_usd"])
        store.initialize(scope, policy)
        number = specimen.run.attempts.get(step, 0) + 1 if attempt is None else attempt
        if type(number) is not int or number <= 0:
            raise ValueError("Invalid ordinary attempt")
        store.reserve_ordinary(scope, f"{step}:{number}", cost, specimen.run.usage.reserved_cost_micros)
    except BudgetExceeded:
        raise
    except Exception as error:
        raise HeldUnknown("research_budget_state_unavailable") from error


def settle_ordinary_liability(repository, principal, specimen, step, *, attempt=None, state_backend=None):
    """After record_step, settle only its complete known provider usage.

    SAM's request-duration estimate and unknown calls have cost_basis=reserved;
    neither can refund any liability. Original seed costs remain immutable.
    """
    from .persistence import DurabilityScope, ResearchStore, SqlConnectStateBackend
    from .production_runtime import research_program_key
    try:
        number = specimen.run.attempts.get(step, 1) if attempt is None else attempt
        calls = [call for call in specimen.run.paid_calls if call["step"] == step and call["attempt"] == number]
        if not calls or any(call["cost_basis"] == "reserved" for call in calls):
            return
        if any(call["cost_basis"] not in {"computed", "billed"}
            or type(call["cost_micros"]) is not int or call["cost_micros"] < 0 for call in calls):
            raise ValueError("Unknown ordinary settlement basis")
        scope = DurabilityScope(principal.scope.organization_id, principal.scope.collection_id,
            specimen.id, "ordinary-budget-settle", 1, principal.user_id, specimen.asset.sensitive)
        backend = state_backend if state_backend is not None else SqlConnectStateBackend(repository)
        store = ResearchStore(backend, research_program_key(specimen.run.id))
        store.settle_ordinary(scope, f"{step}:{number}", sum(call["cost_micros"] for call in calls))
    except Exception as error:
        raise HeldUnknown("research_budget_state_unavailable") from error
