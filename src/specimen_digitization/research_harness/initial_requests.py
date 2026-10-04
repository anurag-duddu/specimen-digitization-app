"""Initial genuine ordinary snapshot -> immutable registered specialist inputs.

This adapter preserves every retained reader handoff. It never promotes an
unstructured label/event to accepted science on a model's say-so. Two things
produce deterministic literal assemblies:

1. an explicit exact field-key line in an actually decided transcript;
2. the hand-over: a candidate the ordinary extractor already stored (``_claims``: the
   whole-region rows it writes today, and the narrow per-reading rows of #262, the organiser)
   whose literal trusted code finds as a verbatim substring of exactly one line of the reading
   the row cites. The span (reading, region, offsets) is computed here from the reading text,
   never read from the extractor or from a stored offset, and a literal that cannot be located
   exactly is carried to the specialist as an ungrounded hint (OrganiserCandidate) that never
   becomes an event or assembly. Only the field's own stored value, in the decided reading,
   for the five ASSEMBLY_FIELDS, gets an accepted event and an assembly.

An event or assembly of the second kind is "the extractor proposed this value and
it is verbatim in the decided reading". It is not a semantic check: whether the
line is the collector, the habitat or the collection code stays the specialist's
verification against the raw readings (the specialist prompts say so).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass

from specimen_digitization.application.active_graph import unpack
from specimen_digitization.application.domain import ValueState
from specimen_digitization.application.storage import digest as canonical_digest
from .contracts import (
    ALL_FIELDS, MAX_ORGANISER_CANDIDATES, MAX_ORGANISER_LITERAL, ROLE_FIELDS, CollectionProfile,
    EvidenceItem, EventHypothesis, EventKind, FieldKey, Geometry, OrganiserCandidate, PromptPin,
    SourceFragment, SpecialistRequest, SpecialistRole, digest,
)
from .evidence import EvidenceError, assemble_field, catalog_literal
from .persistence import StaleWork

# The proposer behind the hand-over today: the ordinary extraction step (application/harness.py).
ORGANISER_SOURCE = "extractor"
# What an organiser event's "accepted" status means: verbatim in the decided reading and proposed
# by the extractor. It is stated as the rule and validator version of every such event.
ORGANISER_RULE = "organiser-verbatim-span/v1"
# The fields an extractor literal becomes an accepted assembly for: the five literal fields that
# no source this deployment offers can ground and that the validator resolves from a complete
# literal assembly alone (evidence.py literal_fields). Every other field's candidate is carried
# located (or ungrounded) and gets no assembly, each for its own reason:
# - the dates and the four elevations resolve only as the exact object of the deterministic
#   settlement helper, which no tool hands a specialist, and the worker holds that value back
#   from the record (native_worker.py); an assembly would only invite a refused resolution,
#   which fails the whole role;
# - taxon and the geography fields resolve from a lookup (GBIF, GEOLocate); an assembly would
#   make the validator require the query to equal the assembly text (taxon) and change what a
#   specialist cites (the reading), for no gain; precise_location also resolves from GEOLocate;
# - verbatim_dts and identified_by_irn have no resolved path.
ASSEMBLY_FIELDS = frozenset((FieldKey.FMNH_INS_NUMBER, FieldKey.COLLECTION_CODE, FieldKey.HABITAT,
    FieldKey.COLLECTION_METHOD, FieldKey.COLLECTORS))
# At most this many candidates of one field are handed over (twenty fields x five = the contract's cap of 100,
# so the cap never starves a field). The organiser (#262) stores one row per reading: more than five for a field
# means several labels or readers. The ones kept are, in order: the field's own stored value, the other rows that
# cite a decided reading, then the rest in stored order; if some are dropped the last slot is a visible marker.
MAX_CANDIDATES_PER_FIELD = 5


class NativeGenerationRequestFactory:
    def __init__(self, repository, *, verify_access, registry):
        self.repository, self.verify_access, self.registry = repository, verify_access, registry

    async def __call__(self, principal, binding, job):
        await self.verify_access(principal, binding.canonical.sensitive)
        binding.validate_job(job, program_key=binding.program_key)
        variables = dict(self.repository.variables(principal.scope),
            id=binding.canonical.specimen_id, revision=binding.base_canonical.record_revision)
        data = await asyncio.to_thread(self.repository.execute, "GetSnapshot", variables)
        row = data.get("specimenSnapshot")
        if (not isinstance(row, dict) or row.get("sha256") != binding.base_canonical.snapshot_sha256
            or canonical_digest(row.get("snapshot")) != binding.base_canonical.snapshot_sha256):
            raise StaleWork("research_original_snapshot_unproved")
        original = await asyncio.to_thread(unpack, row["snapshot"], self.repository.graph_blobs)
        profile = CollectionProfile.model_validate(job["pins"]["profile"])
        if (original.scope != principal.scope or original.id != binding.canonical.specimen_id
            or type(original.version) is not int or original.version != binding.base_canonical.record_revision
            or original.run.id != str(binding.base_canonical.canonical_run_id)
            or original.asset.sha256 != binding.source_sha256
            or original.asset.sensitive is not False or binding.canonical.sensitive is not False
            or canonical_digest(original.run.profile_snapshot) != binding.canonical_profile_digest
            or digest(profile) != binding.profile_digest
            or (profile.organization_id, profile.collection_id) !=
                (principal.scope.organization_id, principal.scope.collection_id)
            or job["pins"]["sources"].get("registry_digest") != self.registry.digest):
            raise StaleWork("research_original_source_profile_unproved")
        scope = binding.research_scope()
        fragments, events, assemblies, evidence, decisions, candidates = self._build_graph(original, scope)
        if not fragments:
            raise StaleWork("research_original_reading_graph_unavailable")
        requests = {}
        for role, keys in ROLE_FIELDS.items():
            pin = job["pins"]["prompts"].get(str(role))
            if pin is None:
                raise StaleWork("research_full_prompt_pin_unavailable")
            prompt = PromptPin.model_validate(pin)
            if (prompt.role != role or prompt.profile_digest != digest(profile)
                or prompt.source_registry_digest != self.registry.digest):
                raise StaleWork("research_full_prompt_pin_changed")
            requests[role] = SpecialistRequest(scope=scope, role=role, field_keys=keys,
                prompt=prompt, fragments=fragments, events=events, assemblies=assemblies,
                evidence=evidence, accepted_decisions=decisions,
                organiser_candidates=tuple(item for item in candidates if item.field_key in keys),
                field_revisions={key:job["fields"][str(key)]["revision"] for key in keys})
        if set(requests) != set(SpecialistRole):
            raise StaleWork("research_complete_specialist_inputs_required")
        return requests

    @staticmethod
    def _graph(specimen, scope):
        """The reading graph: fragments, events, assemblies, native evidence, decision digests.

        The hand-over candidates (``_build_graph``) are not part of this tuple; the events and
        assemblies they ground are."""
        return NativeGenerationRequestFactory._build_graph(specimen, scope)[:5]

    @staticmethod
    def _build_graph(specimen, scope):
        ref = specimen.asset.blob_ref
        if not re.fullmatch(r"[a-f0-9]{64}:[1-9][0-9]*", ref) or ref.partition(":")[0] != specimen.asset.sha256:
            raise StaleWork("research_original_asset_generation_unproved")
        region_map = {item.id:item for item in specimen.run.regions}
        reading_map = {item.id:item for item in specimen.run.observations}
        if len(region_map) != len(specimen.run.regions) or len(reading_map) != len(specimen.run.observations):
            raise StaleWork("research_original_reading_identity_ambiguous")
        fragments, evidence, events, assemblies, decisions = [], [], [], [], []
        # A native Evidence UUID remains the identity. Missing native evidence
        # never becomes a fabricated lookup or an accepted label assembly.
        # The row's identity digests are contracts.digest, the function the publication's evidence
        # provider re-derives them with (canonical_evidence_provider_v2._capture_contexts). The
        # application's storage digest escapes non-ASCII text, so it differs for a quote with an
        # accented letter or a sex sign, and the provider then finds no match for the row and
        # refuses the value that cites it (canonical_capture_missing_actual_evidence). A value that
        # cites a native row (a literal read from an assembly) needs the two to agree.
        for item in specimen.run.evidence:
            evidence.append(EvidenceItem(id=item.id, kind=item.kind, source_id=item.source or "native_evidence",
                locator=item.locator or "native-evidence:"+item.id,
                response_digest=item.digest or digest(item.model_dump(mode="json")),
                source_version="native-evidence-adapter/v1", publisher_assertion_id=digest(item.model_dump(mode="json")),
                excerpt=item.excerpt, retrieved_at=item.created_at, role="supports"))
        seen = set()
        for transcript in specimen.run.transcripts:
            region = region_map.get(transcript.region_id)
            if region is None or region.asset_id != specimen.asset.id:
                raise StaleWork("research_original_region_scope_unproved")
            members = [reading_map.get(identity) for identity in transcript.observation_ids]
            if (not members or any(item is None or item.region_id != region.id for item in members)
                or len({item.id for item in members}) != len(members)
                or {item.observation_id for item in transcript.handoffs} != {item.id for item in members}
                or len(transcript.handoffs) != len(members)):
                raise StaleWork("research_original_handoff_membership_unproved")
            selected = transcript.selected_observation_id
            if transcript.resolved and (selected not in {item.id for item in members}
                or transcript.text != reading_map[selected].literal_text
                or transcript.decision_kind not in {"identical_readings", "first_pass", "human"}):
                raise StaleWork("research_original_transcript_decision_unproved")
            decisions.append("transcript:" + digest(transcript))
            for handoff in transcript.handoffs:
                observation = reading_map[handoff.observation_id]
                if (observation.id in seen or handoff.handed_text != observation.literal_text
                    or handoff.role != ("decided_transcript" if observation.id == selected else "raw_reading")
                    or observation.input_asset_id not in {None, specimen.asset.id}
                    or not re.fullmatch(r"[a-f0-9]{64}", observation.prompt_version)):
                    raise StaleWork("research_original_handoff_literal_unproved")
                seen.add(observation.id)
                deciding = transcript.resolved and handoff.role == "decided_transcript"
                offset = 0
                for ordinal, line in enumerate(observation.literal_text.splitlines(keepends=True)):
                    text = line.rstrip("\r\n")
                    if not text:
                        offset += len(line)
                        continue
                    label, separator, remainder = text.partition(":")
                    key = next((key for key in ALL_FIELDS if str(key) == label.strip()), None)
                    value = remainder.strip() if separator and key is not None else text
                    if not value:
                        offset += len(line)
                        continue
                    begin = offset + (text.find(remainder) + len(remainder) - len(remainder.lstrip())
                        if separator and key is not None else 0)
                    fragment = SourceFragment(id="fragment:" + digest([observation.id,begin,begin+len(value)]),
                        scope=scope, asset_id=specimen.asset.id, asset_generation=ref.partition(":")[2],
                        asset_digest=specimen.asset.sha256, label_id=region.id, region_id=region.id,
                        observation_id=observation.id, reader=observation.route_id, model_id=observation.model_id,
                        prompt_digest=observation.prompt_version, observation_text=observation.literal_text,
                        observation_digest=hashlib.sha256(observation.literal_text.encode()).hexdigest(),
                        start=begin, end=begin+len(value), literal=value, order=ordinal,
                        granularity="line", input_source=handoff.role,
                        geometry=Geometry(coordinate_frame="original_pixel_edges",
                            bounds=(region.x,region.y,region.width,region.height), kind="region",
                            provenance="retained_ordinary_region"), unreadable=bool(observation.unreadable_spans))
                    fragments.append(fragment)
                    kind = (EventKind.DETERMINATION if key == FieldKey.DATE_IDENTIFIED else
                        EventKind.COLLECTING if key in {FieldKey.DATE_VISITED_FROM,FieldKey.DATE_VISITED_TO,FieldKey.COLLECTORS}
                        else EventKind.UNKNOWN)
                    evidence_ids = tuple(item.id for item in specimen.run.evidence if
                        item.kind == "literal" and item.asset_id == specimen.asset.id
                        and item.region_id == region.id and item.excerpt == text
                        and item.locator == "region:"+region.id
                        and set(item.observation_ids) == set(transcript.observation_ids))
                    if not evidence_ids:
                        offset += len(line)
                        continue
                    event = EventHypothesis(id="event:"+digest([fragment.id,str(kind)]), scope=scope,
                        kind=kind, fragment_ids=(fragment.id,), evidence_ids=evidence_ids,
                        reason="explicit_exact_field_key_line" if key is not None else "unstructured_label_event_unqualified",
                        rule_version="exact-field-key-line/v1",
                        status="accepted" if deciding and key is not None and not fragment.unreadable else "proposed",
                        validator_version="exact-field-key-line/v1" if deciding and key is not None and not fragment.unreadable else None)
                    events.append(event)
                    if event.status == "accepted":
                        assemblies.append(assemble_field(assembly_id="assembly:"+digest([fragment.id,str(key)]),
                            scope=scope, field_key=key, fragments=(fragment,), event=event))
                    offset += len(line)
        if seen != set(reading_map):
            raise StaleWork("research_original_readings_not_fully_retained")
        candidates = NativeGenerationRequestFactory._organiser_pass(
            specimen, scope, ref, region_map, reading_map, fragments, events, assemblies)
        return tuple(fragments),tuple(events),tuple(assemblies),tuple(evidence),tuple(decisions),candidates

    @staticmethod
    def _organiser_pass(specimen, scope, ref, region_map, reading_map, fragments, events, assemblies):
        """Second pass: the extractor's stored candidates, located by trusted code.

        For each stored candidate row of each field (``_claims``, both stored shapes), the literal is
        looked for in the lines of the reading the row cites. Exactly one verbatim hit gives a span whose
        offsets are computed here (a stored offset is never a place); anything else is an ungrounded hint
        (reason names why). A located span in the DECIDED reading, of the field's own stored value, for an
        ``ASSEMBLY_FIELDS`` field the validator would accept, in a readable reading, also gets an accepted
        event and an assembly through ``assemble_field``, appended to ``fragments``, ``events`` and
        ``assemblies``. Returns the candidates in field order, at most ``MAX_CANDIDATES_PER_FIELD`` per field
        (a marker says when some were dropped). Nothing here reads a span, an offset or a status from a
        model."""
        decided = {}
        for transcript in specimen.run.transcripts:
            observation = reading_map.get(transcript.selected_observation_id)
            if transcript.resolved and transcript.text and observation is not None:
                decided[transcript.region_id] = (transcript, observation)
        keyed = tuple(assemblies)  # the exact field-key lines' assemblies, before any hand-over assembly
        by_field = {}
        for claim in _claims(specimen, reading_map, decided):
            by_field.setdefault(claim.key, []).append(claim)
        candidates, seen = [], set()
        for key, claims in by_field.items():     # in field-key order
            claims = sorted(claims, key=lambda claim: (not claim.primary, not _cites_decided(claim, decided)))
            dropped = []
            if len(claims) > MAX_CANDIDATES_PER_FIELD:
                claims, dropped = claims[:MAX_CANDIDATES_PER_FIELD - 1], claims[MAX_CANDIDATES_PER_FIELD - 1:]
            built = [NativeGenerationRequestFactory._organiser_candidate(
                specimen, scope, ref, region_map, claim, decided, fragments, events, assemblies, keyed)
                for claim in claims]
            if dropped and dropped[0].literal.strip():
                # Visible, never silent: the field has more candidates than are handed over.
                built.append(_candidate(key, dropped[0].literal.strip()[:MAX_ORGANISER_LITERAL], "ungrounded",
                    "more_candidates_for_the_field_than_are_handed_over",
                    region_id=dropped[0].row.region_id if dropped[0].row is not None else None))
            for item in built:
                if item is not None and item.id not in seen:
                    seen.add(item.id)
                    candidates.append(item)
        return tuple(candidates[:MAX_ORGANISER_CANDIDATES])

    @staticmethod
    def _organiser_candidate(specimen, scope, ref, region_map, claim, decided, fragments, events, assemblies,
                             keyed_assemblies):
        key, row = claim.key, claim.row
        literal = claim.literal.strip()
        if not literal or len(literal) > MAX_ORGANISER_LITERAL:
            return None
        if row is None:
            return _candidate(key, literal, "ungrounded", "no_usable_extractor_row_for_the_literal")
        region_id = row.region_id

        def hint(reason, **where):
            return _candidate(key, literal, "ungrounded", reason, region_id=region_id, label=claim.label, **where)
        observation, entry = claim.observation, decided.get(region_id)
        if observation is None:
            return hint("no_decided_reading_for_the_region")
        text, region = observation.literal_text, region_map[region_id]
        is_decided = entry is not None and entry[1].id == observation.id
        # The extractor's own record of where it read the value: a native evidence row of this region and
        # asset whose quote holds the literal. A row written before the organiser quotes the whole region
        # transcript (and cites every reader); the organiser's rows quote a narrow span of the one reading
        # they cite (_claims has checked that the quote is that reading's text at the stored span). Either way
        # the literal is searched in the cited reading below, and the stored span is not used as a place.
        if (row.asset_id != specimen.asset.id or literal not in row.excerpt or row.excerpt not in text
            or claim.legacy and (not is_decided or row.locator != "region:" + region_id
                or set(row.observation_ids) != set(entry[0].observation_ids))):
            return hint("extractor_quote_does_not_hold_the_literal")
        hits = []
        for ordinal, begin, line in _lines(text):
            at = line.find(literal)
            while at >= 0:
                hits.append((ordinal, begin, line, at))
                at = line.find(literal, at + 1)
        if not hits:
            return hint("literal_spans_more_than_one_line")
        if len(hits) > 1:
            return hint(f"literal_occurs_{len(hits)}_times_in_the_cited_reading")
        ordinal, line_offset, line, at = hits[0]
        start = line_offset + at
        end = start + len(literal)
        where = dict(region_id=region_id, observation_id=observation.id, label=claim.label, start=start, end=end)
        if not is_decided:
            return _candidate(key, literal, "located", "cited_reading_is_not_the_decided_transcript", **where)
        # A keyed line for this field that already carries this very span is the same assembly.
        keyed = [item for item in keyed_assemblies if item.field_key == key]
        by_id = {item.id: item for item in fragments}
        for assembly in keyed:
            fragment = by_id[assembly.fragment_ids[0]]
            if (len(assembly.fragment_ids) == 1 and assembly.interpreted_text == literal
                and (fragment.observation_id, fragment.start, fragment.end) == (observation.id, start, end)):
                return _candidate(key, literal, "grounded", "keyed_line_assembly_holds_the_span", **where,
                    fragment_id=fragment.id, event_id=assembly.event_id, assembly_id=assembly.id,
                    evidence_ids=assembly.evidence_ids)
        if key not in ASSEMBLY_FIELDS:
            return _candidate(key, literal, "located", "hand_over_builds_no_assembly_for_the_field", **where)
        if not claim.primary:
            return _candidate(key, literal, "located", "not_the_stored_field_value", **where)
        if keyed:
            return _candidate(key, literal, "located", "keyed_line_assembly_for_the_field_exists", **where)
        if observation.unreadable_spans:
            return _candidate(key, literal, "located", "decided_reading_has_unreadable_spans", **where)
        if _inside_a_token(line, at, literal):
            return _candidate(key, literal, "located", "literal_starts_or_ends_inside_a_longer_token", **where)
        if _validator_refuses(key, literal):
            return _candidate(key, literal, "located", "validator_would_refuse_the_literal", **where)
        fragment = SourceFragment(id="fragment:" + digest([observation.id, start, end, ORGANISER_RULE]),
            scope=scope, asset_id=specimen.asset.id, asset_generation=ref.partition(":")[2],
            asset_digest=specimen.asset.sha256, label_id=region.id, region_id=region.id,
            observation_id=observation.id, reader=observation.route_id, model_id=observation.model_id,
            prompt_digest=observation.prompt_version, observation_text=text,
            observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=start, end=end,
            literal=literal, order=ordinal, granularity="span", input_source="decided_transcript",
            geometry=Geometry(coordinate_frame="original_pixel_edges",
                bounds=(region.x, region.y, region.width, region.height), kind="region",
                provenance="retained_ordinary_region"), unreadable=False)
        kind = (EventKind.DETERMINATION if key == FieldKey.DATE_IDENTIFIED else
            EventKind.COLLECTING if key in {FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.COLLECTORS}
            else EventKind.UNKNOWN)
        event = EventHypothesis(id="event:" + digest([fragment.id, str(key), ORGANISER_RULE]), scope=scope,
            kind=kind, fragment_ids=(fragment.id,), evidence_ids=(row.id,),
            reason="extractor_literal_verbatim_in_the_decided_reading", rule_version=ORGANISER_RULE,
            status="accepted", validator_version=ORGANISER_RULE)
        assembly = assemble_field(assembly_id="assembly:" + digest([fragment.id, str(key), ORGANISER_RULE]),
            scope=scope, field_key=key, fragments=(fragment,), event=event)
        if fragment.id not in by_id:
            fragments.append(fragment)
        events.append(event)
        assemblies.append(assembly)
        return _candidate(key, literal, "grounded", "verbatim_in_one_line_of_the_decided_reading", **where,
            fragment_id=fragment.id, event_id=event.id, assembly_id=assembly.id, evidence_ids=assembly.evidence_ids)


def _cites_decided(claim, decided):
    """The claim's row cites the decided reading of its region."""
    entry = decided.get(claim.row.region_id) if claim.row is not None else None
    return entry is not None and claim.observation is not None and entry[1].id == claim.observation.id


