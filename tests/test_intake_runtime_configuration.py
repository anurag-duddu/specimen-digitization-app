"""Runtime admission/routing contracts; live consent is a separate acceptance step."""
import json

import pytest

from specimen_digitization.application.runtime_config import collection_worker_jobs, external_email_allowlist

SCOPE = '10000000-0000-4000-8000-000000000001/20000000-0000-4000-8000-000000000002'
ROOT = 'projects/specimen-digitization/locations/us-east4/jobs/'
ROUTE = {'worker_job': ROOT + 'specimen-worker-e2e', 'intake_job': ROOT + 'specimen-intake-e2e', 'actor_uid': 'fixture-worker'}


def routing(value):
    return collection_worker_jobs({'SPECIMEN_COLLECTION_WORKER_JOBS_JSON': json.dumps(value)})


def test_private_admission_defaults_closed_and_matches_exact_mailboxes():
    assert external_email_allowlist({}) == ()
    assert external_email_allowlist({'SPECIMEN_EXTERNAL_EMAIL_ALLOWLIST_JSON': '["Tester@Example.com"]'}) == ('tester@example.com',)
    for value in ('{}', 'null', '"tester@example.com"', '["*@example.com"]', '["example.com"]', '[" tester@example.com"]'):
        with pytest.raises(ValueError):
            external_email_allowlist({'SPECIMEN_EXTERNAL_EMAIL_ALLOWLIST_JSON': value})


def test_routes_canonicalize_sql_uuid_forms_and_preserve_actor_binding():
    assert collection_worker_jobs({}) == ()
    assert routing({SCOPE.replace('-', ''): ROUTE}) == ((SCOPE, ROUTE),)
    with pytest.raises(ValueError):
        routing({SCOPE: ROUTE, SCOPE.replace('-', ''): ROUTE})


@pytest.mark.parametrize('changes', [
    {'actor_uid': ''}, {'actor_uid': ' worker'}, {'actor_uid': 7},
    {'worker_job': ROOT + 'specimen-intake-e2e'},
    {'worker_job': 'projects/another-project/locations/us-east4/jobs/worker'},
    {'worker_job': ROOT + 'worker?override=1'}, {'intake_job': None},
    {'unexpected': 'value'},
])
def test_routes_refuse_ambiguous_identity_or_unreviewed_jobs(changes):
    with pytest.raises(ValueError):
        routing({SCOPE: {**ROUTE, **changes}})


@pytest.mark.parametrize('value', [[], None, {SCOPE: {}}, {'org/collection': ROUTE}, {'': ROUTE}])
def test_routes_reject_bad_configuration_instead_of_defaulting(value):
    with pytest.raises(ValueError):
        routing(value)


def test_two_scopes_cannot_share_a_dedicated_job():
    other = SCOPE[:-1] + '3'
    with pytest.raises(ValueError):
        routing({SCOPE: ROUTE, other: ROUTE})
