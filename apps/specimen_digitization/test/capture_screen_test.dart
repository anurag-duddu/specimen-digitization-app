// The full-screen capture route, run against a fake camera.
//
// Neither the emulator nor CI has a camera, which is why `CaptureCamera` is an
// interface. Everything below the interface is the `camera` package and is out
// of reach of a widget test; everything above it is checked here.

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show MethodChannel;
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
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

const _admissionScope = CollectionScope(
  organizationId: 'org',
  collectionId: 'admission',
  name: 'Test collection',
);
const _admissionOwner = 'camera-admission-test';
const _admissionPreference =
    'camera-auto-ingest-v1:$_admissionOwner:org/admission';

class _AdmissionRepository extends TestRepository {
  final List<({String operation, String row})> requests = [];
  final Map<String, IntakeFile> received = {};
  Completer<void>? uploadGate;
  bool failUpload = false;
  bool serverDuplicate = false;

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    requests.add((operation: 'create', row: file.sha256));
    received[file.sha256] = file;
    return {
      'upload_id': file.sha256,
      'state': serverDuplicate ? 'duplicate' : 'ready',
    };
  }

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async {
    requests.add((operation: 'resume', row: id));
    return {'upload_id': id, 'state': 'ready'};
  }

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {
    requests.add((operation: 'upload', row: session['upload_id'] as String));
    received[file.sha256] = file;
    await uploadGate?.future;
    if (failUpload) {
      throw const ApiFailure('Test upload interrupted.', status: 503);
    }
    progress(1);
  }

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    requests.add((operation: 'complete', row: id));
    return {};
  }
}

/// Controls admission without changing CaptureScreen's asynchronous lifecycle.
class _AdmissionFile extends XFile {
  _AdmissionFile(
    this.bytes, {
    String name = 'admission.png',
    this.gate,
    this.reportedLength,
    this.unreadable = false,
  }) : super(name);

  final Uint8List bytes;
  final Completer<void>? gate;
  final int? reportedLength;
  final bool unreadable;
  bool lengthRequested = false;

  @override
  Future<int> length() async {
    lengthRequested = true;
    await gate?.future;
    return reportedLength ?? bytes.length;
  }

  @override
  Future<Uint8List> readAsBytes() async {
    if (unreadable) throw const FileSystemException('Test file unavailable');
    return bytes;
  }
}

ManifestEntry _admissionEntry(
  String key, {
  UploadState state = UploadState.ready,
}) {
  final digest = key.padRight(64, '0');
  return ManifestEntry(
    digest: digest,
    name: '$key.png',
    file: IntakeFile(
      name: '$key.png',
      bytes: FakeCaptureCamera.frame,
      mimeType: 'image/png',
      sha256: digest,
      method: 'files',
      sensitive: true,
    ),
    state: state,
  );
}

List<ManifestEntry> _oldAdmissionRows() => [
  _admissionEntry('old-ready'),
  _admissionEntry('old-failed', state: UploadState.failed)
    ..session = {'upload_id': 'old-upload'},
  ManifestEntry.restored(
    digest: 'restored'.padRight(64, '0'),
    handle: {'upload_id': 'restored-upload'},
  ),
];

Future<void> _waitAdmission(
  WidgetTester tester,
  bool Function() condition,
  String reason,
) async {
  await waitForCameraCondition(tester, condition);
  expect(condition(), isTrue, reason: reason);
}

Future<void> _pumpAdmissionFrames(WidgetTester tester) async {
  // Seeded Checking rows deliberately keep animating. Advance route/disclosure
  // transitions, then wait for explicit admission/transfer predicates instead
  // of asking an indeterminate progress indicator to settle.
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.runAsync(() async => Future<void>.delayed(Duration.zero));
  await tester.pump();
}

