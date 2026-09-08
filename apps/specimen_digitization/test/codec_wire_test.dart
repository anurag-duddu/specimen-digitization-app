import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/source_pixels.dart';

void main() {
  final fixture =
      jsonDecode(
            File(
              'test/fixtures/backend-codec-wire-examples.json',
            ).readAsStringSync(),
          )
          as Json;
  final original = File(
    'test/fixtures/synthetic-orientation6.heic',
  ).readAsBytesSync();
  final preview = File(
    'test/fixtures/synthetic-heic-derived.png',
  ).readAsBytesSync();
  final asset = fixture['asset'] as Json;
  final completion = fixture['completion_response'] as Json;
  final scope = CollectionScope(
    organizationId: completion['organization_id'],
    collectionId: completion['collection_id'],
    name: 'Synthetic codecs',
  );
  IntakeFile input({int? width, int? height}) => IntakeFile(
    name: 'synthetic-orientation6.heic',
    bytes: original,
    mimeType: 'image/heic',
    sha256: sha256.convert(original).toString(),
    method: 'files',
    width: width,
    height: height,
  );
  test(
    'real HEIC fixture uploads without invented local dimension claims',
    () async {
      expect(
        sha256.convert(original).toString(),
        fixture['item_request']['sha256'],
      );
      var calls = 0;
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8014'),
        token: () async => 'test-only',
        client: MockClient((r) async {
          calls++;
          final body = jsonDecode(r.body) as Json;
          if (r.url.path.endsWith('/batches')) {
            return http.Response('{"batch_id":"b"}', 200);
          }
          expect(body.containsKey('width'), false);
          expect(body.containsKey('height'), false);
          expect(body['media_type'], fixture['item_request']['media_type']);
          expect(body['sha256'], asset['sha256']);
          expect(body['size_bytes'], original.length);
          return http.Response('{"upload_id":"u","state":"created"}', 200);
        }),
      );
      await expectLater(
        repo.createIntake(scope, input(width: 64), 'partial'),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'invalid_dimensions'),
        ),
      );
      expect(calls, 0);
      final result = await repo.createIntake(scope, input(), 'nullable-pair');
      expect(result['upload_id'], 'u');
      expect(calls, 2);
      await repo.createIntake(
        scope,
        input(width: 96, height: 64),
        'local-preview-dimensions',
      );
      expect(calls, 4);
    },
  );
  test(
    'codec asset keeps original identity and verifies decoded preview provenance',
    () async {
      var tamper = false;
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8014'),
        token: () async => 'test-only',
        client: MockClient((r) async {
          if (r.url.path.endsWith('/content')) {
            expect(r.url.queryParameters['view'], 'true');
            return http.Response.bytes(tamper ? [1, 2, 3] : preview, 200);
          }
          return http.Response(
            jsonEncode({
              ...completion,
              'asset': asset,
              'fields': {},
              'run': {},
            }),
            200,
          );
        }),
      );
      final specimen = await repo.specimen(scope, completion['specimen_id']);
      expect(specimen.assets.single['width'], 64);
      expect(specimen.assets.single['height'], 96);
      expect(
        specimen.assets.single['sha256'],
        sha256.convert(original).toString(),
      );
      expect(specimen.assets.single['preview_bytes'], preview);
      expect(
        specimen.assets.single['pixel_basis'],
        'decoded_heif_primary_pixel_edges',
      );
      tamper = true;
      final rejected = await repo.specimen(scope, completion['specimen_id']);
      expect(rejected.assets.single['preview_bytes'], isNull);
      expect(
        rejected.assets.single['preview_error'],
        contains('does not match retained source provenance'),
      );
    },
  );
  testWidgets('decoded HEIC basis and conversion limitations remain visible', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: SourceBasisNotice(asset: asset)),
        ),
      ),
    );
    expect(
      find.textContaining('mapping to its encoded grid is unavailable'),
      findsOneWidget,
    );
    expect(find.textContaining('pillow-heif 1.7.0'), findsOneWidget);
    expect(find.textContaining('hdr_to_rgb8'), findsOneWidget);
  });
}
