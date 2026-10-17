// Platform acceptance for the native camera route. These tests use a fake
// camera because neither iOS Simulator nor the Android emulator proves a
// physical camera capture. They do prove the same Flutter screen at the four
// supported phone/tablet window classes and guard the native host contracts.

import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart' show XFile;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import 'verification/ingestion_repository_fixture.dart';

class _Target {
  const _Target(this.name, this.platform, this.size);

  final String name;
  final TargetPlatform platform;
  final Size size;
}

const List<_Target> _targets = <_Target>[
  _Target('Android phone', TargetPlatform.android, Size(412, 915)),
  _Target('Android tablet', TargetPlatform.android, Size(1280, 800)),
  _Target('iPhone', TargetPlatform.iOS, Size(390, 844)),
  _Target('iPad', TargetPlatform.iOS, Size(1194, 834)),
];

class _MatrixCamera implements CaptureCamera {
  _MatrixCamera(this.bytes, {this.unavailable});

  final Uint8List bytes;
  final CaptureUnavailable? unavailable;
  final StreamController<CapturePreviewReading> _readings =
      StreamController<CapturePreviewReading>.broadcast();

  bool started = false;
  bool disposed = false;
  int captures = 0;

  @override
  double get aspectRatio => 4 / 3;

  @override
  bool get ready => started && !disposed;

  @override
  Stream<CapturePreviewReading> get readings => _readings.stream;

  @override
  Future<void> start() async {
    if (unavailable != null) throw CaptureCameraUnavailable(unavailable!);
    started = true;
  }

  @override
  Widget preview(BuildContext context) => const ColoredBox(
    key: ValueKey<String>('platform-test-preview'),
    color: Colors.black,
  );

  @override
  Future<bool> focusAt(Offset point) async => true;

  @override
  Future<XFile> capture() async {
    captures++;
    return XFile.fromData(
      bytes,
      path: 'platform-capture-$captures.png',
      name: 'platform-capture-$captures.png',
      mimeType: 'image/png',
    );
  }

  @override
  Future<void> dispose() async {
    if (disposed) return;
    disposed = true;
    await _readings.close();
  }
}

class _PermissionPendingCamera implements CaptureCamera {
  final Completer<void> permission = Completer<void>();
  final StreamController<CapturePreviewReading> _readings =
      StreamController<CapturePreviewReading>.broadcast();

  bool disposed = false;

  @override
  double get aspectRatio => 1;

  @override
  bool get ready => false;

  @override
  Stream<CapturePreviewReading> get readings => _readings.stream;

  @override
  Future<void> start() async {
    await permission.future;
    throw const CaptureCameraUnavailable(CaptureUnavailable.permission);
  }

  @override
  Widget preview(BuildContext context) => const SizedBox.expand();

  @override
  Future<bool> focusAt(Offset point) async => false;

  @override
  Future<XFile> capture() => throw UnimplementedError();

  @override
  Future<void> dispose() async {
    if (disposed) return;
    disposed = true;
    await _readings.close();
  }
}

Uint8List _fixture() =>
    File('test/fixtures/synthetic-label.png').readAsBytesSync();