Future<IntakeTransferSession> _pumpAdmission(
  WidgetTester tester,
  _AdmissionRepository repository, {
  bool automatic = true,
  List<ManifestEntry>? rows,
  Future<CaptureResult> Function(BuildContext)? result,
  Future<List<XFile>> Function()? recover,
  bool recoveryMarker = false,
  FakeCaptureCamera? camera,
}) async {
  SharedPreferences.setMockInitialValues({
    _admissionPreference: automatic,
    if (recoveryMarker)
      'pending-camera-owner-v1': '$_admissionOwner:${_admissionScope.key}',
  });
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1100, 2400);
  addTearDown(tester.view.reset);
  final session = intakeTransferSession(
    repository,
    _admissionScope,
    _admissionOwner,
  );
  session.entries.addAll(rows ?? _oldAdmissionRows());
  addTearDown(() async {
    final gate = repository.uploadGate;
    if (gate != null && !gate.isCompleted) gate.complete();
    await tester.pumpWidget(const SizedBox.shrink());
    forgetIntakeTransfers(repository, _admissionOwner);
  });
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: IntakeScreen(
          repository: repository,
          scope: _admissionScope,
          userId: _admissionOwner,
          onComplete: () {},
          cameraFactory: () async => camera ?? FakeCaptureCamera(),
          openCapture: result,
          recoverCamera: recover,
        ),
      ),
    ),
  );
  await _pumpAdmissionFrames(tester);
  return session;
}

Future<void> _openAdmissionCamera(WidgetTester tester) async {
  const key = ValueKey<String>('intake-take-photograph');
  if (find.byKey(key).evaluate().isEmpty) {
    await tester.tap(find.byKey(const ValueKey('intake-add-photos')));
    await _pumpAdmissionFrames(tester);
  }
  await tester.ensureVisible(find.byKey(key));
  await tester.tap(find.byKey(key));
  await _pumpAdmissionFrames(tester);
}

Future<void> _closeAdmissionCamera(WidgetTester tester, String action) async {
  if (action == 'Back') {
    await tester.binding.handlePopRoute();
  } else if (action == 'Close') {
    await tester.tap(
      find.byWidgetPredicate(
        (widget) =>
            widget is UiIconButton &&
            widget.semanticsLabel == CaptureScreen.closeLabel,
      ),
    );
  } else {
    await tester.tap(find.text(action));
  }
  await _pumpAdmissionFrames(tester);
}

Future<void> _acceptAdmissionFile(WidgetTester tester, XFile file) async {
  tester.widget<CaptureScreen>(find.byType(CaptureScreen)).onAccepted!(file);
  await tester.pump();
}

