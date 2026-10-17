"""Durable private drafts and explicit, idempotent bulk submission.

The draft's CAS manifest is the authority for edits and submission. Item bytes
may advance independently; a frozen manifest always identifies immutable content.
No draft method creates a specimen or invokes the scientific pipeline.
"""
from __future__ import annotations

import hashlib
import io
import time
from uuid import NAMESPACE_URL, uuid4, uuid5
from PIL import Image

from .domain import Asset, AuditEvent, Profile, Run, Specimen, now
from .intake_image import verify_photo
from .intake_models import Draft, DraftItem, Submission, SubmissionItem, SourceReference, MAX_PHOTOS, TERMINAL
from .storage import Conflict, Missing, digest


def ident(*parts):
    return str(uuid5(NAMESPACE_URL, 'bulk-intake:' + ':'.join(parts)))


def problem(code, message, action='retry', retryable=True):
    return dict(code=code, message=message, action=action, retryable=retryable)


class IntakeService:
    def __init__(self, repository, blobs, *, authorize, classify, queue_specimen,
                 dispatch_pipeline, dispatch_intake=None, sources=None, codec_policy=None,
                 synthetic=False, clock=time.time):
        self.repo, self.blobs = repository, blobs
        self.authorize, self.classify = authorize, classify
        self.queue_specimen, self.dispatch_pipeline = queue_specimen, dispatch_pipeline
        self.dispatch_intake, self.sources = dispatch_intake, sources
        self.codec_policy, self.synthetic, self.clock = codec_policy, synthetic, clock

    def read(self, p, kind, id):
        doc = self.repo.document(p.scope, kind, id)
        if doc.get('owner_id') != p.user_id:
            raise Missing('Intake item unavailable')
        self.classify(p, doc.get('sensitive', True))
        return doc

    def save(self, p, kind, doc):
        return self.repo.put_document(p.scope, kind, doc['id'], doc, doc.get('revision', 0))

    def read_many(self, p, kind, ids):
        result = {}
        for start in range(0, len(ids), 100):
            rows = self.repo.private_documents(p.scope, kind, p.user_id, ids[start:start + 100])
            for row in rows:
                if row.get('owner_id') != p.user_id:
                    raise Missing('Intake item unavailable')
                self.classify(p, row.get('sensitive', True))
                result[row['id']] = row
        return result

    def list(self, p, kind, *, after='', limit=50):
        if not 1 <= limit <= 100:
            raise ValueError('Choose a page size between 1 and 100')
        if kind == 'intake_submission':
            # A client can reopen after freeze committed but before materializing
            # the submission or launching its worker. Surface and wake that outbox.
            cursor = ''
            while True:
                page = self.list(p, 'intake_draft', after=cursor, limit=100)
                for draft in page['items']:
                    if draft['state'] == 'submitted':
                        try:
                            self.read(p, kind, draft['submission_id'])
                            job = self.repo.document(p.scope, 'intake_job', ident(draft['submission_id'], 'submit'))
                            if job['state'] == 'waiting' and max(job.get('lease_until', 0), job.get('next_attempt', 0)) <= self.clock():
                                self.enqueue(p, draft['submission_id'], 'submit')
                        except Missing:
                            self._materialize_submission(p, draft)
                cursor = page['next_cursor']
                if not cursor:
                    break
        # Native adapters page at the database; the local reference has the same
        # ownership predicate. No collection-wide upload inventory is returned.
        if hasattr(self.repo, 'private_document_page'):
            try:
                self.classify(p, True)
                include_sensitive = True
            except PermissionError:
                include_sensitive = False
            rows = self.repo.private_document_page(p.scope, kind, p.user_id, after, limit + 1, include_sensitive)
        else:
            rows = [d for d in self.repo.documents(p.scope, kind)
                    if d.get('owner_id') == p.user_id and d['id'] > after][:limit + 1]
        for row in rows:
            if row.get('owner_id') != p.user_id:
                raise Missing('Intake item unavailable')
            self.classify(p, row.get('sensitive', True))
        return dict(items=rows[:limit], next_cursor=rows[limit - 1]['id'] if len(rows) > limit else None)

    def create_draft(self, p, body):
        id = ident(p.scope.key if hasattr(p.scope, 'key') else p.scope.model_dump_json(), p.user_id, body.client_id)
        try:
            return self.read(p, 'intake_draft', id)
        except Missing:
            return self.save(p, 'intake_draft', Draft(id=id, owner_id=p.user_id,
                collection_id=p.scope.collection_id, name=body.name, created_at=now()).model_dump())

    def draft(self, p, id, *, mutable=False):
        doc = self.read(p, 'intake_draft', id)
        if mutable and doc['state'] != 'draft':
            raise Conflict('This batch has already been submitted or discarded')
        return doc

    def add_item(self, p, draft_id, body):
        draft = self.draft(p, draft_id)
        policy_sensitive = bool(self.sources and self.sources.required_sensitive(p, body.source))
        if body.replaces_id:
            original = self.item(p, body.replaces_id)
            policy_sensitive = policy_sensitive or self.required_sensitive(p, original)
        if policy_sensitive:
            body = body.model_copy(update={'photo_sensitive': True})
        self.classify(p, body.photo_sensitive)
        if body.source.provider in {'camera', 'files'} and (not body.sha256 or body.size_bytes is None):
            raise ValueError('A local photo requires its checksum and size')
        id = ident(draft_id, body.client_id)
        request = digest(body.model_dump())
        try:
            item = self.read(p, 'intake_item', id)
            if item['request_digest'] != request:
                raise Conflict('Photo identity was reused for different content')
            if draft['state'] == 'submitted' and any(e['id'] == id for e in draft['entries']):
                self.item(p, id)
                return item
        except Missing:
            if draft['state'] != 'draft':
                raise Conflict('This batch has already been submitted or discarded')
            replaced = next((e for e in draft['entries'] if e['id'] == body.replaces_id and not e['removed']), None)
            if body.replaces_id and replaced is None:
                raise ValueError('Choose a photo in this draft to replace')
            if body.replaces_id and replaced is None:
                raise Conflict('The original photo was already replaced or removed')
            if sum(not e['removed'] for e in draft['entries']) - bool(replaced) >= MAX_PHOTOS:
                raise ValueError('A batch holds up to 500 photos. Start another batch.')
            if body.source.provider not in {'camera', 'files'}:
                if self.sources is None:
                    raise ValueError('This source is not configured')
                self.sources.validate(p, body.source)
            item = self.save(p, 'intake_item', DraftItem(id=id, client_id=body.client_id, draft_id=draft_id,
                owner_id=p.user_id, collection_id=p.scope.collection_id,
                filename=body.filename, media_type=body.media_type, size_bytes=body.size_bytes,
                sha256=body.sha256, source=body.source, request_digest=request,
                sensitive=body.photo_sensitive, policy_sensitive=policy_sensitive, derived_from=body.replaces_id).model_dump())
        if not any(e['id'] == id for e in draft['entries']):
            if draft['state'] != 'draft':
                raise Conflict('This batch has already been submitted or discarded')
            replaced = next((e for e in draft['entries'] if e['id'] == body.replaces_id and not e['removed']), None)
            if body.replaces_id and replaced is None:
                raise Conflict('The original photo was already replaced or removed')
            if sum(not e['removed'] for e in draft['entries']) - bool(replaced) >= MAX_PHOTOS:
                raise ValueError('A batch holds up to 500 photos. Start another batch.')
            if replaced:
                replaced['removed'] = True
            draft['entries'].append(dict(id=id, photo_sensitive=body.photo_sensitive, included=True, removed=False))
            draft['sensitive'] = draft['sensitive'] or body.photo_sensitive
            self.save(p, 'intake_draft', draft)
        if body.source.provider not in {'camera', 'files'}:
            self.enqueue(p, id, 'stage')
        return item

    def edit(self, p, id, body):
        draft = self.draft(p, id, mutable=True)
        if draft['revision'] != body.expected_revision:
            raise Conflict('The draft changed. Refresh before editing.')
        chosen = set(body.item_ids)
        if len(chosen) != len(body.item_ids) or chosen - {e['id'] for e in draft['entries']}:
            raise ValueError('Select photos from this draft')
        if body.action == 'sensitive':
            if body.value is None:
                raise ValueError('Choose the classification explicitly')
            self.classify(p, body.value)
            if not body.value:
                from .intake_models import SourceReference
                for id in chosen:
                    item = self.read(p, 'intake_item', id)
                    if item.get('policy_sensitive') or (self.sources and self.sources.required_sensitive(p, SourceReference.model_validate(item['source']))):
                        raise ValueError('This source requires sensitive classification')
            draft['sensitive'] = draft['sensitive'] or body.value
        for entry in draft['entries']:
            if entry['id'] not in chosen:
                continue
            if body.action in {'remove', 'restore'}:
                entry['removed'] = body.action == 'remove'
            elif body.action in {'include', 'exclude'}:
                entry['included'] = body.action == 'include'
            else:
                entry['photo_sensitive'] = body.value
                # Access protection is monotonic even while an owner changes a
                # draft's eventual classification. Existing specimens never change.
                item = self.read(p, 'intake_item', entry['id'])
                if body.value and not item['sensitive']:
                    item['sensitive'] = True
                    self.save(p, 'intake_item', item)
        if sum(not e['removed'] for e in draft['entries']) > MAX_PHOTOS:
            raise ValueError('A batch holds up to 500 photos. Remove another photo before restoring this one.')
        return self.save(p, 'intake_draft', draft)

    def item(self, p, id):
        item = self.read(p, 'intake_item', id)
        self.item_draft(p, item)
        return item

    def item_draft(self, p, item):
        """Follow immutable carry-forward manifests without racing item writes."""
        draft = self.draft(p, item['draft_id'])
        while draft['state'] == 'submitted' and not any(
                e['id'] == item['id'] for e in draft['submitted_entries']):
            if not draft.get('remaining_draft_id'):
                raise Missing('Photo unavailable')
            draft = self.draft(p, draft['remaining_draft_id'])
        if draft['state'] == 'discarded' or not any(e['id'] == item['id'] for e in draft['entries']):
            raise Missing('Photo unavailable')
        return draft

    def content(self, p, id, offset, content):
        item = self.item(p, id)
        if item['source']['provider'] not in {'camera', 'files'}:
            raise ValueError('This photo is imported by the server')
        if not content or len(content) > 4 * 1024 * 1024:
            raise ValueError('Upload chunks must contain at most 4 MiB')
        checksum = hashlib.sha256(content).hexdigest()
        if offset != item['offset'] or item['state'] == 'ready':
            if any(c['offset'] == offset and c['sha256'] == checksum for c in item['chunks']):
                return item
            raise Conflict('Upload offset changed. Resume from the saved position.')
        if offset + len(content) > item['size_bytes']:
            raise ValueError('Upload exceeds the declared photo size')
        item['chunks'].append(dict(offset=offset, size=len(content), sha256=checksum, ref=self.blobs.put(content)))
        item.update(offset=offset + len(content), state='transferring', error=None)
        return self.save(p, 'intake_item', item)

    def required_sensitive(self, p, item):
        # Edits retain source policy, including later policy changes on ancestors.
        seen = set()
        while item['id'] not in seen:
            seen.add(item['id'])
            if item.get('policy_sensitive') or (self.sources and self.sources.required_sensitive(
                    p, SourceReference.model_validate(item['source']))):
                return True
            if not item.get('derived_from'):
                return False
            item = self.read(p, 'intake_item', item['derived_from'])
        raise ValueError('Invalid photo provenance')

    def stage(self, p, id):
        item = self.item(p, id)
        draft = self.item_draft(p, item)
        if item['state'] == 'ready':
            if draft['submission_id']:
                self.enqueue(p, draft['submission_id'], 'submit')
            return item
        if draft['submission_id'] and self.read(p, 'intake_submission', draft['submission_id'])['cancel_requested']:
            self.enqueue(p, draft['submission_id'], 'submit')
            return item
        if item['source']['provider'] in {'camera', 'files'}:
            if item['offset'] != item['size_bytes']:
                raise Conflict('This photo still needs its remaining bytes')
            content = b''.join(self.blobs.get(c['ref']) for c in item['chunks'])
            if hashlib.sha256(content).hexdigest() != item['sha256']:
                raise ValueError('Photo checksum does not match')
        else:
            from .intake_models import SourceReference
            if self.sources.required_sensitive(p, SourceReference.model_validate(item['source'])):
                self.classify(p, True)
            content, media_type = self.sources.read(p, item['source'])
            item.update(media_type=media_type, size_bytes=len(content), offset=len(content),
                        sha256=hashlib.sha256(content).hexdigest())
        if not 0 < len(content) <= 25_000_000:
            raise ValueError('Photo exceeds the 25 MB limit')
        asset = verify_photo(content, dict(item, width=None, height=None), self.blobs, self.codec_policy)
        with Image.open(io.BytesIO(self.blobs.get(asset['view_derivative']['blob_ref']))) as image:
            image.thumbnail((512, 512))
            output = io.BytesIO()
            image.convert('RGB').save(output, format='JPEG', quality=80)
        item.update(asset=asset, thumbnail_ref=self.blobs.put(output.getvalue()), state='ready', error=None)
        saved = self.save(p, 'intake_item', item)
        draft = self.item_draft(p, item)
        if draft['submission_id']:
            self.enqueue(p, draft['submission_id'], 'submit')
        return saved

    def submit(self, p, id, body):
        draft = self.draft(p, id)
        chosen = set(body.item_ids)
        if len(chosen) != len(body.item_ids):
            raise ValueError('Select each photo once')
        if draft['state'] == 'submitted':
            if {e['id'] for e in draft['submitted_entries']} != chosen:
                raise Conflict('This draft was submitted with a different selection')
            return self._materialize_submission(p, draft)
        if draft['state'] != 'draft' or draft['revision'] != body.expected_revision:
            raise Conflict('The draft changed. Review the current batch before submitting.')
        entries = [e for e in draft['entries'] if e['id'] in chosen and e['included'] and not e['removed']]
        if len(entries) != len(chosen):
            raise ValueError('Only included photos can be submitted')
        for entry in entries:
            self.classify(p, entry['photo_sensitive'])
            item = self.item(p, entry['id'])
            if self.required_sensitive(p, item) and not entry['photo_sensitive']:
                raise Conflict('Source policy changed. Mark this photo sensitive and review before submitting.')
            if item['state'] == 'needs_attention':
                raise Conflict('Resolve failed photos or leave them in the draft')
        draft.update(state='submitted', submitted_entries=entries,
                     submission_id=ident(id, 'submission'), submitted_at=now())
        remaining = [e for e in draft['entries'] if e['id'] not in chosen and not e['removed']]
        draft['remaining_draft_id'] = ident(id, 'remaining') if remaining else None
        job = dict(id=ident(draft['submission_id'], 'submit'), target=draft['submission_id'],
            draft_id=id, operation='submit', owner_id=p.user_id, sensitive=False,
            revision=1, state='waiting', next_attempt=0)
        # Freeze and outbox commit together. A restarted worker can materialize
        # the submission even if this request dies immediately after the commit.
        draft = self.repo.commit_intake_submission(p.scope, draft, job)
        return self._materialize_submission(p, draft)

    def _materialize_submission(self, p, draft, *, wake=True):
        id = draft['submission_id']
        try:
            submission = self.read(p, 'intake_submission', id)
        except Missing:
            content = Submission(id=id, draft_id=draft['id'],
                owner_id=p.user_id, collection_id=p.scope.collection_id,
                entries=draft['submitted_entries'], total=len(draft['submitted_entries']),
                sensitive=draft['sensitive'], created_at=draft['submitted_at']).model_dump()
            try:
                submission = self.save(p, 'intake_submission', content)
            except Conflict:
                submission = self.read(p, 'intake_submission', id)
        if draft['remaining_draft_id']:
            try:
                self.draft(p, draft['remaining_draft_id'])
            except Missing:
                selected = {e['id'] for e in draft['submitted_entries']}
                remaining = Draft(id=draft['remaining_draft_id'], owner_id=p.user_id,
                    collection_id=p.scope.collection_id, name=draft['name'], created_at=now(),
                    sensitive=draft['sensitive'], entries=[e for e in draft['entries']
                        if e['id'] not in selected and not e['removed']]).model_dump()
                try:
                    self.save(p, 'intake_draft', remaining)
                except Conflict:
                    self.draft(p, remaining['id'])
        if wake:
            self.enqueue(p, id, 'submit')
        return dict(submission, remaining_draft_id=draft['remaining_draft_id'])

    def enqueue(self, p, target, operation):
        id = ident(target, operation)
        for attempt in range(8):
            try:
                job = self.repo.document(p.scope, 'intake_job', id)
                job.update(state='waiting', next_attempt=0, error=None)
            except Missing:
                job = dict(id=id, target=target, operation=operation, owner_id=p.user_id,
                           sensitive=False, revision=0, state='waiting', next_attempt=0)
            try:
                job = self.save(p, 'intake_job', job)
                break
            except Conflict:
                if attempt == 7:
                    raise
        try:
            dispatch = self.wake(p) if self.dispatch_intake else dict(
                status='local' if self.synthetic else 'unconfigured')
            if hasattr(dispatch, 'model_dump'):
                dispatch = dispatch.model_dump()
            if dispatch and dispatch.get('status') in {'unconfigured', 'failed', 'blocked'}:
                raise RuntimeError('Intake worker could not start')
        except Exception:
            job['error'] = problem('worker_unavailable',
                'Your batch is saved, but the transfer worker could not start. Retry this batch.')
            # A worker may already have claimed a successfully launched job after
            # a lost acknowledgement. Never overwrite that newer claim.
            try:
                self.save(p, 'intake_job', job)
            except Conflict:
                pass
        return job

    def wake(self, p, *, force=False):
        """One start per collection lease; the worker holds an idle grace window."""
        id = ident(p.scope.model_dump_json(), 'intake-wakeup')
        try:
            wake = self.repo.document(p.scope, 'intake_job', id)
        except Missing:
            wake = dict(id=id, owner_id=p.user_id, operation='wake', target=id,
                state='control', sensitive=False, revision=0)
        if not force and wake.get('lease_until', 0) > self.clock():
            return dict(status='coalesced')
        wake['lease_until'] = self.clock() + 60
        try:
            wake = self.save(p, 'intake_job', wake)
        except Conflict:
            return dict(status='coalesced')
        outcome = self.dispatch_intake()
        status = outcome.get('status') if isinstance(outcome, dict) else getattr(outcome, 'status', None)
        if status != 'requested':
            wake['lease_until'] = 0
            try:
                self.save(p, 'intake_job', wake)
            except Conflict:
                pass
        return outcome

    def submission(self, p, id):
        doc = self.read(p, 'intake_submission', id)
        counts = {}
        for result in self.results(p, doc, doc['entries']):
            counts[result['state']] = counts.get(result['state'], 0) + 1
        try:
            job = self.repo.document(p.scope, 'intake_job', ident(id, 'submit'))
            worker_error = job.get('error')
        except Missing:
            worker_error = problem('worker_unavailable', 'Submission is saved. Retry to start its transfer worker.')
        return dict(doc, counts=counts, worker_error=worker_error)

    def result(self, p, submission, entry):
        return self.results(p, submission, [entry])[0]

    def results(self, p, submission, entries):
        items = self.read_many(p, 'intake_item', [e['id'] for e in entries])
        results = self.read_many(p, 'intake_result', [ident(submission['id'], e['id']) for e in entries])
        rows = []
        for entry in entries:
            item = items.get(entry['id'])
            if item is None:
                raise Missing('Photo unavailable')
            rows.append(self._result(p, submission, entry, item, results))
        return rows

    def _result(self, p, submission, entry, item, results):
        id = ident(submission['id'], entry['id'])
        result = results.get(id)
        if result is None:
            result = SubmissionItem(id=id, submission_id=submission['id'], item_id=entry['id'],
                owner_id=p.user_id, collection_id=p.scope.collection_id,
                sensitive=entry['photo_sensitive']).model_dump()
        state = result['state']
        if state == 'waiting' and item['state'] != 'ready':
            state = item['state']
        return dict(result, state=state, filename=item['filename'], offset=item['offset'],
                    size_bytes=item['size_bytes'], error=result['error'] or item['error'])

    def process_submission(self, p, id, *, deadline=None):
        submission = self.read(p, 'intake_submission', id)
        draft = self.draft(p, submission['draft_id'])
        if draft['state'] != 'submitted' or draft['submission_id'] != id:
            raise Conflict('Submission has not committed')
        handoffs = []
        for entry in submission['entries']:
            if deadline is not None and self.clock() >= deadline:
                break
            self.authorize(p)  # membership can change while a batch is running
            submission = self.read(p, 'intake_submission', id)
            handoff = self._handoff(p, submission, entry)
            if handoff:
                handoffs.append(handoff)
        # Queue every accepted image before the single production wakeup. The
        # synthetic reference executes each image directly for local tests.
        if handoffs:
            try:
                for _, specimen in handoffs if self.synthetic else handoffs[-1:]:
                    dispatched = self.dispatch_pipeline(p, specimen)
                    status = dispatched.get('status') if isinstance(dispatched, dict) else getattr(dispatched, 'status', None)
                    if status in {'failed', 'unconfigured'}:
                        raise RuntimeError('Pipeline worker could not start')
                failure = None
            except Exception:
                failure = problem('handoff_uncertain', 'Could not confirm the handoff. Retry to check its saved result.')
            for result, specimen in handoffs:
                result.update(state='needs_attention' if failure else 'sent', lease_until=0, error=failure)
                try:
                    self.save(p, 'intake_result', result)
                except Conflict:
                    pass
        return self.submission(p, id)

    def _handoff(self, p, submission, entry):
        id = ident(submission['id'], entry['id'])
        try:
            result = self.read(p, 'intake_result', id)
        except Missing:
            result = SubmissionItem(id=id, submission_id=submission['id'], item_id=entry['id'],
                owner_id=p.user_id, collection_id=p.scope.collection_id,
                sensitive=entry['photo_sensitive']).model_dump()
        if result['state'] in TERMINAL or (result['state'] == 'needs_attention' and not submission['cancel_requested']):
            return
        if result['lease_until'] > self.clock():
            return
        # Claim first. If cancellation races an already claimed handoff, its
        # durable specimen result wins; cancellation never promises rollback.
        result.update(state='checking', lease_token=str(uuid4()), lease_until=self.clock() + 120)
        try:
            result = self.save(p, 'intake_result', result)
        except Conflict:
            return
        item = self.item(p, entry['id'])
        try:
            existing = self.repo.get(p.scope, ident(id, 'specimen'))
        except Missing:
            existing = None
        if existing is None and submission['cancel_requested']:
            result.update(state='cancelled', lease_until=0)
            self.save(p, 'intake_result', result)
            return
        if existing is None and item['state'] != 'ready':
            result.update(state='waiting', lease_until=0)
            self.save(p, 'intake_result', result)
            return
        try:
            if existing is None and self.required_sensitive(p, item) and not entry['photo_sensitive']:
                raise ValueError('Source policy changed after submission; a sensitive submission is required')
            self.classify(p, entry['photo_sensitive'])
            try:
                self.classify(p, True)
                can_view_sensitive = True
            except PermissionError:
                can_view_sensitive = False
            matches = self.repo.find_checksum(p.scope, item['sha256'], can_view_sensitive)
            duplicate = next((s['id'] for s in matches if s['id'] != ident(id, 'specimen')), None)
            if duplicate:
                existing = self.repo.get(p.scope, duplicate)
                self.classify(p, existing.asset.sensitive)
            elif existing is None:
                asset = Asset(**item['asset'], id=ident(id, 'asset'), sensitive=entry['photo_sensitive'],
                    sha256=item['sha256'], size_bytes=item['size_bytes'], filename=item['filename'],
                    uploader=p.user_id)
                existing = Specimen(id=ident(id, 'specimen'), scope=p.scope,
                    batch_id=ident(submission['id'], str(entry['photo_sensitive'])),
                    run=Run(profile=Profile(synthetic=self.synthetic,
                        institutional_policy_approved=self.synthetic, semantics_confirmed=self.synthetic)), asset=asset)
                existing.audit.append(AuditEvent(actor=p.user_id, action='ingest', reason='Explicit batch submission; verified immutable original'))
                self.queue_specimen(existing, p.user_id)
                existing = self.repo.create(p, existing, 'bulk:' + id,
                    digest(dict(item=entry['id'], sha256=item['sha256'], sensitive=entry['photo_sensitive'])))
            result.update(state='duplicate' if duplicate else 'held' if existing.asset.sensitive else 'checking',
                          specimen_id=existing.id, lease_until=0, error=None)
            if result['state'] == 'checking':
                result['lease_until'] = self.clock() + 120
                return self.save(p, 'intake_result', result), existing
        except (PermissionError, ValueError):
            result.update(state='needs_attention', lease_until=0,
                error=problem('access_or_validation', 'This photo could not be handed off. Check access and retry.', retryable=False))
        except Exception:
            # Deterministic specimen IDs let retry reconcile a committed create
            # or dispatch whose acknowledgement was lost.
            result.update(state='needs_attention', lease_until=0,
                error=problem('handoff_uncertain', 'Could not confirm the handoff. Retry to check its saved result.'))
        self.save(p, 'intake_result', result)

    def retry(self, p, id, item_ids):
        submission = self.read(p, 'intake_submission', id)
        allowed = {e['id'] for e in submission['entries']}
        if not set(item_ids) <= allowed:
            raise ValueError('Select photos from this submission')
        for item_id in item_ids:
            item = self.item(p, item_id)
            if item['state'] == 'needs_attention':
                item.update(state='waiting', error=None)
                self.save(p, 'intake_item', item)
                if item['source']['provider'] not in {'camera', 'files'} or (item['size_bytes'] and item['offset'] == item['size_bytes']):
                    self.enqueue(p, item_id, 'stage')
            result_id = ident(id, item_id)
            try:
                result = self.read(p, 'intake_result', result_id)
            except Missing:
                continue
            if result['state'] == 'needs_attention':
                result.update(state='waiting', error=None, lease_until=0)
                self.save(p, 'intake_result', result)
        self.enqueue(p, id, 'submit')
        return self.submission(p, id)

    def cancel(self, p, id):
        doc = self.read(p, 'intake_submission', id)
        if not doc['cancel_requested']:
            doc['cancel_requested'] = True
            self.save(p, 'intake_submission', doc)
        self.enqueue(p, id, 'submit')
        return self.submission(p, id)

    def discard(self, p, id, revision):
        draft = self.draft(p, id, mutable=True)
        if draft['revision'] != revision:
            raise Conflict('The draft changed. Refresh before discarding.')
        draft.update(state='discarded')
        return self.save(p, 'intake_draft', draft)
