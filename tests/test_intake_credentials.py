"""Local credential lifecycle/race regressions; no live provider acceptance."""
import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from specimen_digitization.application.intake_connections import (
    CREDENTIAL_WRITE_SECONDS, DROPBOX_SCOPES, GOOGLE_READ, SecretManagerTokens,
)
from specimen_digitization.application.intake_sources import ImportProblem
from test_intake_sources import Response, connected


class ProcessDeath(BaseException):
    pass


def finish(manager, p, *, provider='google_drive', reconnect_id=None, refresh='refresh', access='access'):
    started = manager.connect(p, provider, 'folders', 'a' * 64, reconnect_id=reconnect_id)
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    manager.http = SimpleNamespace(
        post=lambda url, **kw: Response({'account_id': 'account', 'email': 'fixture@example.test'})
            if url.endswith('get_current_account') else Response({'access_token': access, 'refresh_token': refresh,
                'scope': GOOGLE_READ if provider == 'google_drive' else DROPBOX_SCOPES}),
        get=lambda *a, **kw: Response({'user': {'permissionId': 'account', 'emailAddress': 'fixture@example.test'}}),
    )
    return manager.complete(p, state, 'code', 'a' * 64)


def test_abandoned_oauth_attempts_store_no_pkce_secret(connected):
    p, manager = connected
    for _ in range(4):
        started = manager.connect(p, 'google_drive', 'folders', 'a' * 64)
        query = parse_qs(urlsplit(started['authorization_url']).query)
        assert query['code_challenge'] == [base64.urlsafe_b64encode(hashlib.sha256(('a' * 64).encode()).digest()).decode().rstrip('=')]
        pending = manager.verify_pending(p, query['state'][0], 'oauth')
        assert 'verifier_ref' not in pending
        assert 'a' * 64 not in str(pending)
    assert list(manager.secrets.values) == ['client-secret']


@pytest.mark.parametrize('rotating', [False, True])
def test_refreshes_keep_one_active_version_and_durable_refresh_token(connected, rotating):
    p, manager = connected
    clock = [100]
    manager.clock = lambda: clock[0]
    connection = finish(manager, p)
    for i in range(5):
        clock[0] += 3601
        fresh = {'access_token': f'access-{i}'}
        if rotating:
            fresh['refresh_token'] = f'refresh-{i}'
        manager.http = SimpleNamespace(post=lambda *a, **kw: Response(fresh))
        assert manager.token(p, connection['id']) == f'access-{i}'
        current = manager.get(p, connection['id'])
        assert manager.secrets.list_versions(connection['id']) == [current['secret_ref']]
        assert manager.secrets.read(current['secret_ref'])['refresh_token'] == (f'refresh-{i}' if rotating else 'refresh')
        assert 'credential_write' not in current
        assert current.get('credential_retirements') == []
        assert 'access_token' not in str(current) and 'refresh_token' not in str(current)


def test_lost_add_reply_is_recovered_without_another_append(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.clock = lambda: 4000
    original = manager.secrets.write
    calls = []
    def lost_reply(id, value):
        calls.append(id)
        original(id, value)
        raise requests.Timeout()
    manager.secrets.write = lost_reply
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'fresh'}))
    assert manager.token(p, connection['id']) == 'fresh'
    assert len(calls) == 1
    assert len(manager.secrets.list_versions(connection['id'])) == 1


def test_death_after_add_recovers_recorded_candidate(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.clock = lambda: 4000
    original = manager.secrets.write
    def die(id, value):
        original(id, value)
        raise ProcessDeath()
    manager.secrets.write = die
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'fresh', 'refresh_token': 'rotated'}))
    with pytest.raises(ProcessDeath):
        manager.token(p, connection['id'])
    manager.secrets.write = original
    assert manager.token(p, connection['id']) == 'fresh'
    assert len(manager.secrets.list_versions(connection['id'])) == 1
    current = manager.get(p, connection['id'])
    assert manager.secrets.read(current['secret_ref'])['refresh_token'] == 'rotated'