@dataclass(frozen=True)
class _Claim:
    """One candidate as the ordinary run stored it: the literal the extractor claimed and its evidence row.

    ``row`` is None for a supported field that cites no extractor row; ``observation`` is the reading the row
    cites (None: a whole-region row of a region with no decided reading); ``legacy`` marks a whole-region row;
    ``primary``: the row carries the field's own stored value."""

    key: FieldKey
    literal: str
    row: object
    observation: object
    legacy: bool
    primary: bool
    label: str | None = None


# The ordinary extraction call's evidence source, the same for both stored shapes below; the deterministic
# keyed-line parser's rows (source "label": one row per `field_key: value` line, locator `region:<id>`, the
# line as the excerpt) are read as whole-region rows too, so a keyed field behaves as it always did.
EXTRACTOR_ROW_SOURCE = "bounded_extraction_v1"
KEYED_ROW_SOURCE = "label"
# What #262 (the organiser, application/organiser.py: parse_locator) stores in an evidence row's locator.
_READING_LOCATOR = re.compile(
    r"reading:(?P<label>[0-9]+[A-Z]):(?P<observation>[^#;\s]+)"
    r"#quote=(?P<qs>[0-9]+)-(?P<qe>[0-9]+);literal=(?P<ls>[0-9]+)-(?P<le>[0-9]+)")


