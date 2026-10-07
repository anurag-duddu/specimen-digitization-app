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
   becomes an event or assembly. Five literal fields may ground from a decided reading or
   unanimous raw readers. Collecting dates require an explicit event line or exact
   same-label collector/locality context; determination dates require their explicit event.
   Elevation assertions require explicit units, parser-supported agreement or a verified
   decided transcript, and collision checks before they may ground.

An event or assembly of the second kind is "the extractor proposed this value and
trusted code found it verbatim in the named reading(s)". For the five literal
fields it is not a semantic check: the specialist still verifies the field's meaning.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal

from specimen_digitization.application.active_graph import unpack
from specimen_digitization.application.domain import ValueState
from specimen_digitization.application.field_harness import labelled
from specimen_digitization.application.organiser import (
    SOURCE as ORGANISER_ROW_SOURCE, extraction_readings, reading_texts_of, stored_candidates,
)
from specimen_digitization.application.storage import digest as canonical_digest
from .contracts import (
    ALL_FIELDS, MAX_ORGANISER_CANDIDATES, MAX_ORGANISER_LITERAL, ROLE_FIELDS, CollectionProfile,
    EvidenceItem, EventHypothesis, EventKind, FieldKey, Geometry, OrganiserCandidate, PromptPin,
    SourceFragment, SpecialistRequest, SpecialistRole, digest,
)
from .evidence import (
    EvidenceError, _MEASUREMENT, _MEASUREMENT_NUMBER, assemble_field, catalog_literal,
    parse_measurement, parse_temporal,
)
from .persistence import StaleWork

# The proposer behind the hand-over today: the ordinary extraction step (application/harness.py).
ORGANISER_SOURCE = "extractor"
# What an organiser event's "accepted" status means: extractor-proposed, verbatim in its named
# reading, and qualified by the field's trusted settlement rule. Existing proof objects keep
# their original version; this adapter creates new v6 events and fragments only.
ORGANISER_RULE = "organiser-verbatim-span/v6"
# The fields an extractor literal becomes an accepted assembly for: the five literal fields that
# no source this deployment offers can ground and that the validator resolves from a complete
# literal assembly alone (evidence.py literal_fields). Date/elevation fields require the
# additional _qualified_special_assemblies check. Other fields' candidates are carried
# located (or ungrounded) and get no assembly, each for its own reason:
# - taxon and the geography fields resolve from a lookup (GBIF, GEOLocate); an assembly would
#   make the validator require the query to equal the assembly text (taxon) and change what a
#   specialist cites (the reading), for no gain; precise_location also resolves from GEOLocate;
# - verbatim_dts and identified_by_irn have no resolved path.
ASSEMBLY_FIELDS = frozenset((FieldKey.FMNH_INS_NUMBER, FieldKey.COLLECTION_CODE, FieldKey.HABITAT,
    FieldKey.COLLECTION_METHOD, FieldKey.COLLECTORS))
COLLECTING_DATE_FIELDS = (FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO)
ELEVATION_FIELDS = (FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
    FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT)
_COLLECTING_DATE_LINE = re.compile(
    r"^\s*(?:collection date|collecting date|date collected|collected(?: on)?)\s*[:=]\s*", re.IGNORECASE)
_DETERMINATION_DATE_LINE = re.compile(
    r"^\s*(?:determination date|date identified|date determined|identified on|determined on)\s*[:=]\s*",
    re.IGNORECASE)
# Scan with the settlement parser's own grammar, without its whole-input anchors.
# Number boundaries force complete numeric groups instead of a prefix such as
# "1" from "1,300". Unit boundaries force full words rather than "m" from
# "meters", while permitting punctuation-separated OCR assertions like
# "1200 m.1300 m". A scanner hit can only veto grounding, never grant an assembly;
# the selected candidate still has the stricter complete-span qualification.
_RETAINED_MEASUREMENT = re.compile(
    r"(?<!\w)" + _MEASUREMENT.pattern[1:-1].replace(
        _MEASUREMENT_NUMBER, _MEASUREMENT_NUMBER + r"(?![\d.,])") + r"(?!\w)", re.IGNORECASE)
_LOCALITY_CONTEXT_FIELDS = frozenset((FieldKey.COUNTRY, FieldKey.PROVINCE_STATE,
    FieldKey.COUNTY, FieldKey.CITY, FieldKey.PRECISE_LOCATION))