def test_unsent_write_fences_after_deadline_and_late_append_cannot_replace_reconnect(connected):
    p, manager = connected
    connection = finish(manager, p)
    clock = [4000]
    manager.clock = lambda: clock[0]
    original = manager.secrets.write
    late = []
    def die_before_add(id, value):
        late.append((id, value))
        raise ProcessDeath()
    manager.secrets.write = die_before_add
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'late', 'refresh_token': 'late-refresh'}))
    with pytest.raises(ProcessDeath):
        manager.token(p, connection['id'])
    with pytest.raises(ImportProblem) as pending:
        manager.token(p, connection['id'])
    assert pending.value.intake_problem['code'] == 'credential_write_pending'
    clock[0] += CREDENTIAL_WRITE_SECONDS + 1
    with pytest.raises(ImportProblem) as fenced:
        manager.token(p, connection['id'])
    assert fenced.value.intake_problem['code'] == 'authorization_required'
    manager.secrets.write = original
    winner = finish(manager, p, reconnect_id=connection['id'], access='winner', refresh='winner-refresh')
    late_ref = original(*late[0])
    revocations = []
    manager.http = SimpleNamespace(post=lambda *a, **kw: revocations.append(a) or Response())
    assert manager.token(p, connection['id']) == 'winner'
    assert manager.get(p, connection['id'])['secret_ref'] == winner['secret_ref']
    assert late_ref in manager.secrets.destroyed
    assert revocations == []


def test_retirement_survives_process_death_after_pointer_commit(connected):
    p, manager = connected
    connection = finish(manager, p)
    old_ref = connection['secret_ref']
    manager.clock = lambda: 4000
    destroy = manager.secrets.destroy
    manager.secrets.destroy = lambda ref: (_ for _ in ()).throw(ProcessDeath())
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'fresh'}))
    with pytest.raises(ProcessDeath):
        manager.token(p, connection['id'])
    current = manager.get(p, connection['id'])
    assert current['secret_ref'] != old_ref
    assert current['credential_retirements'][0]['ref'] == old_ref
    manager.secrets.destroy = destroy
    assert manager.token(p, connection['id']) == 'fresh'
    assert old_ref in manager.secrets.destroyed


def test_lost_destroy_reply_reconciles_without_reading_destroyed_payload(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.clock = lambda: 4000
    destroy = manager.secrets.destroy
    def lost(ref):
        destroy(ref)
        raise requests.Timeout()
    manager.secrets.destroy = lost
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'fresh'}))
    with pytest.raises(requests.Timeout):
        manager.token(p, connection['id'])
    manager.secrets.destroy = destroy
    read = manager.secrets.read
    def checked(ref):
        assert ref not in manager.secrets.destroyed
        return read(ref)
    manager.secrets.read = checked
    assert manager.token(p, connection['id']) == 'fresh'


@pytest.mark.parametrize('same_family', [False, True])
def test_dropbox_reconnect_retires_only_distinct_previous_family(connected, same_family):
    p, manager = connected
    connection = finish(manager, p, provider='dropbox', refresh='old-refresh', access='old-access')
    started = manager.connect(p, 'dropbox', 'folders', 'b' * 64, reconnect_id=connection['id'])
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    revoked = []
    def post(url, **kwargs):
        if url.endswith('get_current_account'):
            return Response({'account_id': 'account', 'email': 'fixture@example.test'})
        if url.endswith('/revoke'):
            revoked.append(kwargs['headers']['Authorization'])
            return Response()
        return Response({'access_token': 'new-access', 'refresh_token': 'old-refresh' if same_family else 'new-refresh', 'scope': DROPBOX_SCOPES})
    manager.http = SimpleNamespace(post=post)
    completed = manager.complete(p, state, 'code', 'b' * 64)
    assert revoked == ([] if same_family else ['Bearer old-access'])
    assert connection['secret_ref'] in manager.secrets.destroyed
    assert manager.disconnect(p, completed['id'])['state'] == 'disconnected'
    assert revoked[-1] == 'Bearer new-access'
    assert manager.secrets.list_versions(completed['id']) == []


