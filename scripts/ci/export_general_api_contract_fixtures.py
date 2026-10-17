"""Export a single synthetic ordinary HTTP journey as exact UTF-8 wire bytes.

Clocks/IDs, native binding discovery and the PNG codec are fixtures. Pillow's
bundled zlib differs across platforms, and production hashes its encoded view
derivative into retained responses. During export only, a scoped encoder seam
writes PNG with fixed STORED deflate blocks; no compressor runs. Production
still performs its own orientation/region saves, with its actual pixels. The
workflow, checkpoints, retained captures, candidate proof and canonical saves are real.
No production credentials, live providers, test imports or response rewriting.
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import struct
import sys
from binascii import crc32
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID
from zlib import adler32

from fastapi.testclient import TestClient
from PIL import Image
from specimen_digitization.application import api, domain, workflow, search, review_risk, provider_circuit
from specimen_digitization.research_harness import persistence


from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION, SYNTHETIC_ORG,
)
from specimen_digitization.application.domain import FieldValue, Scope, ValueState
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.research_harness.canonical_binding import (
    BindingUnavailable, CanonicalIdentity,
)
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, EvidenceItem, FieldKey, FieldProfile,
    FieldResolution, HumanQuestion, ResearchScope, SourceCoverageReceipt,
    SourceResult, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, CapturedResult, DurabilityScope, DurableEffectBroker,
    ImmutableFileBlobs, ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import runtime_pins
from specimen_digitization.research_harness.thread_view import ResearchThreadReader


def _stored_png(image: Image.Image) -> bytes:
    """Encode RGB pixels as PNG using filter 0 and fixed, uncompressed blocks."""
    if image.mode != 'RGB':
        raise ValueError('The export PNG seam requires RGB pixels')
    width, height = image.size
    pixels = image.tobytes('raw', 'RGB')
    stride = width * 3
    scanlines = b''.join(b'\0' + pixels[start:start + stride]
                         for start in range(0, len(pixels), stride))
    # RFC 1950 header: deflate, 32 KiB window, no dictionary, fastest level.
    stream = bytearray(b'\x78\x01')
    for start in range(0, len(scanlines), 65535):
        block = scanlines[start:start + 65535]
        # Byte-aligned BFINAL and BTYPE=00, then little-endian LEN and NLEN.
        stream.append(int(start + len(block) == len(scanlines)))
        stream.extend(struct.pack('<HH', len(block), 65535 - len(block)))
        stream.extend(block)
    stream.extend(struct.pack('>I', adler32(scanlines)))

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', crc32(kind + data)))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', bytes(stream)) + chunk(b'IEND', b''))


@contextmanager
def _portable_png_encoder():
    """Replace explicit PNG saves only for the lifetime of one export journey."""
    original_save = Image.Image.save

    def save(image, fp, format=None, **params):
        if (format or '').upper() != 'PNG':
            return original_save(image, fp, format=format, **params)
        # The journey uses pixel-only RGB PNGs and BytesIO destinations. Fail
        # closed if a future caller needs metadata or another save option.
        if params:
            raise ValueError('The export PNG seam does not support save options')
        fp.write(_stored_png(image))

    with patch.object(Image.Image, 'save', save):
        yield


class RetainedResearch:
    """Real offline journal matching the canonical specimen's actual identity."""

    def __init__(self, root, specimen):
        profile = CollectionProfile(id="fixture-insects", version="1",
            organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION,
            ancestry=(SYNTHETIC_ORG, SYNTHETIC_COLLECTION), knowledge_version="fixture",
            fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS))
        self.scope = ResearchScope(organization_id=SYNTHETIC_ORG,
            collection_id=SYNTHETIC_COLLECTION, specimen_id=specimen.id,
            job_id="offline-review", generation=1, input_digest=specimen.asset.sha256,
            profile_digest=digest(profile), sensitive=specimen.asset.sensitive)
        requests = {role: SpecialistRequest(scope=self.scope, role=role, field_keys=keys,
            prompt=resolve_prompt(role, profile_digest=self.scope.profile_digest,
                source_registry_digest="b" * 64, toolset_digest="c" * 64,
                model_route="harness-deepseek", output_schema_digest="d" * 64))
            for role, keys in ROLE_FIELDS.items()}
        settings = {"max_tokens": 128}
        pins = runtime_pins(profile, requests,
            model={role: {"route": "harness-deepseek"} for role in requests}, settings=settings)
        self.durable = DurabilityScope(SYNTHETIC_ORG, SYNTHETIC_COLLECTION,
            specimen.id, self.scope.job_id, 1, "synthetic-reviewer", specimen.asset.sensitive)
        backend = SqliteStateBackend(root / "research.sqlite3")
        backend.grant(self.durable, can_view_sensitive=True)
        self.store = ResearchStore(backend, "offline-review-budget")
        self.store.initialize(self.durable, BudgetPolicy(100))
        self.store.create_job(self.durable, pins, list(ALL_FIELDS),
            record_revision=specimen.version)
        lease = self.store.claim(self.durable, "offline-worker")
        self.journal = DurableResearchJournal(self.store, self.durable, lease)
        broker = DurableEffectBroker(self.store, ImmutableFileBlobs(root / "captures"))
        resolutions, effects = [], []
        for ordinal, (key, value) in enumerate((
            (FieldKey.COUNTRY, "Philippines"), (FieldKey.PROVINCE_STATE, "Davao del Sur"),
        ), 1):
            evidence_id = "source:" + digest(str(key))
            coverage = SourceCoverageReceipt(source_id="geolocate", field_key=key,
                state="searched", source_version="offline-fixture-v1", receipt_ids=(evidence_id,),
                candidate_count=1, coverage_limit="Synthetic capture only",
                reason="ambiguous: multiple places share the displayed name")
            result = SourceResult(status="ambiguous", coverage=coverage,
                evidence=(EvidenceItem(id=evidence_id, kind="qualified_source", source_id="geolocate",
                    source_version=coverage.source_version, locator="fixture/apo",
                    response_digest=digest(value), publisher_assertion_id="offline-fixture",
                    excerpt="Synthetic retained source candidate"),),
                candidate_json=(json.dumps({"value": value, "match_name": "MOUNT APO",
                    "authority_id": f"geolocate:{ordinal:016x}", "rank": 1,
                    "latitude": 6.99, "longitude": 125.27}),))

            async def capture(*_, payload=result.model_dump(mode="json")):
                return CapturedResult(payload, 0)

            effect = asyncio.run(broker.execute(self.durable, lease,
                "source_lookup:" + digest(str(key)), {"field": str(key)}, 1, capture,
                execution_class="offline", field_keys=(str(key),)))
            effects.append(effect.effect_id)
            resolutions.append(FieldResolution(field_key=key, work_state=WorkState.WAITING_HUMAN,
                value=FieldValue(state=ValueState.AMBIGUOUS, literal=specimen.run.fields[str(key)].literal),
                question=HumanQuestion(field_key=key, question="Which retained place is intended?",
                    reason="semantic_ambiguity", coverage=(coverage,), evidence_ids=(evidence_id,)),
                reason="Retained alternatives need a reviewer"))
        asyncio.run(self.journal.commit(requests[SpecialistRole.GEOGRAPHY], tuple(resolutions),
            receipt_ids=tuple(effects), model_settings_digest=digest(settings)))
        self.thread = asyncio.run(ResearchThreadReader(self.journal).read(self.scope))
        self.candidates = {str(field.field_key): field.review.candidates[0]
            for field in self.thread.fields if field.review and field.review.candidates}