_NON_COLLECTING_CONTEXT = re.compile(
    r"\b(?:det(?:ermination|ermined)?|identified|identification|prep(?:aration|ared)?|slide|genitalia|terminalia)\b",
    re.IGNORECASE)
_PREPARATION_CODE = re.compile(r"^(?:[IVX]+|\d{1,2})-\d{1,2}-(?:\d{2}|\d{4})-[A-Za-z0-9]+\.?$", re.IGNORECASE)
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
        (reason names why). A located literal-field span may become an accepted assembly when the
        ordinary reading settlement agrees. Date/elevation spans additionally require the event/unit
        and source-agreement checks in ``_qualified_special_assemblies``. Both kinds append
        their event and assembly through ``assemble_field``; a collision or silent reader cannot be
        hidden by the candidate cap.
        Returns the candidates in field order, at most ``MAX_CANDIDATES_PER_FIELD`` per field
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
        qualified = _qualified_special_assemblies(specimen, by_field, reading_map, decided, keyed)
        candidates, seen = [], set()
        for key, claims in by_field.items():     # in field-key order
            consensus = _claims_settle_field(specimen, key, claims, reading_map, decided)
            unreadable = consensus and any(claim.observation is not None
                and claim.observation.unreadable_spans for claim in claims
                if claim.row is not None and (claim.row.region_id not in decided
                    or _cites_decided(claim, decided)))
            claims = sorted(claims, key=lambda claim: (not claim.primary, not _cites_decided(claim, decided)))
            dropped = []
            if len(claims) > MAX_CANDIDATES_PER_FIELD:
                claims, dropped = claims[:MAX_CANDIDATES_PER_FIELD - 1], claims[MAX_CANDIDATES_PER_FIELD - 1:]
            built = []
            for claim in claims:
                special_evidence = qualified.get((key, claim.row.id)) if claim.row is not None else None
                context_fragments = ()
                if (special_evidence and key in COLLECTING_DATE_FIELDS and claim.observation is not None
                    and not _qualified_line(claim.observation.literal_text, claim.literal, _COLLECTING_DATE_LINE)):
                    context_rows = set(eid for peer in by_field[key] if peer.observation is not None
                        for eid in _collecting_context_evidence(specimen, by_field, peer.observation, peer.literal))
                    context_claims = [peer for group in by_field.values() for peer in group
                        if peer.row is not None and peer.row.id in context_rows]
                    context_fragments = tuple(fragment.id for fragment in fragments
                        if fragment.granularity == "line" and any(peer.observation is not None
                            and fragment.observation_id == peer.observation.id
                            and peer.literal in fragment.literal for peer in context_claims))
                supporting_evidence = special_evidence or tuple(all_claim.row.id for all_claim in by_field[key]
                    if all_claim.row is not None and all_claim.literal == claim.literal)
                built.append(NativeGenerationRequestFactory._organiser_candidate(
                    specimen, scope, ref, region_map, claim, decided, fragments, events, assemblies, keyed,
                    consensus or special_evidence is not None, unreadable and special_evidence is None,
                    supporting_evidence, qualified_special=special_evidence is not None,
                    context_fragment_ids=context_fragments))
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
                             keyed_assemblies, consensus=False, unreadable=False, supporting_evidence_ids=(),
                             qualified_special=False, context_fragment_ids=()):
        key, row = claim.key, claim.row
        literal = claim.literal.strip()
        if not literal or len(literal) > MAX_ORGANISER_LITERAL:
            return None
        if row is None:
            return _candidate(key, literal, "ungrounded", "no_usable_extractor_row_for_the_literal")
        region_id = row.region_id

        def hint(reason, **where):
            return _candidate(key, literal, "ungrounded", reason, region_id=region_id,
                label=claim.label, ident=row.id, **where)
        observation, entry = claim.observation, decided.get(region_id)
        if observation is None:
            return hint("no_decided_reading_for_the_region" if claim.legacy
                        else "reading_not_in_the_request")
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
            return hint("reading_not_in_the_request" if row.asset_id != specimen.asset.id
                        or observation.region_id != region_id else "extractor_quote_does_not_hold_the_literal")
        hits = []
        for ordinal, begin, line in _lines(text):
            at = line.find(literal)
            while at >= 0:
                hits.append((ordinal, begin, line, at))
                at = line.find(literal, at + 1)
        if not hits:
            return hint("literal_spans_more_than_one_line")
        if len(hits) > 1:
            return hint(f"literal_occurs_{len(hits)}_times_in_the_reading")
        ordinal, line_offset, line, at = hits[0]
        start = line_offset + at
        end = start + len(literal)
        where = dict(region_id=region_id, observation_id=observation.id, label=claim.label, start=start, end=end)
        is_undecided = entry is None
        if not is_decided and not is_undecided:
            stored = specimen.run.fields.get(str(key))
            reason = ("only_the_other_reader_states_it" if stored is None or stored.literal is None
                else "other_reader_of_a_decided_label_is_not_the_value" if claim.primary and not consensus
                else "states_the_literal_the_grounded_reading_states" if stored.literal == literal and consensus
                else "other_reader_states_another_literal")
            return _candidate(key, literal, "located", reason,
                **where, evidence_ids=(row.id,))
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
        if key not in ASSEMBLY_FIELDS and not qualified_special:
            return _candidate(key, literal, "located", "hand_over_builds_no_assembly_for_the_field", **where,
                evidence_ids=(row.id,))
        if not consensus:
            stored = specimen.run.fields.get(str(key))
            reason = ("readings_differ_no_value_chosen" if stored is None or stored.literal is None
                else "not_every_reading_of_the_label_states_it")
            return _candidate(key, literal, "located", reason, **where,
                evidence_ids=(row.id,))
        if unreadable:
            return _candidate(key, literal, "located", "reading_has_unreadable_spans", **where,
                evidence_ids=(row.id,))
        if not claim.primary and not qualified_special:
            return _candidate(key, literal, "located", "states_the_literal_the_grounded_reading_states", **where,
                evidence_ids=(row.id,))
        if keyed:
            return _candidate(key, literal, "located", "keyed_line_assembly_for_the_field_exists", **where)
        if observation.unreadable_spans:
            return _candidate(key, literal, "located", "reading_has_unreadable_spans", **where,
                evidence_ids=(row.id,))
        if _inside_a_token(line, at, literal):
            return _candidate(key, literal, "located", "literal_starts_or_ends_inside_a_longer_token", **where,
                evidence_ids=(row.id,))
        if _validator_refuses(key, literal):
            return _candidate(key, literal, "located", "validator_would_refuse_the_literal", **where,
                evidence_ids=(row.id,))
        fragment = SourceFragment(id="fragment:" + digest([observation.id, start, end, ORGANISER_RULE]),
            scope=scope, asset_id=specimen.asset.id, asset_generation=ref.partition(":")[2],
            asset_digest=specimen.asset.sha256, label_id=region.id, region_id=region.id,
            observation_id=observation.id, reader=observation.route_id, model_id=observation.model_id,
            prompt_digest=observation.prompt_version, observation_text=text,
            observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=start, end=end,
            literal=literal, order=ordinal, granularity="span",
            input_source="decided_transcript" if is_decided else "raw_reading",
            geometry=Geometry(coordinate_frame="original_pixel_edges",
                bounds=(region.x, region.y, region.width, region.height), kind="region",
                provenance="retained_ordinary_region"), unreadable=False)
        kind = (EventKind.DETERMINATION if key == FieldKey.DATE_IDENTIFIED else
            EventKind.COLLECTING if key in {FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.COLLECTORS}
            else EventKind.UNKNOWN)
        event = EventHypothesis(id="event:" + digest([fragment.id, str(key), ORGANISER_RULE]), scope=scope,
            kind=kind, fragment_ids=(fragment.id, *context_fragment_ids), evidence_ids=supporting_evidence_ids or (row.id,),
            reason=(("parser_qualified_elevation_from_decided_transcript" if is_decided else
                     "parser_qualified_elevation_agreement_across_readers")
                    if qualified_special and key in ELEVATION_FIELDS else
                    "parser_qualified_collecting_locality_context_across_readers"
                    if qualified_special and key in COLLECTING_DATE_FIELDS
                    and not _qualified_line(text, literal, _COLLECTING_DATE_LINE) else
                    "explicit_event_or_unit_line_unanimous_across_readers" if qualified_special else
                    "organiser_literal_settled_and_verbatim_in_the_reading"), rule_version=ORGANISER_RULE,
            status="accepted", validator_version=ORGANISER_RULE)
        assembly = assemble_field(assembly_id="assembly:" + digest([fragment.id, str(key), ORGANISER_RULE]),
            scope=scope, field_key=key, fragments=(fragment,), event=event)
        if fragment.id not in by_id:
            fragments.append(fragment)
        events.append(event)
        assemblies.append(assembly)
        return _candidate(key, literal, "grounded", "verbatim_in_one_line_of_the_reading", **where,
            fragment_id=fragment.id, event_id=event.id, assembly_id=assembly.id, evidence_ids=assembly.evidence_ids)


