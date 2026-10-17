import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widgets/harness.dart' show expectAccessible;

class _FakeCamera implements CaptureCamera {
  _FakeCamera({
    this.emptyCaptureMetadata = false,
    Uint8List? captureBytes,
    this.captureName,
    this.captureMimeType,
  }) : captureBytes = captureBytes ?? frame;

  final bool emptyCaptureMetadata;
  final Uint8List captureBytes;
  final String? captureName;
  final String? captureMimeType;
  final StreamController<CapturePreviewReading> _readings =
      StreamController<CapturePreviewReading>.broadcast();
  final List<XFile> captures = <XFile>[];
  bool started = false;

  static final Uint8List frame = File(
    'test/fixtures/synthetic-label.png',
  ).readAsBytesSync();

  @override
  double get aspectRatio => 1;

  @override
  bool get ready => started;

  @override
  Stream<CapturePreviewReading> get readings => _readings.stream;

  @override
  Future<XFile> capture() async {
    final XFile file = XFile.fromData(
      captureBytes,
      name: emptyCaptureMetadata
          ? ''
          : captureName ?? 'camera-${captures.length + 1}.png',
      mimeType: emptyCaptureMetadata ? '' : captureMimeType ?? 'image/png',
    );
    captures.add(file);
    return file;
  }

  @override
  Future<void> dispose() async => _readings.close();

  @override
  Future<bool> focusAt(Offset point) async => true;

  @override
  Widget preview(BuildContext context) =>
      const SizedBox.expand(key: ValueKey<String>('fake-camera-preview'));

  @override
  Future<void> start() async => started = true;
}

