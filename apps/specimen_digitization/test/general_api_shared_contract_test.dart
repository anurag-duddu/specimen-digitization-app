import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:crypto/crypto.dart' as crypto;
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';

const s = '00000000-0000-4000-8000-000000000001';
const r = '00000000-0000-4000-8000-000000000002';
const u = '00000000-0000-4000-8000-000000000003';
const scope = CollectionScope(
  organizationId: s,
  collectionId: r,
  name: 'Synthetic',
);
const root = '/v1/organizations/$s';
// This is the independently written expectation table, never exporter input.
const actions = [
  'retry',
  'resume',
  'pause',
  'cancel',
  'reprocess',
  'field',
  'transcription',
  'reading_metadata',
  'coverage',
  'approve',
  'classification',
  'regions',
  'taxonomy_resolution',
  'authority_resolution',
  'capability_defer',
  'restore_version',
];
final corpusUtf8 = utf8.decode(
  File('../../tests/fixtures/general_api_contracts.json').readAsBytesSync(),
);
Json get corpus => jsonDecode(corpusUtf8) as Json;
Json envelope(String name) => Json.from(corpus['responses'][name]);
Json body(String name) =>
    Json.from(jsonDecode(envelope(name)['body_utf8'] as String));
http.Response response(String name) => http.Response(
  envelope(name)['body_utf8'] as String,
  envelope(name)['status_code'] as int,
  headers: {'content-type': 'application/json; charset=utf-8'},
);
ApiSpecimenRepository repository(
  Future<http.Response> Function(http.Request) handler,
) {
  final repo = ApiSpecimenRepository(
    baseUrl: Uri.parse('http://localhost:8000'),
    token: () async => 'synthetic',
    client: MockClient(handler),
  );
  addTearDown(repo.close);
  return repo;
}

Uint8List get png => base64Decode(corpus['png_base64'] as String);
Future<http.Response> asset(http.Request req) async =>
    http.Response.bytes(png, 200);
void pin(Specimen item, int revision, String disposition) {
  expect(item.id, s);
  expect(item.revision, revision);
  expect(item.recordVersionId, '$r:$revision');
  expect(item.state, 'completed');
  expect(item.disposition, disposition);
}

// This table is handwritten independently of both the Python oracle and exporter.
const selection =
    '70c2cd77f73f5180e59ce357a83eec7c625e495f52a5e4bcb98627731c48b1e8'; // pragma: allowlist secret -- Synthetic retained candidate selection SHA-256.
const pngHash =
    '50262755ff88d14aec25fe44b1876563f4f77b3e95c6fad87c99ebe7fc584a8a'; // pragma: allowlist secret -- Synthetic 28948-byte PNG SHA-256.
const tailHash =
    'bbb49a538af41922d5d53b6d285079c3ba70156b1bdcc2a78c39bd7711e971f3'; // pragma: allowlist secret -- Synthetic PNG remaining-tail SHA-256.
Json recordLiteral(
  int revision,
  String? disposition,
  List<String> advertised,
) => {
  'specimen_id': s,
  'organization_id': s,
  'collection_id': r,
  'revision': revision,
  'record_version_id': '$r:$revision',
  'active_run_id': r,
  'status': 'completed',
  'stage': 'finalized',
  'disposition': disposition,
  'available_actions': advertised,
};
Json workspaceLiteral(
  int revision,
  String disposition,
  List<String> advertised, [
  String parsed = 'United States',
]) => {
  ...recordLiteral(revision, disposition, advertised),
  'fields': {
    'country': {
      'literal': 'United States',
      'parsed': parsed,
      'state': 'supported',
      'value_state': 'supported',
    },
  },
};
Json uploadLiteral(int revision, int offset) => {
  'upload_id': u,
  'specimen_id': s,
  'collection_id': r,
  'revision': revision,
  'state': 'uploading',
  'offset': offset,
  'size_bytes': 28948,
  'upload_method': 'PUT',
  'upload_url': '$root/uploads/$u/content',
  'sha256': pngHash,
  'chunks': [
    {
      'offset': 0,
      'size': 20,
      'sha256':
          '1bf0a9034faa63a8a53121b00ef018df9890126003c37e1416fb5a6401e25afd', // pragma: allowlist secret -- Synthetic PNG first-chunk SHA-256.
    },
    if (offset == 28948) {'offset': 20, 'size': 28928, 'sha256': tailHash},
  ],
};
Map<String, Json> get rawTable => <String, Json>{
  'list': {
    'items': [recordLiteral(20, 'needs_human_review', [])],
    'next_cursor': null,
    'cutoff': '2026-01-02T03:04:05+00:00',
  },
  'workspace': workspaceLiteral(20, 'needs_human_review', actions),
  'error': {
    'error': {
      'code': 'revision_or_idempotency_conflict',
      'category': 'conflict',
      'retryable': false,
      'details': {},
      'message': 'Stale revision',
      'request_id': '00000000-0000-0000-0000-00000000008e',
    },
  },
  'error_readback': workspaceLiteral(20, 'needs_human_review', actions),
  'upload': uploadLiteral(2, 20),
  'upload_tail': uploadLiteral(3, 28948),
  'upload_current': uploadLiteral(3, 28948),
  'upload_complete': {
    ...recordLiteral(1, null, actions),
    'status': 'running',
    'stage': 'ingested',
  },
  'action': workspaceLiteral(21, 'cleared', actions),
  'action_readback': workspaceLiteral(21, 'cleared', actions),
  'review_batch': {
    'requested': 1,
    'applied': 1,
    'refused': 0,
    'skipped': 0,
    'results': [
      {
        'index': 0,
        'specimen_id': s,
        'kind': 'research_candidate',
        'idempotency_key': 'i11-candidate-0',
        'outcome': 'applied',
        'revision': 22,
        'record_version_id': '$r:22',
        'disposition': 'needs_human_review',
      },
    ],
  },
  'review_readback': workspaceLiteral(
    22,
    'needs_human_review',
    actions.where((a) => a != 'reprocess').toList(),
    'Philippines',
  ),
};
void strictRaw(dynamic actual, dynamic expected, String path) {
  if (expected is Map) {
    expect(actual, isA<Map>(), reason: '$path must be an object');
    if (expected.isEmpty) {
      expect(actual, isEmpty, reason: path);
    }
    for (final key in expected.keys) {
      expect(
        (actual as Map).containsKey(key),
        isTrue,
        reason: '$path.$key required',
      );
      strictRaw(actual[key], expected[key], '$path.$key');
    }
  } else if (expected is List) {
    expect(actual, isA<List>(), reason: path);
    expect((actual as List).length, expected.length, reason: path);
    for (var i = 0; i < expected.length; i++) {
      strictRaw(actual[i], expected[i], '$path[$i]');
    }
  } else {
    if (expected is int) {
      expect(actual, isA<int>(), reason: path);
    }
    if (expected is bool) {
      expect(actual, isA<bool>(), reason: path);
    }
    if (expected is String) {
      expect(actual, isA<String>(), reason: path);
    }
    expect(actual, expected, reason: path);
  }
}

