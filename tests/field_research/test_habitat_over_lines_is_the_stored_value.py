"""step._over_lines is a test of the stored VALUE, not of the field's history (lane H4 of the autonomy program, fix
round 6 of PR #464, 2026-11-21; the coordinator's ruling R5, not the owner's words; it replaces R4' of round 5).

A habitat research settles on text its expert read from the transcript over consecutive lines counts for nothing in
the four readers that call step._over_lines and carries the lane's label flag (test_habitat_changes_no_other_field.py,
test_habitat_over_lines_label_flag.py). Which stored value is such a habitat was told, in turn, by two records kept
per FIELD, and each outlived the value it was written for: the finding `transcript_literal:habitat` (round 5: a
one-line value a person extended to two lines), then second_opinion.authority (round 6: a person's decision of an
earlier value, and a value research settled afterwards). Now research marks the value itself where it settles it
(step._settled): run.dependencies[step.OVER_LINES] holds, for the habitat, a digest of the value's literal and of
each reader's verbatim of it; step._over_lines compares that digest with the stored value's; and a person's
decision of the field at the decision endpoint withdraws the mark (second_opinion.decided).

Every sequence here goes through the workflow and the decision endpoint. Nothing in the product is patched but the
API's queue, which marks the run pending so that the test's own workflow drains it. What origin/main 3eb37c11 and
d4225535 do with each sequence was run on those sources:
~/specimen-golive/autonomy-program/H4/fix6_probe_*.txt. The label texts are made up.
"""

from __future__ import annotations

import pytest
from test_step import (
    COLLECTORS,
    LABEL,
    LACKS,
    ORG,
    TEXT,
    TODAY,
    NoGenus,
    Scripted,
    answering,
    build_rig,
    cannot_resolve,
    cleared_as_not_on_label,
    decide,
    mounted,
    review_client,
)
from test_taxon_scope import without_the_taxon_line

from specimen_digitization.application import api as app_api
from specimen_digitization.application.domain import Run, ValueState, now
from specimen_digitization.field_research import second_opinion
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer

HOST = "Mus\nmusculus"
HABITAT_LINE = f"habitat: {LABEL['habitat']}\n"
FLAG = "label_unsettled:habitat"
# The key of research's mark in run.dependencies (step.OVER_LINES), by its text: a stored record holds it.
MARK = "field_research_over_lines"
CANNOT = answering(FieldAnswer(outcome="sources_cannot_resolve", explanation="Not this time."))
# The label of Codex's round-6 sequence: the code "sp. 22" with no genus, "Mus" over "musculus" in the habitat's place.
CODE_BESIDE = without_the_taxon_line("sp. 22").replace(HABITAT_LINE, HOST + "\n")
# The label of the run-the-code reviewer's sequence: "Mus" over "musculus" where the Collection Method's line stood,
# no keyed habitat line; the organiser offers those two lines as the Collection Method's text.
METHOD_GONE = TEXT.replace(f"collection_method: {LABEL['collection_method']}\n", HOST + "\n").replace(HABITAT_LINE, "")
METHOD_CANDIDATES = [*COLLECTORS, *(("collection_method", name, HOST, HOST) for name in ("1A", "1B"))]


def res(literal):
    return answering(FieldAnswer(outcome="resolved", literal=literal, reading_names=["1A", "1B"],
        explanation="As written."))


class Rig:
    """build_rig's record with its resolver mounted, a reviewer's client, and the API's queue replaced so that an
    action or a transcription decision marks the run pending and this rig's workflow drains it."""

    def __init__(self, tmp_path, monkeypatch, text, other, scripts, *, candidates=COLLECTORS, sources=None):
        def queue(specimen, registry, actor):
            specimen.run.stage = "pending"
            specimen.run.queued_at = now()

        monkeypatch.setattr(app_api, "queue", queue)
        self.rig = build_rig(tmp_path, text, other, candidates=candidates)
        self.script = Scripted(dict(scripts))
        mounted(self.rig, self.script, sources=sources)
        self.client = review_client(self.rig)
        self.drain()

    @property
    def run(self):
        """The run as the store holds it now: every read is a load."""
        return self.rig.repository.get(self.rig.principal.scope, self.rig.specimen.id).run

    def drain(self):
        self.rig.workflow.drain(self.rig.principal, self.rig.specimen.id)

    def decide_habitat(self, name, **change):
        """A person's field decision of the Habitat: the stored value with `change`, its evidence kept."""
        value = self.run.fields["habitat"]
        after = value.model_dump(mode="json", exclude={"evidence_ids"}) | {"state": "supported", **change}
        return decide(self.client, self.rig, name, "field", target_id="habitat", after=after,
            evidence_ids=list(value.evidence_ids))

    def transcribe(self, name, text):
        """A person's transcription decision that keeps the label's text: parse and research run again."""
        decide(self.client, self.rig, name, "transcription", target_id=self.run.regions[0].id,
            after={"text": text, "state": "supported"})
        self.drain()

    def retry(self, name):
        current = self.rig.repository.get(self.rig.principal.scope, self.rig.specimen.id)
        response = self.client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
            headers={"Authorization": "Bearer reviewer", "Idempotency-Key": name},
            json={"expected_revision": current.version, "action": "retry", "reason": "Again."})
        assert response.status_code == 200, response.text
        self.drain()


