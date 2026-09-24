// Region boxes on the lane's records (UI.md T4).
//
// A lane run never carries `evidence_pilot`, and intake keeps an oriented
// view with its checksums (S3, 2026-09-23). So a lane record's view
// verifies and its label regions are drawn with the gate unchanged, while
// the pilot's frozen originals, whose view the server strips, keep the
// caveat.

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';

import 'widgets/harness.dart';

const CollectionScope scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'collection',
  name: 'Synthetic collection',
);

/// The original's checksum; the client compares it, never recomputes it.
final String originalSha = 'c' * 64;

/// The oriented view the server serves at `?view=true`, 1000 by 520.
final List<int> viewBytes = File(
  'test/fixtures/synthetic-wide-label.png',
).readAsBytesSync();

/// A workspace response for a record, shaped as `api.py` `workspace()`
/// serves it: a lane run's with its oriented view, or the pilot's, whose
/// view the server strips (`api.py` 369-370).
Json workspace({required bool pilot}) => <String, dynamic>{
  'specimen_id': pilot ? 'pilot-1' : 'lane-1',
  'organization_id': 'org',
  'collection_id': 'collection',
  'revision': 3,
  'record_version_id': 'run-1:3',
  'active_run_id': 'run-1',
  'status': 'completed',
  'disposition': 'needs_human_review',
  'asset': <String, dynamic>{
    'id': 'asset-1',
    'sha256': originalSha,
    'media_type': 'image/png',
    'pixel_basis': 'original_pixel_edges',
    'view_derivative': pilot
        ? null
        : <String, dynamic>{
            'original_sha256': originalSha,
            'derivative_sha256': crypto.sha256.convert(viewBytes).toString(),
            'transform': <String, dynamic>{
              'matrix': <num>[1, 0, 0, 0, 1, 0],
              'original_width': 1000,
              'view_width': 1000,
              'view_height': 520,
            },
          },
  },
  'regions': <Json>[
    <String, dynamic>{
      'region_id': 'r1',
      'bbox': <int>[40, 40, 460, 220],
      'order': 0,
      'rotation_quarter_turns': 0,
    },
  ],
  'run': <String, dynamic>{
    'dependencies': <String, dynamic>{
      if (pilot) 'evidence_pilot': <String, dynamic>{'profile': 'pilot'},
    },
  },
  'fields': <String, dynamic>{},
  'transcriptions': <Json>[],
};

/// The record the repository makes of [body], answering the view with
/// [viewBytes] and the original with a stand-in.
Future<Specimen> load(Json body) {
  final ApiSpecimenRepository repository = ApiSpecimenRepository(
    baseUrl: Uri.parse('http://localhost:8000'),
    token: () async => 'synthetic-test-token',
    appCheckToken: () async => 'synthetic-app-check',
    client: MockClient((http.Request request) async {
      if (request.url.path.endsWith('/content')) {
        return request.url.queryParameters['view'] == 'true'
            ? http.Response.bytes(viewBytes, 200)
            : http.Response.bytes(<int>[1, 2, 3], 200);
      }
      return http.Response(jsonEncode(body), 200);
    }),
  );
  addTearDown(repository.close);
  return repository.specimen(scope, textOf(body['specimen_id']));
}

void main() {
  test(
    "a lane record's oriented view verifies, so its regions are drawn",
    () async {
      final Specimen lane = await load(workspace(pilot: false));
      final Json asset = lane.assets.single;
      expect(asset['preview_is_derivative'], isTrue);
      expect(asset['preview_bytes'], viewBytes);
      expect(
        SourceOrientationCaveat.unverified(asset),
        isFalse,
        reason: 'the gate allows the label regions, unchanged',
      );
    },
  );

  test('a pilot record keeps its caveat: the server strips its view', () async {
    final Specimen pilot = await load(workspace(pilot: true));
    final Json asset = pilot.assets.single;
    expect(asset['preview_is_derivative'], isNot(isTrue));
    expect(SourceOrientationCaveat.unverified(asset), isTrue);
  });

  testWidgets('the caveat is drawn for the pilot and not for the lane', (
    WidgetTester tester,
  ) async {
    const String caveat =
        'This photograph has no verified orientation, so label regions are '
        'not drawn.';
    final Specimen lane =
        await tester.runAsync(() => load(workspace(pilot: false))) as Specimen;
    await pumpComponent(
      tester,
      SourceOrientationCaveat(asset: lane.assets.single),
    );
    expect(find.text(caveat), findsNothing);

    final Specimen pilot =
        await tester.runAsync(() => load(workspace(pilot: true))) as Specimen;
    await pumpComponent(
      tester,
      SourceOrientationCaveat(asset: pilot.assets.single),
    );
    expect(find.text(caveat), findsOneWidget);
  });
}