class BoundDiscovery:
    """Explicit fixture for native binding only, with a real canonical revision check."""

    def __init__(self, repository, specimen, research, binding_id):
        self.repository, self.research = repository, research
        self.scope = specimen.scope
        canonical = CanonicalIdentity(organization_id=SYNTHETIC_ORG,
            collection_id=SYNTHETIC_COLLECTION, specimen_id=specimen.id,
            sensitive=specimen.asset.sensitive, canonical_run_id=specimen.run.id,
            record_revision=specimen.version, record_version_id=str(binding_id),
            host_record_version_id=f"{specimen.run.id}:{specimen.version}",
            snapshot_sha256=digest(specimen.model_dump(mode="json")))
        self.snapshot = SimpleNamespace(canonical=canonical,
            field_mapping={key: str(key) for key in FieldKey}, research_locks=set(),
            research_scope=lambda: research.scope)
        self.snapshot.same_snapshot = lambda other: other is self.snapshot

    async def binding(self, principal, specimen_id):
        current = self.repository.get(principal.scope, specimen_id)
        if (current.version != self.snapshot.canonical.record_revision
                or current.id != self.snapshot.canonical.specimen_id
                or current.scope != self.scope
                or current.run.id != self.snapshot.canonical.canonical_run_id
                or digest(current.model_dump(mode="json")) != self.snapshot.canonical.snapshot_sha256):
            raise BindingUnavailable("canonical_binding_stale")
        return self.snapshot

    async def bound_state(self, principal, specimen_id):
        await self.binding(principal, specimen_id)
        document = self.research.store._read(self.research.durable)
        return (self.snapshot, self.research.store, self.research.durable, document,
            document.state["jobs"][self.research.durable.key])

    async def discover(self, principal, specimen_id):
        from specimen_digitization.research_harness.discovery import DiscoveryCapabilities
        from specimen_digitization.research_harness.discovery_v2 import ResearchDiscoveryResultV2

        await self.binding(principal, specimen_id)
        return ResearchDiscoveryResultV2(canonical=self.snapshot.canonical,
            scope=self.research.scope, human_locked_fields=(),
            capabilities=DiscoveryCapabilities(read=True, retry=False, review=False))

    async def service(self, principal, locator):
        from specimen_digitization.research_harness.persistence import StaleWork
        from specimen_digitization.research_harness.service import ResearchService

        await self.binding(principal, locator.specimen_id)
        async def resolve(actor, requested):
            if (actor.user_id != principal.user_id or requested.specimen_id != self.research.scope.specimen_id
                    or requested.job_id != self.research.scope.job_id
                    or requested.generation != self.research.scope.generation):
                raise StaleWork("research_state_changed")
            return self.research.durable
        return ResearchService(store=self.research.store, resolve_scope=resolve,
            retry_admission=self.research.store.admit_retry)