def test_dropbox_revoke_lost_reply_then_invalid_grant_is_complete(connected):
    _, manager = connected
    responses = iter([Response(status=401), Response({'error': 'invalid_grant'}, status=400)])
    manager.http = SimpleNamespace(post=lambda *a, **kw: next(responses))
    assert manager._revoke('dropbox', {'access_token': 'expired', 'refresh_token': 'already-revoked'})


def test_membership_revoked_before_token_use_is_rechecked(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.service.authorize = lambda p: (_ for _ in ()).throw(PermissionError())
    with pytest.raises(PermissionError):
        manager.token(p, connection['id'])


def test_secret_cleanup_uses_dynamic_parent_filter_and_canonical_identity():
    id = '00000000-0000-4000-8000-000000000001'
    numeric = f'projects/123456789/secrets/specimen-intake-{id}/versions/2'
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response({'versions': [{'name': numeric, 'state': 'ENABLED'}]})
    store = SecretManagerTokens('fixture-project', SimpleNamespace(get=get, post=lambda *a, **kw: calls.append((a, kw)) or Response()), project_number='123456789')
    assert store.version_key(numeric) == store.version_key(numeric.replace('123456789', 'fixture-project'))
    assert store.list_versions(id) == [numeric]
    assert calls[0][1]['params']['filter'] == 'state:(ENABLED OR DISABLED)'
    store.destroy(numeric)
    calls.clear()
    for invalid in [numeric.replace('123456789', '987654321'), numeric.replace('specimen-intake-' + id, 'specimen-intake-google-client'), numeric.replace('/2', '/latest')]:
        with pytest.raises(ValueError):
            store.destroy(invalid)
        with pytest.raises(ValueError):
            store.version_state(invalid)
    with pytest.raises(ValueError):
        store.list_versions('google-client')
    assert calls == []


@pytest.mark.parametrize('provider', ['google_drive', 'dropbox'])
def test_disconnect_during_exchange_retires_newly_issued_grant(connected, provider):
    p, manager = connected
    started = manager.connect(p, provider, 'folders', 'a' * 64)
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    revoked = []
    def post(url, **kwargs):
        if url.endswith('/revoke'):
            revoked.append(kwargs)
            return Response()
        if url.endswith('get_current_account'):
            return Response({'account_id': 'account', 'email': 'fixture@example.test'})
        result = manager.disconnect(p, started['id'])
        assert result['state'] == 'disconnected'
        assert result['error']['code'] == 'revocation_pending'
        return Response({'access_token': 'issued-after-disconnect', 'refresh_token': 'issued-refresh',
                         'scope': GOOGLE_READ if provider == 'google_drive' else DROPBOX_SCOPES})
    manager.http = SimpleNamespace(post=post, get=lambda *a, **kw: Response({'user': {'permissionId': 'account'}}))
    with pytest.raises(ImportProblem):
        manager.complete(p, state, 'code', 'a' * 64)
    assert revoked
    assert manager.get(p, started['id'])['state'] == 'disconnected'
    assert manager.secrets.list_versions(started['id']) == []
    assert 'error' not in manager.disconnect(p, started['id'])


@pytest.mark.parametrize('error,complete', [('invalid_token', True), ('invalid_request', False), ('invalid_client', False)])
def test_google_revoke_accepts_only_explicit_already_invalid_token(connected, error, complete):
    _, manager = connected
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'error': error}, status=400))
    assert manager._revoke('google_drive', {'access_token': 'access', 'refresh_token': 'refresh'}) is complete


def test_google_disconnect_cleans_multiple_versions_after_project_revoke(connected):
    p, manager = connected
    connection = finish(manager, p)
    pending = manager._begin_write(p, connection, 'refresh')
    intent = pending['credential_write']
    manager.secrets.write(connection['id'], {'access_token': 'inflight', 'refresh_token': 'rotated', 'expires_at': 4000,
        '_intake_credential': {key: intent[key] for key in ('id', 'generation', 'kind')}})
    responses = iter([Response(), Response({'error': 'invalid_token'}, status=400)])
    manager.http = SimpleNamespace(post=lambda *a, **kw: next(responses))
    assert 'error' not in manager.disconnect(p, connection['id'])
    assert manager.secrets.list_versions(connection['id']) == []


