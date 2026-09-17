// The contract this client is built against, checked against the contract the
// runtime API publishes (`docs/execution/FRONT_END_REFACTOR.md` section 3I,
// slot B3, item 1).
//
// Where the contract lives, per `docs/execution/CONTRACTS.md`: the canonical
// wire freeze adopts the explicit HTTP serializers in the backend's
// `application/api.py`, and publishes them as `docs/execution/backend-openapi.json`
// (requests) and `docs/execution/backend-wire-examples.json` (responses).
// `docs/execution/FLUTTER.md` pins the copy this client reads by digest.
//
// Three things are checked here, and one of them is uncomfortable.
//
//  1. The client's copy of the response contract is the published one, byte
//     for byte, at the digest the client's own document pins.
//  2. Every path the client can request, and every property it can send, is
//     described by the published request contract, or is named in the
//     amendment below with the line of backend source that declares it. The
//     amendment is a shrink only backlog: the published snapshot predates
//     fifteen routes and five properties the backend has, and every entry
//     leaves this file when the snapshot is regenerated.
//  3. An unknown field never breaks a response, and a missing optional field
//     renders as unmeasured rather than as zero (design/00-north-star.md,
//     the honesty row).

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/sources.dart';

/// The published request contract.
const String openApiPath = '../../docs/execution/backend-openapi.json';

/// The published response contract.
const String wireExamplesPath =
    '../../docs/execution/backend-wire-examples.json';

/// The client's copy of the response contract.
const String clientWireExamplesPath =
    'test/fixtures/backend-wire-examples.json';

/// The document that pins the copy by digest.
const String flutterContractPath = '../../docs/execution/FLUTTER.md';

/// Routes the backend serves that the published snapshot predates.
///
/// Each value is the declaration in the backend source. A shrink only
/// backlog: regenerating `backend-openapi.json` from the running application
/// empties it, and until then a client that reaches for a route outside both
/// this map and the snapshot is a client inventing an endpoint.
const Map<String, String> routeAmendment = <String, String>{
  '/v1/organizations/{organization_id}/images/preflight':
      'src/specimen_digitization/application/api.py:728',
  '/v1/organizations/{organization_id}/sources':
      'src/specimen_digitization/application/api.py:910',
  '/v1/organizations/{organization_id}/sources/{source_id}/objects':
      'src/specimen_digitization/application/api.py:978',
  '/v1/organizations/{organization_id}/batches/{batch_id}/items:from-source':
      'src/specimen_digitization/application/api.py:1036',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/history':
      'src/specimen_digitization/application/api.py:1300',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/history/{revision}':
      'src/specimen_digitization/application/api.py:1316',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/active-graph':
      'src/specimen_digitization/application/api.py:1335',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/phases/{phase}':
      'src/specimen_digitization/application/api.py:1364',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/authority-results/{tool_id}':
      'src/specimen_digitization/application/api.py:1408',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/authority-results/{tool_id}/raw':
      'src/specimen_digitization/application/api.py:1421',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/observations/{observation_id}/raw':
      'src/specimen_digitization/application/api.py:1448',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/observations/{observation_id}/declarations':
      'src/specimen_digitization/application/api.py:1475',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/observations/{observation_id}/metadata':
      'src/specimen_digitization/application/api.py:1509',
  '/v1/organizations/{organization_id}/specimens/{specimen_id}/disagreements/{region_id}':
      'src/specimen_digitization/application/api.py:1525',
  '/v1/organizations/{organization_id}/decisions:batch':
      'src/specimen_digitization/application/api.py:2035',
};

