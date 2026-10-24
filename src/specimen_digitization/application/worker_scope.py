"""Deployment-owned collection boundaries for intake and scientific workers."""

from dataclasses import dataclass
import json
from uuid import UUID

from .domain import Scope
from .lane_dispatch import scope_key


@dataclass(frozen=True)
class WorkerScopePolicy:
    scope: Scope | None = None
    excluded: frozenset[str] = frozenset()

    def memberships(self, rows):
        """Admit the entire inventory before any collection or owner is read."""
        rows = [row for row in rows if row.get('role') in {'operator', 'reviewer', 'manager', 'admin'}]
        if self.scope is not None:
            matched = [row for row in rows if scope_key(Scope(
                organization_id=row['organization_id'],
                collection_id=row['collection_id'],
            )) == scope_key(self.scope)]
            if len(matched) != 1:
                raise PermissionError('Dedicated worker requires its configured collection membership')
            return matched
        return [row for row in rows if scope_key(Scope(
            organization_id=row['organization_id'], collection_id=row['collection_id'],
        )) not in self.excluded]


def worker_scope_from_env(env, *, lane):
    """No request inputs, job overrides or membership-driven route selection.

    Shared jobs exclude every dedicated route. Dedicated jobs must agree on
    scope, actor and their own continuation job before they can read any work.
    """
    from .runtime_config import collection_worker_jobs

    if lane not in {'intake', 'worker'}:
        raise ValueError('Unknown worker lane')
    routes = dict(collection_worker_jobs(env, env.get('GOOGLE_CLOUD_PROJECT')))
    actor = env.get('SPECIMEN_WORKER_ACTOR_UID', '')
    own_job = env.get('SPECIMEN_INTAKE_JOB' if lane == 'intake' else 'SPECIMEN_WORKER_JOB', '')
    actual_job = env.get('CLOUD_RUN_JOB')
    if actual_job and (not own_job or actual_job != own_job.rsplit('/', 1)[-1]):
        raise ValueError('Worker continuation must name its current Cloud Run job')
    raw_scope = env.get('SPECIMEN_WORKER_SCOPE_JSON')
    if raw_scope:
        try:
            value = json.loads(raw_scope)
            if not isinstance(value, dict) or set(value) != {'organization_id', 'collection_id'}:
                raise ValueError
            scope = Scope(**{key: str(UUID(value[key])) for key in value})
        except (TypeError, ValueError, AttributeError):
            raise ValueError('SPECIMEN_WORKER_SCOPE_JSON must name one exact collection') from None
        route = routes.get(scope_key(scope))
        if route is None or route['actor_uid'] != actor or route[f'{lane}_job'] != own_job:
            raise ValueError('Dedicated worker scope, actor and continuation job must match server routing')
        return WorkerScopePolicy(scope=scope)
    if any(own_job in {route['worker_job'], route['intake_job']}
           for route in routes.values()):
        raise ValueError('Dedicated worker requires SPECIMEN_WORKER_SCOPE_JSON')
    return WorkerScopePolicy(excluded=frozenset(routes))
