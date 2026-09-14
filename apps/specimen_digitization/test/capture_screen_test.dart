// The full-screen capture route, run against a fake camera.
//
// Neither the emulator nor CI has a camera, which is why `CaptureCamera` is an
// interface. Everything below the interface is the `camera` package and is out
// of reach of a widget test; everything above it is checked here.

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import 'widget_test.dart' show TestRepository;
import 'widgets/harness.dart';

/// A camera that answers from memory. Records what the screen asked it to do.
class FakeCaptureCamera implements CaptureCamera {
  FakeCaptureCamera({this.unavailable, this.locksFocus = true});

  /// When set, [start] refuses with this reason.
  final CaptureUnavailable? unavailable;

  /// Whether [focusAt] reports a lock. A camera that cannot lock is a fact
  /// the screen shows rather than hides.
  final bool locksFocus;

  final StreamController<CapturePreviewReading> _readings =
      StreamController<CapturePreviewReading>.broadcast();
  final List<Offset> focusPoints = <Offset>[];
  final List<XFile> taken = <XFile>[];
  bool started = false;
  bool disposed = false;

  static final Uint8List frame = File(
    'test/fixtures/synthetic-label.png',
  ).readAsBytesSync();

  @override
  Future<void> start() async {
    if (unavailable != null) throw CaptureCameraUnavailable(unavailable!);
    started = true;
  }

  @override
  bool get ready => started;

  @override
  double get aspectRatio => 1;

  @override
  Widget preview(BuildContext context) =>
      const SizedBox.expand(key: ValueKey<String>('fake-preview'));

  @override
  Stream<CapturePreviewReading> get readings => _readings.stream;

  @override
  Future<bool> focusAt(Offset point) async {
    focusPoints.add(point);
    return locksFocus;
  }

  @override
  Future<XFile> capture() async {
    final XFile file = XFile.fromData(
      frame,
      path: 'capture-${taken.length + 1}.png',
      name: 'capture-${taken.length + 1}.png',
    );
    taken.add(file);
    return file;
  }

  @override
  Future<void> dispose() async {
    disposed = true;
    await _readings.close();
  }

  /// Pushes one preview reading, as the frame stream would.
  void emit(CapturePreviewReading reading) => _readings.add(reading);
}

