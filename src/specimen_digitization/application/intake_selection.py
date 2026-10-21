"""Durable, bounded metadata checks for an already authorized Picker selection."""
import time
from uuid import uuid4

from requests import RequestException

from .intake_connections import picked_file_ids
from .intake_sources import ImportProblem
from .storage import Conflict, Missing

CHUNK_SIZE = 50
CHUNK_SECONDS = 3.0
LEASE_SECONDS = 60


def selection_reply(doc):
    result = dict(state=doc['state'], items=doc.get('items', []), failures=doc.get('failures', []))
    if doc['state'] == 'selecting':
        result['progress'] = dict(processed=doc['selection_cursor'], total=len(doc['selection_ids']))
    if error := doc.get('selection_error') or doc.get('error'):
        result['error'] = error
    return result


class PickerSelection:
    def __init__(self, service, adapter, *, clock=time.time, monotonic=time.monotonic):
        self.service, self.adapter, self.clock, self.monotonic = service, adapter, clock, monotonic

    def schedule(self, p, doc):
        """Ensure one existing intake-worker job; polling never owns continuation."""
        from .bulk_intake import ident
        if doc['state'] != 'selecting' or not self.service.dispatch_intake:
            return doc
        try:
            job = self.service.repo.document(p.scope, 'intake_job', ident(doc['id'], 'selection'))
            if job['owner_id'] != p.user_id or job['target'] != doc['id'] or job['operation'] != 'selection':
                raise Conflict('Picker job identity changed')
            if job['state'] == 'awaiting_authorization':
                connection = self.service.read(p, 'intake_connection', doc['connection_id'])
                if (connection['state'] == 'connected'
                        and connection['revision'] > job.get('authorization_revision', 0)
                        and max(doc.get('selection_retry_at', 0), job.get('next_attempt', 0)) <= self.clock()):
                    job = self.service.enqueue(p, doc['id'], 'selection')
            elif job['state'] == 'waiting':
                job = self.service.wake_job(p, job)
        except Missing:
            job = self.service.enqueue(p, doc['id'], 'selection')
        if job['state'] == 'needs_attention':
            return dict(doc, selection_error=dict(code='selection_retry_exhausted',
                message='Checking paused after repeated failures. Retry to continue with your saved selection.',
                action='retry', retryable=True))
        if job.get('error') and not doc.get('selection_error'):
            return dict(doc, selection_error=job['error'])
        return doc

    def status(self, p, doc):
        if self.service.dispatch_intake:
            return self.schedule(p, doc)
        return self.advance(p, doc['id']) if doc['state'] == 'selecting' else doc

    def retry(self, p, doc):
        """An explicit retry may reset exhaustion, never a live lease or backoff."""
        from .bulk_intake import ident
        if doc['state'] != 'selecting' or not self.service.dispatch_intake:
            return self.status(p, doc)
        try:
            job = self.service.repo.document(p.scope, 'intake_job', ident(doc['id'], 'selection'))
        except Missing:
            return self.schedule(p, doc)
        if job['owner_id'] != p.user_id or job['target'] != doc['id'] or job['operation'] != 'selection':
            raise Conflict('Picker job identity changed')
        if max(job.get('lease_until', 0), job.get('next_attempt', 0),
               doc.get('selection_lease_until', 0), doc.get('selection_retry_at', 0)) <= self.clock():
            job.update(state='waiting', attempts=0, error=None, next_attempt=0, lease_until=0)
            try:
                self.service.wake_job(p, self.service.save(p, 'intake_job', job))
            except Conflict:
                pass  # A worker or another retry won; retain its authoritative state.
        return self.status(p, self.service.read(p, 'intake_oauth', doc['id']))

    def begin(self, p, doc, ids, source):
        if len(ids) > 500 or any(picked_file_ids(value) != [value] for value in ids):
            raise ValueError('Select at most 500 valid Drive files')
        ids = list(dict.fromkeys(ids))
        if doc['state'] in {'selecting', 'selected'}:
            if doc.get('selection_ids') == ids and doc.get('selection_source') == source:
                return self.schedule(p, doc)
            raise Conflict('This Picker selection has already been retained')
        if doc['state'] not in {'authorized', 'picking'}:
            raise Conflict('This Picker session cannot retain a selection')
        doc = dict(doc, state='selecting' if ids else 'selected', selection_ids=ids,
            selection_source=source, selection_cursor=0, items=[], failures=[],
            selection_lease=None, selection_lease_until=0, selection_retry_at=0, selection_error=None)
        try:
            saved = self.service.save(p, 'intake_oauth', doc)
        except Conflict:
            current = self.service.read(p, 'intake_oauth', doc['id'])
            if current.get('selection_ids') == ids and current.get('selection_source') == source:
                saved = current
            else:
                raise
        return self.schedule(p, saved)

    def owned_save(self, p, id, token, update):
        current = self.service.read(p, 'intake_oauth', id)
        if (current['state'] != 'selecting' or current.get('selection_lease') != token
                or current.get('selection_lease_until', 0) <= self.clock()):
            return current, False
        update(current)
        try:
            return self.service.save(p, 'intake_oauth', current), True
        except Conflict:
            return self.service.read(p, 'intake_oauth', id), False

    def advance(self, p, id, *, deadline=None):
        started = self.monotonic()
        doc = self.service.read(p, 'intake_oauth', id)
        if (doc['state'] != 'selecting' or doc.get('selection_lease_until', 0) > self.clock()
                or doc.get('selection_retry_at', 0) > self.clock()):
            return doc
        token = str(uuid4())
        doc.update(selection_lease=token, selection_lease_until=self.clock() + LEASE_SECONDS)
        try:
            doc = self.service.save(p, 'intake_oauth', doc)
        except Conflict:
            return self.service.read(p, 'intake_oauth', id)
        for _ in range(CHUNK_SIZE):
            if (self.monotonic() - started >= CHUNK_SECONDS
                    or (deadline is not None and self.clock() >= deadline)):
                break
            file_id = doc['selection_ids'][doc['selection_cursor']]
            row, failure, error = None, None, None
            try:
                adapter = self.adapter(p, doc['connection_id'])
                row = adapter.row(doc['connection_id'], adapter.metadata(p, doc['connection_id'], file_id, timeout=5))
            except ImportProblem as exc:
                # A permanent file denial is one failed item. Global provider,
                # credential or transient errors retain the cursor for retry.
                if exc.intake_problem['action'] == 'file_access' and not exc.intake_problem['retryable']:
                    failure = dict(id=file_id, error=exc.intake_problem)
                else:
                    error = exc.intake_problem
            except (RequestException, TimeoutError, OSError):
                error = dict(code='provider_unavailable', message='Could not check this photo. Retrying shortly.',
                    action='retry', retryable=True)
            if error:
                def pause(current):
                    current.update(selection_error=error, selection_retry_at=self.clock() + min(3600, max(2, error.get('retry_after', 2))),
                        selection_lease=None, selection_lease_until=0)
                doc, _ = self.owned_save(p, id, token, pause)
                return doc
            def checkpoint(current):
                current['items' if row is not None else 'failures'].append(row if row is not None else failure)
                current['selection_cursor'] += 1
                current.update(selection_error=None, selection_retry_at=0)
                if current['selection_cursor'] == len(current['selection_ids']):
                    current.update(state='selected', selection_lease=None, selection_lease_until=0)
            doc, saved = self.owned_save(p, id, token, checkpoint)
            if not saved or doc['state'] == 'selected':
                return doc
        doc, _ = self.owned_save(p, id, token, lambda current: current.update(selection_lease=None, selection_lease_until=0))
        return doc
