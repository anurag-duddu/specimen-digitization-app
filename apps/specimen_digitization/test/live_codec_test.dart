import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test(
    'real HTTP HEIC intake establishes server coordinates and retains original bytes',
    () async {
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse(Platform.environment['SPECIMEN_TEST_API_BASE_URL']!),
        token: () async => Platform.environment['SPECIMEN_SYNTHETIC_TOKEN'],
        expectedMode: 'synthetic',
      );
      addTearDown(repo.close);
      final scope = (await repo.scopes()).single;
      final bytes = File(
        'test/fixtures/synthetic-orientation6.heic',
      ).readAsBytesSync();
      final file = IntakeFile(
        name: 'synthetic-orientation6.heic',
        bytes: bytes,
        mimeType: 'image/heic',
        sha256: sha256.convert(bytes).toString(),
        method: 'files',
      );
      final session = await repo.createIntake(
        scope,
        file,
        'codec-${DateTime.now().microsecondsSinceEpoch}',
      );
      if (session['state'] != 'duplicate') {
        await repo.upload(scope, session, file, (_) {});
        await repo.completeIntake(
          scope,
          session['upload_id'],
          'codec-complete-${session['upload_id']}',
        );
      }
      final id = session['duplicate_specimen_id'] ?? session['specimen_id'];
      var specimen = await repo.specimen(scope, id);
      for (var i = 0; i < 100 && specimen.disposition == null; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        specimen = await repo.specimen(scope, id);
      }
      expect(specimen.disposition, 'needs_human_review');
      final asset = specimen.assets.single;
      expect(asset['sha256'], file.sha256);
      expect(asset['width'], 64);
      expect(asset['height'], 96);
      expect(asset['pixel_basis'], 'decoded_heif_primary_pixel_edges');
      expect(asset['preview_is_derivative'], true);
      expect(
        sha256.convert(asset['preview_bytes']).toString(),
        asset['view_derivative']['derivative_sha256'],
      );
      expect(asset['processing_derivative']['original_sha256'], file.sha256);
      final transport = http.Client();
      addTearDown(transport.close);
      final originalRequest = http.Request(
        'GET',
        repo.baseUrl.replace(
          path:
              '/v1/organizations/${scope.organizationId}/assets/${asset['id']}/content',
        ),
      )..followRedirects = false;
      originalRequest.headers['Authorization'] = 'Bearer ${await repo.token()}';
      final originalResponse = await http.Response.fromStream(
        await transport.send(originalRequest),
      );
      expect(originalResponse.statusCode, 200);
      expect(originalResponse.bodyBytes, bytes);
      expect(specimen.observations.length, greaterThanOrEqualTo(2));
      // A fresh authenticated repository retrieves the same immutable source basis.
      final reopened = ApiSpecimenRepository(
        baseUrl: repo.baseUrl,
        token: repo.token,
        expectedMode: 'synthetic',
      );
      addTearDown(reopened.close);
      final restored = await reopened.specimen(scope, id);
      expect(restored.assets.single['pixel_basis'], asset['pixel_basis']);
      expect(restored.assets.single['preview_bytes'], asset['preview_bytes']);
      final bounds = List<num>.from(specimen.regions.first['bbox']);
      await repo.review(scope, specimen, {
        'kind': 'segmentation_correction',
        'regions': [
          ...specimen.regions.map((r) => {...r, 'rotation_quarter_turns': 1}),
        ],
        'reason': 'Synthetic HEIC crop quarter-turn in recorded basis',
      }, 'codec-region-${specimen.revision}');
      final changed = await repo.specimen(scope, id);
      expect(changed.regions.first['bbox'], bounds);
      expect(changed.regions.first['rotation_quarter_turns'], 1);
      expect(changed.assets.single['sha256'], file.sha256);
      // ignore: avoid_print
      print(
        'HEIC HTTP specimen=$id initial=${specimen.revision} region_revision=${changed.revision} source_basis=${asset['pixel_basis']}',
      );
    },
    skip: Platform.environment['SPECIMEN_CODEC_LIVE_TEST'] != 'true',
  );
}