def _qualified_special_assemblies(specimen, by_field, reading_map, decided, keyed):
    """Qualify event-specific dates and complete written elevation assertions.

    Dates require every retained reader to quote the same complete literal on an
    explicit event line or an independently evidenced collecting/locality label.
    Determination dates always require their explicit event. Elevations use parser-supported
    complete unit assertions, ranges/qualifiers and harmless formatting agreement,
    or a verified decided transcript. Missing units, unreadable text or
    conflicting quantities never ground.
    """
    qualified = _qualified_elevation_assemblies(specimen, by_field, reading_map, decided, keyed)
    groups = (
        (COLLECTING_DATE_FIELDS, (FieldKey.DATE_VISITED_FROM,), _COLLECTING_DATE_LINE),
        ((FieldKey.DATE_IDENTIFIED,), (FieldKey.DATE_IDENTIFIED,),
         _DETERMINATION_DATE_LINE),
    )
    for fields, preferred, marker in groups:
        claims = [claim for key in fields for claim in by_field.get(key, ())]
        if not claims or any(item.field_key in fields for item in keyed):
            continue
        literals = {claim.literal.strip() for claim in claims}
        regions = {claim.row.region_id for claim in claims if claim.row is not None}
        if len(literals) != 1 or not next(iter(literals)) or len(regions) != 1:
            continue
        literal = next(iter(literals))
        region_id = next(iter(regions))
        readers = [item for item in reading_map.values() if item.region_id == region_id]
        if (len(readers) < 2 or len({item.id for item in readers}) != len(readers)
            or any(not item.literal_text.strip() or item.unreadable_spans for item in readers)):
            continue
        try:
            parse_temporal(literal)
        except EvidenceError:
            continue
        citing = set()
        sound = True
        for claim in claims:
            row, observation = claim.row, claim.observation
            if (claim.legacy or row is None or observation is None
                or row.asset_id != specimen.asset.id or row.region_id != region_id
                or observation.region_id != region_id or tuple(row.observation_ids) != (observation.id,)
                or literal not in row.excerpt or row.excerpt not in observation.literal_text):
                sound = False
                break
            if not _qualified_line(observation.literal_text, literal, marker):
                context = (_collecting_context_evidence(specimen, by_field, observation, literal)
                    if fields == COLLECTING_DATE_FIELDS else ())
                if not context:
                    sound = False
                    break
            citing.add(observation.id)
        if not sound or citing != {item.id for item in readers}:
            continue
        chosen = None
        for key in preferred:
            for claim in by_field.get(key, ()):
                field = specimen.run.fields.get(str(key))
                if (not claim.primary or field is None or field.state != ValueState.SUPPORTED
                    or field.literal != literal):
                    continue
                selected = decided.get(region_id)
                if selected is not None and (claim.observation is None
                                             or claim.observation.id != selected[1].id):
                    continue
                chosen = claim
                break
            if chosen is not None:
                break
        if chosen is None:
            continue
        # This evidence is the extractor's independently verified quote from
        # every reader; the one assembly uses a single exact source span.
        evidence_ids = tuple(dict.fromkeys(claim.row.id for claim in claims))
        qualified[(chosen.key, chosen.row.id)] = evidence_ids
    return qualified