Future<void> _pumpCamera(
  WidgetTester tester, {
  required CaptureCameraFactory camera,
  bool autoIngest = false,
  ValueChanged<XFile>? onAccepted,
  bool deviceFallbackAvailable = true,
}) async {
  final ValueNotifier<CaptureActivity> activity =
      ValueNotifier<CaptureActivity>(
        const CaptureActivity(label: 'Intake queue is ready.'),
      );
  addTearDown(activity.dispose);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: CaptureScreen(
        camera: camera,
        autoIngest: autoIngest,
        onAccepted: onAccepted,
        activity: activity,
        activitySnapshot: () => activity.value,
        deviceFallbackAvailable: deviceFallbackAvailable,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _onTarget(
  WidgetTester tester,
  _Target target,
  Future<void> Function() body,
) async {
  final TargetPlatform? previous = debugDefaultTargetPlatformOverride;
  debugDefaultTargetPlatformOverride = target.platform;
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = target.size;
  try {
    await body();
  } finally {
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    debugDefaultTargetPlatformOverride = previous;
    tester.view.reset();
  }
}

Future<void> _takeAndWaitForReview(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
  await tester.pump();
  await tester.runAsync(() async {
    for (var attempt = 0; attempt < 200; attempt++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump();
      if (find
          .byKey(const ValueKey<String>('capture-send'))
          .evaluate()
          .isNotEmpty) {
        break;
      }
    }
  });
  await tester.pumpAndSettle();
}

Future<void> _waitUntil(
  WidgetTester tester,
  bool Function() condition, {
  int attempts = 200,
}) async {
  await tester.runAsync(() async {
    for (var attempt = 0; attempt < attempts && !condition(); attempt++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump();
    }
  });
  await tester.pumpAndSettle();
}

void _expectInsideWindow(WidgetTester tester, Finder finder, Size window) {
  final Rect screen = Offset.zero & window;
  final Rect control = tester.getRect(finder);
  expect(
    screen.contains(control.topLeft) && screen.contains(control.bottomRight),
    isTrue,
    reason: '$finder must remain reachable inside $window',
  );
}

void main() {
  test('Android declares an optional camera and does not request audio', () {
    final String manifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();
    expect(
      manifest,
      contains('android.permission.CAMERA'),
      reason: 'Android must be allowed to open the in-app camera.',
    );
    expect(manifest, contains('android:name="android.hardware.camera"'));
    expect(
      manifest,
      contains('android:required="false"'),
      reason: 'Devices without a camera must retain the file-picker fallback.',
    );
    expect(
      manifest,
      isNot(contains('android.permission.RECORD_AUDIO')),
      reason: 'Still-image capture initializes the camera with audio disabled.',
    );
  });

  test('iOS declares camera/photo access and supports iPhone and iPad', () {
    final String plist = File('ios/Runner/Info.plist').readAsStringSync();
    final String project = File(
      'ios/Runner.xcodeproj/project.pbxproj',
    ).readAsStringSync();
    expect(plist, contains('<key>NSCameraUsageDescription</key>'));
    expect(plist, contains('<key>NSPhotoLibraryUsageDescription</key>'));
    expect(plist, contains('<key>UISupportedInterfaceOrientations</key>'));
    expect(plist, contains('<key>UISupportedInterfaceOrientations~ipad</key>'));
    expect(
      project,
      contains('TARGETED_DEVICE_FAMILY = "1,2";'),
      reason: 'The native target must include both iPhone and iPad.',
    );
  });

  test('iOS adopts the UIScene lifecycle that iOS 27 requires at launch', () {
    final String plist = File('ios/Runner/Info.plist').readAsStringSync();
    final String delegate = File(
      'ios/Runner/AppDelegate.swift',
    ).readAsStringSync();
    expect(
      plist,
      contains('<key>UIApplicationSceneManifest</key>'),
      reason:
          'An iOS 27 SDK build without a scene manifest is killed by UIKit at '
          'launch (UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption).',
    );
    expect(plist, contains('<string>FlutterSceneDelegate</string>'));
    expect(plist, contains('<string>UIWindowScene</string>'));
    // One window scene, the Flutter one. Whitespace is collapsed so the
    // assertions do not depend on the plist's indentation.
    final String flat = plist.replaceAll(RegExp(r'\s+'), ' ');
    expect(
      flat,
      contains('<key>UIApplicationSupportsMultipleScenes</key> <false/>'),
      reason: 'Flutter does not support multiple scenes yet.',
    );
    expect(
      RegExp('<key>UISceneConfigurationName</key>').allMatches(flat),
      hasLength(1),
    );
    expect(
      flat,
      contains('<key>UISceneStoryboardFile</key> <string>Main</string>'),
    );
    expect(
      File('ios/Runner/Base.lproj/Main.storyboard').readAsStringSync(),
      contains('customClass="FlutterViewController"'),
      reason: 'The scene builds its window from the Main storyboard.',
    );
    expect(
      delegate,
      contains('FlutterImplicitEngineDelegate'),
      reason: 'Plugins must register once the scene creates the engine.',
    );
    expect(
      delegate,
      contains(
        'GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)',
      ),
    );
    expect(
      delegate,
      isNot(contains('GeneratedPluginRegistrant.register(with: self)')),
      reason:
          'Registering with the app delegate runs before the engine exists.',
    );
  });

  test('web keeps preview and still capture without unsupported controls', () {
    final String camera = File(
      'lib/src/capture/capture_camera.dart',
    ).readAsStringSync();
    expect(
      camera,
      contains('if (kIsWeb || controller == null || _streaming || _disposed)'),
      reason: 'camera_web does not support image streaming.',
    );
    expect(
      camera,
      contains('if (kIsWeb) return false;'),
      reason: 'camera_web does not support focus or exposure points.',
    );
    expect(
      camera,
      contains('return await controller.takePicture();'),
      reason: 'Web must retain the supported still-photo capture path.',
    );
  });

  testWidgets(
    'browser or desktop camera failure returns to Intake without a fake native fallback',
    (WidgetTester tester) async {
      const _Target browser = _Target(
        'browser',
        TargetPlatform.macOS,
        Size(1280, 800),
      );
      await _onTarget(tester, browser, () async {
        final _MatrixCamera camera = _MatrixCamera(
          _fixture(),
          unavailable: CaptureUnavailable.noCamera,
        );
        await _pumpCamera(
          tester,
          camera: () async => camera,
          deviceFallbackAvailable: false,
        );
        expect(find.text('Choose files'), findsOneWidget);
        expect(find.text('Use device camera'), findsNothing);
        expect(tester.takeException(), isNull);
      });
    },
  );

  for (final _Target target in _targets) {
    testWidgets('${target.name} can capture, review and send', (
      WidgetTester tester,
    ) async {
      await _onTarget(tester, target, () async {
        final _MatrixCamera camera = _MatrixCamera(_fixture());
        final List<XFile> accepted = <XFile>[];
        await _pumpCamera(
          tester,
          camera: () async => camera,
          onAccepted: accepted.add,
        );

        final Finder shutter = find.byKey(
          const ValueKey<String>('capture-shutter'),
        );
        final Finder autoIngest = find.byKey(
          const ValueKey<String>('capture-auto-ingest'),
        );
        expect(shutter.hitTestable(), findsOneWidget);
        expect(autoIngest.hitTestable(), findsOneWidget);
        expect(
          find.byKey(const ValueKey<String>('capture-intake-activity')),
          findsOneWidget,
        );
        _expectInsideWindow(tester, shutter, target.size);
        _expectInsideWindow(tester, autoIngest, target.size);

        // The native hosts advertise both orientations. Rotate the active
        // camera before capture so the review controls are proven in the
        // opposite window as well, including short phone landscapes.
        final Size rotated = Size(target.size.height, target.size.width);
        tester.view.physicalSize = rotated;
        await tester.pumpAndSettle();
        expect(shutter.hitTestable(), findsOneWidget);
        expect(autoIngest.hitTestable(), findsOneWidget);
        _expectInsideWindow(tester, shutter, rotated);
        _expectInsideWindow(tester, autoIngest, rotated);

        await _takeAndWaitForReview(tester);
        final Finder send = find.byKey(const ValueKey<String>('capture-send'));
        await tester.ensureVisible(send);
        await tester.pumpAndSettle();
        expect(send.hitTestable(), findsOneWidget);
        expect(
          find.byKey(const ValueKey<String>('capture-rotate')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey<String>('capture-crop')),
          findsOneWidget,
        );
        _expectInsideWindow(tester, send, rotated);

        await tester.tap(send);
        await tester.pumpAndSettle();
        expect(accepted, hasLength(1));
        expect(
          find.byKey(const ValueKey<String>('platform-test-preview')),
          findsOneWidget,
        );
        expect(tester.takeException(), isNull);
      });
    });

    testWidgets('${target.name} auto-ingest returns to capture immediately', (
      WidgetTester tester,
    ) async {
      await _onTarget(tester, target, () async {
        final _MatrixCamera camera = _MatrixCamera(_fixture());
        final List<XFile> accepted = <XFile>[];
        await _pumpCamera(
          tester,
          camera: () async => camera,
          autoIngest: true,
          onAccepted: accepted.add,
        );

        await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
        await tester.pumpAndSettle();
        expect(accepted, hasLength(1));
        expect(
          find.byKey(const ValueKey<String>('platform-test-preview')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey<String>('capture-send')),
          findsNothing,
        );
        expect(find.text('1'), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    });
  }

  testWidgets(
    'backgrounding releases the camera and resume creates a new one',
    (WidgetTester tester) async {
      await _onTarget(tester, _targets.first, () async {
        final List<_MatrixCamera> cameras = <_MatrixCamera>[];
        await _pumpCamera(
          tester,
          camera: () async {
            final _MatrixCamera camera = _MatrixCamera(_fixture());
            cameras.add(camera);
            return camera;
          },
        );
        expect(cameras, hasLength(1));
        expect(cameras.single.started, isTrue);

        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        await tester.pump();
        await _waitUntil(tester, () => cameras.first.disposed);
        expect(cameras.first.disposed, isTrue);

        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await tester.pump();
        await _waitUntil(tester, () => cameras.length == 2);
        expect(cameras, hasLength(2));
        expect(cameras.last.started, isTrue);
        expect(cameras.last.disposed, isFalse);
        expect(tester.takeException(), isNull);
      });
    },
  );

  testWidgets('Intake opens the camera above its shell in phone landscape', (
    WidgetTester tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final _MatrixCamera camera = _MatrixCamera(_fixture());
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(412, 915);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Column(
          children: <Widget>[
            const Text('Shell header'),
            Expanded(
              child: Navigator(
                onGenerateRoute: (RouteSettings settings) =>
                    MaterialPageRoute<void>(
                      builder: (BuildContext context) => IntakeScreen(
                        repository: PreviewRepository(),
                        scope: previewScope,
                        userId: 'owner',
                        onComplete: () {},
                        cameraFactory: () async => camera,
                      ),
                    ),
              ),
            ),
            const Text('Shell footer'),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Take photos'));
    await tester.pumpAndSettle();

    expect(find.text('Shell header'), findsNothing);
    expect(find.text('Shell footer'), findsNothing);
    tester.view.physicalSize = const Size(915, 412);
    await tester.pumpAndSettle();
    final Finder shutter = find.byKey(
      const ValueKey<String>('capture-shutter'),
    );
    expect(shutter.hitTestable(), findsOneWidget);
    _expectInsideWindow(tester, shutter, const Size(915, 412));
    expect(find.text(CaptureScreen.doneLabel).hitTestable(), findsOneWidget);

    await _takeAndWaitForReview(tester);
    final Finder send = find.byKey(const ValueKey<String>('capture-send'));
    expect(send.hitTestable(), findsOneWidget);
    await tester.tap(send);
    await _waitUntil(
      tester,
      () => find.text('1 sending').evaluate().isNotEmpty,
    );
    // PreviewRepository deliberately advances upload progress on a timer. The
    // image admission above needs real async polling, while these timers need
    // the widget test clock to move.
    for (var step = 0; step < 6; step++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    await tester.pumpAndSettle();
    expect(
      find.text('1 to fix'),
      findsOneWidget,
      reason: tester
          .widgetList<Text>(find.byType(Text))
          .map((Text text) => text.data)
          .whereType<String>()
          .where(
            (String text) => text.contains('saved') || text.contains('sending'),
          )
          .join(' | '),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'Android permission overlay does not start a second camera on resume',
    (WidgetTester tester) async {
      await _onTarget(tester, _targets.first, () async {
        final List<_PermissionPendingCamera> cameras =
            <_PermissionPendingCamera>[];
        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light(),
            home: CaptureScreen(
              camera: () async {
                final _PermissionPendingCamera camera =
                    _PermissionPendingCamera();
                cameras.add(camera);
                return camera;
              },
            ),
          ),
        );
        await tester.pump();
        expect(cameras, hasLength(1));

        // Android sends inactive/resumed while the permission controller is
        // over the activity. This must leave the original start waiting for
        // its permission result, rather than creating a second controller.
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.inactive,
        );
        await tester.pump();
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await tester.pump();
        expect(cameras, hasLength(1));
        expect(cameras.single.disposed, isFalse);

        cameras.single.permission.complete();
        await _waitUntil(
          tester,
          () => find
              .text(CaptureUnavailable.permission.message)
              .evaluate()
              .isNotEmpty,
        );
        expect(cameras, hasLength(1));
        expect(
          find.text(CaptureUnavailable.permission.message),
          findsOneWidget,
        );
        expect(find.text('Use device camera'), findsNothing);
        expect(find.text('Choose files'), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    },
  );
}
