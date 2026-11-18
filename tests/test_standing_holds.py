"""Every writer of a run's reasons is classified (plan WP K1, Codex round 2 on PR #455).

The source is scanned with `ast` for every assignment to `<anything>.reasons` (tuple targets
included) and every `.reasons.append/extend/insert`. Each site is one of:
- RECOMPUTATION: the clearance rules recompute the reasons from the run (field research's
  finalize_fields and refinalize, the ordinary path's policy.finalize), or another pipeline's own
  recomputation that the field-research profile does not use (the research harness's canonical
  materializations, the evidence harness's phase gate, the evidence pilot);
- STANDING: a path outside the recomputation writes a standing hold (application/standing_holds.py),
  which every recomputation carries until the event that resolves it;
- BLOCKER: a path replaces the reasons with a blocker; it keeps the standing holds beside it.
A new writer fails this test until it is classified here. The live paths that recompute or block
must call standing_holds (checked on their source).
"""

import ast
import inspect
from pathlib import Path

from specimen_digitization.application import standing_holds

SRC = Path(standing_holds.__file__).resolve().parents[1]

RECOMPUTATION = {
    ("field_research/step.py", "finalize_fields"),
    ("field_research/step.py", "refinalize"),
    ("application/policy.py", "finalize"),
    ("research_harness/canonical_materialization.py", "materialize"),
    ("research_harness/canonical_materialization_v2.py", "_materialize"),
    ("research_harness/canonical_progress_materialization_v2.py", "materialize_progress_v2"),
    ("application/evidence_runtime.py", "apply_phase_gate"),
    ("application/evidence_pilot.py", "_evidence_step"),
}
# The site, and the standing hold it writes.
STANDING = {
    ("field_research/step.py", "refinalize"): standing_holds.APPROVAL,
    ("field_research/step.py", "_retained_reassessment"): standing_holds.REASSESSMENT_UNCONFIRMED,
    ("application/history_restore.py", "restored_specimen"): standing_holds.HISTORY_RESTORED,
}
BLOCKER = {
    ("application/active_graph.py", "save_recoverably"),
    ("application/workflow.py", "_step"),
    ("application/history_restore.py", "restored_specimen"),
    ("field_research/step.py", "refinalize"),
    ("application/policy.py", "finalize"),
}
# The live paths that recompute the reasons or replace them with a blocker: each keeps the standing holds.
CARRIERS = {
    ("field_research/step.py", "finalize_fields"), ("field_research/step.py", "refinalize"),
    ("application/policy.py", "finalize"), ("application/active_graph.py", "save_recoverably"),
    ("application/workflow.py", "_step"),
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


def test_every_writer_of_a_runs_reasons_is_classified():
    found = writers()
    known = RECOMPUTATION | set(STANDING) | BLOCKER
    assert found - known == set(), "classify each new writer of a run's reasons in tests/test_standing_holds.py"
    assert known - found == set(), "a classified writer no longer writes reasons: remove it here"


def test_every_standing_hold_written_is_one_the_recomputations_carry():
    for site, code in STANDING.items():
        assert code in standing_holds.STANDING, site
        assert standing_holds.is_standing(code) and standing_holds.is_standing(code + ":detail")


def test_each_live_recomputation_and_blocker_keeps_the_standing_holds():
    import importlib

    for path, name in CARRIERS:
        module = importlib.import_module("specimen_digitization." + path[:-3].replace("/", "."))
        source = inspect.getsource(getattr(module, name) if hasattr(module, name)
            else getattr(module.Workflow, name))
        assert "standing_holds(" in source or "pending_person_holds(" in source, (path, name)


def test_a_standing_hold_is_resolved_by_its_own_event_only():
    holds = [standing_holds.APPROVAL, standing_holds.HISTORY_RESTORED, "location_reassessment_unconfirmed:city",
        "mandatory_unresolved:fmnh_ins_number"]
    assert standing_holds.standing_holds(holds, approved=False) == holds[:3]
    assert standing_holds.standing_holds(holds, approved=False, settles_reassessment=True) == holds[:2]
    assert standing_holds.standing_holds(holds, approved=True) == []