void assertRaw(String name) => assertRawEnvelope(name, envelope(name));
void assertRawEnvelope(String name, Json captured) {
  strictRaw(
    captured['status_code'],
    name == 'error' ? 409 : 200,
    '$name.status_code',
  );
  expect(captured['body_utf8'], isA<String>());
  expect(captured.keys, unorderedEquals(['status_code', 'body_utf8']));
  final value = Json.from(jsonDecode(captured['body_utf8'] as String));
  strictRaw(value, rawTable[name], name);
  if ([
    'workspace',
    'error_readback',
    'action',
    'action_readback',
    'review_readback',
  ].contains(name)) {
    expect(value.containsKey('latest_record_version_id'), isFalse);
  }
  if (name == 'error') {
    for (final key in [
      'specimen_id',
      'revision',
      'record_version_id',
      'status',
      'stage',
      'disposition',
      'available_actions',
    ]) {
      expect(value.containsKey(key), isFalse);
      expect((value['error'] as Map).containsKey(key), isFalse);
    }
  }
  if (name == 'review_batch') {
    for (final key in ['status', 'stage', 'available_actions']) {
      expect((value['results'][0] as Map).containsKey(key), isFalse);
    }
  }
  if (name.startsWith('upload') && name != 'upload_complete') {
    for (final key in [
      'record_version_id',
      'disposition',
      'available_actions',
    ]) {
      expect(value.containsKey(key), isFalse);
    }
  }
}

const approveBody = {
  'expected_revision': 20,
  'reason': 'I11 synthetic reviewed',
  'base_record_version_id': '$r:20',
  'kind': 'approve',
  'target_id': '',
  'after': {'confirmed': true},
  'evidence_ids': [],
};
const candidateBody = {
  'reason': 'I11 retained source reviewed',
  'decisions': [
    {
      'specimen_id': s,
      'expected_revision': 21,
      'base_record_version_id': '$r:21',
      'kind': 'research_candidate',
      'target_id': 'country',
      'after': {'selection_id': selection},
      'idempotency_key': 'i11-candidate-0',
    },
  ],
};