def _bare_collecting_date_line(line, literal):
    """A whole date, optionally followed by a separately written elevation.

    A prefix of a preparation code such as IX-17-66-1 is not a complete span.
    The date parser supplies precision and century policy; no context invents a year.
    """
    line = line.strip()
    if _PREPARATION_CODE.fullmatch(line) or _PREPARATION_CODE.fullmatch(literal):
        return False
    if line == literal:
        return True
    if not line.startswith(literal) or not line[len(literal):].startswith((" ", "\t")):
        return False
    try:
        parse_measurement(line[len(literal):].strip())
    except EvidenceError:
        return False
    return True


def _complete_collecting_dates(line):
    """Inspect complete written dates, including a date/elevation line."""
    stripped = line.strip()
    prefix = _COLLECTING_DATE_LINE.match(stripped)
    if prefix is not None:
        stripped = stripped[prefix.end():].strip()
    for end in (len(stripped), *(match.start() for match in re.finditer(r"\s+", stripped))):
        literal = stripped[:end]
        if not _bare_collecting_date_line(stripped, literal):
            continue
        try:
            parsed = parse_temporal(literal)
        except EvidenceError:
            continue
        yield parsed.canonical, parsed.precision, parsed.century_rule


def _collecting_context_evidence(specimen, by_field, observation, literal):
    """Ground collecting context from independent exact quotes on this label.

    The extractor's field assignment alone is insufficient: its date must be
    complete, its collector and locality spans must be independently quoted,
    and the retained reading must contain no competing complete event date.
    """
    text = observation.literal_text
    if _NON_COLLECTING_CONTEXT.search(text):
        return ()
    matching = [line for _, _, line in _lines(text) if literal in line]
    if len(matching) != 1 or not _bare_collecting_date_line(matching[0], literal):
        return ()
    parsed = parse_temporal(literal)
    expected = (parsed.canonical, parsed.precision, parsed.century_rule)
    dates = [identity for _, _, line in _lines(text) for identity in _complete_collecting_dates(line)]
    if dates != [expected]:
        return ()
    context = {"collector": [], "locality": []}
    for key in (FieldKey.COLLECTORS, *_LOCALITY_CONTEXT_FIELDS):
        for claim in by_field.get(key, ()):
            row = claim.row
            if (claim.legacy or row is None or claim.observation is None
                or claim.observation.id != observation.id or row.asset_id != specimen.asset.id
                or row.region_id != observation.region_id or tuple(row.observation_ids) != (observation.id,)
                or not claim.literal.strip() or not re.search(r"[A-Za-z]", claim.literal)
                or claim.literal not in row.excerpt or row.excerpt not in text):
                continue
            hits = [(line, line.find(claim.literal)) for _, _, line in _lines(text) if claim.literal in line]
            if (len(hits) != 1 or hits[0][0].count(claim.literal) != 1
                or _inside_a_token(hits[0][0], hits[0][1], claim.literal)):
                continue
            if key == FieldKey.COLLECTORS and re.search(r"\d", claim.literal):
                continue
            try:
                parse_temporal(claim.literal)
            except EvidenceError:
                pass
            else:
                continue
            context["collector" if key == FieldKey.COLLECTORS else "locality"].append(row.id)
    if not context["collector"] or not context["locality"]:
        return ()
    return tuple(dict.fromkeys((*context["collector"], *context["locality"])))