def over_lines(run):
    return field_step._over_lines(run, "habitat", run.fields["habitat"], field_step.human_keys(run))


def marked(run):
    """Whether the run holds research's mark for the habitat, and the key it is kept under at all."""
    marks = run.dependencies.get(MARK)
    return (isinstance(marks, dict) and "habitat" in marks, MARK in run.dependencies)


def habitat(run):
    value = run.fields["habitat"]
    return (value.state, value.literal)


def same_after_a_second_finalize(run):
    again = run.model_copy(deep=True)
    before = (list(again.reasons), list(again.open_reasons))
    field_step.refinalize(again, today=TODAY)
    return (list(again.reasons), list(again.open_reasons)) == before


def test_research_settling_over_lines_after_a_persons_decision_is_researchs_value_again(tmp_path, monkeypatch):
    """Codex's round-6 sequence, then requirement P2 after P3. The label writes the code "sp. 22" with no genus and
    "Mus" over "musculus". Research settles the Habitat "Mus" on ONE line; a person confirms it
    (Run.person_decided_fields then names the habitat, and nothing clears that record). A transcription decision
    keeps the label's text: parse and research run again, and research now settles the Habitat "Mus" over
    "musculus"; the collectors settle; the Taxon's expert answers that the sources cannot resolve "sp. 22".
    origin/main refuses that Habitat, a possible genus stays on the label, and the Taxon stays unresolved. On
    d4225535 the person's decision of the EARLIER value made step._over_lines false for research's new one, its
    words were accounted for, and owner decision B settled "sp. 22" (the run-the-code reviewer ran it:
    reviews/g51_probes/g51_464/r6/out/r6_codex_reparse_collectors_*.txt). Now the value research settled is marked
    as research's whatever the record of the person's earlier decision holds, and the Taxon ends as on origin/main.
    Then the person confirms the two-line Habitat: the mark is withdrawn, the value is the person's, and a Retry and
    a second finalize leave it so. Red on d4225535's source (the Taxon is settled there)."""
    record = Rig(tmp_path, monkeypatch, CODE_BESIDE, CODE_BESIDE,
        {"taxon": cannot_resolve("sp. 22", asks=["sp. 22"]), "habitat": res("Mus")}, sources=NoGenus)
    run = record.run
    assert habitat(run) == (ValueState.SUPPORTED, "Mus") and not over_lines(run)
    # P5: a habitat read from the transcript on one line leaves the finding and no key of the lane's.
    assert any(finding.reason_code == field_step.transcript_code("habitat") for finding in run.findings)
    assert marked(run) == (False, False)

    run = record.decide_habitat("confirm-1")
    assert run.person_decided_fields == ["habitat"] and marked(run) == (False, False)

    record.script.scripts.update({"habitat": res(HOST), "collectors": res("J. Smith")})
    record.transcribe("transcribe-1", CODE_BESIDE)
    run = record.run
    assert record.script.calls.count("habitat") == 2 and run.person_decided_fields == ["habitat"]
    assert "habitat" in second_opinion.authority(run)
    assert habitat(run) == (ValueState.SUPPORTED, HOST)
    # The other field first: the Taxon ends as on origin/main.
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal) == (ValueState.UNRESOLVED, "sp. 22")
    assert {"mandatory_unresolved:taxon", "taxonomy_unresolved"} <= set(run.reasons)
    assert over_lines(run) and marked(run) == (True, True)

    # P2 after P3: the person confirms research's two lines. The value is the person's: no mark, no key.
    run = record.decide_habitat("confirm-2")
    assert habitat(run) == (ValueState.SUPPORTED, HOST)
    assert not over_lines(run) and marked(run) == (False, False)
    # P4: a Retry asks the Taxon again and not the Habitat; the stored value stays the person's.
    record.retry("retry-1")
    run = record.run
    assert record.script.calls.count("habitat") == 2 and record.script.calls.count("taxon") == 3
    assert habitat(run) == (ValueState.SUPPORTED, HOST)
    assert not over_lines(run) and marked(run) == (False, False)
    assert same_after_a_second_finalize(run)


