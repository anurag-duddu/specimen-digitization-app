"""Initial genuine ordinary snapshot -> immutable registered specialist inputs.

This adapter preserves every retained reader handoff. It never promotes an
unstructured label/event to accepted science on a model's say-so. Two things
produce deterministic literal assemblies:

1. an explicit exact field-key line in an actually decided transcript;
2. the hand-over: a field value the ordinary extractor already stored
   (``run.fields``) whose literal trusted code finds as a verbatim substring of
   exactly one line of the decided reading. The span (reading, region, offsets) is
   computed here from the reading text, never read from the extractor, and a
   literal that cannot be located exactly is carried to the specialist as an
   ungrounded hint (OrganiserCandidate) that never becomes an event or assembly.

An event or assembly of the second kind is "the extractor proposed this value and
it is verbatim in the decided reading". It is not a semantic check: whether the
line is the collector, the habitat or the collection code stays the specialist's
verification against the raw readings (the specialist prompts say so).
"""
from __future__ import annotations

import asyncio
import hashlib
import re

from specimen_digitization.application.active_graph import unpack
from specimen_digitization.application.domain import ValueState
from specimen_digitization.application.storage import digest as canonical_digest
from .contracts import (
    ALL_FIELDS, MAX_ORGANISER_CANDIDATES, MAX_ORGANISER_LITERAL, ROLE_FIELDS, CollectionProfile,
    EvidenceItem, EventHypothesis, EventKind, FieldKey, Geometry, OrganiserCandidate, PromptPin,
    SourceFragment, SpecialistRequest, SpecialistRole, digest,
)
from .evidence import assemble_field
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
        for item in specimen.run.evidence:
            evidence.append(EvidenceItem(id=item.id, kind=item.kind, source_id=item.source or "native_evidence",
                locator=item.locator or "native-evidence:"+item.id,
                response_digest=item.digest or canonical_digest(item.model_dump(mode="json")),
                source_version="native-evidence-adapter/v1", publisher_assertion_id=canonical_digest(item.model_dump(mode="json")),
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
        """Second pass: the extractor's stored field values, located by trusted code.

        For each supported field the ordinary extractor stored (``run.fields``) and each region its
        evidence row cites, the literal is looked for in the lines of that region's decided reading.
        Exactly one verbatim hit gives a span whose offsets are computed here; anything else is an
        ungrounded hint (reason names why). A located span of an ``ASSEMBLY_FIELDS`` field in a
        readable decided reading also gets an accepted event and an assembly through
        ``assemble_field``, appended to ``fragments``, ``events`` and ``assemblies``. Returns the
        candidates in field order. Nothing here reads a span, an offset or a status from a model."""
        decided = {}
        for transcript in specimen.run.transcripts:
            observation = reading_map.get(transcript.selected_observation_id)
            if transcript.resolved and transcript.text and observation is not None:
                decided[transcript.region_id] = (transcript, observation)
        rows = {item.id: item for item in specimen.run.evidence}
        keyed = tuple(assemblies)  # the exact field-key lines' assemblies, before any hand-over assembly
        candidates = []
        for name, value in specimen.run.fields.items():
            try:
                key = FieldKey(name)
            except ValueError:
                continue
            literal = value.literal
            if (value.state != ValueState.SUPPORTED or not isinstance(literal, str) or not literal.strip()
                or len(literal) > MAX_ORGANISER_LITERAL):
                continue
            cited = [rows[item] for item in value.evidence_ids if item in rows and rows[item].kind == "literal"]
            regions = list(dict.fromkeys(row.region_id for row in cited if row.region_id))
            if not regions:
                candidates.append(_candidate(key, literal, "ungrounded", "no_extractor_evidence_row_for_the_literal"))
            for region_id in regions[:max(0, MAX_ORGANISER_CANDIDATES - len(candidates))]:
                candidates.append(NativeGenerationRequestFactory._organiser_candidate(
                    specimen, scope, ref, region_map, key, literal, region_id,
                    decided.get(region_id), [row for row in cited if row.region_id == region_id],
                    fragments, events, assemblies, keyed))
        return tuple(candidates[:MAX_ORGANISER_CANDIDATES])

    @staticmethod
    def _organiser_candidate(specimen, scope, ref, region_map, key, literal, region_id, entry, cited,
                             fragments, events, assemblies, keyed_assemblies):
        def hint(reason):
            return _candidate(key, literal, "ungrounded", reason, region_id=region_id)
        if entry is None:
            return hint("no_decided_reading_for_the_region")
        transcript, observation = entry
        text, region = observation.literal_text, region_map[region_id]
        # The extractor's own record of where it read the value: a native evidence row of this
        # region whose quote holds the literal and lies inside the decided reading (the ordinary
        # extractor quotes the whole region transcript; a narrower quote passes as well). So a
        # literal found below is a verbatim substring of the decided reading, and the span is
        # searched in it, not taken from the row.
        backing = tuple(row.id for row in cited if row.asset_id == specimen.asset.id
            and row.locator == "region:" + region_id and set(row.observation_ids) == set(transcript.observation_ids)
            and literal in row.excerpt and row.excerpt in text)
        if not backing:
            return hint("extractor_quote_does_not_hold_the_literal")
        hits = []
        for ordinal, begin, line in _lines(text):
            at = line.find(literal)
            while at >= 0:
                hits.append((ordinal, begin + at))
                at = line.find(literal, at + 1)
        if not hits:
            return hint("literal_spans_more_than_one_line")
        if len(hits) > 1:
            return hint(f"literal_occurs_{len(hits)}_times_in_the_decided_reading")
        (ordinal, begin), end = hits[0], hits[0][1] + len(literal)
        where = dict(region_id=region_id, observation_id=observation.id, start=begin, end=end)
        # A keyed line for this field that already carries this very span is the same assembly.
        keyed = [item for item in keyed_assemblies if item.field_key == key]
        by_id = {item.id: item for item in fragments}
        for assembly in keyed:
            fragment = by_id[assembly.fragment_ids[0]]
            if (len(assembly.fragment_ids) == 1 and assembly.interpreted_text == literal
                and (fragment.observation_id, fragment.start, fragment.end) == (observation.id, begin, end)):
                return _candidate(key, literal, "grounded", "keyed_line_assembly_holds_the_span", **where,
                    fragment_id=fragment.id, event_id=assembly.event_id, assembly_id=assembly.id,
                    evidence_ids=assembly.evidence_ids)
        if key not in ASSEMBLY_FIELDS:
            return _candidate(key, literal, "located", "hand_over_builds_no_assembly_for_the_field", **where)
        if keyed:
            return _candidate(key, literal, "located", "keyed_line_assembly_for_the_field_exists", **where)
        if observation.unreadable_spans:
            return _candidate(key, literal, "located", "decided_reading_has_unreadable_spans", **where)
        fragment = SourceFragment(id="fragment:" + digest([observation.id, begin, end, ORGANISER_RULE]),
            scope=scope, asset_id=specimen.asset.id, asset_generation=ref.partition(":")[2],
            asset_digest=specimen.asset.sha256, label_id=region.id, region_id=region.id,
            observation_id=observation.id, reader=observation.route_id, model_id=observation.model_id,
            prompt_digest=observation.prompt_version, observation_text=text,
            observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=begin, end=end,
            literal=literal, order=ordinal, granularity="span", input_source="decided_transcript",
            geometry=Geometry(coordinate_frame="original_pixel_edges",
                bounds=(region.x, region.y, region.width, region.height), kind="region",
                provenance="retained_ordinary_region"), unreadable=False)
        kind = (EventKind.DETERMINATION if key == FieldKey.DATE_IDENTIFIED else
            EventKind.COLLECTING if key in {FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.COLLECTORS}
            else EventKind.UNKNOWN)
        event = EventHypothesis(id="event:" + digest([fragment.id, str(key), ORGANISER_RULE]), scope=scope,
            kind=kind, fragment_ids=(fragment.id,), evidence_ids=backing,
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