Future<CaptureResult?> pumpCapture(
  WidgetTester tester,
  FakeCaptureCamera camera,
) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(500, 900);
  addTearDown(tester.view.reset);
  CaptureResult? result;
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Builder(
        builder: (BuildContext context) => Scaffold(
          body: Center(
            child: ElevatedButton(
              onPressed: () async {
                result = await Navigator.of(
                  context,
                ).push(CaptureScreen.route(() async => camera));
              },
              child: const Text('Open camera'),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Open camera'));
  await tester.pumpAndSettle();
  return result;
}

Future<void> takeOne(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the viewfinder draws framing guides and an honest hint', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);

    expect(camera.started, isTrue);
    expect(find.byKey(const ValueKey<String>('fake-preview')), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('capture-framing-guides')),
      findsOneWidget,
    );
    expect(find.text(NotCalibratedChip.label), findsOneWidget);
    expect(
      find.text('Exposure is not measured on this device.'),
      findsOneWidget,
      reason: 'no reading yet is unmeasured, never a pass',
    );
    expect(
      find.text('Framing, focus and label coverage are not checked here.'),
      findsOneWidget,
    );
    expect(find.text('0 photographs in this batch'), findsOneWidget);
  });

  testWidgets('a clipped frame produces a glare hint, a clean one does not', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);

    camera.emit(
      const CapturePreviewReading(
        mean: 200,
        darkFraction: 0,
        brightFraction: 0.4,
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(
        'Bright areas are clipping. Check for glare before you capture.',
      ),
      findsOneWidget,
    );

    camera.emit(
      const CapturePreviewReading(
        mean: 120,
        darkFraction: 0,
        brightFraction: 0,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('No clipping measured in this frame.'), findsOneWidget);
    expect(find.text(NotCalibratedChip.label), findsOneWidget);
  });

  testWidgets('tapping the viewfinder locks focus and exposure at that point', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);

    final Rect viewfinder = tester.getRect(
      find.byKey(const ValueKey<String>('fake-preview')),
    );
    await tester.tapAt(viewfinder.center);
    await tester.pumpAndSettle();

    expect(camera.focusPoints, hasLength(1));
    expect(camera.focusPoints.single.dx, closeTo(0.5, 0.02));
    expect(camera.focusPoints.single.dy, closeTo(0.5, 0.02));
    expect(find.byIcon(Symbols.lock), findsOneWidget);
    expect(
      tester
          .getSemantics(
            find.byKey(const ValueKey<String>('capture-focus-mark')),
          )
          .label,
      'Focus and exposure locked',
    );
    handle.dispose();
  });

  testWidgets('a camera that cannot lock says so rather than implying a lock', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final FakeCaptureCamera camera = FakeCaptureCamera(locksFocus: false);
    await pumpCapture(tester, camera);
    await tester.tapAt(
      tester.getRect(find.byKey(const ValueKey<String>('fake-preview'))).center,
    );
    await tester.pumpAndSettle();
    expect(find.byIcon(Symbols.lock_open), findsOneWidget);
    expect(
      tester
          .getSemantics(
            find.byKey(const ValueKey<String>('capture-focus-mark')),
          )
          .label,
      'This camera did not lock focus',
    );
    handle.dispose();
  });

  testWidgets('every capture goes through a review step with Retake', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);

    await takeOne(tester);
    expect(find.text('Retake'), findsOneWidget);
    expect(find.text('Use photograph'), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('fake-preview')), findsNothing);

    await tester.tap(find.text('Retake'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey<String>('fake-preview')), findsOneWidget);
    expect(
      find.text('0 photographs in this batch'),
      findsOneWidget,
      reason: 'a retaken photograph was never in the batch',
    );
  });

  testWidgets('batch mode returns to the viewfinder after each accept', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);

    await takeOne(tester);
    await tester.tap(find.text('Use photograph'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey<String>('fake-preview')), findsOneWidget);
    expect(find.text('1 photograph in this batch'), findsOneWidget);

    await takeOne(tester);
    await tester.tap(find.text('Use photograph'));
    await tester.pumpAndSettle();
    expect(find.text('2 photographs in this batch'), findsOneWidget);
    expect(camera.taken, hasLength(2));
  });

  testWidgets(
    'Done hands back every accepted photograph and frees the camera',
    (WidgetTester tester) async {
      final FakeCaptureCamera camera = FakeCaptureCamera();
      CaptureResult? result;
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(500, 900);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Builder(
            builder: (BuildContext context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () async {
                    result = await Navigator.of(
                      context,
                    ).push(CaptureScreen.route(() async => camera));
                  },
                  child: const Text('Open camera'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open camera'));
      await tester.pumpAndSettle();

      await takeOne(tester);
      await tester.tap(find.text('Use photograph'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      expect(result, isNotNull);
      expect(result!.needsFallback, isFalse);
      expect(result!.files, hasLength(1));
      expect(camera.disposed, isTrue);
    },
  );

  testWidgets('a camera that will not start explains itself and falls back', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera(
      unavailable: CaptureUnavailable.permission,
    );
    CaptureResult? result;
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(500, 900);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (BuildContext context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () async {
                  result = await Navigator.of(
                    context,
                  ).push(CaptureScreen.route(() async => camera));
                },
                child: const Text('Open camera'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();

    expect(
      find.text(CaptureUnavailable.permission.message),
      findsOneWidget,
      reason: 'the reason is a plain sentence, never a code',
    );
    await tester.tap(find.text('Use the device camera instead'));
    await tester.pumpAndSettle();
    expect(result!.needsFallback, isTrue);
    expect(result!.unavailable, CaptureUnavailable.permission);
  });

  testWidgets(
    'accepted captures land in the same manifest a file picker fills',
    (WidgetTester tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1100, 2400);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: IntakeScreen(
              repository: TestRepository(),
              scope: const CollectionScope(
                organizationId: 'org',
                collectionId: 'insects',
                name: 'Synthetic insects',
              ),
              userId: 'owner',
              onComplete: () {},
              openCapture: (BuildContext _) async => CaptureResult(
                files: <XFile>[
                  XFile.fromData(
                    File('test/fixtures/synthetic-label.png').readAsBytesSync(),
                    path: 'from-camera.png',
                    name: 'from-camera.png',
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final Finder take = find.byKey(
        const ValueKey<String>('intake-take-photograph'),
      );
      expect(
        take,
        findsOneWidget,
        reason: 'the test platform is Android, where the camera exists',
      );
      await tester.ensureVisible(take);
      await tester.pumpAndSettle();
      await tester.runAsync(() async {
        await tester.tap(take);
        for (var attempt = 0; attempt < 200; attempt++) {
          await Future<void>.delayed(const Duration(milliseconds: 25));
          await tester.pump();
          if (find.text('from-camera.png').evaluate().isNotEmpty) break;
        }
      });
      await tester.pumpAndSettle();

      expect(find.byType(IntakeManifestRow), findsOneWidget);
      expect(find.text('from-camera.png'), findsOneWidget);
      expect(find.text('0 of 1 accepted'), findsOneWidget);
    },
  );

  group('preview readings are a histogram, never a verdict', () {
    test('a clipped highlight is named as glare, not as a failure', () {
      const CapturePreviewReading glare = CapturePreviewReading(
        mean: 220,
        darkFraction: 0,
        brightFraction: 0.3,
      );
      expect(glare.hint, contains('Check for glare'));
      expect(glare.hint, isNot(contains('fail')));
    });

    test('a crushed shadow is named as lighting', () {
      const CapturePreviewReading dark = CapturePreviewReading(
        mean: 10,
        darkFraction: 0.6,
        brightFraction: 0,
      );
      expect(dark.hint, contains('Check the lighting'));
    });

    test('a frame with nothing to say says nothing', () {
      const CapturePreviewReading clean = CapturePreviewReading(
        mean: 128,
        darkFraction: 0.01,
        brightFraction: 0.01,
      );
      expect(clean.hint, isNull);
    });

    test('a luma plane is sampled on a stride and bounded', () {
      final Uint8List plane = Uint8List(64 * 64)..fillRange(0, 64 * 64, 255);
      final CapturePreviewReading reading = CapturePreviewReading.fromPlane(
        plane,
        width: 64,
        height: 64,
      );
      expect(reading.mean, closeTo(255, 0.001));
      expect(reading.brightFraction, 1);
      expect(reading.darkFraction, 0);
    });

    test('a BGRA plane is weighted, not read as a single channel', () {
      // One white pixel, written blue, green, red, alpha.
      final Uint8List plane = Uint8List.fromList(<int>[255, 255, 255, 255]);
      final CapturePreviewReading reading = CapturePreviewReading.fromPlane(
        plane,
        width: 1,
        height: 1,
        bytesPerPixel: 4,
        bgra: true,
      );
      expect(reading.mean, closeTo(255, 0.001));
    });

    test('an impossible geometry is refused rather than guessed', () {
      expect(
        () =>
            CapturePreviewReading.fromPlane(Uint8List(4), width: 0, height: 4),
        throwsArgumentError,
      );
      expect(
        () =>
            CapturePreviewReading.fromPlane(Uint8List(0), width: 4, height: 4),
        throwsArgumentError,
      );
    });
  });

  testWidgets('the viewfinder and the review step meet the guidelines', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);
    await expectAccessible(tester);
    await takeOne(tester);
    await expectAccessible(tester);
  });
}
