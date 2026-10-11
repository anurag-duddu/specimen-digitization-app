import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widgets/harness.dart' show expectAccessible;

class _FakeCamera implements CaptureCamera {
  _FakeCamera({this.emptyCaptureMetadata = false});

  final bool emptyCaptureMetadata;
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
      frame,
      name: emptyCaptureMetadata ? '' : 'camera-${captures.length + 1}.png',
      mimeType: emptyCaptureMetadata ? '' : 'image/png',
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
    expect(find.text('Send for processing'), findsNothing);
    expect(find.text('Retake'), findsNothing);
    expect(find.text('1 photograph in this batch'), findsOne);
  });

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

    expect(find.text('Send for processing'), findsOne);
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

    await tester.tap(find.byKey(const ValueKey<String>('capture-auto-ingest')));
    await tester.pumpAndSettle();
    expect(changes, <bool>[true]);
    expect(
      find.text('Each photo is sent to the Intake queue immediately.'),
      findsOne,
    );

    await _takePhotograph(tester);
    expect(accepted, hasLength(1));
    expect(find.text('Send for processing'), findsNothing);
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
      expect(find.text('Send for processing'), findsOne);
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
      tester
          .getSemantics(
            find.byKey(const ValueKey<String>('capture-auto-ingest')),
          )
          .label,
      'Auto-ingest',
    );
    await expectAccessible(tester);

    await _takePhotograph(tester, waitForReview: true);
    expect(find.bySemanticsLabel('The photograph you took'), findsOne);
    await expectAccessible(tester);
    semantics.dispose();
  });
}