def test_late_add_result_cannot_promote_or_revoke_new_google_winner(connected):
    p, manager = connected
    connection = finish(manager, p)
    clock = [4000]
    manager.clock = lambda: clock[0]
    original = manager.secrets.write
    old_refs, winner, revoked = [], [], []
    def delayed(id, value):
        manager.secrets.write = original
        clock[0] += CREDENTIAL_WRITE_SECONDS + 1
        with pytest.raises(ImportProblem):
            manager.token(p, id)
        winner.append(finish(manager, p, reconnect_id=id, access='winner', refresh='winner-refresh'))
        manager.http = SimpleNamespace(post=lambda *a, **kw: revoked.append(a) or Response())
        ref = original(id, value)
        old_refs.append(ref)
        return ref
    manager.secrets.write = delayed
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'loser', 'refresh_token': 'loser-refresh'}))
    with pytest.raises(ImportProblem) as error:
        manager.token(p, connection['id'])
    assert error.value.intake_problem['code'] == 'connection_changed'
    assert manager.get(p, connection['id'])['secret_ref'] == winner[0]['secret_ref']
    assert manager.token(p, connection['id']) == 'winner'
    assert old_refs[0] in manager.secrets.destroyed
    assert revoked == []


def test_pending_write_serializes_parallel_refreshes(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.clock = lambda: 4000
    calls = []
    def post(*args, **kwargs):
        calls.append(args)
        with pytest.raises(ImportProblem) as pending:
            manager.token(p, connection['id'])
        assert pending.value.intake_problem['code'] == 'credential_write_pending'
        return Response({'access_token': 'fresh'})
    manager.http = SimpleNamespace(post=post)
    assert manager.token(p, connection['id']) == 'fresh'
    assert len(calls) == 1


def test_cleanup_preserves_current_ref_across_project_aliases(connected):
    p, manager = connected
    connection = finish(manager, p)
    original = connection['secret_ref']
    aliased = 'numeric:' + original
    manager.secrets.values[aliased] = manager.secrets.values[original]
    key = manager.secrets.version_key
    manager.secrets.version_key = lambda ref: key(ref.removeprefix('numeric:'))
    manager.secrets.list_versions = lambda id: [aliased]
    assert manager.token(p, connection['id']) == 'access'
    assert manager.secrets.destroyed == set()


def test_native_poll_recovers_credential_and_confirmed_selection_after_crash(connected):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from specimen_digitization.application.intake_connections import GOOGLE_FILE
    from specimen_digitization.application.intake_cloud_sources import CloudSource
    from specimen_digitization.application.intake_source_routes import install_source_routes

    p, manager = connected
    started = manager.connect(p, 'google_drive', 'files', 'a' * 64)
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    original = manager.secrets.write
    def die(id, value):
        original(id, value)
        raise ProcessDeath()
    manager.secrets.write = die
    posts, metadata = [], []
    manager.http = SimpleNamespace(
        post=lambda *a, **kw: posts.append(a) or Response({'access_token': 'access', 'refresh_token': 'refresh', 'scope': GOOGLE_FILE}),
        get=lambda *a, **kw: Response({'user': {'permissionId': 'account'}}),
        request=lambda *a, **kw: metadata.append(a) or Response({'id': 'photo', 'name': 'photo.jpg', 'mimeType': 'image/jpeg', 'version': '7'}),
    )
    with pytest.raises(ProcessDeath):
        manager.complete(p, state, 'code', 'a' * 64, selected_files='photo')
    assert manager.service.read(p, 'intake_oauth', started['picker_id'])['state'] == 'exchanging'
    manager.secrets.write = original
    manager.service.sources.providers['google_drive'] = CloudSource(manager, 'google_drive')
    app = FastAPI()
    install_source_routes(app, '/v1/organizations/{organization_id}', manager.service, manager,
        identity=lambda: p.user_id, principal=lambda *a, **kw: p)
    client = TestClient(app)
    root = f'/v1/organizations/{p.scope.organization_id}/collections/{p.scope.collection_id}/intake'
    result = client.get(root + f"/connections/{started['id']}/picker/{started['picker_id']}")
    assert result.status_code == 200
    assert result.json()['state'] == 'selected'
    assert result.json()['items'][0]['source']['object_id'] == 'photo'
    assert len(posts) == 1  # Polling does not issue a new token or consent request.
    assert len(metadata) == 1


def test_confirmed_add_is_adopted_when_secret_version_listing_is_stale(connected):
    p, manager = connected
    manager.secrets.list_versions = lambda id: []
    connection = finish(manager, p)
    assert manager.token(p, connection['id']) == 'access'
    assert 'credential_write' not in manager.get(p, connection['id'])


def test_stale_list_cannot_resurrect_confirmed_destroyed_version(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.clock = lambda: 4000
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'fresh'}))
    assert manager.token(p, connection['id']) == 'fresh'
    old_ref = connection['secret_ref']
    current = manager.get(p, connection['id'])
    manager.secrets.list_versions = lambda id: [old_ref, current['secret_ref']]
    read = manager.secrets.read
    def checked(ref):
        assert ref not in manager.secrets.destroyed
        return read(ref)
    manager.secrets.read = checked
    assert manager.token(p, connection['id']) == 'fresh'
    assert current['credential_retired_versions'] == [[manager.secrets.version_key(old_ref)[1]] * 2]