/// Properties the backend's request models carry that the snapshot predates.
///
/// Keyed by the schema the snapshot does publish, or by the model name where
/// the snapshot publishes no schema at all. Same shrink only rule as the
/// routes above. Every one of these is `extra="forbid"` on the live model, so
/// a property outside both this map and the snapshot is a 422 waiting for the
/// first live request.
const Map<String, Map<String, String>> propertyAmendment =
    <String, Map<String, String>>{
      'BatchInput': <String, String>{
        'sensitive': 'src/specimen_digitization/application/api.py:89',
      },
      'ItemInput': <String, String>{
        'sensitive': 'src/specimen_digitization/application/api.py:98',
      },
      'Region': <String, String>{
        'rotation_quarter_turns':
            'src/specimen_digitization/application/domain.py:125',
      },
      'ClassificationInput': <String, String>{
        'profile_collection_id':
            'src/specimen_digitization/application/api.py:158',
      },
      'DecisionBatchInput': <String, String>{
        'reason': 'src/specimen_digitization/application/api.py:138',
        'decisions': 'src/specimen_digitization/application/api.py:138',
        'specimen_id': 'src/specimen_digitization/application/api.py:124',
        'expected_revision': 'src/specimen_digitization/application/api.py:124',
        'base_record_version_id':
            'src/specimen_digitization/application/api.py:124',
        'kind': 'src/specimen_digitization/application/api.py:124',
        'target_id': 'src/specimen_digitization/application/api.py:124',
        'before': 'src/specimen_digitization/application/api.py:124',
        'after': 'src/specimen_digitization/application/api.py:124',
        'evidence_ids': 'src/specimen_digitization/application/api.py:124',
        'idempotency_key': 'src/specimen_digitization/application/api.py:124',
      },
    };

/// Snapshot properties the live backend has since made optional.
///
/// The snapshot marks these required; the backend declares them nullable with
/// a default. The client omits them for the formats whose coordinate basis the
/// server establishes (HEIF primary, RAW active area), which the snapshot
/// alone would call a malformed request.
const Map<String, Map<String, String>> relaxedRequirement =
    <String, Map<String, String>>{
      'ItemInput': <String, String>{
        'width': 'src/specimen_digitization/application/api.py:105',
        'height': 'src/specimen_digitization/application/api.py:106',
      },
    };

/// One request the client made.
typedef Sent = ({String method, String path, Json? body});

/// The session the probe is verified against, off the checked in contract.
final Json contractSession =
    (jsonDecode(File(clientWireExamplesPath).readAsStringSync())
            as Json)['session']
        as Json;

/// The collection that session grants.
final String contractCollectionId =
    ((contractSession['memberships'] as List).first as Map)['collection_id']
        as String;

/// The collection the probe reaches for.
final CollectionScope scope = CollectionScope(
  organizationId:
      ((contractSession['memberships'] as List).first as Map)['organization_id']
          as String,
  collectionId: contractCollectionId,
  name: 'Entomology',
);

/// The record the probe drives.
///
/// It carries the artifact receipt the complete graph route refuses to be
/// asked for without, and one observation, so the declaration route is
/// reached rather than refused before it is sent.
final Specimen contractRecord = Specimen(<String, dynamic>{
  'specimen_id': 'sp-1',
  'revision': 3,
  'active_run_id': 'run-1',
  'latest_record_version_id': 'run-1:3',
  'assets': <Json>[
    <String, dynamic>{'asset_id': 'asset-1'},
  ],
  'observations': <Json>[
    <String, dynamic>{
      'observation_id': 'target-1',
      'region_id': 'r1',
      'raw_sha256': 'b' * 64,
    },
  ],
  'artifact_receipt': <String, dynamic>{
    'artifact_size_bytes': 1024,
    'artifact_sha256': 'b' * 64,
    'revision': 3,
    'record_version_id': 'run-1:3',
  },
});

/// The workspace body the probe answers, so the photograph route is reached.
final Json contractWorkspace =
    (jsonDecode(File(clientWireExamplesPath).readAsStringSync())
            as Json)['workspace_response']
        as Json;

/// How many distinct routes the client can reach.
///
/// A floor, so this probe can never go quiet: it once recorded one path and
/// reported that every path the client makes is described.
const int reachableRoutes = 29;

