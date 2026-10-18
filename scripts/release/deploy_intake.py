"""Define the private intake job through the existing protected runtime release."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from deploy_models import checked_image, collection_routes, release_context, read, scoped_job_env, LOCATION, settings
from deploy_api import api_env


def job_env():
    return {**api_env(), **settings.tracing_env('intake')}


def command(image, sha, env_file, *, job_name='specimen-intake'):
    import re
    if job_name != 'specimen-intake' and not re.fullmatch(r'specimen-intake-[a-z0-9-]+', job_name):
        raise ValueError('Dedicated intake jobs require an explicit intake name')
    checked_image('api', image)
    job = settings.INTAKE
    secrets = ','.join(f'{name}={secret}:{settings.SECRET_VERSIONS[secret]}'
        for name, secret in job['secret_env'].items())
    return ['gcloud', 'run', 'jobs', 'deploy', job_name, *LOCATION, '--quiet',
        '--image', image, '--service-account', job['service_account'], '--cpu', job['cpu'],
        '--memory', job['memory'], '--tasks', '1', '--parallelism', '1', '--max-retries', str(job['max_retries']),
        '--task-timeout', str(job['timeout_seconds']), '--command', ','.join(job['command']),
        '--args', ','.join(job['args']), '--env-vars-file', str(env_file), '--set-secrets', secrets,
        '--labels', f'source-sha={sha}']


def verify_definition(resource, image, sha, *, expected_env=None):
    spec = resource.get('spec', {}).get('template', {}).get('spec', {})
    task = spec.get('template', {}).get('spec', {})
    containers = task.get('containers', [])
    if len(containers) != 1:
        raise ValueError('intake: exactly one container is required')
    container = containers[0]
    job = settings.INTAKE
    if (resource.get('metadata', {}).get('labels', {}).get('source-sha') != sha
        or container.get('image') != image or task.get('serviceAccountName') != job['service_account']
        or container.get('command') != job['command'] or container.get('args') != job['args']
        or (int(spec.get('taskCount', 0)), int(spec.get('parallelism', 0)), int(task.get('maxRetries', -1)), int(task.get('timeoutSeconds', 0))) != (1, 1, 2, 3600)):
        raise ValueError('intake: deployed job differs from reviewed definition')
    if container.get('resources', {}).get('limits') != {'cpu': job['cpu'], 'memory': job['memory']}:
        raise ValueError('intake: resource limits differ')
    actual = {row['name']: row for row in container.get('env', [])}
    expected = job_env() if expected_env is None else expected_env
    if set(actual) != set(expected) | set(job['secret_env']):
        raise ValueError('intake: unexpected or missing environment setting')
    for name, value in expected.items():
        if actual[name].get('value') != value:
            raise ValueError('intake: environment differs')
    for name, secret in job['secret_env'].items():
        ref = actual[name].get('valueFrom', {}).get('secretKeyRef', {})
        if ref != {'name': secret, 'key': str(settings.SECRET_VERSIONS[secret])}:
            raise ValueError('intake: pinned credential differs')


def verify_policy(policy):
    bindings = policy.get('bindings', [])
    members = {m for b in bindings for m in b.get('members', [])}
    if members & {'allUsers', 'allAuthenticatedUsers'}:
        raise ValueError('intake: job must remain private')
    invokers = {m for b in bindings if b.get('role') == 'roles/run.invoker' and not b.get('condition') for m in b.get('members', [])}
    if f"serviceAccount:{settings.API['service_account']}" not in invokers:
        raise ValueError('intake: scoped API invoker grant is missing; owner setup required')


def main(argv):
    if len(argv) != 2:
        raise ValueError('Usage: deploy_intake.py API_IMAGE_DIGEST')
    sha = release_context(os.environ)
    image = checked_image('api', argv[1])
    routes = collection_routes()
    jobs = [('specimen-intake', job_env())] + [
        (route['intake_job'].rsplit('/', 1)[1], scoped_job_env(job_env(), scope, route))
        for scope, route in routes.items()]
    for name, values in jobs:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'intake-env.yaml'
            path.write_text(''.join(f'{k}: {json.dumps(v)}\n' for k, v in sorted(values.items())))
            subprocess.run(command(image, sha, path, job_name=name), check=True)
        verify_definition(read('jobs', name), image, sha, expected_env=values)
        verify_policy(read('jobs', name, 'get-iam-policy'))
        print(f'Verified private intake job {name} at {sha}; no transfer executed')


if __name__ == '__main__':
    main(sys.argv)