void main() {
  group('camera admission:', () {
    for (final action in ['Close', 'Done', 'Back', 'Back to Intake']) {
      testWidgets('zero-photo $action preserves old rows without sending', (
        tester,
      ) async {
        final repository = _AdmissionRepository();
        final camera = FakeCaptureCamera(
          unavailable: action == 'Back to Intake'
              ? CaptureUnavailable.permission
              : null,
        );
        final session = await _pumpAdmission(
          tester,
          repository,
          camera: camera,
        );
        final before = [
          for (final entry in session.entries)
            (entry.state, entry.file, entry.session),
        ];
        await _openAdmissionCamera(tester);
        await _closeAdmissionCamera(tester, action);
        await _waitAdmission(
          tester,
          () => !session.busy,
          'return pump finished',
        );
        expect(repository.requests, isEmpty);
        expect([
          for (final entry in session.entries)
            (entry.state, entry.file, entry.session),
        ], before);
        expect(camera.taken, isEmpty);
        expect(
          (await SharedPreferences.getInstance()).getBool(_admissionPreference),
          isTrue,
        );
        expect(tester.takeException(), isNull);
      });
    }

    for (final callback in [false, true]) {
      for (final rejection in [
        'empty',
        'format',
        'size',
        'resolution',
        'read',
      ]) {
        testWidgets(
          '${callback ? 'callback' : 'returned'} $rejection rejection does not release old rows',
          (tester) async {
            final bytes = Uint8List.fromList(FakeCaptureCamera.frame);
            if (rejection == 'resolution') {
              ByteData.sublistView(bytes).setUint32(16, 65537);
            }
            final file = _AdmissionFile(
              bytes,
              name: rejection == 'format' ? 'refused.txt' : 'refused.png',
              reportedLength: rejection == 'empty'
                  ? 0
                  : rejection == 'size'
                  ? intakeMaximumBytes + 1
                  : null,
              unreadable: rejection == 'read',
            );
            final repository = _AdmissionRepository();
            final session = await _pumpAdmission(
              tester,
              repository,
              result: callback
                  ? null
                  : (_) async => CaptureResult(files: [file]),
            );
            await _openAdmissionCamera(tester);
            if (callback) await _acceptAdmissionFile(tester, file);
            await _waitAdmission(
              tester,
              () => session.entries.any((e) => e.state == UploadState.skipped),
              'the existing refusal is recorded',
            );
            await _waitAdmission(
              tester,
              () => !session.busy,
              'admission settled',
            );
            expect(repository.requests, isEmpty);
            expect(session.entries[0].state, UploadState.ready);
            expect(session.entries[1].state, UploadState.failed);
            expect(session.entries[2].file, isNull);
          },
        );
      }

      for (final duplicate in ['settled', 'checking', 'uploading']) {
        testWidgets(
          '${callback ? 'callback' : 'returned'} $duplicate local duplicate does not release old rows',
          (tester) async {
            final file = _AdmissionFile(FakeCaptureCamera.frame);
            final digest = sha256.convert(file.bytes).toString();
            final existing = _admissionEntry(digest)
              ..state = duplicate == 'settled'
                  ? UploadState.accepted
                  : duplicate == 'uploading'
                  ? UploadState.uploading
                  : UploadState.ready
              ..checking = duplicate == 'checking';
            final repository = _AdmissionRepository();
            final session = await _pumpAdmission(
              tester,
              repository,
              rows: [..._oldAdmissionRows(), existing],
              result: callback
                  ? null
                  : (_) async => CaptureResult(files: [file]),
            );
            await _openAdmissionCamera(tester);
            if (callback) await _acceptAdmissionFile(tester, file);
            await _waitAdmission(
              tester,
              () => session.entries.any((e) => e.state == UploadState.skipped),
              'local duplicate is refused',
            );
            await _waitAdmission(
              tester,
              () => !session.busy,
              'admission settled',
            );
            expect(repository.requests, isEmpty);
            expect(session.entries[0].state, UploadState.ready);
          },
        );
      }
    }

    for (final action in ['Close', 'Done', 'Back']) {
      testWidgets('failed streamed transfer is not retried by $action', (
        tester,
      ) async {
        final repository = _AdmissionRepository()..failUpload = true;
        final session = await _pumpAdmission(tester, repository, rows: []);
        await _openAdmissionCamera(tester);
        await tester.tap(find.byKey(const ValueKey('capture-shutter')));
        await _waitAdmission(
          tester,
          () =>
              !session.busy &&
              session.entries.length == 1 &&
              session.entries.single.state == UploadState.failed &&
              session.entries.single.sendable,
          'first pump is terminal, nonbusy and retryable BEFORE exit',
        );
        final row = session.entries.single.digest;
        expect(repository.requests, [
          (operation: 'create', row: row),
          (operation: 'upload', row: row),
        ]);
        final before = [...repository.requests];
        await _closeAdmissionCamera(tester, action);
        await _waitAdmission(tester, () => !session.busy, 'return settled');
        expect(repository.requests, before);
        expect(session.entries.single.sendable, isTrue);
      });
    }

    for (final automatic in [false, true]) {
      testWidgets('returned valid photo keeps automatic=$automatic behavior', (
        tester,
      ) async {
        final bytes = FakeCaptureCamera.frame;
        final digest = sha256.convert(bytes).toString();
        final repository = _AdmissionRepository();
        final session = await _pumpAdmission(
          tester,
          repository,
          automatic: automatic,
          rows: [],
          result: (_) async => CaptureResult(files: [_AdmissionFile(bytes)]),
        );
        await _openAdmissionCamera(tester);
        await _waitAdmission(
          tester,
          () => session.entries.isNotEmpty,
          'admitted',
        );
        if (!automatic) {
          expect(repository.requests, isEmpty);
          final send = find.byKey(const ValueKey('intake-upload'));
          await tester.ensureVisible(send);
          await tester.tap(send);
        }
        await _waitAdmission(
          tester,
          () => !session.busy && session.entries.single.settled,
          'valid accepted photo reaches existing transfer',
        );
        expect(repository.requests, [
          (operation: 'create', row: digest),
          (operation: 'upload', row: digest),
          (operation: 'resume', row: digest),
          (operation: 'complete', row: digest),
        ]);
        expect(repository.received[digest]!.bytes, orderedEquals(bytes));
        expect(repository.received[digest]!.method, 'camera');
        expect(repository.received[digest]!.width, isPositive);
        expect(repository.received[digest]!.height, isPositive);
      });
    }

    testWidgets('manual review Send still transfers before Done', (
      tester,
    ) async {
      final repository = _AdmissionRepository();
      final session = await _pumpAdmission(
        tester,
        repository,
        automatic: false,
        rows: [],
      );
      await _openAdmissionCamera(tester);
      await takeOne(tester);
      expect(repository.requests, isEmpty);
      await tester.tap(find.byKey(const ValueKey('capture-send')));
      await _waitAdmission(
        tester,
        () => !session.busy && session.entries.any((e) => e.settled),
        'manual acceptance starts transfer even with automatic off',
      );
      expect(find.byType(CaptureScreen), findsOneWidget);
      final before = [...repository.requests];
      await _closeAdmissionCamera(tester, 'Done');
      expect(repository.requests, before);
      expect(
        (await SharedPreferences.getInstance()).getBool(_admissionPreference),
        isFalse,
      );
    });

    testWidgets('unsent manual review never releases old rows', (tester) async {
      final repository = _AdmissionRepository();
      final session = await _pumpAdmission(
        tester,
        repository,
        automatic: false,
      );
      await _openAdmissionCamera(tester);
      await takeOne(tester);
      await _closeAdmissionCamera(tester, 'Back');
      expect(repository.requests, isEmpty);
      expect(session.entries, hasLength(3));
    });

    for (final earned in [false, true]) {
      testWidgets(
        'unmount keeps earned=$earned admissions without admitting the later file',
        (tester) async {
          final gate = Completer<void>();
          final first = _AdmissionFile(
            FakeCaptureCamera.frame,
            name: 'first.png',
            reportedLength: earned ? null : 0,
          );
          final later = _AdmissionFile(
            File('test/fixtures/synthetic-wide-label.png').readAsBytesSync(),
            name: 'later.png',
            gate: gate,
          );
          final firstDigest = sha256.convert(first.bytes).toString();
          final laterDigest = sha256.convert(later.bytes).toString();
          final repository = _AdmissionRepository();
          final session = await _pumpAdmission(
            tester,
            repository,
            result: (_) async => CaptureResult(files: [first, later]),
          );
          addTearDown(() {
            if (!gate.isCompleted) gate.complete();
          });
          final take = find.byKey(const ValueKey('intake-take-photograph'));
          if (take.evaluate().isEmpty) {
            await tester.tap(find.byKey(const ValueKey('intake-add-photos')));
            await _pumpAdmissionFrames(tester);
          }
          // Keep the actual selection future so the zero-earned assertion is
          // made after admission returns, not before a delayed pump can start.
          final choosing =
              Function.apply(tester.widget<UiButton>(take).onPressed!, const [])
                  as Future<void>;
          await _waitAdmission(
            tester,
            () => later.lengthRequested && session.entries.length == 4,
            'first file is handled while the second admission is gated',
          );
          expect(repository.requests, isEmpty);
          expect(session.busy, isFalse);
          expect(
            session.entries.last.state,
            earned ? UploadState.ready : UploadState.skipped,
          );
          final admitted = earned ? session.entries.last : null;
          final before = [
            for (final entry in session.entries)
              (entry.state, entry.file, entry.session),
          ];
          await tester.pumpWidget(const SizedBox.shrink());
          expect(find.byType(IntakeScreen), findsNothing);
          gate.complete();
          await tester.runAsync(() async => choosing);
          await _waitAdmission(
            tester,
            () => !session.busy,
            'the retained session finishes any earned pump after unmount',
          );
          expect(session.entries, hasLength(4));
          expect(session.entries.any((e) => e.digest == laterDigest), isFalse);
          expect(repository.requests.any((r) => r.row == laterDigest), isFalse);
          if (earned) {
            expect(admitted!.state, UploadState.accepted);
            expect(
              repository.requests
                  .where((r) => r.row == firstDigest)
                  .map((r) => r.operation),
              ['create', 'upload', 'resume', 'complete'],
            );
            expect(
              repository.received[firstDigest]!.bytes,
              orderedEquals(first.bytes),
            );
          } else {
            expect(repository.requests, isEmpty);
            expect([
              for (final entry in session.entries)
                (entry.state, entry.file, entry.session),
            ], before);
          }
          expect(tester.takeException(), isNull);
        },
      );
    }

    testWidgets('accepted admission may finish after the camera closes', (
      tester,
    ) async {
      final gate = Completer<void>();
      final repository = _AdmissionRepository();
      final session = await _pumpAdmission(tester, repository, rows: []);
      await _openAdmissionCamera(tester);
      await _acceptAdmissionFile(
        tester,
        _AdmissionFile(FakeCaptureCamera.frame, gate: gate),
      );
      expect(session.entries, isEmpty);
      await _closeAdmissionCamera(tester, 'Done');
      expect(repository.requests, isEmpty);
      gate.complete();
      await _waitAdmission(
        tester,
        () => !session.busy && session.entries.any((e) => e.settled),
        'accepted callback owns admission even after camera pop',
      );
      expect(repository.requests.map((r) => r.operation), [
        'create',
        'upload',
        'resume',
        'complete',
      ]);
    });

    testWidgets('multiple accepts join the running pump without double sends', (
      tester,
    ) async {
      final gate = Completer<void>();
      final repository = _AdmissionRepository()..uploadGate = gate;
      final session = await _pumpAdmission(tester, repository, rows: []);
      await _openAdmissionCamera(tester);
      final first = FakeCaptureCamera.frame;
      final second = File(
        'test/fixtures/synthetic-wide-label.png',
      ).readAsBytesSync();
      await _acceptAdmissionFile(tester, _AdmissionFile(first));
      await _waitAdmission(
        tester,
        () =>
            session.busy &&
            repository.requests.any((r) => r.operation == 'upload'),
        'first transfer is held busy',
      );
      await _acceptAdmissionFile(
        tester,
        _AdmissionFile(second, name: 'second.png'),
      );
      await _waitAdmission(
        tester,
        () => session.entries.length == 2 && session.entries.last.sendable,
        'second acceptance joins the same busy batch',
      );
      await _closeAdmissionCamera(tester, 'Done');
      gate.complete();
      await _waitAdmission(
        tester,
        () => !session.busy && session.entries.every((e) => e.settled),
        'the existing pump drains both accepted photos',
      );
      for (final bytes in [first, second]) {
        final digest = sha256.convert(bytes).toString();
        expect(
          repository.requests
              .where((r) => r.row == digest)
              .map((r) => r.operation),
          ['create', 'upload', 'resume', 'complete'],
        );
        expect(repository.received[digest]!.bytes, orderedEquals(bytes));
      }
    });

    for (final state in [UploadState.ready, UploadState.interrupted]) {
      testWidgets('same-digest $state re-admission remains a positive action', (
        tester,
      ) async {
        final bytes = FakeCaptureCamera.frame;
        final digest = sha256.convert(bytes).toString();
        final old = state == UploadState.interrupted
            ? ManifestEntry.restored(
                digest: digest,
                handle: {'upload_id': 'existing-upload'},
              )
            : _admissionEntry(digest);
        final repository = _AdmissionRepository();
        final session = await _pumpAdmission(
          tester,
          repository,
          rows: [old],
          result: (_) async => CaptureResult(files: [_AdmissionFile(bytes)]),
        );
        await _openAdmissionCamera(tester);
        await _waitAdmission(
          tester,
          () => !session.busy && old.settled,
          're-admitted old row is eligible without a new manifest row',
        );
        expect(session.entries, [same(old)]);
        expect(
          repository.requests.map((r) => r.operation),
          state == UploadState.interrupted
              ? ['resume', 'upload', 'resume', 'complete']
              : ['create', 'upload', 'resume', 'complete'],
        );
        if (state == UploadState.interrupted) {
          expect(
            repository.requests.every((r) => r.row == 'existing-upload'),
            isTrue,
          );
        }
      });
    }

    testWidgets('server duplicate is admitted and genuine batch drain survives', (
      tester,
    ) async {
      final repository = _AdmissionRepository()..serverDuplicate = true;
      final session = await _pumpAdmission(
        tester,
        repository,
        rows: [_admissionEntry('old-ready')],
        result: (_) async => CaptureResult(
          files: [
            _AdmissionFile(Uint8List.fromList([1, 2, 3])),
          ],
        ),
      );
      await _openAdmissionCamera(tester);
      await _waitAdmission(
        tester,
        () =>
            !session.busy &&
            session.entries.length == 2 &&
            session.entries.every((e) => e.settled),
        'unsupported local decoder is tolerated and server duplicates are normal acceptance',
      );
      expect(repository.requests, [
        (operation: 'create', row: 'old-ready'.padRight(64, '0')),
        (operation: 'create', row: sha256.convert([1, 2, 3]).toString()),
      ]);
      expect(
        session.entries.every((e) => e.state == UploadState.duplicate),
        isTrue,
      );
    });

    for (final selected in [false, true]) {
      for (final automatic in selected ? [false, true] : [true]) {
        testWidgets(
          'platform picker selected=$selected automatic=$automatic keeps marker and send policy',
          (tester) async {
            const channel = MethodChannel('plugins.flutter.io/image_picker');
            var calls = 0;
            final messenger = TestDefaultBinaryMessengerBinding
                .instance
                .defaultBinaryMessenger;
            messenger.setMockMethodCallHandler(channel, (call) async {
              expect(call.method, 'pickImage');
              calls++;
              expect(
                (await SharedPreferences.getInstance()).getString(
                  'pending-camera-owner-v1',
                ),
                '$_admissionOwner:${_admissionScope.key}',
              );
              return selected
                  ? File('test/fixtures/synthetic-label.png').absolute.path
                  : null;
            });
            addTearDown(
              () => messenger.setMockMethodCallHandler(channel, null),
            );
            final repository = _AdmissionRepository();
            final session = await _pumpAdmission(
              tester,
              repository,
              automatic: automatic,
              rows: selected ? [] : null,
              result: (_) async =>
                  const CaptureResult(unavailable: CaptureUnavailable.noCamera),
            );
            await _openAdmissionCamera(tester);
            await _waitAdmission(
              tester,
              () => calls == 1 && (!selected || session.entries.isNotEmpty),
              'the real platform-picker adapter returns its mocked result',
            );
            if (selected && automatic) {
              await _waitAdmission(
                tester,
                () => !session.busy && session.entries.single.settled,
                'automatic fallback transfers',
              );
              expect(repository.requests.map((r) => r.operation), [
                'create',
                'upload',
                'resume',
                'complete',
              ]);
            } else {
              await _waitAdmission(
                tester,
                () => !session.busy,
                'picker settled',
              );
              expect(repository.requests, isEmpty);
            }
            expect(
              (await SharedPreferences.getInstance()).getString(
                'pending-camera-owner-v1',
              ),
              isNull,
            );
            expect(
              (await SharedPreferences.getInstance()).getBool(
                _admissionPreference,
              ),
              automatic,
            );
          },
        );
      }
    }

    testWidgets('recovered camera admission still waits for explicit Send', (
      tester,
    ) async {
      final repository = _AdmissionRepository();
      final session = await _pumpAdmission(
        tester,
        repository,
        rows: [],
        recoveryMarker: true,
        recover: () async => [_AdmissionFile(FakeCaptureCamera.frame)],
      );
      await _waitAdmission(
        tester,
        () => session.entries.isNotEmpty,
        'recovery admits its image',
      );
      expect(repository.requests, isEmpty);
      expect(session.entries.single.sendable, isTrue);
      expect(
        (await SharedPreferences.getInstance()).getString(
          'pending-camera-owner-v1',
        ),
        isNull,
      );
    });

    testWidgets(
      'explicit per-file Retry and page Send still own old transfers',
      (tester) async {
        final repository = _AdmissionRepository();
        final session = await _pumpAdmission(tester, repository);
        await _openAdmissionCamera(tester);
        await _closeAdmissionCamera(tester, 'Done');
        await _waitAdmission(
          tester,
          () => !session.busy,
          'camera return settled',
        );
        expect(repository.requests, isEmpty);
        final failed = session.entries[1];
        final retry = find.byKey(ValueKey('intake-retry-${failed.digest}'));
        await tester.ensureVisible(retry);
        await tester.tap(retry);
        await _waitAdmission(
          tester,
          () => !session.busy && failed.settled,
          'explicit retry finishes',
        );
        expect(repository.requests, [
          (operation: 'resume', row: 'old-upload'),
          (operation: 'upload', row: 'old-upload'),
          (operation: 'resume', row: 'old-upload'),
          (operation: 'complete', row: 'old-upload'),
        ]);
        expect(session.entries.first.state, UploadState.ready);
        final send = find.byKey(const ValueKey('intake-upload'));
        await tester.ensureVisible(send);
        await tester.tap(send);
        await _waitAdmission(
          tester,
          () => !session.busy && session.entries.first.settled,
          'explicit page Send finishes',
        );
        expect(
          repository.requests
              .where((r) => r.row == session.entries.first.digest)
              .map((r) => r.operation),
          ['create', 'upload', 'resume', 'complete'],
        );
        expect(session.entries[2].file, isNull);
        expect(session.entries[2].state, UploadState.interrupted);
      },
    );
  });

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
