"""Durable, bounded metadata checks for an already authorized Picker selection."""
import time
from uuid import uuid4

from requests import RequestException

from .intake_connections import picked_file_ids
from .intake_sources import ImportProblem
from .storage import Conflict

CHUNK_SIZE = 5
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

    def begin(self, p, doc, ids, source):
        if len(ids) > 500 or any(picked_file_ids(value) != [value] for value in ids):
            raise ValueError('Select at most 500 valid Drive files')
        ids = list(dict.fromkeys(ids))
        if doc['state'] in {'selecting', 'selected'}:
            if doc.get('selection_ids') == ids and doc.get('selection_source') == source:
                return doc
            raise Conflict('This Picker selection has already been retained')
        if doc['state'] not in {'authorized', 'picking'}:
            raise Conflict('This Picker session cannot retain a selection')
        doc = dict(doc, state='selecting' if ids else 'selected', selection_ids=ids,
            selection_source=source, selection_cursor=0, items=[], failures=[],
            selection_lease=None, selection_lease_until=0, selection_retry_at=0, selection_error=None)
        try:
            return self.service.save(p, 'intake_oauth', doc)
        except Conflict:
            current = self.service.read(p, 'intake_oauth', doc['id'])
            if current.get('selection_ids') == ids and current.get('selection_source') == source:
                return current
            raise

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

    def advance(self, p, id):
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
            if self.monotonic() - started >= CHUNK_SECONDS:
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