def _claims(specimen, reading_map, decided):
    """The extractor's candidates in ``run.fields``, in field-key order, both stored shapes.

    Compatibility with #262 (the organiser), without importing it (it may merge before or after this
    branch). Two shapes of evidence row carry a candidate, both of source ``bounded_extraction_v1``:
    - the whole-region row written today: locator ``region:<region_id>``, the whole region transcript as
      the excerpt, every reader's observation id. It stands for the literal its field stored, and only
      when it is the field's first row (later rows of an AMBIGUOUS field carry a literal the run never
      stored); it cites the region's decided reading. (#262's reader returns it only when the literal lies
      in the excerpt; here a literal the quote does not hold is handed over as a hint, with that reason.)
      A supported field that cites no extractor row at all is handed over as a hint too;
    - #262's row: locator ``reading:<label>:<observation id>#quote=a-b;literal=c-d``, ONE observation id,
      the narrow quote as the excerpt; one row per candidate of every reading of the label (the other
      reader's and an undecided label's included), whatever the field's state.
    The uniform structure is what #262's ``organiser.stored_candidates`` returns (field key, literal,
    label, observation id, region id, legacy or not; ``primary`` = the field's own value). After #262
    merges this reader can be replaced by that function in a follow-up. The stored spans of the second
    shape are used for one thing only: to name the string the extractor claimed (a row whose quote or
    literal span does not fit the reading it names is skipped, as #262's reader skips it). Where the
    literal sits is searched again in the reading by trusted code; a stored offset is never a place.
    A keyed line's row (source ``label``, locator ``region:<id>``, the line as the excerpt; #262's reader skips
    it) is read like a whole-region row, so that a keyed field is handed over as before: grounded by naming the
    keyed pass's own assembly of that span."""
    rows = {item.id: item for item in specimen.run.evidence}
    for name in sorted(specimen.run.fields):
        try:
            key = FieldKey(name)
        except ValueError:
            continue
        value, primary_taken, claimed_any = specimen.run.fields[name], False, False
        for place, evidence_id in enumerate(value.evidence_ids):
            row = rows.get(evidence_id)
            if row is None or row.source not in {EXTRACTOR_ROW_SOURCE, KEYED_ROW_SOURCE} or row.kind != "literal" \
                    or not row.region_id:
                continue
            found = _READING_LOCATOR.fullmatch(row.locator or "")
            if found is not None and row.source == EXTRACTOR_ROW_SOURCE:
                observation = reading_map.get(found["observation"])
                if observation is None or tuple(row.observation_ids) != (observation.id,) or (
                        observation.region_id != row.region_id):
                    continue
                text = observation.literal_text
                qs, qe, ls, le = (int(found[part]) for part in ("qs", "qe", "ls", "le"))
                if text[qs:qe] != row.excerpt or not qs <= ls < le <= qe:
                    continue
                claimed, legacy, label = text[ls:le], False, found["label"]
            elif place == 0 and row.locator == "region:" + row.region_id and isinstance(value.literal, str):
                entry = decided.get(row.region_id)
                claimed, observation, legacy, label = value.literal, entry[1] if entry else None, True, None
            else:
                continue
            primary = (value.state == ValueState.SUPPORTED and claimed == value.literal and not primary_taken)
            primary_taken = primary_taken or primary
            claimed_any = True
            yield _Claim(key, claimed, row, observation, legacy, primary, label)
        if not claimed_any and value.state == ValueState.SUPPORTED and isinstance(value.literal, str):
            # A stored value with no usable row to place it in: handed over as a hint, never placed.
            yield _Claim(key, value.literal, None, None, True, False)


