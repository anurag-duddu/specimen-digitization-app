import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import 'intake_harness.dart';
import 'widget_test.dart' show TestRepository;

const CollectionScope _scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Synthetic insects',
);

const String _owner = 'owner';
const String _filename = 'iphone-orientation-6.jpg';

class _RecordingIntakeRepository extends TestRepository {
  final List<IntakeFile> created = <IntakeFile>[];

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    created.add(file);
    return <String, dynamic>{
      'upload_id': 'upload-${created.length}',
      'state': 'uploading',
      'offset': 0,
    };
  }

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async =>
      <String, dynamic>{'upload_id': id, 'state': 'uploading', 'offset': 1};

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async => progress(1);

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => <String, dynamic>{'upload_state': 'accepted'};
}

enum _IntakeSource {
  files('chosen file', 'files'),
  manualCamera('manual camera', 'camera'),
  autoIngestCamera('auto-ingest camera', 'camera'),
  recoveredCamera('interrupted camera recovery', 'camera');

  const _IntakeSource(this.description, this.method);

  final String description;
  final String method;
}

Uint8List _orientationSixJpeg() {
  final image.Image raster = image.Image(width: 120, height: 80);
  for (var y = 0; y < raster.height; y++) {
    for (var x = 0; x < raster.width; x++) {
      raster.setPixelRgb(x, y, x * 2, y * 3, (x + y) % 256);
    }
  }
  final Uint8List jpeg = Uint8List.fromList(
    image.encodeJpg(raster, quality: 90),
  );
  final ByteData tiff = ByteData(26)
    ..setUint8(0, 0x49)
    ..setUint8(1, 0x49)
    ..setUint16(2, 42, Endian.little)
    ..setUint32(4, 8, Endian.little)
    ..setUint16(8, 1, Endian.little)
    ..setUint16(10, 0x0112, Endian.little)
    ..setUint16(12, 3, Endian.little)
    ..setUint32(14, 1, Endian.little)
    ..setUint16(18, 6, Endian.little);
  final Uint8List tiffBytes = tiff.buffer.asUint8List();
  final int app1Length = 2 + 6 + tiffBytes.lengthInBytes;
  return Uint8List.fromList(<int>[
    ...jpeg.sublist(0, 2),
    0xff,
    0xe1,
    app1Length >> 8,
    app1Length & 0xff,
    0x45,
    0x78,
    0x69,
    0x66,
    0,
    0,
    ...tiffBytes,
    ...jpeg.sublist(2),
  ]);
}

Uint8List _oversizedJpegHeader() => Uint8List.fromList(<int>[
  0xff,
  0xd8,
  0xff,
  0xc0,
  0x00,
  0x0b,
  0x08,
  0xff,
  0xff,
  0xff,
  0xff,
  0x01,
  0x01,
  0x11,
  0x00,
]);

XFile _photo(Uint8List bytes) => XFile.fromData(
  bytes,
  path: _filename,
  name: _filename,
  mimeType: 'image/jpeg',
);

Future<void> _waitFor(
  WidgetTester tester,
  bool Function() condition, {
  required String reason,
}) async {
  var finished = false;
  await tester.runAsync(() async {
    for (var attempt = 0; attempt < 200; attempt++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump();
      if (condition()) {
        finished = true;
        break;
      }
    }
  });
  expect(finished, isTrue, reason: reason);
  await tester.pumpAndSettle();
}

Future<void> _pumpIntake(
  WidgetTester tester, {
  required _IntakeSource source,
  required _RecordingIntakeRepository repository,
  required Uint8List bytes,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{
    if (source == _IntakeSource.autoIngestCamera)
      'camera-auto-ingest-v1:$_owner:${_scope.key}': true,
    if (source == _IntakeSource.recoveredCamera)
      'pending-camera-owner-v1': '$_owner:${_scope.key}',
  });
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1100, 2400);
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: IntakeScreen(
          repository: repository,
          scope: _scope,
          userId: _owner,
          onComplete: () {},
          pickImages: source == _IntakeSource.files
              ? (bool camera) async {
                  expect(camera, isFalse);
                  return <XFile>[_photo(bytes)];
                }
              : null,
          openCapture:
              source == _IntakeSource.manualCamera ||
                  source == _IntakeSource.autoIngestCamera
              ? (BuildContext _) async =>
                    CaptureResult(files: <XFile>[_photo(bytes)])
              : null,
          recoverCamera: source == _IntakeSource.recoveredCamera
              ? () async => <XFile>[_photo(bytes)]
              : null,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _selectSource(WidgetTester tester, _IntakeSource source) async {
  switch (source) {
    case _IntakeSource.files:
      await chooseFiles(tester);
    case _IntakeSource.manualCamera:
    case _IntakeSource.autoIngestCamera:
      await tester.ensureVisible(takePhotographButton);
      await tester.pumpAndSettle();
      await tester.tap(takePhotographButton);
    case _IntakeSource.recoveredCamera:
      break;
  }
  await _waitFor(
    tester,
    () => find.text(_filename).evaluate().isNotEmpty,
    reason: '${source.description} should add the rotated JPEG to Intake',
  );
}

void main() {
  for (final _IntakeSource source in _IntakeSource.values) {
    testWidgets(
      '${source.description} sends encoded JPEG dimensions and unchanged bytes',
      (WidgetTester tester) async {
        final Uint8List original = _orientationSixJpeg();
        final Uint8List snapshot = Uint8List.fromList(original);
        final _RecordingIntakeRepository repository =
            _RecordingIntakeRepository();
        await _pumpIntake(
          tester,
          source: source,
          repository: repository,
          bytes: original,
        );

        await _selectSource(tester, source);
        if (source != _IntakeSource.autoIngestCamera) {
          expect(
            repository.created,
            isEmpty,
            reason: '${source.description} must wait for explicit submission',
          );
          await submitBatch(tester);
        }
        await _waitFor(
          tester,
          () => repository.created.length == 1,
          reason: '${source.description} should reach the intake repository',
        );

        final IntakeFile submitted = repository.created.single;
        expect(submitted.method, source.method);
        expect(submitted.width, 120);
        expect(submitted.height, 80);
        expect(submitted.bytes, orderedEquals(snapshot));
        expect(original, orderedEquals(snapshot));
      },
    );
  }

  testWidgets('encoded dimensions enforce resolution limits before decode', (
    WidgetTester tester,
  ) async {
    final _RecordingIntakeRepository repository = _RecordingIntakeRepository();
    await _pumpIntake(
      tester,
      source: _IntakeSource.files,
      repository: repository,
      bytes: _oversizedJpegHeader(),
    );

    await chooseFiles(tester);

    expect(repository.created, isEmpty);
    expect(
      find.textContaining('over 40 megapixels'),
      findsOneWidget,
      reason: 'encoded raster claims must not bypass the existing local cap',
    );
    expect(uploadButton, findsNothing);
  });
}