void assertCorpus(Json fixture) {
  strictRaw(fixture['schema_version'], 1, 'schema_version');
  strictRaw(fixture['selection_id'], selection, 'selection_id');
  expect(fixture.containsKey('checkpoints'), isFalse);
  final image = base64Decode(fixture['png_base64'] as String);
  expect(image.length, 28948);
  expect(crypto.sha256.convert(image).toString(), pngHash);
  expect(image.sublist(20).length, 28928);
  expect(crypto.sha256.convert(image.sublist(20)).toString(), tailHash);
  for (final name in rawTable.keys) {
    assertRawEnvelope(name, Json.from(fixture['responses'][name]));
  }
  final requests = fixture['requests'] as Map;
  for (final name in ['action', 'error', 'review_batch', 'upload_complete']) {
    final captured = Json.from(requests[name]);
    strictRaw(captured['method'], 'POST', '$name.method');
    final path = name == 'review_batch'
        ? '$root/decisions:batch'
        : name == 'upload_complete'
        ? '$root/uploads/$u/complete'
        : '$root/specimens/$s/decisions';
    strictRaw(captured['path'], path, '$name.path');
    final key = switch (name) {
      'action' => 'i11-approve',
      'error' => 'i11-stale',
      'upload_complete' => 'i11-complete',
      _ =>
        '7651ca196a03f7cc18d5625844ca3b2fdc68a62d7b19c691c3b222ad40a77aa8', // pragma: allowlist secret -- Synthetic candidate request idempotency SHA-256.
    };
    strictRaw(captured['headers'], {'Idempotency-Key': key}, '$name.headers');
    final expected = switch (name) {
      'action' => approveBody,
      'error' => {
        ...approveBody,
        'expected_revision': 19,
        'base_record_version_id': '$r:19',
      },
      'upload_complete' => {'expected_revision': 3},
      _ => candidateBody,
    };
    final decoded = jsonDecode(captured['body_utf8'] as String);
    strictRaw(decoded, expected, '$name.request');
    expect(decoded, expected, reason: 'exact outgoing $name request');
  }
  final tail = Json.from(requests['upload_tail']);
  strictRaw(tail['method'], 'PUT', 'upload_tail.method');
  strictRaw(tail['path'], '$root/uploads/$u/content', 'upload_tail.path');
  strictRaw(tail['headers'], {
    'Upload-Offset': '20',
    'Idempotency-Key': 'chunk-$u-20',
  }, 'upload_tail.headers');
}

