"""Initial genuine ordinary snapshot -> immutable registered specialist inputs.

This adapter preserves every retained reader handoff. It never promotes an
unstructured label/event to accepted science. Only explicit exact field-key
lines in an actually decided transcript produce deterministic literal assemblies.
"""
from __future__ import annotations

import asyncio
import hashlib
import re

from specimen_digitization.application.active_graph import unpack
from specimen_digitization.application.storage import digest as canonical_digest
from .contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, EvidenceItem, EventHypothesis,
    EventKind, FieldKey, Geometry, PromptPin, SourceFragment, SpecialistRequest,
    SpecialistRole, digest,
)
from .evidence import assemble_field
from .persistence import StaleWork


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
        fragments, events, assemblies, evidence, decisions = self._graph(original, scope)
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
                field_revisions={key:job["fields"][str(key)]["revision"] for key in keys})
        if set(requests) != set(SpecialistRole):
            raise StaleWork("research_complete_specialist_inputs_required")
        return requests

    @staticmethod
    def _graph(specimen, scope):
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
        return tuple(fragments),tuple(events),tuple(assemblies),tuple(evidence),tuple(decisions)