({Uint8List bytes, int orientationOffset}) _jpegWithZeroOrientation() {
  final Uint8List jpeg = Uint8List.fromList(
    image.encodeJpg(image.Image(width: 3, height: 2), quality: 90),
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
    ..setUint16(18, 0, Endian.little);
  final Uint8List tiffBytes = tiff.buffer.asUint8List();
  final int app1Length = 2 + 6 + tiffBytes.lengthInBytes;
  final Uint8List bytes = Uint8List.fromList(<int>[
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
  return (bytes: bytes, orientationOffset: 30);
}

Future<void> _pumpCamera(
  WidgetTester tester, {
  required _FakeCamera camera,
  bool autoIngest = false,
  ValueChanged<XFile>? onAccepted,
  ValueChanged<bool>? onAutoIngestChanged,
  Listenable? activity,
  CaptureActivity Function()? activitySnapshot,
  Size size = const Size(390, 844),
  double textScale = 1,
  TargetPlatform platform = TargetPlatform.android,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light().copyWith(platform: platform),
      home: CaptureScreen(
        camera: () async => camera,
        autoIngest: autoIngest,
        onAccepted: onAccepted,
        onAutoIngestChanged: onAutoIngestChanged,
        activity: activity,
        activitySnapshot: activitySnapshot,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _takePhotograph(
  WidgetTester tester, {
  bool waitForReview = false,
}) async {
  await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
  await tester.pump();
  if (waitForReview) {
    // Image dimensions are decoded off the UI isolate. `pumpAndSettle` only
    // observes Flutter frames, so wait for that real asynchronous work before
    // asserting the review surface.
    await tester.runAsync(() async {
      for (var attempt = 0; attempt < 200; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
        await tester.pump();
        if (find
                .byKey(const ValueKey<String>('capture-send'))
                .evaluate()
                .isNotEmpty ||
            find
                .text(CaptureUnavailable.failed.message)
                .evaluate()
                .isNotEmpty) {
          break;
        }
      }
    });
  }
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('auto-ingest sends a capture without opening review', (
    WidgetTester tester,
  ) async {
    final _FakeCamera camera = _FakeCamera();
    final List<XFile> accepted = <XFile>[];
    await _pumpCamera(
      tester,
      camera: camera,
      autoIngest: true,
      onAccepted: accepted.add,
    );

    await _takePhotograph(tester);

    expect(accepted, hasLength(1));
    expect(find.byKey(const ValueKey<String>('fake-camera-preview')), findsOne);
    expect(find.text('Send'), findsNothing);
    expect(find.text('Retake'), findsNothing);
    expect(find.text('1'), findsOne);
  });

  for (final bool autoIngest in <bool>[true, false]) {
    testWidgets(
      '${autoIngest ? 'auto-ingest' : 'manual send'} repairs camera EXIF zero without changing pixels',
      (WidgetTester tester) async {
        final capture = _jpegWithZeroOrientation();
        final _FakeCamera camera = _FakeCamera(
          captureBytes: capture.bytes,
          captureName: 'camera.jpg',
          captureMimeType: 'image/jpeg',
        );
        final List<XFile> accepted = <XFile>[];
        await _pumpCamera(
          tester,
          camera: camera,
          autoIngest: autoIngest,
          onAccepted: accepted.add,
        );

        await _takePhotograph(tester, waitForReview: !autoIngest);
        if (!autoIngest) {
          await tester.tap(find.byKey(const ValueKey<String>('capture-send')));
          await tester.pumpAndSettle();
        }

        expect(accepted, hasLength(1));
        final Uint8List submitted = await accepted.single.readAsBytes();
        final Uint8List original = await camera.captures.single.readAsBytes();
        expect(original[capture.orientationOffset], 0);
        expect(submitted[capture.orientationOffset], 1);
        expect(
          <int>[
            for (int index = 0; index < original.lengthInBytes; index++)
              if (original[index] != submitted[index]) index,
          ],
          <int>[capture.orientationOffset],
        );
        final image.Image originalPixels = image.decodeImage(original)!;
        final image.Image submittedPixels = image.decodeImage(submitted)!;
        expect(submittedPixels.width, originalPixels.width);
        expect(submittedPixels.height, originalPixels.height);
        expect(
          submittedPixels.getBytes(order: image.ChannelOrder.rgba),
          orderedEquals(
            originalPixels.getBytes(order: image.ChannelOrder.rgba),
          ),
        );
      },
    );
  }

  testWidgets('auto-ingest names a web capture with empty metadata', (
    WidgetTester tester,
  ) async {
    final _FakeCamera camera = _FakeCamera(emptyCaptureMetadata: true);
    final List<XFile> accepted = <XFile>[];
    await _pumpCamera(
      tester,
      camera: camera,
      autoIngest: true,
      onAccepted: accepted.add,
    );

    await _takePhotograph(tester);

    expect(accepted, hasLength(1));
    expect(accepted.single.name, 'camera-photo-1.png');
    expect(accepted.single.mimeType, 'image/png');
    expect(await accepted.single.readAsBytes(), _FakeCamera.frame);
  });

  testWidgets('manual mode offers review and editing before submission', (
    WidgetTester tester,
  ) async {
    final _FakeCamera camera = _FakeCamera();
    final List<XFile> accepted = <XFile>[];
    await _pumpCamera(tester, camera: camera, onAccepted: accepted.add);

    await _takePhotograph(tester, waitForReview: true);

    expect(find.text('Send'), findsOne);
    expect(find.text('Retake'), findsOne);
    expect(find.text('Rotate'), findsOne);
    expect(find.text('Crop'), findsOne);
    expect(accepted, isEmpty);

    await tester.tap(find.byKey(const ValueKey<String>('capture-send')));
    await tester.pumpAndSettle();
    expect(accepted, hasLength(1));
    expect(find.byKey(const ValueKey<String>('fake-camera-preview')), findsOne);
  });

  testWidgets('unedited manual send names a web capture with empty metadata', (
    WidgetTester tester,
  ) async {
    final _FakeCamera camera = _FakeCamera(emptyCaptureMetadata: true);
    final List<XFile> accepted = <XFile>[];
    await _pumpCamera(tester, camera: camera, onAccepted: accepted.add);

    await _takePhotograph(tester, waitForReview: true);
    await tester.tap(find.byKey(const ValueKey<String>('capture-send')));
    await tester.pumpAndSettle();

    expect(accepted, hasLength(1));
    expect(accepted.single.name, 'camera-photo-1.png');
    expect(accepted.single.mimeType, 'image/png');
    expect(await accepted.single.readAsBytes(), _FakeCamera.frame);
  });

  testWidgets('the camera toggle changes which capture path is used', (
    WidgetTester tester,
  ) async {
    final _FakeCamera camera = _FakeCamera();
    final List<XFile> accepted = <XFile>[];
    final List<bool> changes = <bool>[];
    await _pumpCamera(
      tester,
      camera: camera,
      onAccepted: accepted.add,
      onAutoIngestChanged: changes.add,
    );

    await tester.tap(find.text('Send now'));
    await tester.pumpAndSettle();
    expect(changes, <bool>[true]);
    expect(
      find.text('Camera photos skip review and send as soon as you take them.'),
      findsNothing,
    );

    await _takePhotograph(tester);
    expect(accepted, hasLength(1));
    expect(find.text('Send'), findsNothing);
  });

  testWidgets('Intake activity stays visible and updates while capturing', (
    WidgetTester tester,
  ) async {
    final _FakeCamera camera = _FakeCamera();
    final ChangeNotifier activity = ChangeNotifier();
    addTearDown(activity.dispose);
    CaptureActivity current = const CaptureActivity(
      label: 'Intake queue · Uploading 1 of 2',
      progress: 0.25,
    );
    await _pumpCamera(
      tester,
      camera: camera,
      autoIngest: true,
      activity: activity,
      activitySnapshot: () => current,
    );

    expect(
      find.byKey(const ValueKey<String>('capture-intake-activity')),
      findsOne,
    );
    expect(find.text('Intake queue · Uploading 1 of 2'), findsOne);
    final UiProgress progress = tester.widget<UiProgress>(
      find.byType(UiProgress),
    );
    expect(progress.value, 0.25);

    current = const CaptureActivity(
      label: 'Intake queue · 1 needs attention',
      problem: true,
    );
    activity.notifyListeners();
    await tester.pump();
    expect(find.text('Intake queue · 1 needs attention'), findsOne);
    expect(find.byType(UiProgress), findsNothing);
  });

  for (final (String name, Size size, TargetPlatform platform)
      in <(String, Size, TargetPlatform)>[
        ('iPhone-sized', const Size(390, 844), TargetPlatform.iOS),
        (
          'Android-tablet-sized',
          const Size(1024, 1366),
          TargetPlatform.android,
        ),
      ]) {
    testWidgets('$name viewfinder and review fit at 200 percent text', (
      WidgetTester tester,
    ) async {
      final _FakeCamera camera = _FakeCamera();
      await _pumpCamera(
        tester,
        camera: camera,
        size: size,
        textScale: 2,
        platform: platform,
      );

      expect(tester.takeException(), isNull);
      expect(
        find.byKey(const ValueKey<String>('capture-shutter')).hitTestable(),
        findsOne,
      );
      await _takePhotograph(tester, waitForReview: true);
      expect(tester.takeException(), isNull);
      expect(find.text('Send'), findsOne);
      expect(find.text('Retake'), findsOne);
    });
  }

  testWidgets('camera controls have labels and platform-sized tap targets', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    final _FakeCamera camera = _FakeCamera();
    await _pumpCamera(tester, camera: camera);

    expect(find.bySemanticsLabel(CaptureScreen.shutterLabel), findsOne);
    expect(find.bySemanticsLabel(CaptureScreen.closeLabel), findsOne);
    expect(
      tester.getSemantics(find.bySemanticsLabel('Review')).label,
      'Review',
    );
    await expectAccessible(tester);

    await _takePhotograph(tester, waitForReview: true);
    expect(find.bySemanticsLabel('The photo you took'), findsOne);
    await expectAccessible(tester);
    semantics.dispose();
  });
}