def _inside_a_token(line, at, literal):
    """The literal starts or ends inside a longer alphanumeric token of its line (``12345`` in
    ``FMNH INS 0012345``, ``00123`` in ``00123456``)."""
    before = line[at - 1] if at > 0 else ""
    after = line[at + len(literal)] if at + len(literal) < len(line) else ""
    return ((bool(before) and literal[0].isalnum() and before.isalnum())
            or (bool(after) and literal[-1].isalnum() and after.isalnum()))


def _validator_refuses(key, written):
    """The shape rules evidence.validate_resolution applies to a literal read from an assembly, which a
    resolution can never satisfy: a read-only copy of evidence.py's checks, so that trusted code does not
    build an accepted assembly the validator is certain to refuse (a refused resolution costs the specialist's
    one retry and then its whole role). test_organiser_handover.py checks this against the validator."""
    if key == FieldKey.FMNH_INS_NUMBER:
        try:
            catalog_literal(written)
        except EvidenceError:
            return True
    if key == FieldKey.COLLECTORS and (re.search(r"\d", written) or not re.search(r"[^\W\d_]{2}", written, re.UNICODE)):
        return True
    if key == FieldKey.COLLECTION_CODE and written.upper().replace(" ", "") in {"FMNHINS", "FMNH-INS"}:
        return True
    return key in {FieldKey.HABITAT, FieldKey.COLLECTION_METHOD} and (
        not re.search(r"[^\W\d_]{2}", written, re.UNICODE)
        or re.fullmatch(r"[A-Za-z0-9]+(?:[-./][A-Za-z0-9]+)+", written) is not None and re.search(r"\d", written) is not None)


def _lines(text):
    """(ordinal, offset of the line in the reading, the line without its \\r\\n) for every line,
    split exactly as the keyed-line pass splits them."""
    offset = 0
    for ordinal, line in enumerate(text.splitlines(keepends=True)):
        yield ordinal, offset, line.rstrip("\r\n")
        offset += len(line)


def _candidate(key, literal, status, reason, **fields):
    identity = digest([ORGANISER_SOURCE, str(key), literal, fields.get("region_id"), fields.get("observation_id"),
        fields.get("start"), fields.get("end")])
    return OrganiserCandidate(id="organiser:" + identity, field_key=key, literal=literal, source=ORGANISER_SOURCE,
        status=status, reason=reason, **fields)
