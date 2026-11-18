"""Every writer of a run's reasons is classified, and every hold that outlives a recomputation is
derived from durable state (plan WP K1, Codex rounds 2 and 3 on PR #455).

The source is scanned with `ast` for every assignment to `<anything>.reasons` (tuple targets
included) and every `.reasons.append/extend/insert`. Each site is one of:
- RECOMPUTATION: the reasons computed from the run (field research's finalize_fields and refinalize,
  the ordinary path's policy.finalize), or another pipeline's own computation the field-research
  profile does not use (the research harness's materializations, the evidence harness, the pilot);
- BLOCKER: the reasons replaced by a blocker; nothing depends on the list it replaces;
- DERIVED: a hold written outside the recomputation, which is backed by state recorded on the run
  (application/standing_holds.py: note_pending) so every later computation derives it again.
A new writer fails this test until it is classified here.
"""

import ast
import importlib
import inspect
from pathlib import Path

from specimen_digitization.application import standing_holds
from specimen_digitization.application.domain import Run, RunFinding

SRC = Path(standing_holds.__file__).resolve().parents[1]

RECOMPUTATION = {
    ("field_research/step.py", "finalize_fields"),
    ("application/policy.py", "finalize"),
    ("research_harness/canonical_materialization.py", "materialize"),
    ("research_harness/canonical_materialization_v2.py", "_materialize"),
    ("research_harness/canonical_progress_materialization_v2.py", "materialize_progress_v2"),
    ("application/evidence_runtime.py", "apply_phase_gate"),
    ("application/evidence_pilot.py", "_evidence_step"),
}
BLOCKER = {
    ("application/active_graph.py", "save_recoverably"),
    ("application/workflow.py", "_step"),
    ("application/history_restore.py", "restored_specimen"),
    ("field_research/step.py", "refinalize"),
    ("application/policy.py", "finalize"),
}
# The site, and the hold it writes, which state recorded on the run backs.
DERIVED = {
    ("field_research/step.py", "_retained_reassessment"): standing_holds.REASSESSMENT_UNCONFIRMED,
    ("application/history_restore.py", "restored_specimen"): standing_holds.HISTORY_RESTORED,
}


def writers():
    found = set()
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text())
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            hit = False
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                hit = any(isinstance(elt, ast.Attribute) and elt.attr == "reasons"
                    for target in targets for elt in (target.elts if isinstance(target, ast.Tuple) else [target]))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                hit = (node.func.attr in {"append", "extend", "insert"} and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "reasons")
            if not hit:
                continue
            up = node
            while up in parents and not isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                up = parents[up]
            found.add((path.relative_to(SRC).as_posix(), getattr(up, "name", None)))
    return found


def source_of(path, name):
    module = importlib.import_module("specimen_digitization." + path[:-3].replace("/", "."))
    if hasattr(module, name):
        return inspect.getsource(getattr(module, name))
    owner = next(value for value in vars(module).values() if isinstance(value, type) and hasattr(value, name))
    return inspect.getsource(getattr(owner, name))


def test_every_writer_of_a_runs_reasons_is_classified():
    found = writers()
    known = RECOMPUTATION | BLOCKER | set(DERIVED)
    assert found - known == set(), "classify each new writer of a run's reasons in tests/test_standing_holds.py"
    assert known - found == set(), "a classified writer no longer writes reasons: remove it here"


def test_every_hold_written_outside_the_recomputation_is_recorded_on_the_run():
    for (path, name), code in DERIVED.items():
        assert code in standing_holds.DERIVED, (path, name)
        assert "note_pending(" in source_of(path, name), (path, name)


def test_the_live_recomputations_derive_the_holds_and_read_no_earlier_hold():
    for path, name in (("field_research/step.py", "finalize_fields"), ("application/policy.py", "finalize")):
        assert "derived_holds(" in source_of(path, name), (path, name)
    # A person's decision records its approval hold where it enters (api.py apply_decision), never in a
    # finalize, which a decision may skip (Codex round 4 on #455).
    refinalize = source_of("field_research/step.py", "refinalize")
    assert "note_pending(" not in refinalize and "person_acted(" not in refinalize


