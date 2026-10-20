import 'dart:async';

import 'package:crypto/crypto.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'capture_screen_test.dart'
    show FakeCaptureCamera, takeOne, waitForCameraCondition;
import 'intake_integration_test.dart' show IntegrationRepository;
import 'intake_harness.dart';
import 'widgets/harness.dart';

class WaitingRepository extends IntegrationRepository {
  final uploadGate = Completer<void>();
  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {
    await uploadGate.future;
    progress(1);
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets(
    'last-shot menu removes only its Ready photo and disappears on sending',
    (tester) async {
      final repo = WaitingRepository();
      final scope = (await repo.scopes()).first;
      SharedPreferences.setMockInitialValues({
        'camera-auto-ingest-v1:last-shot:${scope.key}': true,
      });
      await pumpComponent(
        tester,
        IntakeScreen(
          repository: repo,
          scope: scope,
          userId: 'last-shot',
          onComplete: () {},
          cameraFactory: () async => FakeCaptureCamera(),
        ),
        size: const Size(390, 844),
      );
      final session = intakeTransferSession(repo, scope, 'last-shot');
      session.entries.add(
        ManifestEntry(
          digest: 'first',
          name: 'first.png',
          state: UploadState.ready,
          file: IntakeFile(
            name: 'first.png',
            bytes: FakeCaptureCamera.frame,
            mimeType: 'image/png',
            sha256: 'first',
            method: 'files',
            sensitive: false,
          ),
        ),
      );
      unawaited(session.start());
      await tester.pumpAndSettle();
      final resumedDigest = sha256.convert(FakeCaptureCamera.frame).toString();
      final resumed = ManifestEntry(
        digest: resumedDigest,
        name: 'old-camera.png',
        state: UploadState.interrupted,
      );
      final later = ManifestEntry(
        digest: 'later',
        name: 'later.png',
        state: UploadState.ready,
        file: IntakeFile(
          name: 'later.png',
          bytes: FakeCaptureCamera.frame,
          mimeType: 'image/png',
          sha256: 'later',
          method: 'files',
          sensitive: false,
        ),
      );
      session.entries.addAll([resumed, later]);
      session.changed();
      await tester.pumpAndSettle();
      await tester.tap(takePhotographButton);
      await tester.pumpAndSettle();
      await takeOne(tester);
      await waitForCameraCondition(tester, () => resumed.file != null);
      await tester.pumpAndSettle();
      expect(resumed.state, UploadState.ready);
      final options = find.bySemanticsLabel('Last photo options');
      await tester.tap(options);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Remove last photo'));
      await tester.pumpAndSettle();
      expect(session.entries.map((e) => e.digest), ['first', 'later']);
      session.remove(later);
      expect(options, findsNothing);
      // A new capture waits behind the same transfer, then loses the action
      // as soon as sending starts, even when its menu was already open.
      await takeOne(tester);
      await waitForCameraCondition(tester, () => session.entries.length == 2);
      await tester.pumpAndSettle();
      await tester.tap(options);
      await tester.pumpAndSettle();
      repo.uploadGate.complete();
      await waitForCameraCondition(tester, () => session.entries.isEmpty);
      await tester.pumpAndSettle();
      expect(options, findsNothing);
      expect(find.text('Remove last photo'), findsNothing);
      expect(repo.sent, hasLength(2));
      await tester.pumpWidget(const SizedBox.shrink());
      forgetIntakeTransfers(repo, 'last-shot');
      await repo.failures.close();
    },
  );

  testWidgets('camera fallback picker cannot admit into a changed collection', (
    tester,
  ) async {
    final repo = IntegrationRepository();
    final scope = (await repo.scopes()).first;
    const other = CollectionScope(
      organizationId: 'other',
      collectionId: 'other',
      name: 'Other',
      permissions: ['upload'],
    );
    final selection = Completer<List<XFile>>();
    final activeScope = ValueNotifier(scope);
    await pumpComponent(
      tester,
      ValueListenableBuilder<CollectionScope>(
        valueListenable: activeScope,
        builder: (context, scope, _) => IntakeScreen(
          repository: repo,
          scope: scope,
          userId: 'fallback-owner',
          onComplete: () {},
          cameraFactory: () async =>
              FakeCaptureCamera(unavailable: CaptureUnavailable.noCamera),
          pickFiles: () => selection.future,
        ),
      ),
      size: const Size(390, 844),
    );
    await tester.tap(takePhotographButton);
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(CaptureScreen),
        matching: find.text('Choose files'),
      ),
    );
    await tester.pumpAndSettle();
    activeScope.value = other;
    await tester.pumpAndSettle();
    selection.complete([
      XFile.fromData(FakeCaptureCamera.frame, name: 'old.png', path: 'old.png'),
    ]);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pumpAndSettle();
    expect(
      intakeTransferSession(repo, scope, 'fallback-owner').entries,
      isEmpty,
    );
    expect(
      intakeTransferSession(repo, other, 'fallback-owner').entries,
      isEmpty,
    );
    expect(repo.sent, isEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    activeScope.dispose();
    forgetIntakeTransfers(repo, 'fallback-owner');
    await repo.failures.close();
  });

