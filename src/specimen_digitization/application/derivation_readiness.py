"""Read the deployed worker configuration before offering G38 side work."""
from types import MappingProxyType

from .lane_dispatch import RUN_API


class DeployedDerivationWorker:
    """A scoped, read-only check; never starts a job or calls a provider."""

    def __init__(self, config, provenance, dispatcher):
        self.config, self.source_sha, self.dispatcher = config, provenance['source_sha'], dispatcher

    def __call__(self, principal, specimen):
        return self.research_environment(principal, specimen) is not None

    def research_environment(self, principal, specimen):
        """Return only the actual verified worker switch, never process overrides.

        The API admits a durable command; the configured worker still owns
        provider execution. Both G38 and field retry read the same deployment.
        """
        from ..research_harness.committed_pins import committed_harness_route
        if (self.dispatcher is None or self.dispatcher.job != self.config.worker_job
                or specimen.scope != principal.scope or specimen.asset.sensitive is not False
                or principal.scope.collection_id not in dict(self.config.collection_bindings)
                or committed_harness_route(specimen.run.profile_snapshot) is None):
            return None
        try:
            response = self.dispatcher.session().get(RUN_API + self.dispatcher.job, timeout=3)
            if response.status_code != 200:
                return None
            resource = response.json()
            task = resource['template']['template']
            containers = task['containers']
            if len(containers) != 1:
                return None
            environment = containers[0].get('env', [])
            harness = [row for row in environment if row.get('name') == 'SPECIMEN_RESEARCH_HARNESS']
            ready = (resource.get('name') == self.dispatcher.job
                and resource.get('labels', {}).get('source-sha') == self.source_sha
                and resource.get('reconciling') not in (True,)
                and resource.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED'
                and resource.get('template', {}).get('taskCount') == 1
                and resource.get('template', {}).get('parallelism') == 1
                and task.get('maxRetries', 0) == 0
                and containers[0].get('args') == ['--mode', 'production', '--drain', '--max-seconds', '3300']
                and harness == [{'name':'SPECIMEN_RESEARCH_HARNESS', 'value':'on'}])
            if ready:
                return MappingProxyType({row['name']: row['value'] for row in harness})
            return None
        except Exception:
            return None