def test_holds_are_derived_from_the_runs_state():
    run = Run(pending_review=[])
    assert standing_holds.derived_holds(run) == []
    standing_holds.note_pending(run, standing_holds.APPROVAL, "location_reassessment_unconfirmed:city")
    run.findings.append(RunFinding(rule_id=standing_holds.GIVEN_UP, rule_version="1", severity="warning",
        reason_code="field_research_given_up:token_budget_exhausted"))
    run.reasons = ["evidence_integrity_failure"]  # a blocker replaced the list: nothing depends on it
    assert standing_holds.derived_holds(run) == [standing_holds.APPROVAL, "location_reassessment_unconfirmed:city",
        standing_holds.GIVEN_UP]
    standing_holds.replace_reassessment(run, ["location_reassessment_unconfirmed:county"])
    assert run.pending_review == [standing_holds.APPROVAL, "location_reassessment_unconfirmed:county"]
    standing_holds.replace_reassessment(run, [])
    assert run.pending_review == [standing_holds.APPROVAL]
    run.human_approved = True
    assert standing_holds.derived_holds(run) == []
    standing_holds.clear_on_approval(run)
    assert run.pending_review == []


def test_a_run_stored_before_the_key_adopts_its_stored_holds_once():
    legacy = Run(reasons=[standing_holds.APPROVAL, "mandatory_unresolved:taxon", "history_restored_requires_review"])
    assert legacy.pending_review is None and "pending_review" not in legacy.model_dump(mode="json")
    standing_holds.adopt_legacy(legacy)
    assert legacy.pending_review == [standing_holds.APPROVAL, standing_holds.HISTORY_RESTORED]
    legacy.reasons = ["location_reassessment_unconfirmed:city"]
    standing_holds.adopt_legacy(legacy)  # the key is set: the reasons are never read again
    assert legacy.pending_review == [standing_holds.APPROVAL, standing_holds.HISTORY_RESTORED]
    untouched = Run(reasons=["mandatory_unresolved:taxon"])
    standing_holds.adopt_legacy(untouched)
    assert untouched.pending_review == [] and standing_holds.derived_holds(untouched) == []


def test_no_helper_turns_an_unset_key_into_an_empty_one_without_adopting_first():
    """Codex round 4 on #455: a legacy run's stored hold is adopted by every helper that writes the key."""
    for write in (lambda run: standing_holds.replace_reassessment(run, []),
            lambda run: standing_holds.note_pending(run, standing_holds.GIVEN_UP),
            standing_holds.person_acted):
        legacy = Run(reasons=[standing_holds.APPROVAL, "mandatory_unresolved:taxon"])
        write(legacy)
        assert standing_holds.APPROVAL in legacy.pending_review


def test_a_stored_run_without_the_key_adopts_its_holds_where_it_is_loaded():
    """Codex round 4 on #455: adoption happens where a stored run is loaded (active_graph.unpack), before
    any code can write the key or the reasons; a stored run with the key set is read as stored."""
    from specimen_digitization.application.active_graph import unpack

    def stored(**run):
        payload = {"id": "s1", "version": 1, "scope": {"organization_id": "o", "collection_id": "c"},
            "asset": {"id": "a1", "blob_ref": "b", "sha256": "0" * 64, "media_type": "image/png", "width": 1,
                "height": 1, "size_bytes": 1, "filename": "a.png", "uploader": "u"},
            "run": Run(**run).model_dump(mode="json")}
        return unpack(payload, None)

    legacy = stored(reasons=[standing_holds.APPROVAL, "location_reassessment_unconfirmed:city"])
    assert legacy.run.pending_review == [standing_holds.APPROVAL, "location_reassessment_unconfirmed:city"]
    current = stored(reasons=[standing_holds.APPROVAL], pending_review=[])
    assert current.run.pending_review == []
    # Nothing to adopt: the loaded record equals the record saved (storage's review proofs compare them);
    # every helper that writes the key adopts first.
    untouched = stored(reasons=["mandatory_unresolved:taxon"])
    assert untouched.run.pending_review is None