  testWidgets('a later Ready capture does not reopen the last-shot menu', (
    tester,
  ) async {
    final activity = ValueNotifier(false);
    await pumpComponent(
      tester,
      CaptureScreen(
        camera: () async => FakeCaptureCamera(),
        autoIngest: true,
        onCaptured: (_) {},
        activity: activity,
        canRemovePhoto: (_) => activity.value,
        removePhoto: (_) => true,
      ),
      size: const Size(390, 844),
    );
    activity.value = true;
    await takeOne(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Last photo options'));
    await tester.pumpAndSettle();
    expect(find.text('Remove last photo'), findsOneWidget);
    activity.value = false;
    await tester.pumpAndSettle();
    expect(find.text('Remove last photo'), findsNothing);
    await takeOne(tester);
    activity.value = true;
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Last photo options'), findsOneWidget);
    expect(find.text('Remove last photo'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    activity.dispose();
  });

  for (final sensitive in [false, true]) {
    testWidgets(
      'real capture route sends reviewed sensitivity=$sensitive and keeps live completion',
      (tester) async {
        final repo = IntegrationRepository();
        final scope = (await repo.scopes()).first;
        final camera = FakeCaptureCamera();
        await pumpComponent(
          tester,
          IntakeScreen(
            repository: repo,
            scope: scope,
            userId: 'camera-test',
            onComplete: () {},
            cameraFactory: () async => camera,
          ),
          size: const Size(390, 844),
        );
        await tester.tap(takePhotographButton);
        await tester.pumpAndSettle();
        expect(
          tester
              .widget<UiSwitch>(find.byKey(const ValueKey('capture-sensitive')))
              .value,
          isFalse,
        );
        await takeOne(tester);
        expect(
          repo.sent,
          isEmpty,
          reason: 'Review does not send on the shutter',
        );
        final toggle = find.byKey(const ValueKey('capture-review-sensitive'));
        expect(toggle, findsOneWidget);
        if (sensitive) {
          await tester.ensureVisible(toggle);
          await tester.tap(toggle);
          await tester.pump();
        }
        await tester.tap(find.byKey(const ValueKey('capture-send')));
        await waitForCameraCondition(tester, () => repo.sent.isNotEmpty);
        await tester.pumpAndSettle();
        expect(repo.sent.single.sensitive, sensitive);
        expect(find.byType(CaptureScreen), findsOneWidget);
        expect(find.text('1 sent'), findsOneWidget);
        await tester.tap(find.text('Done'));
        await tester.pumpAndSettle();
        expect(find.text('All 1 sent'), findsOneWidget);
        expect(tester.widget<UiSwitch>(sensitivityControl).value, isFalse);
        await tester.pumpWidget(const SizedBox.shrink());
        forgetIntakeTransfers(repo, 'camera-test');
        await repo.failures.close();
      },
    );
  }

  for (final reason in [
    CaptureUnavailable.permission,
    CaptureUnavailable.noCamera,
  ]) {
    testWidgets(
      'camera $reason Choose files opens file picker and waits for Send',
      (tester) async {
        final repo = IntegrationRepository();
        final scope = (await repo.scopes()).first;
        SharedPreferences.setMockInitialValues({
          'camera-auto-ingest-v1:fallback:${scope.key}': true,
        });
        var picks = 0;
        await pumpComponent(
          tester,
          IntakeScreen(
            repository: repo,
            scope: scope,
            userId: 'fallback',
            onComplete: () {},
            cameraFactory: () async => FakeCaptureCamera(unavailable: reason),
            pickFiles: () async {
              picks++;
              return [
                XFile.fromData(
                  FakeCaptureCamera.frame,
                  name: 'fallback.png',
                  path: 'fallback.png',
                ),
              ];
            },
          ),
          size: const Size(390, 844),
        );
        await tester.tap(takePhotographButton);
        await tester.pumpAndSettle();
        await tester.tap(
          find.descendant(
            of: find.byType(CaptureScreen),
            matching: find.text('Choose files'),
          ),
        );
        await waitForCameraCondition(
          tester,
          () => find.text('fallback.png').evaluate().isNotEmpty,
        );
        final session = intakeTransferSession(repo, scope, 'fallback');
        expect(picks, 1);
        expect(session.entries.single.file!.method, 'files');
        expect(session.entries.single.state, UploadState.ready);
        expect(repo.sent, isEmpty);
        expect(find.text('Send 1 photo'), findsOneWidget);
        await tester.pumpWidget(const SizedBox.shrink());
        forgetIntakeTransfers(repo, 'fallback');
        await repo.failures.close();
      },
    );
  }
}
