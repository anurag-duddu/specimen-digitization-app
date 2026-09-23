// What the repository makes of a workspace response and a queue search
// (UI.md T1.3, T1.5 and T1.6), over a scripted HTTP client.

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

const CollectionScope scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'collection',
  name: 'Synthetic collection',
);

/// The original's checksum on the first version of the record.
final String firstSha = 'a' * 64;

/// A workspace response the way `api.py` `workspace()` shapes one.
Json workspace({
  String? sha,
  Json? derivative,
  List<Json> transcriptions = const <Json>[],
}) => <String, dynamic>{
  'specimen_id': 'pilot-1',
  'organization_id': 'org',
  'collection_id': 'collection',
  'revision': 4,
  'record_version_id': 'run-1:4',
  'active_run_id': 'run-1',
  'status': 'processing_blocked',
  'disposition': null,
  'asset': <String, dynamic>{
    'id': 'asset-1',
    'sha256': sha ?? firstSha,
    'view_derivative': ?derivative,
  },
  'run': <String, dynamic>{},
  'fields': <String, dynamic>{},
  'transcriptions': transcriptions,
};

/// A repository whose server answers [body] for every JSON request and
/// [image] for the photograph, counting both.
class ScriptedServer {
  ScriptedServer(this.body);

  Json body;
  List<int> image = <int>[1, 2, 3];
  int imageStatus = 200;
  int images = 0;
  final List<Uri> json = <Uri>[];

  late final ApiSpecimenRepository repository = ApiSpecimenRepository(
    baseUrl: Uri.parse('http://localhost:8000'),
    token: () async => 'synthetic-test-token',
    appCheckToken: () async => 'synthetic-app-check',
    client: MockClient((http.Request request) async {
      if (request.url.path.endsWith('/content')) {
        images++;
        return http.Response.bytes(image, imageStatus);
      }
      json.add(request.url);
      return http.Response(jsonEncode(answer(request)), 200);
    }),
  );

  Json answer(http.Request request) => body;
}

