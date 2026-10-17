"""Bounded, leased intake work. Scientific inference remains in its own worker."""
from uuid import uuid4
from .bulk_intake import problem
from .storage import Conflict, Missing


def active_jobs(repository, scope):
    if hasattr(repository, 'active_intake_jobs'):
        return repository.active_intake_jobs(scope)
    return (job for job in repository.documents(scope, 'intake_job') if job['state'] == 'waiting')


class IntakeWorker:
    def __init__(self, service):
        self.service = service

    def drain(self, p, *, limit=500, deadline=None):
        service = self.service
        processed = 0
        for job in active_jobs(service.repo, p.scope):
            if processed >= limit or (deadline is not None and service.clock() >= deadline):
                break
            if job['owner_id'] != p.user_id or job['state'] != 'waiting' or job.get('next_attempt', 0) > service.clock():
                continue
            if job.get('lease_until', 0) > service.clock():
                continue
            job.update(lease_until=service.clock() + 180, lease_token=str(uuid4()), error=None)
            try:
                job = service.save(p, 'intake_job', job)
            except Conflict:
                continue
            try:
                service.authorize(p)
                if job['operation'] == 'stage':
                    service.stage(p, job['target'])
                else:
                    if job.get('draft_id'):
                        service._materialize_submission(p, service.draft(p, job['draft_id']), wake=False)
                    result = service.process_submission(p, job['target'], deadline=min(
                        deadline or float('inf'), service.clock() + 120))
                    if any(result['counts'].get(s, 0) for s in ('waiting', 'transferring', 'checking')):
                        items = service.read_many(p, 'intake_item', [e['id'] for e in result['entries']])
                        results = service.results(p, result, result['entries'])
                        runnable = any(r['state'] in {'waiting', 'checking'} and
                            items[r['item_id']]['state'] == 'ready' for r in results)
                        job.update(state='waiting' if runnable else 'awaiting_content',
                            lease_until=0, next_attempt=service.clock() + 10)
                        service.save(p, 'intake_job', job)
                        continue
                job.update(state='done', lease_until=0)
            except Conflict:
                job.update(lease_until=0, next_attempt=service.clock() + 5)
            except Exception as exc:
                # Raw provider exception strings can contain URLs and tokens.
                details = getattr(exc, 'intake_problem', None) or problem(
                    'transfer_failed', 'Could not finish this transfer. Retry when access and connection are available.')
                attempts = job.get('attempts', 0) + 1
                retry = details.get('retryable', False) and attempts < 4
                job.update(state='waiting' if retry else 'needs_attention', lease_until=0,
                    error=details, attempts=attempts, next_attempt=service.clock() +
                    max(details.get('retry_after', 0), min(300, 5 * 2 ** attempts)))
                if job['operation'] == 'stage':
                    try:
                        item = service.item(p, job['target'])
                        item.update(state='waiting' if retry else 'needs_attention', error=details)
                        service.save(p, 'intake_item', item)
                    except (Missing, PermissionError):
                        pass
            try:
                service.save(p, 'intake_job', job)
            except Conflict:
                pass  # An API request queued newer work; never erase its wake-up.
            processed += 1
        return dict(processed=processed)


def main():
    """Cloud Run job entry point. It reads queued work; accepts no owner override."""
    import argparse
    import os
    import time
    from .cli import production_app
    from .domain import Principal, Scope
    from .production import verified_actor_context
    from .runtime_config import RuntimeConfig

    parser = argparse.ArgumentParser()
    parser.add_argument('--max-seconds', type=int, default=3300)
    args = parser.parse_args()
    if not 30 <= args.max_seconds <= 3300:
        parser.error('Use a bounded worker window between 30 and 3300 seconds')
    worker = os.environ.get('SPECIMEN_WORKER_ACTOR_UID')
    if not worker:
        parser.error('A configured worker identity is required')
    app = production_app(RuntimeConfig.from_env())
    service = app.state.intake
    deadline = service.clock() + args.max_seconds
    pending = []
    idle_since = service.clock()
    while service.clock() < deadline:
        pending = []
        with verified_actor_context(worker):
            memberships = service.repo.memberships(worker)
        for membership in memberships:
            scope = Scope(organization_id=membership['organization_id'], collection_id=membership['collection_id'])
            with verified_actor_context(worker):
                jobs = list(active_jobs(service.repo, scope))
            owners = {job['owner_id'] for job in jobs if job['state'] == 'waiting'}
            for owner in owners:
                with verified_actor_context(owner):
                    member = next((m for m in service.repo.memberships(owner)
                        if m['organization_id'] == scope.organization_id and m['collection_id'] == scope.collection_id), None)
                    if not member:
                        continue
                    p = Principal(user_id=owner, scope=scope, role=member['role'])
                    IntakeWorker(service).drain(p, limit=50, deadline=deadline)
                    pending.extend((p, j) for j in active_jobs(service.repo, scope)
                        if j['state'] == 'waiting' and j['owner_id'] == owner)
                    if jobs:
                        idle_since = service.clock()
        if not pending:
            if service.clock() - idle_since >= 65:
                break
            time.sleep(min(5, max(0, deadline - service.clock())))
            continue
        # Honor persisted backoff/leases instead of launching executions in a hot
        # loop. Awaiting client bytes has no timer: save() wakes that work.
        due = min(max(j.get('next_attempt', 0), j.get('lease_until', 0)) for _, j in pending)
        time.sleep(max(0, min(30, deadline - service.clock(), max(1, due - service.clock()))))
    # Continuation re-reads SQL and claims fresh leases; it cannot duplicate a
    # specimen whose creation committed before this execution stopped.
    if pending:
        p, job = pending[0]
        with verified_actor_context(p.user_id):
            service.wake(p, force=True)


if __name__ == '__main__':
    main()