def test_retired_intervals_preserve_unknown_gaps_for_later_cleanup(connected):
    p, manager = connected
    connection = finish(manager, p)
    hidden = manager.secrets.write(connection['id'], {'access_token': 'hidden', 'refresh_token': 'hidden-refresh', 'expires_at': 0})
    known = manager.secrets.write(connection['id'], {'access_token': 'known', 'refresh_token': 'known-refresh', 'expires_at': 0})
    list_versions = manager.secrets.list_versions
    manager.secrets.list_versions = lambda id: [ref for ref in list_versions(id) if ref != hidden]
    assert manager.token(p, connection['id']) == 'access'
    current = manager.get(p, connection['id'])
    assert known in manager.secrets.destroyed
    assert not manager._retired(current, hidden)
    manager.secrets.list_versions = list_versions
    assert manager.token(p, connection['id']) == 'access'
    assert hidden in manager.secrets.destroyed
    assert manager.get(p, connection['id'])['secret_ref'] == connection['secret_ref']


def test_destroy_retry_waits_for_positive_metadata_confirmation(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.clock = lambda: 4000
    destroy = manager.secrets.destroy
    attempts = []
    def lost(ref):
        attempts.append(ref)
        destroy(ref)
        raise requests.Timeout()
    manager.secrets.destroy = lost
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'fresh'}))
    with pytest.raises(requests.Timeout):
        manager.token(p, connection['id'])
    old_ref = connection['secret_ref']
    manager.secrets.list_versions = lambda id: []  # Stale absence cannot prove destruction.
    manager.secrets.version_state = lambda ref: 'ENABLED'
    manager.secrets.destroy = lambda ref: attempts.append(ref) or (_ for _ in ()).throw(ImportProblem('credential_storage', 'retry'))
    with pytest.raises(ImportProblem):
        manager.token(p, connection['id'])
    assert not manager._retired(manager.get(p, connection['id']), old_ref)
    manager.secrets.version_state = lambda ref: 'DESTROYED'
    assert manager.token(p, connection['id']) == 'fresh'
    assert manager._retired(manager.get(p, connection['id']), old_ref)
    assert len(attempts) == 2


def test_revocation_claim_blocks_peer_disconnect_and_reconnect(connected):
    p, manager = connected
    connection = finish(manager, p)
    calls = []
    def post(*a, **kw):
        calls.append(a)
        peer = manager.disconnect(p, connection['id'])
        assert peer['error']['code'] == 'revocation_pending'
        with pytest.raises(ImportProblem) as pending:
            manager.connect(p, 'google_drive', 'folders', 'b' * 64, reconnect_id=connection['id'])
        assert pending.value.intake_problem['code'] == 'revocation_pending'
        return Response()
    manager.http = SimpleNamespace(post=post)
    assert 'error' not in manager.disconnect(p, connection['id'])
    assert len(calls) == 1