# Synthetic inputs, not expected outputs. Tests independently pin the wire.
S = '00000000-0000-4000-8000-000000000001'
R = '00000000-0000-4000-8000-000000000002'
U = '00000000-0000-4000-8000-000000000003'
TOKEN = 'i11-synthetic-only'
PREFIX = '/v1/organizations/' + api.SYNTHETIC_ORG
FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED if tz else FIXED.replace(tzinfo=None)


def export_fixture_bytes(root: Path, reverse_reads: bool = False) -> bytes:
    """Run one fresh HTTP journey; restore every patched generator on exit.

    ``root`` must be fresh local storage. ``reverse_reads`` changes only the
    order of the two independent initial GETs, for determinism qualification.
    """
    with _portable_png_encoder():
        return _export_fixture_bytes(root, reverse_reads)


def _export_fixture_bytes(root: Path, reverse_reads: bool) -> bytes:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    original_uuid5 = api.uuid5
    sequence = iter([UUID(R), *(UUID(int=n) for n in range(100, 2000))])
    research_sequence = iter(UUID(int=n) for n in range(3000, 4000))
    circuit_sequence = iter(UUID(int=n) for n in range(5000, 6000))

    def intake_uuid(namespace, name):
        if name.endswith('specimen'):
            return UUID(S)
        if name.endswith('one'):
            return UUID(U)
        return original_uuid5(namespace, name)

    def headers(key):
        return {'Authorization': 'Bearer ' + TOKEN, 'Idempotency-Key': key}

    image = io.BytesIO()
    Image.new('RGB', (120, 80), 'white').save(image, format='PNG')
    data = image.getvalue()
    corpus = {'schema_version': 1, 'png_base64': base64.b64encode(data).decode(),
              'responses': {}, 'requests': {}}

    def retain(name, response):
        # Exact transport bytes: no response normalization or decoded duplicate.
        corpus['responses'][name] = {
            'status_code': response.status_code,
            'body_utf8': response.content.decode('utf-8'),
        }
        assert response.status_code == (409 if name == 'error' else 200), response.text
        if name in {'error', 'action', 'review_batch', 'upload_tail', 'upload_complete'}:
            request = response.request
            captured = {'method': request.method, 'path': request.url.path,
                        'headers': {'Idempotency-Key': request.headers['Idempotency-Key']}}
            if name == 'upload_tail':
                captured['headers']['Upload-Offset'] = request.headers['Upload-Offset']
            else:
                captured['body_utf8'] = request.content.decode('utf-8')
            corpus['requests'][name] = captured
        return response.json()

    with ExitStack() as stack:
        for module in (domain, api, workflow, search, review_risk):
            stack.enter_context(patch.object(module, 'datetime', FixedDatetime, create=True))
        stack.enter_context(patch.object(api, 'uuid5', intake_uuid))
        stack.enter_context(patch.object(domain, 'uuid4', lambda: next(sequence)))
        stack.enter_context(patch.object(persistence, 'uuid4', lambda: next(research_sequence)))
        stack.enter_context(patch.object(provider_circuit, 'uuid4', lambda: next(circuit_sequence)))
        stack.enter_context(patch.object(
            persistence.SqliteStateBackend, '_time', staticmethod(lambda db: FIXED.timestamp())))
        # Inject workflow-local clocks; never alter process-wide time.monotonic.
        original_init = workflow.Workflow.__init__

        def deterministic_init(self, *args, **kwargs):
            kwargs['clock'] = lambda: FIXED
            kwargs['monotonic'] = lambda: 100.0
            original_init(self, *args, **kwargs)

        stack.enter_context(patch.object(workflow.Workflow, '__init__', deterministic_init))
        with TestClient(api.local_app(root, TOKEN), raise_server_exceptions=False) as client:
            def post(path, body, key):
                response = client.post(PREFIX + path, headers=headers(key), json=body)
                assert response.status_code == 200, response.text
                return response

            batch = post('/batches', {'collection_id': api.SYNTHETIC_COLLECTION,
                                     'display_name': 'I11 synthetic'}, 'i11-batch').json()
            post(f"/batches/{batch['batch_id']}/items", {
                'client_item_id': 'one', 'filename': 'synthetic.png',
                'media_type': 'image/png', 'size_bytes': len(data),
                'width': 120, 'height': 80, 'sha256': hashlib.sha256(data).hexdigest(),
            }, 'i11-item')
            for offset, chunk in [(0, data[:20]), (20, data[20:])]:
                retain('upload' if offset == 0 else 'upload_tail', client.put(
                    PREFIX + f'/uploads/{U}/content', content=chunk,
                    headers={**headers(f'chunk-{U}-{offset}'), 'Upload-Offset': str(offset)}))
            retain('upload_current', client.get(
                PREFIX + f'/uploads/{U}', headers=headers('i11-upload-current')))
            retain('upload_complete', post('/uploads/' + U + '/complete',
                                           {'expected_revision': 3}, 'i11-complete'))
            reads = [('workspace', f'/specimens/{S}/workspace', {}),
                     ('list', '/specimens', {'collection_id': api.SYNTHETIC_COLLECTION})]
            for name, path, params in reversed(reads) if reverse_reads else reads:
                retain(name, client.get(PREFIX + path, headers=headers('i11-read'), params=params))
            request = {'expected_revision': 20, 'base_record_version_id': R + ':20',
                       'kind': 'approve', 'reason': 'I11 synthetic reviewed',
                       'target_id': '', 'after': {'confirmed': True}, 'evidence_ids': []}
            stale = {**request, 'expected_revision': 19, 'base_record_version_id': R + ':19'}
            retain('error', client.post(PREFIX + f'/specimens/{S}/decisions',
                                       headers=headers('i11-stale'), json=stale))
            retain('error_readback', client.get(
                PREFIX + f'/specimens/{S}/workspace', headers=headers('i11-reconcile')))
            retain('action', post(f'/specimens/{S}/decisions', request, 'i11-approve'))
            retain('action_readback', client.get(
                PREFIX + f'/specimens/{S}/workspace', headers=headers('i11-reopen')))

        # Reopen the same canonical repository. Only native binding discovery
        # is supplied; the capture/journal/resolver/application/CAS proof is real.
        repository = SQLiteRepository(root / 'state.sqlite3')
        scope = domain.Scope(organization_id=api.SYNTHETIC_ORG,
                             collection_id=api.SYNTHETIC_COLLECTION)
        specimen = repository.get(scope, S)
        research = RetainedResearch(root, specimen)
        blobs = LocalBlobs(root / 'blobs')
        app = api.create_app(
            mode='emulator', repository=repository, blobs=blobs,
            adapters=workflow.SyntheticAdapters(blobs, api.SYNTHETIC_TEXT),
            research_version='v2', identity_verifier=lambda *_: 'synthetic-reviewer',
            memberships=lambda _: [{'organization_id': api.SYNTHETIC_ORG,
                'collection_id': api.SYNTHETIC_COLLECTION, 'role': 'reviewer',
                'can_view_sensitive': True}])
        app.state.research_discovery.current = BoundDiscovery(
            repository, specimen, research, UUID(int=4000))
        selection = research.candidates['country'].selection_id
        corpus['selection_id'] = selection
        request = {'reason': 'I11 retained source reviewed', 'decisions': [{
            'specimen_id': S, 'expected_revision': 21, 'base_record_version_id': R + ':21',
            'kind': 'research_candidate', 'target_id': 'country',
            'after': {'selection_id': selection}, 'idempotency_key': 'i11-candidate-0'}]}
        with TestClient(app, raise_server_exceptions=False) as client:
            retain('review_batch', client.post(PREFIX + '/decisions:batch', json=request,
                headers=headers('7651ca196a03f7cc18d5625844ca3b2fdc68a62d7b19c691c3b222ad40a77aa8')))
            retain('review_readback', client.get(
                PREFIX + f'/specimens/{S}/workspace', headers=headers('i11-review-readback')))
    return (json.dumps(corpus, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--output', type=Path)
    destination.add_argument('--check', type=Path)
    args = parser.parse_args(argv)
    with TemporaryDirectory(prefix='general-api-contract-') as temporary:
        wire = export_fixture_bytes(Path(temporary))
    if args.check:
        if args.check.read_bytes() != wire:
            parser.exit(1, 'Shared API fixture differs; regenerate with --output.\n')
    else:
        args.output.write_bytes(wire)
    return 0


if __name__ == '__main__':
    sys.exit(main())