@pytest.mark.parametrize("unread", [False, True], ids=["label-read-alike", "label-unread"])
def test_a_habitat_research_settles_over_lines_in_a_retry_after_a_persons_decision(tmp_path, monkeypatch, unread):
    """The run-the-code reviewer's round-6 sequence, with no re-parse (requirement P3 again). Research leaves the
    Habitat unsettled; a person decides it, "Mus". The Retry asks the Habitat AGAIN: origin/main's step.build_tasks
    leaves out a decision carried into a run and a field an attempt settled, not a decision made on the run where no
    attempt settled the field. That is origin/main's rule, not this change's; it is what makes this sequence
    reachable. The habitat's expert answers "Mus" over "musculus" from the transcript, which the organiser had
    offered as the Collection Method's text, and the Collection Method's expert answers that the label lacks it.
    origin/main refuses the Habitat and holds the Collection Method (`mandatory_unresolved:collection_method`). On
    d4225535 research's two lines were taken for the person's, held the Collection Method's organiser text for rule
    A's mark, and the Collection Method was cleared as not on the label with no flag. Now research's value is
    research's: the Collection Method is held as on origin/main, and on a label whose transcription is unresolved the
    Habitat carries the lane's own label flag (item M). Red on d4225535's source.

    Then the person confirms research's two lines (P2 after P3): the mark is withdrawn and the flag is gone. A second
    Retry asks the Collection Method again and its expert answers as before: the person's Habitat is then read as any
    settled value, it holds that organiser text, and the Collection Method is cleared as not on the label. (On
    origin/main, run for the unread label, that Retry asks the person's Habitat again, refuses the answer and leaves
    it unresolved, so there the Collection Method stays held:
    ~/specimen-golive/autonomy-program/H4/fix6_probe_b2_b4_b6u_main-3eb37c11.txt.)"""
    other = METHOD_GONE.replace("leg. J. Smith", "leg. J. Smyth") if unread else METHOD_GONE
    record = Rig(tmp_path, monkeypatch, METHOD_GONE, other, {"habitat": CANNOT, "collection_method": CANNOT},
        candidates=METHOD_CANDIDATES)
    assert record.run.fields["habitat"].state == ValueState.UNRESOLVED

    run = record.decide_habitat("decide-1", literal="Mus", parsed="Mus", normalized="Mus")
    assert habitat(run) == (ValueState.SUPPORTED, "Mus") and run.person_decided_fields == ["habitat"]
    assert marked(run) == (False, False)

    record.script.scripts.update({"habitat": res(HOST), "collection_method": answering(LACKS)})
    record.retry("retry-1")
    run = record.run
    assert record.script.calls.count("habitat") == 2
    assert habitat(run) == (ValueState.SUPPORTED, HOST) and "habitat" in second_opinion.authority(run)
    # The other field first: the Collection Method is held as on origin/main.
    method = run.fields["collection_method"]
    assert method.state == ValueState.NOT_PRESENT and "collection_method" not in cleared_as_not_on_label(run)
    assert "mandatory_unresolved:collection_method" in run.reasons
    assert over_lines(run) and marked(run) == (True, True)
    assert (FLAG in run.open_reasons) is unread
    assert same_after_a_second_finalize(run)

    run = record.decide_habitat("confirm-2")
    assert habitat(run) == (ValueState.SUPPORTED, HOST)
    assert not over_lines(run) and marked(run) == (False, False) and FLAG not in run.open_reasons
    record.retry("retry-2")
    run = record.run
    assert record.script.calls.count("habitat") == 2 and record.script.calls.count("collection_method") == 3
    assert habitat(run) == (ValueState.SUPPORTED, HOST) and not over_lines(run) and FLAG not in run.open_reasons
    assert "collection_method" in cleared_as_not_on_label(run)
    assert "mandatory_unresolved:collection_method" not in run.reasons