def test_stale_revocation_claim_owner_cannot_call_provider_after_takeover(connected):
    p, manager = connected
    connection = finish(manager, p)
    clock = [100]
    manager.clock = lambda: clock[0]
    read = manager.secrets.read
    intercepted = [False]
    calls = []
    def checked(ref):
        if ref == connection['secret_ref'] and not intercepted[0]:
            intercepted[0] = True
            clock[0] += CREDENTIAL_WRITE_SECONDS + 1
            assert 'error' not in manager.disconnect(p, connection['id'])
        return read(ref)
    manager.secrets.read = checked
    manager.http = SimpleNamespace(post=lambda *a, **kw: calls.append(a) or Response())
    # The first owner sees its claim removed by the successful takeover and
    # never sends a second project-wide revocation.
    manager.disconnect(p, connection['id'])
    assert len(calls) == 1
    assert manager.secrets.list_versions(connection['id']) == []


def test_confirmed_candidate_hint_recovers_after_restart_despite_stale_list(connected):
    p, manager = connected
    connection = finish(manager, p)
    manager.clock = lambda: 4000
    settle = manager._settle
    interrupted = [False]
    def crash_after_hint(p, current, **kwargs):
        if current.get('credential_write', {}).get('candidate_ref') and not interrupted[0]:
            interrupted[0] = True
            raise ProcessDeath()
        return settle(p, current, **kwargs)
    manager._settle = crash_after_hint
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({'access_token': 'fresh'}))
    with pytest.raises(ProcessDeath):
        manager.token(p, connection['id'])
    pending = manager.get(p, connection['id'])
    assert pending['credential_write']['candidate_ref']
    manager.secrets.list_versions = lambda id: []
    manager._settle = settle
    assert manager.token(p, connection['id']) == 'fresh'
    assert connection['secret_ref'] in manager.secrets.destroyed


@pytest.mark.parametrize('provider,same_family', [('google_drive', False), ('dropbox', False), ('dropbox', True)])
def test_rejected_reconnect_preserves_accepted_credential(connected, provider, same_family):
    p, manager = connected
    accepted = finish(manager, p, provider=provider)
    started = manager.connect(p, provider, 'folders', 'b' * 64, reconnect_id=accepted['id'])
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    revoked = []
    def post(url, **kwargs):
        if url.endswith('/revoke'):
            revoked.append(kwargs)
            return Response()
        return Response({'access_token': 'rejected-access', 'refresh_token': 'refresh' if same_family else 'rejected-refresh', 'scope': ''})
    manager.http = SimpleNamespace(post=post)
    with pytest.raises(ImportProblem) as rejected:
        manager.complete(p, state, 'code', 'b' * 64)
    assert rejected.value.intake_problem['code'] == 'scope_declined'
    current = manager.get(p, accepted['id'])
    assert current['state'] == 'connected'
    assert current['secret_ref'] == accepted['secret_ref']
    assert accepted['secret_ref'] not in manager.secrets.destroyed
    assert manager.token(p, accepted['id']) == 'access'
    assert manager.secrets.list_versions(accepted['id']) == [accepted['secret_ref']]
    assert len(revoked) == (1 if provider == 'dropbox' and not same_family else 0)
    pending = manager.service.read(p, 'intake_oauth', manager.decode_state(state)['id'])
    assert pending['state'] == 'failed' and pending['error']['code'] == 'scope_declined'


