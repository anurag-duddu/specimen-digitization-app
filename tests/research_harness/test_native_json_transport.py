"""Loopback HTTP custody; no Firebase, provider, worker or model calls."""
import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import requests

from test_native_canonical_v2_contract import basis_v1, causal, receipt
from test_native_materialization_loader_v2 import native_materialization_response
from specimen_digitization.application.production import SqlConnectRepository
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import digest
from specimen_digitization.research_harness.native_canonical import SqlConnectNativeOperationClient
from specimen_digitization.research_harness.native_canonical_v2 import CanonicalBindingV2
from specimen_digitization.research_harness.native_json import NATIVE_JSON_READS
from specimen_digitization.research_harness.native_materialization_inputs_v2 import NativeMaterializationInputsV2
from specimen_digitization.research_harness.publication_v2 import NativeCausalReceiptV2, PreparationV2


@pytest.fixture
def http_read():
    replies, calls = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            body = json.dumps({'data': replies.pop(0)}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with requests.Session() as session:
        repository = SqlConnectRepository(project='demo-specimen-data', location='us-east4',
            service='specimen-digitization-service', connector='specimen-server', session=session,
            emulator_host=f'127.0.0.1:{server.server_port}')

        def read(operation, data, adapter='native'):
            replies.append(data)
            client = repository if adapter == 'repository' else SqlConnectNativeOperationClient(repository)
            result = client.execute(operation, {'actorUid': 'synthetic-worker'})
            assert calls[-1][0].endswith(':impersonateQuery')
            assert calls[-1][1] == {'operationName': operation, 'variables': {'actorUid': 'synthetic-worker'}}
            return result

        yield read
    server.shutdown()
    thread.join()
    server.server_close()


def envelope(operation, row, **access):
    return {**access, NATIVE_JSON_READS[operation]: {'exact_json': json.dumps(row, allow_nan=False)}}


@pytest.mark.parametrize('adapter', ['native', 'repository'])
@pytest.mark.parametrize('operation', NATIVE_JSON_READS)
def test_http_text_preserves_exact_number_kinds_and_pin_digest(http_read, adapter, operation):
    original = {'pins': {'timeouts': [15.0] * 13, 'integer': 15, 'large_integer': 2**53 + 1,
        'small_float': 1e-8, 'large_float': 1e20, 'flag': False, 'unknown': None}}
    decoded = http_read(operation, envelope(operation, original), adapter)[NATIVE_JSON_READS[operation]]
    assert digest(decoded) == digest(original)
    assert type(decoded['pins']['timeouts'][0]) is float
    assert type(decoded['pins']['integer']) is int
    assert type(decoded['pins']['flag']) is bool
    assert decoded['pins']['unknown'] is None


@pytest.mark.parametrize('adapter', ['native', 'repository'])
def test_http_preserves_valid_literal_non_ascii_text(http_read, adapter):
    original = {'label': 'Dávao — 日本', 'number': 15.0, 'nested': {'μήκος': '🦋'}}
    raw = json.dumps(original, ensure_ascii=False, allow_nan=False)
    assert not raw.isascii()
    decoded = http_read('GetCanonicalResearchBindingV2', {'binding': {'exact_json': raw}}, adapter)['binding']
    assert decoded == original and digest(decoded) == digest(original)


@pytest.mark.parametrize('adapter', ['native', 'repository'])
@pytest.mark.parametrize('row', [
    {'pins': {}}, {'exact_json': {}}, {'exact_json': ''}, {'exact_json': '{"pins":'},
    {'exact_json': '{"pins":{},"pins":{}}'}, {'exact_json': '{"pins":{"n":NaN}}'},
    {'exact_json': '{"pins":{"n":Infinity}}'}, {'exact_json': '{"pins":{"n":1e309}}'},
    {'exact_json': 'null'}, {'exact_json': '[]'}, {'exact_json': '{}', 'unexpected': True},
    {'exact_json': '\ud800'},
])
def test_http_refuses_lossy_or_malformed_envelope_before_any_reader(http_read, adapter, row):
    with pytest.raises(PublicationUnavailable) as failure:
        http_read('GetCanonicalResearchBindingV2', {'binding': row}, adapter)
    # pytest's regex view includes exception notes; the original error contract
    # and the sanitized native transport context are independent assertions.
    assert str(failure.value) == 'native_v2_exact_json_unavailable'
    notes = getattr(failure.value, '__notes__', [])
    assert notes == (['sql_connect_operation=GetCanonicalResearchBindingV2; '
                      'phase=response_validation; attempt=1'] if adapter == 'native' else [])


def test_http_missing_is_distinct_from_absent_row(http_read):
    assert http_read('GetCanonicalResearchBindingV2', {'binding': None}) == {'binding': None}
    with pytest.raises(PublicationUnavailable, match='exact_json_unavailable'):
        http_read('GetCanonicalResearchBindingV2', {})


def test_real_binding_validator_keeps_exact_pins_and_refuses_altered_text(http_read, causal):
    c = causal
    row = native_materialization_response(c)['binding']
    row.pop('materialization_inputs')
    reg = row['registrations'][0]
    # Synthetic original registration commits the same 13 typed values as the
    # production failure. The read cannot invent or re-pin this digest.
    job = reg['job']
    job['pins']['sources'] = {'registry_policies': [{'timeout_seconds': 15.0} for _ in range(13)]}
    reg['runtime_binding_digest'] = job['binding_digest'] = digest(job['pins'])
    reg['read_bundle']['job'] = copy.deepcopy(job)
    data = http_read('GetCanonicalResearchBindingV2', envelope('GetCanonicalResearchBindingV2', row))
    parsed = CanonicalBindingV2.from_native(c.b.principal.scope, c.b.scope.specimen_id, data['binding'])
    assert digest(parsed.registration.job['pins']) == reg['runtime_binding_digest']
    for value in (15, 16.0, True, '15.0'):
        altered = copy.deepcopy(row)
        for current in (altered['registrations'][0]['job'], altered['registrations'][0]['read_bundle']['job']):
            current['pins']['sources']['registry_policies'][0]['timeout_seconds'] = value
        data = http_read('GetCanonicalResearchBindingV2', envelope('GetCanonicalResearchBindingV2', altered))
        with pytest.raises(PublicationUnavailable, match='native_v2_job_binding_invalid'):
            CanonicalBindingV2.from_native(c.b.principal.scope, c.b.scope.specimen_id, data['binding'])


def test_materialization_keeps_the_original_private_state_and_its_guards(http_read, causal):
    c = causal
    response = native_materialization_response(c)
    row = response.pop('binding')
    data = http_read('GetCanonicalResearchMaterializationInputsV2',
        envelope('GetCanonicalResearchMaterializationInputsV2', row, **response))
    loaded = NativeMaterializationInputsV2.from_response(c.b.principal, c.intent, c.prep, data)
    assert digest(loaded.state_document) == digest(c.state)
    # The established limit belongs to each original String preimage, not the
    # combined response containing multiple complete retained causal receipts.
    from specimen_digitization.research_harness.native_materialization_inputs_v2 import MAX_JSON
    oversized = copy.deepcopy(data)
    oversized['binding']['materialization_inputs']['private_state_integrity']['state_json'] = ' ' * MAX_JSON + '{}'
    with pytest.raises(PublicationUnavailable, match='native_materialization_json_unavailable'):
        NativeMaterializationInputsV2.from_response(c.b.principal, c.intent, c.prep, oversized)
    altered = copy.deepcopy(data)
    state = altered['binding']['materialization_inputs']['private_state_integrity']['state']
    lease = state['jobs'][c.intent.job_key]['lease']
    assert type(lease['expires_at']) is float and lease['expires_at'].is_integer()
    lease['expires_at'] = int(lease['expires_at'])
    with pytest.raises(PublicationUnavailable, match='native_materialization_state_integrity'):
        NativeMaterializationInputsV2.from_response(c.b.principal, c.intent, c.prep, altered)


def test_retained_preparation_and_causal_preimages_survive_http(http_read, causal):
    c = causal
    preparation = c.prep.model_dump(mode='json')
    data = http_read('GetResearchPublicationIntentV2', envelope('GetResearchPublicationIntentV2',
        {'preparations': [preparation]}))
    assert PreparationV2.model_validate(data['intent']['preparations'][0]) == c.prep
    causal_row = receipt(c).model_dump(mode='json')
    data = http_read('GetResearchPublicationReceiptV2', envelope('GetResearchPublicationReceiptV2',
        {'causal': causal_row}))
    assert NativeCausalReceiptV2.model_validate(data['retained']['causal']).model_dump(mode='json') == causal_row