def test_the_mark_is_withdrawn_for_the_decided_field_and_a_stale_one_names_no_value(tmp_path, monkeypatch):
    """The mark's own rules, on a record whose Habitat research settled over lines (through the workflow; the
    label's readers differ on another line).
    - Durable (P4): the run read back from the store, and the run rebuilt from its JSON, give the same answer.
    - Withdrawn by second_opinion.decided for the decided field, the one function the endpoint calls for each
      deciding kind (application/api.py: field, research_candidate, authority_resolution with the target's key;
      taxonomy_resolution with "taxon"). A decision of another field leaves the habitat's mark. Only the field kind
      is run through the endpoint in this file: a locked research selection needs a research review context and an
      authority resolution an authority candidate, and the habitat has neither in these rigs.
    - A stale mark is harmless: where the stored value is replaced with no withdrawal (another literal, or another
      reader's verbatim of it), the digest no longer names it; the value put back, it does again.
    - A value on one line is never such a value, whatever the mark holds."""
    other = METHOD_GONE.replace("leg. J. Smith", "leg. J. Smyth")
    record = Rig(tmp_path, monkeypatch, METHOD_GONE, other, {"habitat": res(HOST)})
    run = record.run
    assert habitat(run) == (ValueState.SUPPORTED, HOST) and over_lines(run) and marked(run) == (True, True)
    assert FLAG in run.open_reasons
    assert field_step.OVER_LINES == MARK
    assert over_lines(Run.model_validate(run.model_dump(mode="json")))
    # The API's detail read of a record that holds the mark.
    detail = record.client.get(f"/v1/organizations/{ORG}/specimens/{record.rig.specimen.id}",
        headers={"Authorization": "Bearer reviewer"})
    assert detail.status_code == 200, detail.text

    def changed(change):
        copy = run.model_copy(deep=True)
        change(copy)
        return copy

    # A decision of another field: the habitat's mark stays. The decided field's: withdrawn, key and all.
    for key in ("taxon", "collection_method", "collectors"):
        assert over_lines(changed(lambda copy, key=key: second_opinion.decided(copy, key)))
    decided = changed(lambda copy: second_opinion.decided(copy, "habitat"))
    assert not over_lines(decided) and marked(decided) == (False, False)
    assert decided.person_decided_fields == ["habitat"]

    # Stale: the value replaced with no withdrawal.
    value = run.fields["habitat"]
    reader = next(iter(value.verbatim_by_observation))
    for update in ({"literal": "Mus\nmuscalus"}, {"literal": "Mus musculus"},
            {"verbatim_by_observation": {**value.verbatim_by_observation, reader: "Mus\nmuscalus"}},
            {"verbatim_by_observation": {}}):
        stale = changed(lambda copy, update=update: copy.fields.__setitem__("habitat", value.model_copy(update=update)))
        assert marked(stale) == (True, True) and not over_lines(stale), update
    assert over_lines(changed(lambda copy: copy.fields.__setitem__("habitat", value.model_copy(deep=True))))
    # A carried decision is left out by the caller's set, as before.
    assert not field_step._over_lines(run, "habitat", value, frozenset({"habitat"}))

    # Through the endpoint: the field decision withdraws it, and the stored run holds no key of the lane's.
    run = record.decide_habitat("confirm-1")
    assert not over_lines(run) and marked(run) == (False, False) and FLAG not in run.open_reasons


def test_a_record_with_no_habitat_over_lines_has_no_new_key(tmp_path, monkeypatch):
    """Requirement P5. The rig's own label, whose habitat is a keyed line the organiser offers whole, through the
    workflow: the Habitat settles and run.dependencies holds no key of the lane's; nor after a person's decision of
    it and a Retry. (The 100 stored truth runs finalized again are compared byte for byte with origin/main's in
    ~/specimen-golive/autonomy-program/H4/replay_h4_fix6.txt.)"""
    record = Rig(tmp_path, monkeypatch, TEXT, TEXT, {"collection_method": CANNOT})
    run = record.run
    assert habitat(run) == (ValueState.SUPPORTED, LABEL["habitat"])
    assert MARK not in run.dependencies and not over_lines(run)
    run = record.decide_habitat("confirm-1")
    assert MARK not in run.dependencies
    record.retry("retry-1")
    assert MARK not in record.run.dependencies


def test_a_re_parse_sets_the_mark_by_what_research_settles_then(tmp_path, monkeypatch):
    """Requirement P4 for a re-parse, with no decision of the field. Research settles the Habitat over two lines:
    marked. A transcription decision keeps the label's text, parse and research run again, and research now settles
    "Mus" on one line: the mark is removed, key and all (step._settled removes it where it settles the habitat any
    other way). Once more, and research settles the two lines again: marked again. (A move to the units path and a
    reprocess run parse and research again in the same way; they are not run here.)"""
    record = Rig(tmp_path, monkeypatch, CODE_BESIDE, CODE_BESIDE,
        {"taxon": cannot_resolve("sp. 22", asks=["sp. 22"]), "habitat": res(HOST)}, sources=NoGenus)
    run = record.run
    assert habitat(run) == (ValueState.SUPPORTED, HOST) and over_lines(run) and marked(run) == (True, True)

    record.script.scripts["habitat"] = res("Mus")
    record.transcribe("transcribe-1", CODE_BESIDE)
    run = record.run
    assert record.script.calls.count("habitat") == 2
    assert habitat(run) == (ValueState.SUPPORTED, "Mus") and not over_lines(run) and marked(run) == (False, False)

    record.script.scripts["habitat"] = res(HOST)
    record.transcribe("transcribe-2", CODE_BESIDE)
    run = record.run
    assert record.script.calls.count("habitat") == 3 and run.person_decided_fields == []
    assert habitat(run) == (ValueState.SUPPORTED, HOST) and over_lines(run) and marked(run) == (True, True)
