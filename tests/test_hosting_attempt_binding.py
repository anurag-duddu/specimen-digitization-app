"""Exercise real deploy admission offline; every executable here is synthetic."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/ci/deploy_hosting.sh'
REPOSITORY = 'anurag-duddu/specimen-digitization-app'
SHA = 'a' * 40


def marker():
    return {'schemaVersion': 1, 'repository': REPOSITORY, 'commitSha': SHA,
            'runId': '123', 'runAttempt': '1', 'builtAt': '2026-09-09T18:32:38Z'}


def run_deploy(tmp_path, *, body=None, overrides=None, credential=True):
    assert shutil.which('jq'), 'jq is required by the production shell'
    artifact = tmp_path / 'apps/specimen_digitization/build/web'
    artifact.mkdir(parents=True)
    value = marker() if body is None else body
    (artifact / 'deployment.json').write_text(value if isinstance(value, str) else json.dumps(value))
    creds = tmp_path / 'synthetic-credential.json'
    if credential:
        creds.write_text('{}')
    calls = tmp_path / 'hosting-cli-calls.json'
    binary = tmp_path / 'bin'
    binary.mkdir()
    # The recorder stands in for the installed firebase binary. It is copied into
    # the private prefix by the synthetic npm below, so a deploy can only reach it
    # through an install that actually happened.
    recorder = tmp_path / 'recorder.py'
    recorder.write_text(f'#!{sys.executable}\n'
                        'import json, os, pathlib, sys\n'
                        'pathlib.Path(os.environ["FAKE_CLI_CALLS"]).write_text(json.dumps(sys.argv[1:]))\n')
    fake_npm = binary / 'npm'
    fake_npm.write_text(f'#!{sys.executable}\n'
                        'import json, os, pathlib, shutil, sys\n'
                        'argv = sys.argv[1:]\n'
                        'pathlib.Path(os.environ["FAKE_NPM_CALLS"]).write_text(json.dumps(argv))\n'
                        'target = pathlib.Path(argv[argv.index("--prefix") + 1]) / "node_modules" / ".bin"\n'
                        'target.mkdir(parents=True, exist_ok=True)\n'
                        'shutil.copy(os.environ["FAKE_CLI_RECORDER"], target / "firebase")\n'
                        '(target / "firebase").chmod(0o700)\n')
    fake_npm.chmod(0o700)
    # A reintroduced npx must fail the exact-command assertion rather than work.
    fake_npx = binary / 'npx'
    fake_npx.write_text(f'#!{sys.executable}\n'
                        'import json, os, pathlib, sys\n'
                        'pathlib.Path(os.environ["FAKE_CLI_CALLS"]).write_text(json.dumps(["npx", *sys.argv[1:]]))\n')
    fake_npx.chmod(0o700)
    # Do not pass local cloud credentials or user configuration into this fixture.
    env = {'PATH': str(binary) + os.pathsep + os.environ['PATH'], 'FAKE_CLI_CALLS': str(calls),
           'FAKE_NPM_CALLS': str(tmp_path / 'npm-calls.json'), 'FAKE_CLI_RECORDER': str(recorder),
           'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REPOSITORY': REPOSITORY,
           'GITHUB_REF': 'refs/heads/main',
           'GITHUB_WORKFLOW_REF': REPOSITORY + '/.github/workflows/ci-cd.yml@refs/heads/main',
           'DEPLOYMENT_ENVIRONMENT': 'production', 'GITHUB_SHA': SHA, 'GITHUB_RUN_ID': '123',
           'GITHUB_RUN_ATTEMPT': '1', 'GOOGLE_GHA_CREDS_PATH': str(creds)}
    for key, value in (overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    result = subprocess.run(['bash', str(SCRIPT)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=5)
    return result, json.loads(calls.read_text()) if calls.exists() else []


def test_exact_artifact_attempt_reaches_only_synthetic_hosting_command(tmp_path):
    result, calls = run_deploy(tmp_path)
    assert result.returncode == 0, result.stderr
    assert calls == ['deploy', '--only', 'hosting',
                     '--project', 'specimen-digitization', '--non-interactive',
                     '--message', 'GitHub Actions ' + SHA]


def test_the_pinned_cli_is_installed_without_running_dependency_scripts(tmp_path):
    result, calls = run_deploy(tmp_path)
    assert result.returncode == 0, result.stderr
    npm = json.loads((tmp_path / 'npm-calls.json').read_text())
    assert npm[0] == 'install'
    assert '--ignore-scripts' in npm
    assert 'firebase-tools@15.8.0' in npm
    # The install must land in a private prefix, never in the checkout.
    prefix = npm[npm.index('--prefix') + 1]
    assert Path(prefix).is_absolute() and not prefix.startswith(str(tmp_path) + os.sep + 'apps')


@pytest.mark.parametrize('key', ['GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'])
@pytest.mark.parametrize('value', [None, '', 'unknown', '0', '01', '-1', '+1', '1.0', '1\n'])
def test_invalid_workflow_identity_stops_before_credentials_or_any_cli(tmp_path, key, value):
    result, calls = run_deploy(tmp_path, overrides={key: value}, credential=False)
    assert result.returncode != 0
    assert 'run' in result.stderr.lower()
    assert 'credential' not in result.stderr.lower()
    assert calls == []


@pytest.mark.parametrize('field,value', [
    ('repository', 'foreign/repository'), ('commitSha', 'b' * 40),
    ('runId', '124'), ('runAttempt', '2'), ('runId', 'unknown'), ('runAttempt', '01'),
    ('runId', 123), ('runAttempt', True), ('schemaVersion', True), ('schemaVersion', 2),
    ('builtAt', '2026-02-31T18:32:38Z'), ('builtAt', None),
])
def test_foreign_stale_or_invalid_marker_never_reaches_the_cli(tmp_path, field, value):
    result, calls = run_deploy(tmp_path, body={**marker(), field: value})
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize('field', list(marker()))
def test_missing_marker_field_never_reaches_the_cli(tmp_path, field):
    value = marker()
    del value[field]
    result, calls = run_deploy(tmp_path, body=value)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize('field', list(marker()))
def test_duplicate_marker_field_cannot_hide_behind_matching_last_value(tmp_path, field):
    body = '{' + json.dumps(field) + ':"wrong",' + json.dumps(marker())[1:]
    result, calls = run_deploy(tmp_path, body=body)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize('body', [
    {}, [], 'null', '<html>not metadata</html>', {**marker(), 'extra': 'unexpected'},
    json.dumps(marker()) + '\n' + json.dumps(marker()),
    json.dumps({'commitSha': SHA}) + '\n' + json.dumps({k: v for k, v in marker().items() if k != 'commitSha'}),
])
def test_marker_requires_one_complete_exact_object(tmp_path, body):
    result, calls = run_deploy(tmp_path, body=body)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize('key,value', [
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
    ('GITHUB_REPOSITORY', 'foreign/repository'), ('GITHUB_REF', 'refs/heads/other'),
    ('GITHUB_WORKFLOW_REF', REPOSITORY + '/.github/workflows/other.yml@refs/heads/main'),
    ('DEPLOYMENT_ENVIRONMENT', 'preview'), ('GITHUB_SHA', 'bad'),
])
def test_existing_protected_release_context_still_required(tmp_path, key, value):
    result, calls = run_deploy(tmp_path, overrides={key: value})
    assert result.returncode != 0
    assert calls == []


def test_workflow_artifact_and_public_verification_share_exact_attempt():
    workflow = yaml.load((ROOT / '.github/workflows/ci-cd.yml').read_text(), Loader=yaml.BaseLoader)
    upload = next(step for step in workflow['jobs']['flutter']['steps']
                  if step.get('name') == 'Upload web release')
    deploy = workflow['jobs']['deploy-hosting']
    download = next(step for step in deploy['steps'] if step.get('name') == 'Download tested web release')
    expected = 'flutter-web-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}'
    assert upload['with']['name'] == download['with']['name'] == expected
    assert download['with'] == {'name': expected, 'path': 'apps/specimen_digitization/build/web'}
    smoke = next(step for step in deploy['steps'] if step.get('name') == 'Verify the public site')
    assert smoke['run'] == ('scripts/ci/smoke_hosting.sh https://specimen-digitization.web.app '
                            '"$GITHUB_SHA" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT"')