def _measurement_identity(measurement):
    """Formatting never changes quantities; units and written qualifiers still matter."""
    return (Decimal(measurement.from_quantity), Decimal(measurement.to_quantity),
        measurement.from_unit, measurement.to_unit, measurement.single,
        tuple(item.casefold() for item in measurement.qualifiers),
        Decimal(measurement.uncertainty) if measurement.uncertainty is not None else None)


def _qualified_elevation_line(text, literal):
    """One complete exact unit-bearing span, including on a narrative locality line.

    The extractor proposes the field meaning; trusted code proves its written
    assertion. Do not silently discard a sign, qualifier, range or uncertainty
    next to that span. The specialist still receives the original whole reading.
    """
    matching = [(line, at) for _, _, line in _lines(text)
        for at in range(len(line)) if line.startswith(literal, at)]
    if len(matching) != 1:
        return False
    line, at = matching[0]
    if _inside_a_token(line, at, literal):
        return False
    before, after = line[:at].rstrip(), line[at + len(literal):].lstrip()
    if (before and before[-1] in "+-–—~≈±"
        or at and line[at - 1] == "." and literal[0].isdigit()
        or at > 1 and line[at - 1] == "," and line[at - 2].isdigit() and literal[0].isdigit()
        or re.search(r"(?:^|\W)(?:c\.?|ca\.?|about|approx\.?|to)\s*$", before, re.IGNORECASE)
        or re.match(r"(?:[-–—±]|\+/-|to\b)", after, re.IGNORECASE)):
        return False
    return True