void main() {
  final Json contract =
      jsonDecode(File(openApiPath).readAsStringSync()) as Json;
  final Json paths = contract['paths'] as Json;
  final Json schemas = (contract['components'] as Json)['schemas'] as Json;

  Set<String> propertiesOf(String schema) => <String>{
    ...((schemas[schema] as Json?)?['properties'] as Json? ??
            const <String, dynamic>{})
        .keys,
    ...?propertyAmendment[schema]?.keys,
  };

  Set<String> requiredOf(String schema) =>
      <String>{...?(schemas[schema] as Json?)?['required'] as List<dynamic>?}
          .map((Object? key) => key.toString())
          .where(
            (String key) =>
                !(relaxedRequirement[schema]?.containsKey(key) ?? false),
          )
          .toSet();

  num boundOf(String schema, String property, String bound) =>
      (((schemas[schema] as Json)['properties'] as Json)[property]
              as Json)[bound]
          as num;

  group('the contract this client reads is the contract the API published', () {
    test('the client copy is the published copy, at the pinned digest', () {
      final String published = File(wireExamplesPath).readAsStringSync();
      final String client = File(clientWireExamplesPath).readAsStringSync();
      expect(
        client,
        published,
        reason:
            'the client copy of the response contract has drifted from '
            '$wireExamplesPath',
      );
      final String pin = RegExp(r'\b[a-f0-9]{64}\b')
          .allMatches(File(flutterContractPath).readAsStringSync())
          .map((RegExpMatch m) => m.group(0)!)
          .first;
      expect(
        crypto.sha256
            .convert(File(clientWireExamplesPath).readAsBytesSync())
            .toString(),
        pin,
        reason:
            'the digest $flutterContractPath pins no longer matches the '
            'file it pins',
      );
    });
  });

  group('every request the client can make is one the contract describes', () {
    late List<Sent> sent;

    /// A repository that records what it sent and answers just enough for
    /// the next call to be made.
    ///
    /// The session and the collections are answered from the checked in wire
    /// contract, because `ApiSpecimenRepository` refuses every protected call
    /// until a session has been verified. Without that the probe would reach
    /// one path and pass on nothing, which is what it did the first time it
    /// was written.
    ApiSpecimenRepository recording({
      Json Function(http.Request request)? answer,
    }) => ApiSpecimenRepository(
      baseUrl: Uri.parse('https://api.example.org'),
      token: () async => 'contract-token',
      appCheckToken: () async => 'contract-app-check',
      client: MockClient((http.Request request) async {
        sent.add((
          method: request.method,
          path: request.url.path,
          body:
              request.body.isEmpty ||
                  request.headers['Content-Type'] != 'application/json'
              ? null
              : Json.from(jsonDecode(request.body) as Map),
        ));
        if (request.url.path == '/v1/session') {
          return http.Response(jsonEncode(contractSession), 200);
        }
        if (request.url.path.endsWith('/collections')) {
          return http.Response(
            jsonEncode(<String, dynamic>{
              'items': <Json>[
                <String, dynamic>{
                  'collection_id': contractCollectionId,
                  'display_name': 'Entomology',
                },
              ],
            }),
            200,
          );
        }
        if (request.url.path.endsWith('/content') && request.method == 'GET') {
          return http.Response.bytes(<int>[1, 2, 3], 200);
        }
        return http.Response(
          jsonEncode(answer?.call(request) ?? <String, dynamic>{}),
          200,
        );
      }),
    );

    setUp(() => sent = <Sent>[]);

    /// Swallows the failure a stub answer causes; the request is the subject.
    Future<void> attempt(Future<void> Function() call) async {
      try {
        await call();
      } catch (_) {
        // The stub answers an empty body, so most calls fail their own
        // verification. What was sent is already recorded.
      }
    }

    test('every path matches a published route or a named amendment', () async {
      final IntakeFile file = IntakeFile(
        name: 'label.png',
        bytes: Uint8List.fromList(<int>[1, 2, 3]),
        mimeType: 'image/png',
        sha256: 'a' * 64,
        method: 'files',
        width: 1000,
        height: 520,
      );
      final ApiSpecimenRepository repository = recording(
        answer: (http.Request httpRequest) =>
            httpRequest.url.path.endsWith('/batches')
            ? <String, dynamic>{'batch_id': 'batch-1', 'sensitive': true}
            : httpRequest.url.path.endsWith('/workspace')
            ? <String, dynamic>{...contractWorkspace, 'specimen_id': 'sp-1'}
            : <String, dynamic>{},
      );
      addTearDown(repository.close);

      await attempt(repository.scopes);
      await attempt(() => repository.profiles(scope));
      await attempt(() => repository.specimenPage(scope));
      await attempt(() => repository.specimen(scope, 'sp-1'));
      await attempt(
        () => repository.historyPage(scope, 'sp-1', throughRevision: 3),
      );
      await attempt(() => repository.historicalSpecimen(scope, 'sp-1', 2));
      for (final ArtifactKind kind in ArtifactKind.values) {
        await attempt(
          () => repository.artifact(
            scope,
            contractRecord,
            ArtifactRequest(kind, 'target-1', sha256: 'b' * 64),
          ),
        );
      }
      await attempt(() => repository.preflight(scope, file));
      await attempt(() => repository.createIntake(scope, file, 'key'));
      await attempt(() => repository.resumeIntake(scope, 'upload-1'));
      await attempt(
        () => repository.upload(
          scope,
          <String, dynamic>{'upload_id': 'upload-1'},
          file,
          (double _) {},
        ),
      );
      await attempt(() => repository.completeIntake(scope, 'upload-1', 'key'));
      for (final String kind in <String>[
        'field_correction',
        'classification_correction',
        'segmentation_correction',
        'run_action',
      ]) {
        await attempt(
          () => repository.review(scope, contractRecord, <String, dynamic>{
            'kind': kind,
            'reason': 'Contract probe',
            'action': 'pause',
            'value': 'insects',
            'state': 'supported',
            'regions': <Json>[
              <String, dynamic>{
                'region_id': 'r1',
                'bbox': <int>[0, 0, 10, 10],
                'order': 0,
              },
            ],
          }, 'key'),
        );
      }
      await attempt(
        () => repository.reviewMany(
          scope,
          <Specimen>[contractRecord],
          BulkDecisionKind.approve,
          'Contract probe',
          'key',
        ),
      );
      await attempt(
        () => repository.retry(scope, contractRecord, 'Retry', 'key'),
      );
      await attempt(() => repository.sources(scope));
      await attempt(() => repository.sourceObjectPage(scope, 'src-1'));
      await attempt(
        () => repository.importFromSource(scope, 'src-1', <SourceObject>[
          SourceObject(<String, dynamic>{
            'object_id': 'obj-1',
            'generation': '1',
            'media_type': 'image/jpeg',
            'size_bytes': 1024,
          }),
        ], 'key'),
      );

      final Set<String> reached = sent
          .map((Sent request) => request.path)
          .toSet();
      expect(
        reached,
        hasLength(greaterThanOrEqualTo(reachableRoutes)),
        reason:
            'the probe reached ${reached.length} routes, which is fewer '
            'than the client has. A probe that stops early reports that '
            'every path is described when it checked almost none:\n'
            '${(reached.toList()..sort()).join('\n')}',
      );
      final Set<String> templates = <String>{
        ...paths.keys,
        ...routeAmendment.keys,
      };
      final List<String> unmatched = reached
          .where(
            (String path) =>
                !templates.any((String template) => matches(template, path)),
          )
          .toList();
      expect(
        unmatched,
        isEmpty,
        reason:
            'the client requests paths that neither $openApiPath nor the '
            'named amendment describes:\n${unmatched.join('\n')}',
      );
    });

    test('every property sent is one the request model declares', () async {
      final ApiSpecimenRepository repository = recording(
        answer: (http.Request request) => request.url.path.endsWith('/batches')
            ? <String, dynamic>{'batch_id': 'batch-1', 'sensitive': true}
            : <String, dynamic>{'revision': 4},
      );
      addTearDown(repository.close);

      final IntakeFile file = IntakeFile(
        name: 'label.png',
        bytes: Uint8List.fromList(<int>[1, 2, 3]),
        mimeType: 'image/png',
        sha256: 'a' * 64,
        method: 'files',
        width: 1000,
        height: 520,
      );
      await attempt(() => repository.createIntake(scope, file, 'key'));
      await attempt(() => repository.completeIntake(scope, 'upload-1', 'key'));
      await attempt(
        () => repository.review(scope, contractRecord, <String, dynamic>{
          'kind': 'field_correction',
          'target_id': 'country',
          'value': 'United States',
          'state': 'supported',
          'reason': 'Contract probe',
        }, 'key'),
      );
      await attempt(
        () => repository.review(scope, contractRecord, <String, dynamic>{
          'kind': 'classification_correction',
          'value': 'insects',
          'profile_collection_id': 'insects',
          'reason': 'Contract probe',
        }, 'key'),
      );
      await attempt(
        () => repository.review(scope, contractRecord, <String, dynamic>{
          'kind': 'segmentation_correction',
          'reason': 'Contract probe',
          'regions': <Json>[
            <String, dynamic>{
              'region_id': 'r1',
              'bbox': <int>[0, 0, 10, 10],
              'order': 0,
              'rotation_quarter_turns': 1,
            },
          ],
        }, 'key'),
      );
      await attempt(
        () => repository.review(scope, contractRecord, <String, dynamic>{
          'kind': 'run_action',
          'action': 'pause',
          'reason': 'Contract probe',
        }, 'key'),
      );
      await attempt(
        () => repository.reviewMany(
          scope,
          <Specimen>[contractRecord],
          BulkDecisionKind.confirmCoverage,
          'Contract probe',
          'key',
        ),
      );

      void check(String schema, Json body) {
        final Set<String> declared = propertiesOf(schema);
        expect(
          body.keys.where((String key) => !declared.contains(key)),
          isEmpty,
          reason:
              '$schema forbids extra properties, and the client sends one '
              'that neither the published schema nor the amendment declares: '
              '${body.keys.toList()}',
        );
        expect(
          requiredOf(schema).where((String key) => !body.containsKey(key)),
          isEmpty,
          reason:
              '$schema requires a property the client did not send: '
              '${body.keys.toList()}',
        );
      }

      Json bodyFor(bool Function(Sent request) where) =>
          sent.firstWhere(where).body!;

      check('BatchInput', bodyFor((Sent r) => r.path.endsWith('/batches')));
      check('ItemInput', bodyFor((Sent r) => r.path.endsWith('/items')));
      check('RevisionInput', bodyFor((Sent r) => r.path.endsWith('/complete')));
      check(
        'DecisionInput',
        bodyFor((Sent r) => r.path.endsWith('/decisions')),
      );
      check(
        'ClassificationInput',
        bodyFor((Sent r) => r.path.endsWith('/classification')),
      );
      check('ActionInput', bodyFor((Sent r) => r.path.endsWith('/actions')));
      final Json regions = bodyFor((Sent r) => r.path.endsWith('/regions'));
      check('RegionsInput', regions);
      for (final Json region in objects(regions['regions'])) {
        check('Region', region);
      }
      final Json batch = bodyFor(
        (Sent r) => r.path.endsWith('/decisions:batch'),
      );
      check('DecisionBatchInput', batch);
      for (final Json decision in objects(batch['decisions'])) {
        check('DecisionBatchInput', decision);
      }
    });
  });

  group('the bounds the client enforces are the bounds the contract sets', () {
    test('an intake file is refused at exactly the wire maximum', () {
      expect(intakeMaximumBytes, boundOf('ItemInput', 'size_bytes', 'maximum'));
      expect(intakeMaximumSide, boundOf('ItemInput', 'width', 'maximum'));
      expect(intakeMaximumSide, boundOf('ItemInput', 'height', 'maximum'));
    });
  });

  group('unknown fields are tolerated and absences are not zero', () {
    const CollectionScope scope = CollectionScope(
      organizationId: 'org',
      collectionId: 'insects',
      name: 'Entomology',
    );

    test(
      'a field the client has never heard of does not break a record',
      () async {
        final Json wire = Json.from(
          (jsonDecode(File(clientWireExamplesPath).readAsStringSync())
                  as Json)['workspace_response']
              as Map,
        );
        final ApiSpecimenRepository repository = ApiSpecimenRepository(
          baseUrl: Uri.parse('https://api.example.org'),
          token: () async => 'contract-token',
          client: MockClient((http.Request request) async {
            if (request.url.path.endsWith('/content')) {
              return http.Response.bytes(<int>[1, 2, 3], 200);
            }
            return http.Response(
              jsonEncode(<String, dynamic>{
                ...wire,
                'a_field_from_a_later_release': <String, dynamic>{
                  'nested': <int>[1, 2, 3],
                },
                'asset': <String, dynamic>{
                  ...wire['asset'] as Json,
                  'a_new_derivative': 'unknown to this client',
                },
              }),
              200,
            );
          }),
        );
        addTearDown(repository.close);
        final Specimen record = await repository.specimen(scope, 'sp-1');
        expect(record.id, wire['specimen_id']);
        expect(record.fields, hasLength((wire['fields'] as Json).length));
        expect(record.assets.single['preview_bytes'], <int>[1, 2, 3]);
      },
    );

    test('a count the server did not take stays absent, never zero', () async {
      final ApiSpecimenRepository repository = ApiSpecimenRepository(
        baseUrl: Uri.parse('https://api.example.org'),
        token: () async => 'contract-token',
        client: MockClient(
          (http.Request request) async => http.Response(
            jsonEncode(<String, dynamic>{
              'inventory_id': 'inv-1',
              'items': <Json>[],
              'object_count': 4,
              // `matching_count` omitted: the server did not count.
            }),
            200,
          ),
        ),
      );
      addTearDown(repository.close);
      final SourceObjectPage page = await repository.sourceObjectPage(
        scope,
        'src-1',
      );
      expect(
        page.matchingCount,
        isNull,
        reason:
            'an absent count became a number, so a control would offer a '
            'select all it cannot put an honest figure on',
      );
      expect(page.objectCount, 4);
    });

    test('an unfinished run keeps a null disposition', () {
      const Specimen record = Specimen(<String, dynamic>{
        'specimen_id': 'sp-1',
        'operational_state': 'processing',
        'disposition': null,
      });
      expect(record.disposition, isNull);
      expect(record.status, isNot('cleared'));
    });

    test('a cost the run has not settled is not recorded, not zero', () {
      const Json usage = <String, dynamic>{
        'reserved_cost_micros': 0,
        'actual_cost_micros': null,
      };
      expect(usage['actual_cost_micros'], isNull);
      expect(textOf(usage['actual_cost_micros']), 'Not recorded');
    });
  });
}

/// True when [path] is an instance of the OpenAPI [template].
bool matches(String template, String path) {
  final List<String> wanted = template.split('/');
  final List<String> actual = path.split('/');
  if (wanted.length != actual.length) return false;
  for (int i = 0; i < wanted.length; i++) {
    final String segment = wanted[i];
    if (segment.startsWith('{') && segment.endsWith('}')) continue;
    // A route may end in a literal suffix after a placeholder, as
    // `items:from-source` does; compare those literally.
    if (segment != actual[i]) return false;
  }
  return true;
}
