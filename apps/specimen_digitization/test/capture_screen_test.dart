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
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/not_calibrated_chip.dart';

import 'widget_test.dart' show TestRepository;
import 'widgets/harness.dart';

class CaptureIntakeRepository extends TestRepository {
  final List<IntakeFile> captured = <IntakeFile>[];

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    captured.add(file);
    return <String, dynamic>{
      'upload_id': 'capture-upload',
      'state': 'uploading',
    };
  }

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async =>
      <String, dynamic>{'upload_id': id, 'state': 'uploading'};
}

/// A camera that answers from memory. Records what the screen asked it to do.
class FakeCaptureCamera implements CaptureCamera {
  FakeCaptureCamera({
    this.unavailable,
    this.locksFocus = true,
    Uint8List? captureBytes,
  }) : captureBytes = captureBytes ?? frame;

  /// When set, [start] refuses with this reason.
  final CaptureUnavailable? unavailable;

  /// Whether [focusAt] reports a lock. A camera that cannot lock is a fact
  /// the screen shows rather than hides.
  final bool locksFocus;

  final Uint8List captureBytes;

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
      captureBytes,
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

/// A camera whose capture and disposal can be held across lifecycle changes.
class ControlledCaptureCamera implements CaptureCamera {
  ControlledCaptureCamera({this.startGate, this.captureGate, this.disposeGate});

  final Completer<void>? startGate;
  final Completer<XFile>? captureGate;
  final Completer<void>? disposeGate;
  final StreamController<CapturePreviewReading> _readings =
      StreamController<CapturePreviewReading>.broadcast();
  bool started = false;
  bool disposeStarted = false;
  bool disposed = false;
  int disposeCalls = 0;
  int captureCalls = 0;

  @override
  double get aspectRatio => 1;

  @override
  bool get ready => started && !disposed;

  @override
  Stream<CapturePreviewReading> get readings => _readings.stream;

  @override
  Future<XFile> capture() async {
    captureCalls++;
    return captureGate?.future ??
        XFile.fromData(
          FakeCaptureCamera.frame,
          path: 'controlled-capture.png',
          name: 'controlled-capture.png',
        );
  }

  @override
  Future<void> dispose() async {
    disposeCalls++;
    disposeStarted = true;
    await disposeGate?.future;
    if (disposed) return;
    disposed = true;
    await _readings.close();
  }

  @override
  Future<bool> focusAt(Offset point) async => true;

  @override
  Widget preview(BuildContext context) =>
      const SizedBox.expand(key: ValueKey<String>('controlled-preview'));

  @override
  Future<void> start() async {
    await startGate?.future;
    started = true;
  }
}

Future<CaptureResult?> pumpCapture(
  WidgetTester tester,
  CaptureCamera camera,
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
  await tester.pump();
  await tester.runAsync(() async {
    for (var attempt = 0; attempt < 200; attempt++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump();
      if (find
              .byKey(const ValueKey<String>('capture-send'))
              .evaluate()
              .isNotEmpty ||
          find.text(CaptureUnavailable.failed.message).evaluate().isNotEmpty ||
          find
              .text(
                'The photograph could not be read. Take it again, or return to Intake and choose the file.',
              )
              .evaluate()
              .isNotEmpty) {
        break;
      }
    }
  });
  await tester.pumpAndSettle();
}

Future<void> waitForCameraCondition(
  WidgetTester tester,
  bool Function() condition,
) async {
  await tester.runAsync(() async {
    for (var attempt = 0; attempt < 200 && !condition(); attempt++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump();
    }
  });
  await tester.pump();
}

void main() {
  testWidgets(
    'crop controls move the frame without dragging and cancel keeps pixels',
    (tester) async {
      final camera = FakeCaptureCamera();
      final semantics = tester.ensureSemantics();
      await pumpCapture(tester, camera);
      await takeOne(tester);
      await tester.tap(find.byKey(const ValueKey('capture-crop')));
      await tester.pumpAndSettle();
      final move = find.byWidgetPredicate(
        (widget) => widget is UiButton && widget.label == 'Move left',
      );
      await tester.ensureVisible(move);
      await tester.tap(move);
      await tester.pumpAndSettle();
      final crop = find.bySemanticsLabel(RegExp('Crop selection\\.'));
      expect(tester.getSemantics(crop).value, startsWith('Left 4 percent'));
      final cancel = find.byWidgetPredicate(
        (widget) => widget is UiButton && widget.label == 'Cancel crop',
      );
      await tester.ensureVisible(cancel);
      await tester.tap(cancel);
      await tester.pumpAndSettle();
      final image = tester.widget<Image>(find.byType(Image));
      expect((image.image as MemoryImage).bytes, camera.captureBytes);
      expect(find.byKey(const ValueKey('capture-send')), findsOneWidget);
      expect(tester.takeException(), isNull);
      semantics.dispose();
    },
  );

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
    expect(find.byIcon(UiIcons.locked.defaultGlyph), findsOneWidget);
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
    expect(find.byIcon(UiIcons.unlocked.defaultGlyph), findsOneWidget);
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
    expect(find.text('Send for processing'), findsOneWidget);
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

  testWidgets('an unreadable photo stays in the camera with a useful message', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera(
      captureBytes: Uint8List.fromList(<int>[1, 2, 3]),
    );
    await pumpCapture(tester, camera);

    await takeOne(tester);

    expect(find.byKey(const ValueKey<String>('fake-preview')), findsOneWidget);
    expect(
      find.text(
        'The photograph could not be read. Take it again, or return to Intake and choose the file.',
      ),
      findsOneWidget,
    );
    expect(find.text(CaptureUnavailable.failed.message), findsNothing);
  });