def _qualified_elevation_assemblies(specimen, by_field, reading_map, decided, keyed):
    """Ground a complete elevation supported by all readers or a decided transcript.

    All retained claims must parse to the same written quantities, units and
    qualifiers. Every undecided reader must contribute; a verified decided
    transcript may stand alone. Other readings and conflicting claims remain
    available as located alternatives rather than being erased or guessed.
    """
    if any(item.field_key in ELEVATION_FIELDS for item in keyed):
        return {}
    claims = [claim for key in ELEVATION_FIELDS for claim in by_field.get(key, ())]
    regions = {claim.row.region_id for claim in claims if claim.row is not None}
    if not claims or len(regions) != 1:
        return {}
    region_id = next(iter(regions))
    readers = [item for item in reading_map.values() if item.region_id == region_id]
    selected = decided.get(region_id)
    expected = ({selected[1].id} if selected is not None else {item.id for item in readers})
    if (not expected or len({item.id for item in readers}) != len(readers)
        or selected is None and (len(readers) < 2 or any(not item.literal_text.strip()
                                                      or item.unreadable_spans for item in readers))):
        return {}
    identity, citing = None, set()
    for claim in claims:
        row, observation, literal = claim.row, claim.observation, claim.literal.strip()
        if (claim.legacy or row is None or observation is None or not literal
            or row.asset_id != specimen.asset.id or row.region_id != region_id
            or observation.region_id != region_id or observation.unreadable_spans
            or tuple(row.observation_ids) != (observation.id,)
            or literal not in row.excerpt or row.excerpt not in observation.literal_text
            or not _qualified_elevation_line(observation.literal_text, literal)):
            return {}
        try:
            measurement = parse_measurement(literal)
        except EvidenceError:
            return {}
        endpoint_unit = measurement.from_unit if "_from_" in str(claim.key) else measurement.to_unit
        if not str(claim.key).endswith("_" + endpoint_unit):
            return {}
        parsed_identity = _measurement_identity(measurement)
        if identity is not None and identity != parsed_identity:
            return {}
        identity = parsed_identity
        citing.add(observation.id)
    if not expected <= citing:
        return {}
    # Extractor rows are proposals, not an exhaustive inventory of the reading.
    # Check every retained reader of the same label, including an unclaimed peer
    # of a decided transcript, before treating one proposed assertion as settled.
    # A silent reader remains allowed by the decided-transcript rule; a contrary
    # written unit assertion does not become silent just because extraction omitted it.
    for observation in readers:
        for match in _RETAINED_MEASUREMENT.finditer(observation.literal_text):
            try:
                retained = parse_measurement(match.group().strip())
            except EvidenceError:
                continue
            if _measurement_identity(retained) != identity:
                return {}
    eligible = [claim for claim in claims if selected is None or claim.observation.id == selected[1].id]
    if not eligible:
        return {}
    # Harmless formatting differences can leave the ordinary field AMBIGUOUS,
    # with no primary row. Qualify a retained source assertion directly rather
    # than fabricating a field literal or changing that ordinary field state.
    chosen = min(eligible, key=lambda claim: not claim.primary)
    # A grounded candidate's immutable native evidence must contain its exact
    # literal. Other formatting-equivalent readings retain their own located
    # candidates and evidence; all were checked above, none is rewritten.
    evidence_ids = tuple(dict.fromkeys(claim.row.id for claim in claims
        if claim.literal.strip() == chosen.literal.strip()))
    return {(chosen.key, chosen.row.id): evidence_ids}


def _qualified_line(text, literal, marker, *, allow_full_line=False):
    """Require a unique exact span and a complete explicit event/unit line."""
    matching = []
    for _, _, line in _lines(text):
        if literal in line:
            matching.extend((line, at) for at in range(len(line)) if line.startswith(literal, at))
    if len(matching) != 1:
        return False
    line, _ = matching[0]
    prefix = marker.match(line)
    return prefix is not None and (line[prefix.end():].strip() == literal
                                   or allow_full_line and line.strip() == literal)


def _cites_decided(claim, decided):
    """The claim's row cites the decided reading of its region."""
    entry = decided.get(claim.row.region_id) if claim.row is not None else None
    return entry is not None and claim.observation is not None and entry[1].id == claim.observation.id


