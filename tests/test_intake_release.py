"""Protected definition only: these tests never contact Cloud Run."""
import copy
import importlib.util
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/release'))
_spec = importlib.util.spec_from_file_location('intake_release', ROOT / 'scripts/release/deploy_intake.py')
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)
SHA = 'a' * 40
IMAGE = f'{release.settings.REGION}-docker.pkg.dev/{release.settings.PROJECT}/specimen-runtime/api@sha256:' + 'b' * 64


def definition():
    job = release.settings.INTAKE
    return {'metadata': {'labels': {'source-sha': SHA}}, 'spec': {'template': {'spec': {
        'taskCount': 1, 'parallelism': 1, 'template': {'spec': {
            'serviceAccountName': job['service_account'], 'maxRetries': 2, 'timeoutSeconds': 3600,
            'containers': [{'image': IMAGE, 'command': job['command'], 'args': job['args'],
                'resources': {'limits': {'cpu': job['cpu'], 'memory': job['memory']}},
                'env': [{'name': k, 'value': v} for k, v in release.job_env().items()] + [
                    {'name': k, 'valueFrom': {'secretKeyRef': {'name': v, 'key': str(release.settings.SECRET_VERSIONS[v])}}}
                    for k, v in job['secret_env'].items()]}]}}}}}}


def test_intake_definition_never_executes_and_uses_api_digest():
    command = release.command(IMAGE, SHA, Path('/tmp/env.yaml'))
    assert command[:5] == ['gcloud', 'run', 'jobs', 'deploy', 'specimen-intake']
    assert '--execute-now' not in command
    release.verify_definition(definition(), IMAGE, SHA)
    with pytest.raises(ValueError): release.command(IMAGE.split('@')[0] + ':latest', SHA, Path('/tmp/env.yaml'))
    with pytest.raises(ValueError): release.release_context({'GITHUB_REF': 'refs/heads/main'})


@pytest.mark.parametrize('field,value', [('taskCount', 2), ('parallelism', 2)])
def test_intake_definition_rejects_unreviewed_parallelism(field, value):
    resource = copy.deepcopy(definition())
    resource['spec']['template']['spec'][field] = value
    with pytest.raises(ValueError): release.verify_definition(resource, IMAGE, SHA)


def test_intake_job_requires_private_api_invoker():
    binding = {'role': 'roles/run.invoker', 'members': ['serviceAccount:' + release.settings.API['service_account']]}
    release.verify_policy({'bindings': [binding]})
    for policy in ({'bindings': []}, {'bindings': [binding, {'role': 'roles/run.invoker', 'members': ['allUsers']}]}):
        with pytest.raises(ValueError): release.verify_policy(policy)