void main() {
  group('disagreements', () {
    test('lists a region only when its readings differ', () async {
      final ScriptedServer server = ScriptedServer(
        workspace(
          transcriptions: <Json>[
            <String, dynamic>{
              'region_id': 'identical',
              'resolved': false,
              'alternatives': <String>['Chicago 1912'],
            },
            <String, dynamic>{
              'region_id': 'differing',
              'resolved': false,
              'alternatives': <String>['Chicago 1912', 'Chicago 1917'],
            },
            <String, dynamic>{
              'region_id': 'resolved',
              'resolved': true,
              'alternatives': <String>['Chicago 1912', 'Chicago 1917'],
            },
          ],
        ),
      );
      final Specimen specimen = await server.repository.specimen(
        scope,
        'pilot-1',
      );
      expect(
        objects(specimen.data['disagreements']).map((Json d) => d['region_id']),
        <String>['differing'],
      );
    });
  });

  group('disagreements without alternatives', () {
    test(
      'a region is judged by its readings when the list is missing',
      () async {
        final ScriptedServer server = ScriptedServer(<String, dynamic>{
          ...workspace(
            transcriptions: <Json>[
              <String, dynamic>{'region_id': 'r1', 'resolved': false},
            ],
          ),
          'observations': <Json>[
            <String, dynamic>{
              'region_id': 'r1',
              'literal_text': 'Chicago 1912',
            },
            <String, dynamic>{
              'region_id': 'r1',
              'literal_text': 'Chicago 1917',
            },
          ],
        });
        final Specimen specimen = await server.repository.specimen(
          scope,
          'pilot-1',
        );
        expect(
          objects(
            specimen.data['disagreements'],
          ).map((Json d) => d['region_id']),
          <String>['r1'],
        );
      },
    );
  });

  group('the photograph', () {
    test('a reload of the same asset reuses the bytes it has', () async {
      final ScriptedServer server = ScriptedServer(workspace());
      final Specimen first = await server.repository.specimen(scope, 'pilot-1');
      final Specimen second = await server.repository.specimen(
        scope,
        'pilot-1',
      );
      expect(server.images, 1, reason: 'the 20 second poll re-downloaded it');
      expect(
        identical(
          second.assets.single['preview_bytes'],
          first.assets.single['preview_bytes'],
        ),
        isTrue,
        reason: 'the same bytes keep the decoded image',
      );
    });

    test('a new checksum is a new photograph', () async {
      final ScriptedServer server = ScriptedServer(workspace());
      await server.repository.specimen(scope, 'pilot-1');
      server
        ..body = workspace(sha: 'b' * 64)
        ..image = <int>[4, 5, 6];
      final Specimen next = await server.repository.specimen(scope, 'pilot-1');
      expect(server.images, 2);
      expect(next.assets.single['preview_bytes'], <int>[4, 5, 6]);
    });

    test('a view derivative is keyed by its own checksum too', () async {
      Json derivativeOf(List<int> bytes) => <String, dynamic>{
        'original_sha256': firstSha,
        'derivative_sha256': crypto.sha256.convert(bytes).toString(),
      };
      final ScriptedServer server = ScriptedServer(
        workspace(derivative: derivativeOf(<int>[1, 2, 3])),
      );
      await server.repository.specimen(scope, 'pilot-1');
      await server.repository.specimen(scope, 'pilot-1');
      expect(server.images, 1);
      server
        ..body = workspace(derivative: derivativeOf(<int>[7, 8, 9]))
        ..image = <int>[7, 8, 9];
      final Specimen next = await server.repository.specimen(scope, 'pilot-1');
      expect(server.images, 2);
      expect(next.assets.single['preview_bytes'], <int>[7, 8, 9]);
      expect(next.assets.single['preview_is_derivative'], isTrue);
    });

    test('a failed download is asked for again', () async {
      final ScriptedServer server = ScriptedServer(workspace())
        ..imageStatus = 503;
      final Specimen failed = await server.repository.specimen(
        scope,
        'pilot-1',
      );
      expect(failed.assets.single['preview_bytes'], isNull);
      server.imageStatus = 200;
      final Specimen next = await server.repository.specimen(scope, 'pilot-1');
      expect(server.images, 2);
      expect(next.assets.single['preview_bytes'], <int>[1, 2, 3]);
    });

    test('a new access check starts without the photographs', () async {
      final Json wire =
          jsonDecode(
                File(
                  'test/fixtures/backend-wire-examples.json',
                ).readAsStringSync(),
              )
              as Json;
      final ScriptedServer server = _SessionServer(workspace(), wire);
      await server.repository.specimen(scope, 'pilot-1');
      await server.repository.scopes();
      await server.repository.specimen(scope, 'pilot-1');
      expect(server.images, 2);
    });
  });

  group('queue search', () {
    test('an identifier that is not a UUID asks the server nothing', () async {
      final ScriptedServer server = ScriptedServer(<String, dynamic>{
        'items': <Json>[],
      });
      for (final String key in <String>[
        'specimen_id',
        'asset_id',
        'active_run_id',
        'batch_id',
      ]) {
        final SpecimenPage page = await server.repository.specimenPage(
          scope,
          filters: <String, String>{key: 'FMNH-12'},
        );
        expect(page.items, isEmpty, reason: key);
        expect(page.nextCursor, isNull, reason: key);
      }
      expect(server.json, isEmpty, reason: 'the API answers these with 422');
    });

    test('a UUID is sent in the form the API stores', () async {
      final ScriptedServer server = ScriptedServer(<String, dynamic>{
        'items': <Json>[],
      });
      await server.repository.specimenPage(
        scope,
        filters: <String, String>{
          'specimen_id': ' {6F9619FF-8B86-D011-B42D-00CF4FC964FF} ',
        },
      );
      expect(
        server.json.single.queryParameters['specimen_id'],
        '6f9619ff-8b86-d011-b42d-00cf4fc964ff',
      );
    });
  });
}

/// A server that also answers the session and collection checks from the
/// recorded wire examples.
class _SessionServer extends ScriptedServer {
  _SessionServer(super.body, this.wire);

  final Json wire;

  @override
  Json answer(http.Request request) {
    final Json session = wire['session'] as Json;
    if (request.url.path == '/v1/session') return session;
    if (request.url.path.endsWith('/collections')) {
      return <String, dynamic>{
        'items': <Json>[
          <String, dynamic>{
            'collection_id': objects(
              session['memberships'],
            ).first['collection_id'],
            'display_name': 'Synthetic collection',
          },
        ],
      };
    }
    return body;
  }
}