  testWidgets('batch mode returns to the viewfinder after each accept', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);

    await takeOne(tester);
    await tester.tap(find.text('Send for processing'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey<String>('fake-preview')), findsOneWidget);
    expect(find.text('1 photograph in this batch'), findsOneWidget);

    await takeOne(tester);
    await tester.tap(find.text('Send for processing'));
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
      await tester.tap(find.text('Send for processing'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      expect(result, isNotNull);
      expect(result!.needsFallback, isFalse);
      expect(result!.files, hasLength(1));
      await waitForCameraCondition(tester, () => camera.disposed);
      expect(camera.disposed, isTrue);
    },
  );

  testWidgets('closing during auto-ingest capture does not accept late bytes', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    final Completer<XFile> captureGate = Completer<XFile>();
    final ControlledCaptureCamera camera = ControlledCaptureCamera(
      captureGate: captureGate,
    );
    final List<XFile> accepted = <XFile>[];
    CaptureResult? result;
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(500, 900);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (BuildContext context) => Scaffold(
            body: ElevatedButton(
              onPressed: () async {
                result = await Navigator.of(context).push(
                  CaptureScreen.route(
                    () async => camera,
                    autoIngest: true,
                    onAccepted: accepted.add,
                  ),
                );
              },
              child: const Text('Open camera'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
    await tester.pump();

    await tester.tap(find.bySemanticsLabel(CaptureScreen.closeLabel));
    await tester.pumpAndSettle();
    expect(result?.streamed, isTrue);

    captureGate.complete(
      XFile.fromData(
        FakeCaptureCamera.frame,
        path: 'late-capture.png',
        name: 'late-capture.png',
      ),
    );
    await waitForCameraCondition(tester, () => camera.disposed);
    expect(accepted, isEmpty);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets('streamed captures are counted without being returned again', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera camera = FakeCaptureCamera();
    final List<XFile> accepted = <XFile>[];
    CaptureResult? result;
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(500, 900);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (BuildContext context) => Scaffold(
            body: ElevatedButton(
              onPressed: () async {
                result = await Navigator.of(context).push(
                  CaptureScreen.route(
                    () async => camera,
                    autoIngest: true,
                    onAccepted: accepted.add,
                  ),
                );
              },
              child: const Text('Open camera'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
    await tester.pumpAndSettle();
    expect(find.text('1 photograph in this batch'), findsOneWidget);
    await tester.tap(find.text(CaptureScreen.doneLabel));
    await tester.pumpAndSettle();

    expect(accepted, hasLength(1));
    expect(result?.streamed, isTrue);
    expect(result?.files, isEmpty);
  });

  testWidgets('an unsent review stays visible across a failed resume', (
    WidgetTester tester,
  ) async {
    final FakeCaptureCamera first = FakeCaptureCamera();
    final FakeCaptureCamera failedResume = FakeCaptureCamera(
      unavailable: CaptureUnavailable.failed,
    );
    var factories = 0;
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(500, 900);
    addTearDown(tester.view.reset);
    addTearDown(
      () => tester.binding.handleAppLifecycleStateChanged(
        AppLifecycleState.resumed,
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: CaptureScreen(
          camera: () async => factories++ == 0 ? first : failedResume,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await takeOne(tester);
    expect(find.text('Send for processing'), findsOneWidget);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await waitForCameraCondition(tester, () => first.disposed);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await waitForCameraCondition(tester, () => factories == 2);
    await tester.pumpAndSettle();

    expect(failedResume.disposed, isTrue);
    expect(find.text('Send for processing'), findsOneWidget);
    expect(find.text('Retake'), findsOneWidget);
    expect(find.text(CaptureUnavailable.failed.message), findsNothing);
  });

  testWidgets('rebuilding during camera disposal never draws a stale preview', (
    WidgetTester tester,
  ) async {
    final Completer<void> disposeGate = Completer<void>();
    final ControlledCaptureCamera camera = ControlledCaptureCamera(
      disposeGate: disposeGate,
    );
    await pumpCapture(tester, camera);
    addTearDown(() {
      if (!disposeGate.isCompleted) disposeGate.complete();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    });

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await waitForCameraCondition(tester, () => camera.disposeStarted);
    tester.view.physicalSize = const Size(520, 900);
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('controlled-preview')), findsNothing);
    expect(find.byKey(const ValueKey('capture-shutter')), findsNothing);
    disposeGate.complete();
    await waitForCameraCondition(tester, () => camera.disposed);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('retaking a suspended review waits for a current camera', (
    WidgetTester tester,
  ) async {
    final ControlledCaptureCamera camera = ControlledCaptureCamera();
    await pumpCapture(tester, camera);
    addTearDown(
      () => tester.binding.handleAppLifecycleStateChanged(
        AppLifecycleState.resumed,
      ),
    );
    await takeOne(tester);
    final Uint8List before =
        (tester.widget<Image>(find.byType(Image)).image as MemoryImage).bytes;
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await waitForCameraCondition(tester, () => camera.disposed);
    expect(
      (tester.widget<Image>(find.byType(Image)).image as MemoryImage).bytes,
      orderedEquals(before),
    );

    await tester.tap(find.text('Retake'));
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('capture-shutter')), findsNothing);
    expect(find.byKey(const ValueKey('controlled-preview')), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('resume waits for the previous controller to finish disposing', (
    WidgetTester tester,
  ) async {
    final Completer<void> disposeGate = Completer<void>();
    final ControlledCaptureCamera first = ControlledCaptureCamera(
      disposeGate: disposeGate,
    );
    final ControlledCaptureCamera second = ControlledCaptureCamera();
    var factories = 0;
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(500, 900);
    addTearDown(tester.view.reset);
    addTearDown(
      () => tester.binding.handleAppLifecycleStateChanged(
        AppLifecycleState.resumed,
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: CaptureScreen(
          camera: () async => factories++ == 0 ? first : second,
        ),
      ),
    );
    await tester.pumpAndSettle();

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await waitForCameraCondition(tester, () => first.disposeStarted);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump(const Duration(milliseconds: 100));
    expect(factories, 1);
    expect(second.started, isFalse);

    disposeGate.complete();
    await waitForCameraCondition(tester, () => second.started);
    expect(factories, 2);
    expect(first.disposed, isTrue);
  });

  testWidgets('a late camera factory cannot start after route disposal', (
    WidgetTester tester,
  ) async {
    final Completer<CaptureCamera> factoryGate = Completer<CaptureCamera>();
    final ControlledCaptureCamera camera = ControlledCaptureCamera();
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: CaptureScreen(camera: () => factoryGate.future),
      ),
    );
    await tester.pump();
    expect(find.byKey(const ValueKey('capture-shutter')), findsNothing);

    await tester.pumpWidget(const SizedBox.shrink());
    factoryGate.complete(camera);
    await waitForCameraCondition(tester, () => camera.disposed);

    expect(camera.started, isFalse);
    expect(camera.disposeCalls, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('late initialization releases its camera once after route pop', (
    WidgetTester tester,
  ) async {
    final Completer<void> startGate = Completer<void>();
    final ControlledCaptureCamera camera = ControlledCaptureCamera(
      startGate: startGate,
    );
    final GlobalKey<NavigatorState> navigator = GlobalKey<NavigatorState>();
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigator,
        theme: AppTheme.light(),
        home: const SizedBox.shrink(),
      ),
    );
    final Future<CaptureResult?> result = navigator.currentState!.push(
      CaptureScreen.route(() async => camera),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(camera.started, isFalse);
    expect(find.byKey(const ValueKey('capture-shutter')), findsNothing);

    navigator.currentState!.pop();
    await tester.pumpAndSettle();
    expect(await result, isNull);
    startGate.complete();
    await waitForCameraCondition(tester, () => camera.disposed);

    expect(camera.disposeCalls, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a late capture failure cannot replace a resumed camera', (
    WidgetTester tester,
  ) async {
    final Completer<XFile> captureGate = Completer<XFile>();
    final ControlledCaptureCamera first = ControlledCaptureCamera(
      captureGate: captureGate,
    );
    final ControlledCaptureCamera second = ControlledCaptureCamera();
    var factories = 0;
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(500, 900);
    addTearDown(tester.view.reset);
    addTearDown(
      () => tester.binding.handleAppLifecycleStateChanged(
        AppLifecycleState.resumed,
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: CaptureScreen(
          camera: () async => factories++ == 0 ? first : second,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('capture-shutter')));
    await tester.pump();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await waitForCameraCondition(tester, () => first.disposed);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await waitForCameraCondition(tester, () => second.started);

    captureGate.completeError(
      const CaptureCameraUnavailable(CaptureUnavailable.permission),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('controlled-preview')), findsOneWidget);
    expect(find.text(CaptureUnavailable.permission.message), findsNothing);
    expect(second.disposeCalls, 0);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final bool autoIngest in [false, true]) {
    testWidgets(
      'late capture leaves the next ${autoIngest ? 'automatic' : 'manual'} capture in control',
      (WidgetTester tester) async {
        final Completer<XFile> firstCapture = Completer<XFile>();
        final Completer<XFile> secondCapture = Completer<XFile>();
        final ControlledCaptureCamera first = ControlledCaptureCamera(
          captureGate: firstCapture,
        );
        final ControlledCaptureCamera second = ControlledCaptureCamera(
          captureGate: secondCapture,
        );
        final List<XFile> accepted = [];
        var factories = 0;
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = const Size(500, 900);
        addTearDown(tester.view.reset);
        addTearDown(
          () => tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.resumed,
          ),
        );
        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light(),
            home: CaptureScreen(
              camera: () async => factories++ == 0 ? first : second,
              autoIngest: autoIngest,
              onAccepted: accepted.add,
            ),
          ),
        );
        await tester.pumpAndSettle();
        final Finder shutter = find.byKey(const ValueKey('capture-shutter'));
        await tester.tap(shutter);
        await tester.pump();
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        await waitForCameraCondition(tester, () => first.disposed);
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await waitForCameraCondition(tester, () => second.started);
        await tester.tap(shutter);
        await tester.pump();
        expect(second.captureCalls, 1);

        firstCapture.complete(
          XFile.fromData(
            FakeCaptureCamera.frame,
            path: 'stale.png',
            name: 'stale.png',
          ),
        );
        await tester.pumpAndSettle();
        expect(accepted, isEmpty);
        expect(find.text('Send for processing'), findsNothing);
        await tester.tap(shutter);
        await tester.pump();
        expect(second.captureCalls, 1);

        secondCapture.complete(
          XFile.fromData(
            FakeCaptureCamera.frame,
            path: 'current.png',
            name: 'current.png',
          ),
        );
        if (autoIngest) {
          await waitForCameraCondition(tester, () => accepted.isNotEmpty);
        } else {
          await waitForCameraCondition(
            tester,
            () => find.text('Send for processing').evaluate().isNotEmpty,
          );
          expect(accepted, isEmpty);
          await tester.tap(find.text('Send for processing'));
          await tester.pump();
        }
        expect(accepted, hasLength(1));
        expect(accepted.single.name, 'current.png');
        expect(first.disposeCalls, 1);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      },
    );
  }

  testWidgets('a camera that will not start returns cleanly to Intake', (
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
    expect(find.text('Use device camera'), findsNothing);
    expect(find.text('Back to Intake'), findsOneWidget);
    await tester.tap(find.text('Back to Intake'));
    await tester.pumpAndSettle();
    expect(result!.needsFallback, isFalse);
    expect(result!.unavailable, isNull);
  });

  testWidgets(
    'camera opt-in and return to manual mode persist across reopening Intake',
    (WidgetTester tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(700, 1000);
      addTearDown(tester.view.reset);
      final CaptureIntakeRepository repository = CaptureIntakeRepository();
      final List<FakeCaptureCamera> cameras = [];
      Widget intake() => MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: IntakeScreen(
            repository: repository,
            scope: const CollectionScope(
              organizationId: 'org',
              collectionId: 'insects',
              name: 'Synthetic insects',
            ),
            userId: 'owner',
            onComplete: () {},
            cameraFactory: () async {
              final FakeCaptureCamera camera = FakeCaptureCamera();
              cameras.add(camera);
              return camera;
            },
          ),
        ),
      );
      Future<void> openCamera() async {
        final Finder take = find.byKey(
          const ValueKey('intake-take-photograph'),
        );
        await tester.ensureVisible(take);
        await tester.tap(take);
        await tester.pumpAndSettle();
      }

      final Finder toggle = find.descendant(
        of: find.byType(CaptureScreen),
        matching: find.byKey(const ValueKey('capture-auto-ingest')),
      );
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      const String preference = 'camera-auto-ingest-v1:owner:org/insects';

      await tester.pumpWidget(intake());
      await tester.pumpAndSettle();
      await openCamera();
      expect(tester.widget<UiSwitch>(toggle).value, isFalse);
      for (final bool enabled in [true, false]) {
        await tester.tap(toggle);
        await tester.pumpAndSettle();
        expect(prefs.getBool(preference), enabled);
        await tester.tap(find.text(CaptureScreen.doneLabel));
        await tester.pumpAndSettle();
        expect(find.byType(CaptureScreen), findsNothing);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pumpWidget(intake());
        await tester.pumpAndSettle();
        await openCamera();
        expect(tester.widget<UiSwitch>(toggle).value, enabled);
      }
      await tester.tap(find.text(CaptureScreen.doneLabel));
      await tester.pumpAndSettle();
      expect(cameras, hasLength(3));
      await waitForCameraCondition(
        tester,
        () => cameras.every((camera) => camera.disposed),
      );
      expect(cameras.every((camera) => camera.disposed), isTrue);
      expect(repository.captured, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'accepted captures land in the same manifest a file picker fills',
    (WidgetTester tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'camera-auto-ingest-v1:owner:org/insects': true,
      });
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1100, 2400);
      addTearDown(tester.view.reset);
      final repository = CaptureIntakeRepository();
      var completed = 0;
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: IntakeScreen(
              repository: repository,
              scope: const CollectionScope(
                organizationId: 'org',
                collectionId: 'insects',
                name: 'Synthetic insects',
              ),
              userId: 'owner',
              onComplete: () => completed++,
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
      // Accepting a camera photograph releases it to continuous Intake.
      expect(repository.captured, hasLength(1));
      expect(repository.captured.single.method, 'camera');
      expect(repository.captured.single.sensitive, isTrue);
      expect(
        completed,
        1,
        reason: 'upload completion preserves the existing refresh contract',
      );
      expect(find.text('Waiting to start'), findsOneWidget);
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

  testWidgets('the viewfinder and the review step lay out at 200 percent '
      'text in a compact window', (WidgetTester tester) async {
    // The promise the control contract makes is 200 percent, and the camera
    // is where it costs the most: the shutter, the counter and the two
    // review actions share one narrow window.
    final List<String> errors = <String>[];
    final void Function(FlutterErrorDetails)? previous = FlutterError.onError;
    FlutterError.onError = (FlutterErrorDetails details) =>
        errors.add(details.exceptionAsString());
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    addTearDown(() => FlutterError.onError = previous);

    final FakeCaptureCamera camera = FakeCaptureCamera();
    await pumpCapture(tester, camera);
    await takeOne(tester);

    FlutterError.onError = previous;
    expect(errors, isEmpty, reason: 'the capture route at 200 percent text');
    expect(tester.takeException(), isNull);
    expect(find.text('Send for processing'), findsOneWidget);
    expect(find.text('Retake'), findsOneWidget);
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