void main() {
  test('one_source_relative_root_read_and_raw_wire_types', () {
    assertCorpus(corpus);
    expect(
      File('../../tests/fixtures/general_api_contracts.json').existsSync(),
      isTrue,
    );
    expect(corpus['schema_version'], 1);
    expect(corpus['selection_id'], selection);
    for (final name in rawTable.keys) {
      assertRaw(name);
    }
    expect(png.length, 28948);
    expect(
      crypto.sha256.convert(png).toString(),
      '50262755ff88d14aec25fe44b1876563f4f77b3e95c6fad87c99ebe7fc584a8a', // pragma: allowlist secret -- Synthetic 28948-byte PNG SHA-256.
    );
    expect(
      crypto.sha256.convert(png.sublist(20)).toString(),
      'bbb49a538af41922d5d53b6d285079c3ba70156b1bdcc2a78c39bd7711e971f3', // pragma: allowlist secret -- Synthetic PNG remaining-tail SHA-256.
    );
    for (final name in [
      'list',
      'workspace',
      'error',
      'upload',
      'action',
      'review_batch',
    ]) {
      expect(envelope(name)['status_code'], name == 'error' ? 409 : 200);
    }
    expect(body('workspace')['revision'], isA<int>());
    expect(body('workspace')['fields']['country']['literal'], 'United States');
    expect(body('workspace').containsKey('latest_record_version_id'), isFalse);
    expect(body('error')['error'], containsPair('category', 'conflict'));
    expect(body('error')['error'], containsPair('retryable', false));
    expect(body('error')['error'], containsPair('details', {}));
  });
  test('approval21_ack_readback_and_next_base', () async {
    assertRaw('action');
    assertRaw('action_readback');

    final listing = Json.from(body('list')['items'][0]);
    for (final entry in [
      listing,
      body('workspace'),
      body('action'),
      body('review_readback'),
    ]) {
      expect(entry['specimen_id'], isA<String>());
      expect(entry['specimen_id'], s);
      expect(entry['revision'], isA<int>());
      expect(entry['record_version_id'], isA<String>());
      expect(entry['status'], 'completed');
      expect(entry['stage'], 'finalized');
    }
    pin(Specimen(body('action')), 21, 'cleared');
    final ack = body('review_batch');
    expect(ack['requested'], 1);
    expect(ack['applied'], 1);
    expect(ack['refused'], 0);
    expect(ack['skipped'], 0);
    final row = Json.from(ack['results'][0]);
    expect(row['index'], 0);
    expect(row['specimen_id'], s);
    expect(row['revision'], 22);
    expect(row['revision'], isA<int>());
    expect(row['record_version_id'], '$r:22');
    expect(row['kind'], 'research_candidate');
    expect(row['outcome'], 'applied');
    expect(row['disposition'], 'needs_human_review');
    expect(row['idempotency_key'], 'i11-candidate-0');
    var phase = 0;
    final calls = <String>[];
    final repo = repository((q) async {
      if (q.url.path.endsWith('/content')) return asset(q);
      calls.add('${q.method} ${q.url.path}');
      if (q.method == 'GET') {
        expect(q.url.path, '$root/specimens/$s/workspace');
        return response(
          phase == 0
              ? 'workspace'
              : phase == 1
              ? 'action_readback'
              : 'review_readback',
        );
      }
      expect(q.method, 'POST');
      if (phase == 0) {
        expect(q.url.path, '$root/specimens/$s/decisions');
        expect(jsonDecode(q.body), approveBody);
        expect(q.headers['Idempotency-Key'], 'i11-approve');
        phase = 1;
        return response('action');
      }
      expect(phase, 1);
      expect(q.url.path, '$root/decisions:batch');
      expect(jsonDecode(q.body), candidateBody);
      expect(
        q.headers['Idempotency-Key'],
        '7651ca196a03f7cc18d5625844ca3b2fdc68a62d7b19c691c3b222ad40a77aa8', // pragma: allowlist secret -- Synthetic candidate request idempotency SHA-256.
      );
      phase = 2;
      return response('review_batch');
    });
    final original = await repo.specimen(scope, s);
    final approved = await repo.review(scope, original, {
      'kind': 'approve',
      'reason': 'I11 synthetic reviewed',
    }, 'i11-approve');
    pin(approved, 21, 'cleared');
    final next = await repo.reviewCandidateBatch(
      scope,
      approved,
      [
        {
          'kind': 'research_candidate',
          'target_id': 'country',
          'selection_id': selection,
        },
      ],
      'I11 retained source reviewed',
      'i11-candidate',
    );
    expect(next.saved, 1);
    pin(next.specimen, 22, 'needs_human_review');
    expect(calls, [
      'GET $root/specimens/$s/workspace',
      'POST $root/specimens/$s/decisions',
      'GET $root/specimens/$s/workspace',
      'POST $root/decisions:batch',
      'GET $root/specimens/$s/workspace',
    ]);
  });
  test('list20_identity_and_workspace_only_eligibility', () async {
    assertRaw('list');

    final repo = repository((q) async {
      expect(q.method, 'GET');
      expect(q.url.path, '$root/specimens');
      expect(q.url.queryParameters['collection_id'], r);
      return response('list');
    });
    final page = await repo.specimenPage(scope);
    final item = page.items.single;
    pin(item, 20, 'needs_human_review');
    expect(item.data['available_actions'], isEmpty);
    final eligibility = BulkSelectionEligibility(
      requested: [item],
      records: {s: item},
      unavailable: {},
    );
    expect(eligibility.eligibleFor(BulkDecisionKind.approve), isEmpty);
  });
  test('workspace20_alias_and_review_outbound', () async {
    assertRaw('workspace');

    final posts = <http.Request>[];
    var current = 'workspace';
    final repo = repository((q) async {
      if (q.url.path.endsWith('/content')) return asset(q);
      if (q.method == 'GET') {
        expect(q.url.path, '$root/specimens/$s/workspace');
        return response(current);
      }
      expect(q.method, 'POST');
      expect(q.url.path, '$root/specimens/$s/decisions');
      posts.add(q);
      current = 'action_readback';
      return response('action');
    });
    final original = await repo.specimen(scope, s);
    pin(original, 20, 'needs_human_review');
    expect(original.data['latest_record_version_id'], '$r:20');
    expect(original.data['available_actions'], actions);
    expect(
      original.fields.singleWhere(
        (f) => f['field_key'] == 'country',
      )['literal_value'],
      'United States',
    );
    final approved = await repo.review(scope, original, {
      'kind': 'approve',
      'reason': 'I11 synthetic reviewed',
    }, 'i11-approve');
    pin(approved, 21, 'cleared');
    expect(posts, hasLength(1));
    final sent = jsonDecode(posts.single.body) as Json;
    expect(sent['expected_revision'], 20);
    expect(sent['base_record_version_id'], '$r:20');
    expect(sent['kind'], 'approve');
    expect(posts.single.headers['Idempotency-Key'], 'i11-approve');
    expect(sent, {
      'expected_revision': 20,
      'reason': 'I11 synthetic reviewed',
      'base_record_version_id': '$r:20',
      'kind': 'approve',
      'target_id': '',
      'after': {'confirmed': true},
      'evidence_ids': [],
    });
  });
  test('error409_preserves_choice_key_and_scoped_reconcile', () async {
    assertRaw('error');
    assertRaw('error_readback');

    final posts = <http.Request>[];
    var reads = 0;
    final repo = repository((q) async {
      if (q.url.path.endsWith('/content')) return asset(q);
      if (q.method == 'GET') {
        reads++;
        expect(q.url.path, '$root/specimens/$s/workspace');
        return response(posts.isEmpty ? 'workspace' : 'error_readback');
      }
      expect(q.method, 'POST');
      expect(q.url.path, '$root/specimens/$s/decisions');
      posts.add(q);
      return response('error');
    });
    final original = await repo.specimen(scope, s);
    final stale = Specimen({
      ...original.data,
      'revision': 19,
      'record_version_id': '$r:19',
      'latest_record_version_id': '$r:19',
    });
    await expectLater(
      repo.review(scope, stale, {
        'kind': 'approve',
        'reason': 'I11 synthetic reviewed',
      }, 'i11-stale'),
      throwsA(
        isA<ApiFailure>()
            .having((e) => e.status, 'status', 409)
            .having((e) => e.code, 'code', 'revision_or_idempotency_conflict')
            .having((e) => e.conflict, 'conflict', true)
            .having((e) => e.details, 'details', isEmpty),
      ),
    );
    expect(posts, hasLength(1));
    expect(reads, 1);
    expect(jsonDecode(posts.single.body), {
      ...approveBody,
      'expected_revision': 19,
      'base_record_version_id': '$r:19',
    });
    expect(posts.single.headers['Idempotency-Key'], 'i11-stale');
    expect(posts.single.url.path, '$root/specimens/$s/decisions');
    final reconciled = await repo.specimen(scope, s);
    pin(reconciled, 20, 'needs_human_review');
    expect(reads, 2);
    expect(posts, hasLength(1));
  });
  test('upload20_tail_and_complete3', () async {
    assertRaw('upload');
    assertRaw('upload_tail');
    assertRaw('upload_current');
    assertRaw('upload_complete');

    final sends = <http.Request>[];
    final methods = <String>[];
    var uploaded = false;
    final repo = repository((q) async {
      methods.add(q.method);
      if (q.method == 'GET') {
        expect(q.url.path, '$root/uploads/$u');
        return response(uploaded ? 'upload_current' : 'upload');
      }
      sends.add(q);
      if (q.method == 'PUT') {
        expect(q.url.path, '$root/uploads/$u/content');
        expect(q.headers['Upload-Offset'], '20');
        expect(q.headers['Idempotency-Key'], 'chunk-$u-20');
        expect(q.bodyBytes.length, 28928);
        expect(q.bodyBytes, png.sublist(20));
        uploaded = true;
        return response('upload_tail');
      }
      expect(q.url.path, '$root/uploads/$u/complete');
      expect(jsonDecode(q.body), {'expected_revision': 3});
      return response('upload_complete');
    });
    final state = await repo.resumeIntake(scope, u);
    expect(state['upload_id'], u);
    expect(state['state'], 'uploading');
    expect(state['offset'], 20);
    expect(state['revision'], 2);
    await repo.upload(
      scope,
      state,
      IntakeFile(
        name: 'synthetic.png',
        bytes: png,
        mimeType: 'image/png',
        sha256: body('upload')['sha256'],
        method: 'files',
      ),
      (p) => expect(p, 1),
    );
    await repo.completeIntake(scope, u, 'i11-complete');
    expect(sends.map((q) => q.method).toList(), ['PUT', 'POST']);
    expect(methods, ['GET', 'GET', 'PUT', 'GET', 'POST']);
    expect(sends.last.headers['Idempotency-Key'], 'i11-complete');
  });
  test('candidate22_exact_ack_readback_and_retained_keys', () async {
    assertRaw('review_batch');
    assertRaw('review_readback');

    final sends = <http.Request>[];
    var saved = false;
    final repo = repository((q) async {
      if (q.url.path.endsWith('/content')) return asset(q);
      if (q.method == 'GET') {
        expect(q.url.path, '$root/specimens/$s/workspace');
        return response(saved ? 'review_readback' : 'action_readback');
      }
      sends.add(q);
      expect(q.method, 'POST');
      expect(q.url.path, '$root/decisions:batch');
      expect(jsonDecode(q.body), candidateBody);
      saved = true;
      return response('review_batch');
    });
    final original = await repo.specimen(scope, s);
    pin(original, 21, 'cleared');
    // Independent selection receipt; the exporter never supplies expectations.
    const selection =
        '70c2cd77f73f5180e59ce357a83eec7c625e495f52a5e4bcb98627731c48b1e8'; // pragma: allowlist secret -- Synthetic retained candidate selection SHA-256.
    expect(corpus['selection_id'], selection);
    final result = await repo.reviewCandidateBatch(
      scope,
      original,
      [
        {
          'kind': 'research_candidate',
          'target_id': 'country',
          'selection_id': selection,
        },
      ],
      'I11 retained source reviewed',
      'i11-candidate',
    );
    expect(result.saved, 1);
    expect(result.stopped, false);
    pin(result.specimen, 22, 'needs_human_review');
    expect(
      result.specimen.data['available_actions'],
      actions.where((v) => v != 'reprocess').toList(),
    );
    final sent = jsonDecode(sends.single.body) as Json;
    final decision = Json.from(sent['decisions'][0]);
    expect(
      sends.single.headers['Idempotency-Key'],
      '7651ca196a03f7cc18d5625844ca3b2fdc68a62d7b19c691c3b222ad40a77aa8', // pragma: allowlist secret -- Synthetic candidate request idempotency SHA-256.
    );
    expect(sent['reason'], 'I11 retained source reviewed');
    expect(decision['specimen_id'], s);
    expect(decision['expected_revision'], 21);
    expect(decision['base_record_version_id'], '$r:21');
    expect(decision['kind'], 'research_candidate');
    expect(decision['target_id'], 'country');
    expect(decision['after'], {'selection_id': selection});
    expect(decision['idempotency_key'], 'i11-candidate-0');
  });
  test('malformed_upload_ack_stops_without_duplicate_or_completion', () async {
    var writes = 0;
    final repo = repository((q) async {
      if (q.method == 'GET') return response('upload');
      writes++;
      return http.Response(
        jsonEncode({...body('upload_tail'), 'offset': 20}),
        200,
      );
    });
    await expectLater(
      repo.upload(
        scope,
        body('upload'),
        IntakeFile(
          name: 'synthetic.png',
          bytes: png,
          mimeType: 'image/png',
          sha256: body('upload')['sha256'],
          method: 'files',
        ),
        (_) {},
      ),
      throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'offset')),
    );
    expect(writes, 1);
  });
  test(
    'candidate_bad_identity_ack_retains_retry_keys_without_readback',
    () async {
      var reads = 0;
      final repo = repository((q) async {
        if (q.url.path.endsWith('/content')) return asset(q);
        if (q.method == 'GET') {
          reads++;
          return response('action_readback');
        }
        final answer = body('review_batch');
        answer['results'][0]['specimen_id'] = 'other';
        return http.Response(jsonEncode(answer), 200);
      });
      final original = await repo.specimen(scope, s);
      await expectLater(
        repo.reviewCandidateBatch(
          scope,
          original,
          [
            {
              'kind': 'research_candidate',
              'target_id': 'country',
              'selection_id':
                  '70c2cd77f73f5180e59ce357a83eec7c625e495f52a5e4bcb98627731c48b1e8', // pragma: allowlist secret -- Synthetic retained candidate selection SHA-256.
            },
          ],
          'I11 retained source reviewed',
          'i11-candidate',
        ),
        throwsA(
          isA<ReviewBatchFailure>()
              .having((e) => e.saved, 'saved', 0)
              .having((e) => e.retainKeys, 'retainKeys', true),
        ),
      );
      expect(reads, 1);
    },
  );
  test('workspace20_scoped_detail_enables_approve', () async {
    final paths = <String>[];
    final repo = repository((q) async {
      paths.add(q.url.path);
      if (q.url.path.endsWith('/content')) return asset(q);
      expect(q.method, 'GET');
      expect(q.url.path, '$root/specimens/$s/workspace');
      return response('workspace');
    });
    final current = await repo.specimen(scope, s);
    final eligibility = BulkSelectionEligibility(
      requested: [current],
      records: {s: current},
      unavailable: {},
    );
    expect(eligibility.eligibleFor(BulkDecisionKind.approve).single.id, s);
    expect(paths.first, '$root/specimens/$s/workspace');
  });
  test('compat_record_version_alias', () {
    // models.dart recordVersionId intentionally accepts either client spelling.
    final server = body('workspace');
    final alias = {
      ...server,
      'latest_record_version_id': server['record_version_id'],
    }..remove('record_version_id');
    pin(Specimen(server), 20, 'needs_human_review');
    pin(Specimen(alias), 20, 'needs_human_review');
    final missing = {...alias}..remove('latest_record_version_id');
    expect(Specimen(missing).recordVersionId, '');
    expect(
      BulkSelectionEligibility(
        requested: [Specimen(missing)],
        records: {s: Specimen(missing)},
        unavailable: {},
      ).eligibleFor(BulkDecisionKind.approve),
      isEmpty,
    );
  });
  test('compat_optional_defaults_never_enable_action', () {
    // models.dart defaults missing data; defaults do not advertise permissions.
    const item = Specimen({'specimen_id': s});
    expect(item.revision, 0);
    expect(item.state, 'unknown');
    expect(item.disposition, isNull);
    expect(item.recordVersionId, '');
    expect(
      BulkSelectionEligibility(
        requested: [item],
        records: {s: item},
        unavailable: {},
      ).eligibleFor(BulkDecisionKind.approve),
      isEmpty,
    );
  });
  test('compat_unknown_extra_keys', () async {
    // request decoder and Specimen preserve extensible unknown keys.
    var saved = false;
    var posts = 0;
    final repo = repository((q) async {
      if (q.url.path.endsWith('/content')) return asset(q);
      if (q.method == 'POST') {
        posts++;
        expect(q.url.path, '$root/specimens/$s/decisions');
        expect(jsonDecode(q.body), approveBody);
        expect(q.headers['Idempotency-Key'], 'i11-approve');
        saved = true;
        return response('action');
      }
      expect(q.method, 'GET');
      expect(q.url.path, '$root/specimens/$s/workspace');
      return http.Response(
        jsonEncode({
          ...body(saved ? 'action_readback' : 'workspace'),
          'future_key': {'nested': true},
        }),
        200,
      );
    });
    final item = await repo.specimen(scope, s);
    pin(item, 20, 'needs_human_review');
    expect(item.data['future_key'], {'nested': true});
    final approved = await repo.review(scope, item, {
      'kind': 'approve',
      'reason': 'I11 synthetic reviewed',
    }, 'i11-approve');
    pin(approved, 21, 'cleared');
    expect(posts, 1);
    expect(approved.data['future_key'], {'nested': true});
  });
  test('compat_error_metadata_not_promoted_to_save_state', () async {
    // ApiFailure retains error status/code/message/details only.
    var posts = 0;
    var reads = 0;
    final repo = repository((q) async {
      if (q.url.path.endsWith('/content')) return asset(q);
      if (q.method == 'GET') {
        reads++;
        return response('workspace');
      }
      posts++;
      return http.Response(
        jsonEncode({
          'error': {
            ...body('error')['error'] as Map,
            'revision': 99,
            'specimen_id': 'forged',
            'disposition': 'cleared',
          },
        }),
        409,
      );
    });
    final item = await repo.specimen(scope, s);
    await expectLater(
      repo.review(scope, item, {
        'kind': 'approve',
        'reason': 'I11 synthetic reviewed',
      }, 'i11-approve'),
      throwsA(isA<ApiFailure>().having((e) => e.conflict, 'conflict', true)),
    );
    pin(item, 20, 'needs_human_review');
    expect(posts, 1);
    expect(reads, 1);
  });
  test('compat_action_ack_requires_scoped_readback', () async {
    // review discards ACK fields and always reopens the scoped workspace.
    final calls = <String>[];
    final repo = repository((q) async {
      if (q.url.path.endsWith('/content')) return asset(q);
      calls.add('${q.method} ${q.url.path}');
      if (q.method == 'POST') return http.Response('{}', 200);
      expect(q.url.path, '$root/specimens/$s/workspace');
      return response('action_readback');
    });
    final item = Specimen({
      ...body('workspace'),
      'latest_record_version_id': '$r:20',
    });
    final approved = await repo.review(scope, item, {
      'kind': 'approve',
      'reason': 'I11 synthetic reviewed',
    }, 'i11-approve');
    pin(approved, 21, 'cleared');
    expect(calls, [
      'POST $root/specimens/$s/decisions',
      'GET $root/specimens/$s/workspace',
    ]);
  });
  test('compat_upload_revision_from_current_get', () async {
    // upload resumes by offset; completeIntake obtains revision from a new GET.
    var reads = 0;
    var writes = 0;
    var completes = 0;
    final repo = repository((q) async {
      if (q.method == 'GET') {
        reads++;
        expect(q.url.path, '$root/uploads/$u');
        if (writes == 0) {
          return http.Response(
            jsonEncode(body('upload')..remove('revision')),
            200,
          );
        }
        return response('upload_current');
      }
      if (q.method == 'PUT') {
        writes++;
        expect(q.bodyBytes.length, 28928);
        expect(q.bodyBytes, png.sublist(20));
        return response('upload_tail');
      }
      completes++;
      expect(jsonDecode(q.body), {'expected_revision': 3});
      return response('upload_complete');
    });
    await repo.upload(
      scope,
      body('upload'),
      IntakeFile(
        name: 'synthetic.png',
        bytes: png,
        mimeType: 'image/png',
        sha256: pngHash,
        method: 'files',
      ),
      (_) {},
    );
    await repo.completeIntake(scope, u, 'i11-complete');
    expect(reads, 2);
    expect(writes, 1);
    expect(completes, 1);
  });
  for (final offset in [20, 28949]) {
    test('upload_bad_offset_${offset}_never_completes', () async {
      var puts = 0;
      var completes = 0;
      final repo = repository((q) async {
        if (q.method == 'GET') return response('upload');
        if (q.method == 'POST') {
          completes++;
          return response('upload_complete');
        }
        puts++;
        return http.Response(
          jsonEncode({...body('upload_tail'), 'offset': offset}),
          200,
        );
      });
      await expectLater(() async {
        await repo.upload(
          scope,
          body('upload'),
          IntakeFile(
            name: 'synthetic.png',
            bytes: png,
            mimeType: 'image/png',
            sha256: pngHash,
            method: 'files',
          ),
          (_) {},
        );
        await repo.completeIntake(scope, u, 'i11-complete');
      }(), throwsA(isA<ApiFailure>().having((e) => e.code, 'code', 'offset')));
      expect(puts, 1);
      expect(completes, 0);
    });
  }
  for (final mode in [
    'conflict',
    'bad-ack',
    'stale-readback',
    'lost-readback',
    'exact',
  ]) {
    test('controller_choice_key_draft_$mode', () async {
      final session = _ContractSession();
      final posts = <http.Request>[];
      final detailPaths = <String>[];
      var reconciling = false;
      final pending = PendingFieldChange(
        fieldKey: 'country',
        displayName: 'Country',
        state: 'supported',
        candidateSelectionId: selection,
        baseLiteral: 'United States',
        candidateValue: 'Philippines',
        candidateLabel: 'Synthetic retained source',
      );
      final change = pending.toChange('I11 retained source reviewed');
      final repo = repository((q) async {
        if (q.url.path == '/v1/session') {
          return http.Response(
            jsonEncode({
              'user_id': session.userId,
              'mode': 'synthetic',
              'memberships': [
                {'organization_id': s, 'collection_id': r, 'role': 'reviewer'},
              ],
            }),
            200,
          );
        }
        if (q.url.path == '$root/collections') {
          return http.Response(
            jsonEncode({
              'items': [
                {'collection_id': r},
              ],
            }),
            200,
          );
        }
        if (q.url.path == '$root/specimens') return response('list');
        if (q.url.path.endsWith('/content')) return asset(q);
        if (q.method == 'GET') {
          expect(q.url.path, '$root/specimens/$s/workspace');
          detailPaths.add(q.url.path);
          if (posts.isEmpty) {
            return response(
              mode == 'conflict' ? 'workspace' : 'action_readback',
            );
          }
          if (mode == 'conflict') return response('error_readback');
          if (!reconciling && mode == 'lost-readback') {
            throw http.ClientException('readback lost');
          }
          return response(
            !reconciling && mode == 'stale-readback'
                ? 'action_readback'
                : 'review_readback',
          );
        }
        expect(q.method, 'POST');
        expect(q.url.path, '$root/decisions:batch');
        posts.add(q);
        final sent = jsonDecode(q.body) as Json;
        final row = sent['decisions'][0] as Map;
        expect(row['after'], {'selection_id': selection});
        expect(row['expected_revision'], mode == 'conflict' ? 20 : 21);
        expect(
          row['base_record_version_id'],
          mode == 'conflict' ? '$r:20' : '$r:21',
        );
        if (mode == 'conflict') return response('error');
        // Controller creates keys. The mock echoes that actual key, as the API does.
        final ack = body('review_batch');
        ack['results'][0]['idempotency_key'] = row['idempotency_key'];
        if (mode == 'bad-ack') ack['results'][0]['specimen_id'] = 'other';
        return http.Response(jsonEncode(ack), 200);
      });
      final controller = WorkspaceController(
        repository: repo,
        session: session,
        pollInterval: const Duration(days: 1),
      );
      addTearDown(() async {
        controller.dispose();
        await session.events.close();
      });
      await controller.checkAccess();
      await controller.openSpecimen(s);
      pin(
        controller.selected!,
        mode == 'conflict' ? 20 : 21,
        mode == 'conflict' ? 'needs_human_review' : 'cleared',
      );
      final outcome = await controller.mutateBatch([
        change,
      ], 'I11 retained source reviewed');
      if (mode == 'exact') {
        expect(outcome.saved, 1);
        expect(outcome.requiresReconciliation, isFalse);
        pin(outcome.confirmed!, 22, 'needs_human_review');
        expect(
          outcome.confirmed!.fields.singleWhere(
            (f) => f['field_key'] == 'country',
          )['literal_value'],
          'United States',
        );
        expect(
          outcome.confirmed!.fields.singleWhere(
            (f) => f['field_key'] == 'country',
          )['parsed_value'],
          'Philippines',
        );
        expect(posts, hasLength(1));
        return;
      }
      final known = mode == 'stale-readback' || mode == 'lost-readback';
      expect(outcome.saved, known ? 1 : 0);
      expect(outcome.confirmed, isNull);
      expect(outcome.requiresReconciliation, isTrue);
      expect(outcome.acknowledgement?.recordVersionId, known ? '$r:22' : null);
      pin(
        controller.selected!,
        mode == 'conflict' ? 20 : 21,
        mode == 'conflict' ? 'needs_human_review' : 'cleared',
      );
      // An identical retry must preserve the choice, per-entry key and HTTP key.
      final again = await controller.mutateBatch([
        pending.toChange('I11 retained source reviewed'),
      ], 'I11 retained source reviewed');
      expect(again.confirmed, isNull);
      expect(posts, hasLength(2));
      expect(posts[1].body, posts[0].body);
      expect(
        posts[1].headers['Idempotency-Key'],
        posts[0].headers['Idempotency-Key'],
      );
      expect(pending.candidateSelectionId, selection);
      expect(pending.baseLiteral, 'United States');
      if (mode == 'conflict') {
        expect(controller.error!.actionLabel, 'Refresh and compare');
      }
      reconciling = true;
      final count = posts.length;
      await controller.error!.action();
      expect(
        posts,
        hasLength(count),
        reason: 'refresh must not resend a choice',
      );
      expect(detailPaths, everyElement('$root/specimens/$s/workspace'));
      pin(
        controller.selected!,
        mode == 'conflict' ? 20 : 22,
        'needs_human_review',
      );
      if (mode == 'conflict') {
        final afterRefresh = await controller.mutateBatch([
          pending.toChange('I11 retained source reviewed'),
        ], 'I11 retained source reviewed');
        expect(afterRefresh.confirmed, isNull);
        expect(afterRefresh.saved, 0);
        expect(posts, hasLength(count + 1));
        expect(posts.last.body, posts.first.body);
        expect(
          posts.last.headers['Idempotency-Key'],
          posts.first.headers['Idempotency-Key'],
        );
      }

      if (known) {
        expect(
          controller.isAcknowledgedBatchReadback(
            outcome.acknowledgement!,
            controller.selected!,
          ),
          isTrue,
        );
        final blocked = await controller.mutateBatch([
          change,
        ], 'I11 retained source reviewed');
        expect(blocked.saved, 0);
        expect(posts, hasLength(count), reason: 'old choice cannot be rebased');
      }
    });
  }
}

class _ContractSession implements SessionAccess {
  final events = StreamController<bool>.broadcast();
  @override
  bool get signedIn => true;
  @override
  String get userId => 'synthetic-reviewer';
  @override
  String get displayName => 'Synthetic reviewer';
  @override
  Stream<bool> get changes => events.stream;
  @override
  Future<String?> token() async => 'synthetic-token';
  @override
  Future<void> signIn(String email, String password) async {}
  @override
  Future<void> signOut() async {}
  @override
  Future<void> resetPassword(String email) async {}
}