@pytest.mark.parametrize('provider', ['google_drive', 'dropbox'])
def test_first_rejection_cleanup_survives_crash_and_blocks_new_grant(connected, provider):
    p, manager = connected
    started = manager.connect(p, provider, 'folders', 'a' * 64)
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response({
        'access_token': 'rejected-access', 'refresh_token': 'rejected-refresh', 'scope': ''}))
    revoke = manager._revoke
    def die(*args):
        current = manager.get(p, started['id'])
        assert not current.get('secret_ref')
        retirement = current['credential_retirements'][0]
        assert retirement['revoke'] and retirement['revocation_claim']
        assert manager.secrets.read(retirement['ref'])['refresh_token'] == 'rejected-refresh'
        raise ProcessDeath()
    manager._revoke = die
    with pytest.raises(ProcessDeath):
        manager.complete(p, state, 'code', 'a' * 64)
    with pytest.raises(ImportProblem) as blocked:
        manager.connect(p, provider, 'folders', 'b' * 64, reconnect_id=started['id'])
    assert blocked.value.intake_problem['code'] == 'revocation_pending'
    manager.clock = lambda: 100 + CREDENTIAL_WRITE_SECONDS + 1
    manager._revoke = revoke
    manager.http = SimpleNamespace(post=lambda *a, **kw: Response())
    recovered = manager.recover(p, started['id'])
    assert recovered['state'] == 'needs_authorization' and not recovered.get('secret_ref')
    assert manager.secrets.list_versions(started['id']) == []
    pending = manager.service.read(p, 'intake_oauth', manager.decode_state(state)['id'])
    assert pending['state'] == 'failed' and pending['error']['code'] == 'scope_declined'


@pytest.mark.parametrize('provider', ['google_drive', 'dropbox'])
@pytest.mark.parametrize('failure', ['timeout', 'invalid_metadata', 'refused', 'mismatch'])
def test_account_rejections_durably_retire_known_issued_tokens(connected, provider, failure):
    p, manager = connected
    started = manager.connect(p, provider, 'folders', 'a' * 64)
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    revoked = []
    def account():
        if failure == 'timeout':
            raise requests.Timeout()
        if failure == 'invalid_metadata':
            return Response(['invalid'])
        if failure == 'refused':
            return Response(status=503)
        return Response({})
    def post(url, **kwargs):
        if url.endswith('/revoke'):
            revoked.append(kwargs)
            return Response()
        if url.endswith('get_current_account'):
            return account()
        return Response({'access_token': 'issued-access', 'refresh_token': 'issued-refresh',
            'scope': GOOGLE_READ if provider == 'google_drive' else DROPBOX_SCOPES})
    manager.http = SimpleNamespace(post=post, get=lambda *a, **kw: account())
    with pytest.raises(ImportProblem):
        manager.complete(p, state, 'code', 'a' * 64)
    current = manager.get(p, started['id'])
    assert not current.get('secret_ref') and not current.get('credential_write')
    assert manager.secrets.list_versions(started['id']) == []
    assert len(revoked) == 1
    assert manager.service.read(p, 'intake_oauth', manager.decode_state(state)['id'])['state'] == 'failed'


@pytest.mark.parametrize('provider', ['google_drive', 'dropbox'])
@pytest.mark.parametrize('missing', ['access_token', 'refresh_token', 'both'])
def test_offline_access_rejection_retires_any_issued_credential(connected, provider, missing):
    p, manager = connected
    started = manager.connect(p, provider, 'folders', 'a' * 64)
    state = parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
    token = {'access_token': 'issued-access', 'refresh_token': 'issued-refresh',
        'scope': GOOGLE_READ if provider == 'google_drive' else DROPBOX_SCOPES}
    for key in ('access_token', 'refresh_token') if missing == 'both' else (missing,):
        token.pop(key)
    revoked = []
    def post(url, **kwargs):
        if url.endswith('/revoke'):
            revoked.append(kwargs)
            return Response()
        if kwargs['data'].get('grant_type') == 'refresh_token':
            return Response({'access_token': 'refreshed-for-revocation'})
        return Response(token)
    manager.http = SimpleNamespace(post=post)
    with pytest.raises(ImportProblem) as rejected:
        manager.complete(p, state, 'code', 'a' * 64)
    assert rejected.value.intake_problem['code'] == 'offline_access_required'
    current = manager.get(p, started['id'])
    assert not current.get('secret_ref') and not current.get('credential_write')
    assert manager.secrets.list_versions(started['id']) == []
    assert len(revoked) == (0 if missing == 'both' else 1)