def _claims_settle_field(specimen, key, claims, reading_map, decided):
    """Recheck the stage-7 reading rule before accepting an organiser assembly.

    The ordinary field value is a proposal. A decided label contributes only its
    selected reading; an undecided label contributes a value only if every
    nonempty reader independently states that one literal. Every label that
    states the field must agree. This checks all stored rows before the five
    candidate handover cap is applied, so truncation cannot hide a conflict.
    """
    value = specimen.run.fields.get(str(key))
    if (value is None or value.state != ValueState.SUPPORTED or not isinstance(value.literal, str)
        or not value.literal.strip()):
        return False
    own: dict[str, dict[str, set[str]]] = {}
    for claim in claims:
        row, observation = claim.row, claim.observation
        if row is None or observation is None or row.asset_id != specimen.asset.id:
            return False
        if (row.region_id != observation.region_id or claim.literal not in row.excerpt
            or row.excerpt not in observation.literal_text):
            return False
        region_id = row.region_id
        selected = decided.get(region_id)
        if selected is not None and selected[1].id != observation.id:
            continue  # The other reader is evidence beside a decided transcript, never a vote.
        own.setdefault(region_id, {}).setdefault(observation.id, set()).add(claim.literal)
    if not own:
        return False
    for region_id, readers in own.items():
        if region_id in decided:
            if readers.get(decided[region_id][1].id) != {value.literal}:
                return False
            continue
        expected = {item.id for item in reading_map.values()
            if item.region_id == region_id and item.literal_text.strip()}
        if not expected or set(readers) != expected or any(texts != {value.literal}
                                                         for texts in readers.values()):
            return False
    return True


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


KEYED_ROW_SOURCE = "label"


def _claims(specimen, reading_map, decided):
    """Read both extractor row shapes through the organiser's one read contract.

    Keyed-line parser rows predate the organiser and already have an accepted
    assembly, so they keep a small explicit compatibility path. A supported
    field whose cited rows cannot be read is still handed over as an ungrounded
    hint. The stored offsets name the model's proposed literal only; trusted
    code independently searches the named reading for its span.
    """
    run = specimen.run
    rows = {item.id: item for item in run.evidence}
    names = labelled(extraction_readings(run))
    stored = {}
    for item in stored_candidates(run.fields, run.evidence, reading_texts_of(run)):
        stored.setdefault(item.field_key, []).append(item)
    for name in sorted(specimen.run.fields):
        try:
            key = FieldKey(name)
        except ValueError:
            continue
        value, claimed_any = specimen.run.fields[name], False
        for item in stored.get(name, ()):
            row = rows[item.evidence_id]
            if item.legacy:
                entry = decided.get(item.region_id)
                observation = entry[1] if entry else None
            else:
                named = names.get(item.label)
                observation = reading_map.get(item.observation_id)
                if (named is None or observation is None or named.observation_id != observation.id
                    or named.region_id != item.region_id or named.text != observation.literal_text
                    or tuple(row.observation_ids) != (observation.id,)):
                    # Retain the model's row as an ungrounded hint. An invalid
                    # row must also prevent a different row from grounding a
                    # stale supported value by hiding the disagreement.
                    observation = None
            claimed_any = True
            yield _Claim(key, item.literal, row, observation, item.legacy, item.primary, item.label)
        if not claimed_any and value.state == ValueState.SUPPORTED and isinstance(value.literal, str):
            # A pre-organiser whole-region row with a broken quote remains an
            # explicit ungrounded hint, preserving the reason the old handover
            # gave for it. The shared reader rightly excludes it as evidence.
            for evidence_id in value.evidence_ids:
                row = rows.get(evidence_id)
                if (row is None or row.source != ORGANISER_ROW_SOURCE or row.kind != "literal"
                    or not row.region_id or row.locator != "region:" + row.region_id):
                    continue
                entry = decided.get(row.region_id)
                claimed_any = True
                yield _Claim(key, value.literal, row, entry[1] if entry else None, True, True)
                break
        if not claimed_any and value.state == ValueState.SUPPORTED and isinstance(value.literal, str):
            # Explicit keyed-line rows retain their original accepted assembly.
            for evidence_id in value.evidence_ids:
                row = rows.get(evidence_id)
                if (row is None or row.source != KEYED_ROW_SOURCE or row.kind != "literal"
                    or not row.region_id or row.locator != "region:" + row.region_id):
                    continue
                entry = decided.get(row.region_id)
                claimed_any = True
                yield _Claim(key, value.literal, row, entry[1] if entry else None, True, True)
                break
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


def _candidate(key, literal, status, reason, *, ident=None, **fields):
    identity = digest([ORGANISER_SOURCE, str(key), literal, fields.get("region_id"), fields.get("observation_id"),
        fields.get("start"), fields.get("end")] + ([ident] if ident is not None else []))
    return OrganiserCandidate(id="organiser:" + identity, field_key=key, literal=literal, source=ORGANISER_SOURCE,
        status=status, reason=reason, **fields)
