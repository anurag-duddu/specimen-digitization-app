"""Run the real smoke shell against synthetic curl, sleep and clock executables."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/ci/smoke_hosting.sh'
SITE = 'https://specimen-digitization.web.app'
SHA = 'a' * 40
OLD = 'b' * 40
TITLE = '<!doctype html><html><head><title>Specimen Digitization</title></head><body></body></html>'


def marker(sha=SHA):
    return {'schemaVersion': 1, 'repository': 'anurag-duddu/specimen-digitization-app',
            'commitSha': sha, 'runId': '123', 'runAttempt': '1', 'builtAt': '2026-09-09T18:32:38Z'}


FAKE = r'''
import json, os, pathlib, sys
path = pathlib.Path(os.environ['SMOKE_TEST_STATE'])
s = json.loads(path.read_text())
args, command = sys.argv[1:], pathlib.Path(sys.argv[0]).name
result, code = '', 0
if command == 'date':
    assert args == ['+%s'], args
    s['clock_calls'] = s.get('clock_calls', 0) + 1
    if s.get('reverse_clock') and s['clock_calls'] == 3:
        s['now'] -= 1
    result = '1000' if s.get('freeze_clock') else str(int(s['now']))
elif command == 'sleep':
    duration = int(args[0])
    assert 0 < duration <= 5
    s['sleeps'].append(duration)
    s['now'] += duration
elif command == 'curl':
    url = args[-1]
    kind = 'marker' if '/deployment.json?' in url else 'html'
    queue = s[kind]
    response = queue.pop(0) if len(queue) > 1 else queue[0]
    def option(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    maximum = float(option('--max-time', '999999'))
    connect = float(option('--connect-timeout', '999999'))
    elapsed = response.get('elapsed', 0)
    s['calls'].append({'kind': kind, 'url': url, 'at': s['now'], 'args': args,
                       'maximum': maximum, 'connect': connect})
    s['now'] += min(elapsed, maximum)
    code = 28 if elapsed > maximum else response.get('code', 0)
    body = response.get('body', '')
    if not isinstance(body, str):
        body = json.dumps(body)
    output = option('--output')
    if output:
        pathlib.Path(output).write_text(body)
        result = response.get('status', '200') if '--write-out' in args else ''
    else:
        result = body
else:
    raise AssertionError(command)
path.write_text(json.dumps(s))
sys.stdout.write(result)
sys.exit(code)
'''


def run_smoke(tmp_path, *, markers=None, html=None, site=SITE, sha=SHA, reverse_clock=False, freeze_clock=False):
    assert shutil.which('jq'), 'jq is required by the production shell'
    state = {'now': 1000, 'calls': [], 'sleeps': [], 'reverse_clock': reverse_clock, 'freeze_clock': freeze_clock,
             'marker': markers or [{'body': marker()}], 'html': html or [{'body': TITLE}]}
    state_path = tmp_path / 'state.json'
    state_path.write_text(json.dumps(state))
    binary = tmp_path / 'bin'
    binary.mkdir()
    for name in ('curl', 'sleep', 'date'):
        target = binary / name
        target.write_text(f'#!{sys.executable}\n' + FAKE)
        target.chmod(0o700)
    env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
           'SMOKE_TEST_STATE': str(state_path)}
    result = subprocess.run(['bash', str(SCRIPT), site, sha], env=env, capture_output=True,
                            text=True, timeout=30)
    return result, json.loads(state_path.read_text())


def assert_bounded(state):
    assert state['now'] <= 1300
    for call in state['calls']:
        assert 0 < call['maximum'] <= min(15, 1300 - call['at'])
        assert 0 < call['connect'] <= min(5, call['maximum'])
        args = call['args']
        assert args[0] == '--disable'
        assert '--retry' in args and args[args.index('--retry') + 1] == '0'
        assert '--location' not in args
        assert call['url'].startswith(SITE + '/') and '?sha=' + SHA in call['url']


def test_stale_same_repository_marker_can_propagate_before_strict_success(tmp_path):
    result, state = run_smoke(tmp_path, markers=[{'body': marker(OLD)}, {'body': marker()}])
    assert result.returncode == 0, result.stderr
    assert [c['kind'] for c in state['calls']].count('marker') == 2
    assert state['sleeps'] == [5]
    assert SHA in result.stdout and 'Production smoke passed' in result.stdout
    assert_bounded(state)


def test_persistently_stale_marker_expires_and_never_reports_success(tmp_path):
    result, state = run_smoke(tmp_path, markers=[{'body': marker(OLD)}])
    assert result.returncode != 0
    assert len([c for c in state['calls'] if c['kind'] == 'marker']) > 1
    assert 'deadline' in result.stderr.lower()
    assert 'Production smoke passed' not in result.stdout
    assert_bounded(state)


@pytest.mark.parametrize('body', [
    '<html>arbitrary HTTP 200</html>', '{}', '[]', 'null',
    json.dumps({**marker(), 'repository': 'foreign/repository'}),
    json.dumps({**marker(OLD), 'commitSha': 'not-a-sha'}),
    json.dumps({**marker(OLD), 'schemaVersion': 2}),
    json.dumps({**marker(OLD), 'runId': 'unknown'}),
    json.dumps({**marker(OLD), 'builtAt': '2026-02-31T18:32:38Z'}),
    json.dumps(marker(OLD)) + json.dumps(marker()),
    json.dumps(marker())[:-1] + ',"repository":"foreign/repository"}',
    json.dumps(marker())[:-1] + ',"commitSha":"' + OLD + '"}',
])
def test_invalid_or_foreign_marker_fails_immediately_without_semantic_retry(tmp_path, body):
    result, state = run_smoke(tmp_path, markers=[{'body': body}, {'body': marker()}])
    assert result.returncode != 0
    assert len([c for c in state['calls'] if c['kind'] == 'marker']) == 1
    assert not state['sleeps']
    assert 'Production smoke passed' not in result.stdout


def test_matching_sha_still_requires_real_application_title(tmp_path):
    result, state = run_smoke(tmp_path, html=[{'body': '<html><title>Other app</title></html>'}])
    assert result.returncode != 0
    assert 'Production smoke passed' not in result.stdout
    assert not state['sleeps']


def test_network_failures_share_total_budget_and_cap_every_curl(tmp_path):
    result, state = run_smoke(tmp_path, markers=[{'body': '', 'status': '000', 'code': 28, 'elapsed': 1000}])
    assert result.returncode != 0
    assert len([c for c in state['calls'] if c['kind'] == 'marker']) > 1
    assert_bounded(state)
    assert 'deadline' in result.stderr.lower()


def test_network_then_stale_then_current_uses_one_shared_budget(tmp_path):
    result, state = run_smoke(tmp_path, html=[{'code': 7, 'status': '000', 'elapsed': 3}, {'body': TITLE}],
        markers=[{'code': 28, 'status': '000', 'elapsed': 1000}, {'body': marker(OLD)}, {'body': marker()}])
    assert result.returncode == 0, result.stderr
    assert len(state['sleeps']) == 3
    assert_bounded(state)


@pytest.mark.parametrize('status', ['301', '302', '401', '403'])
def test_redirects_and_auth_errors_are_not_readiness_or_retry(tmp_path, status):
    result, state = run_smoke(tmp_path, markers=[{'body': marker(), 'status': status}])
    assert result.returncode != 0
    assert not state['sleeps']
    assert len([c for c in state['calls'] if c['kind'] == 'marker']) == 1


@pytest.mark.parametrize('site,sha', [('https://foreign.example', SHA), (SITE + '/', SHA), (SITE, 'bad'), (SITE, 'A' * 40)])
def test_unapproved_site_or_sha_never_makes_a_request(tmp_path, site, sha):
    result, state = run_smoke(tmp_path, site=site, sha=sha)
    assert result.returncode != 0
    assert not state['calls']


def test_backward_clock_fails_closed_before_new_request(tmp_path):
    result, state = run_smoke(tmp_path, reverse_clock=True, markers=[{'body': marker(OLD)}, {'body': marker()}])
    assert result.returncode != 0
    assert 'clock' in result.stderr.lower()
    assert not state['sleeps']


def test_matching_marker_arriving_at_deadline_cannot_qualify(tmp_path):
    responses = [{'body': marker(OLD), 'elapsed': 10} for _ in range(19)]
    responses.append({'body': marker(), 'elapsed': 15})
    result, state = run_smoke(tmp_path, markers=responses)
    assert result.returncode != 0
    assert state['now'] == 1300
    assert 'deadline' in result.stderr.lower()
    assert 'Production smoke passed' not in result.stdout
    assert_bounded(state)


@pytest.mark.parametrize('status', ['408', '429', '503'])
def test_transient_http_error_can_recover_without_internal_curl_retries(tmp_path, status):
    result, state = run_smoke(tmp_path, markers=[{'status': status, 'code': 22}, {'body': marker()}])
    assert result.returncode == 0, result.stderr
    assert state['sleeps'] == [5]
    assert state['calls'][-1]['kind'] == 'marker'
    assert_bounded(state)


@pytest.mark.parametrize('body', [
    json.dumps({**marker(), 'schemaVersion': 2}),
    json.dumps({**marker(), 'runAttempt': 'unknown'}),
    json.dumps({**marker(), 'builtAt': '2026-02-31T18:32:38Z'}),
    '{"repository":"foreign/repository",' + json.dumps(marker())[1:],
    '{"commitSha":"' + OLD + '",' + json.dumps(marker())[1:],
])
def test_expected_sha_cannot_hide_invalid_provenance(tmp_path, body):
    result, state = run_smoke(tmp_path, markers=[{'body': body}])
    assert result.returncode != 0
    assert not state['sleeps']
    assert len([c for c in state['calls'] if c['kind'] == 'marker']) == 1


def test_title_embedded_in_json_is_not_application_html(tmp_path):
    result, state = run_smoke(tmp_path, html=[{'body': json.dumps({'unexpected': TITLE})}])
    assert result.returncode != 0
    assert 'Production smoke passed' not in result.stdout
    assert not state['sleeps']


def test_partial_http_200_transport_failure_may_retry_without_parsing_partial_marker(tmp_path):
    result, state = run_smoke(tmp_path, markers=[
        {'body': '{"repository":', 'status': '200', 'code': 28, 'elapsed': 3}, {'body': marker()}])
    assert result.returncode == 0, result.stderr
    assert state['sleeps'] == [5]
    assert_bounded(state)


@pytest.mark.parametrize('code', [23, 60, 63])
def test_local_write_tls_validation_and_size_failures_are_not_retried(tmp_path, code):
    result, state = run_smoke(tmp_path, markers=[{'code': code, 'status': '000'}, {'body': marker()}])
    assert result.returncode != 0
    assert not state['sleeps']
    assert len([c for c in state['calls'] if c['kind'] == 'marker']) == 1



def test_frozen_clock_exhausts_fixed_attempt_limit(tmp_path):
    result, state = run_smoke(tmp_path, markers=[{'body': marker(OLD)}], freeze_clock=True)
    assert result.returncode != 0
    assert 'attempt limit' in result.stderr.lower()
    assert len([c for c in state['calls'] if c['kind'] == 'marker']) == 60
    assert len(state['calls']) == 120
    assert 'Production smoke passed' not in result.stdout


def test_separate_partial_json_documents_cannot_combine_into_one_marker(tmp_path):
    value = marker()
    first = {key: value[key] for key in ('schemaVersion', 'repository', 'commitSha')}
    second = {key: value[key] for key in ('runId', 'runAttempt', 'builtAt')}
    result, state = run_smoke(tmp_path, markers=[{'body': json.dumps(first) + '\n' + json.dumps(second)}])
    assert result.returncode != 0
    assert not state['sleeps']
    assert 'Production smoke passed' not in result.stdout
