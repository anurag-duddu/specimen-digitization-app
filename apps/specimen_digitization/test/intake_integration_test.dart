import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'golden/golden_harness.dart';
import 'intake_harness.dart';
import 'ui_finders.dart';

class IntegrationRepository extends GoldenRepository
    implements AccessFailureSource {
  final failures = StreamController<ApiFailure>.broadcast(sync: true);
  bool allowed = true;
  final sent = <IntakeFile>[];
  int attempts = 0;
  @override
  Stream<ApiFailure> get accessFailures => failures.stream;
  @override
  Future<List<CollectionScope>> scopes() async {
    if (!allowed) {
      throw const ApiFailure(
        'Sign in required',
        status: 401,
        code: 'unauthorized',
      );
    }
    return super.scopes();
  }

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    attempts++;
    if (!allowed) {
      const failure = ApiFailure(
        'Sign in required',
        status: 401,
        code: 'unauthorized',
      );
      failures.add(failure);
      throw failure;
    }
    sent.add(file);
    return {'upload_id': file.sha256, 'sensitive': file.sensitive};
  }

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async => {
    'upload_id': id,
  };
  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => {'specimen_id': id, 'status': 'running'};
}

Future<IntakeTransferSession> mount(
  WidgetTester tester,
  IntegrationRepository repo,
) async {
  await pumpGoldenApp(
    tester,
    window: const Size(390, 844),
    brightness: Brightness.light,
    location: goldenIntakeLocation,
    repository: repo,
  );
  final screen = tester.widget<IntakeScreen>(find.byType(IntakeScreen));
  final session = intakeTransferSession(repo, screen.scope, screen.userId);
  addTearDown(repo.failures.close);
  for (var i = 0; i < 2; i++) {
    session.entries.add(
      ManifestEntry(
        digest: 'photo-$i',
        name: 'photo-$i.png',
        state: UploadState.ready,
        file: IntakeFile(
          name: 'photo-$i.png',
          bytes: goldenPreviewBytes,
          mimeType: 'image/png',
          sha256: 'photo-$i',
          method: 'files',
          sensitive: false,
        ),
      ),
    );
  }
  session.changed();
  await tester.pumpAndSettle();
  return session;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets(
    'routed sticky Send honors per-photo sensitivity and retains completion',
    (tester) async {
      final repo = IntegrationRepository();
      await mount(tester, repo);
      final controller = WorkspaceScope.of(
        tester.element(find.byType(IntakeScreen)),
      );
      controller.search('previous-barcode');
      await controller.applyFilters({'status': 'processing_blocked'});
      await tester.pumpAndSettle();
      final row = find.byType(IntakeManifestRow).first;
      await tester.ensureVisible(row);
      await tester.tap(
        find.descendant(of: row, matching: find.byType(UiMenuTrigger)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Mark sensitive').last);
      await tester.pumpAndSettle();
      expect(find.text('Sensitive'), findsOneWidget);
      expect(uploadButton.hitTestable(), findsOneWidget);
      expect(tester.getRect(uploadButton).bottom, lessThanOrEqualTo(844));
      await tester.tap(uploadButton);
      await tester.pumpAndSettle();
      expect(repo.sent.map((file) => file.sensitive), [true, false]);
      expect(find.byType(IntakeManifestRow), findsNothing);
      expect(find.text('All 2 sent'), findsOneWidget);
      await tester.ensureVisible(uiButton('View in Specimens'));
      await tester.tap(uiButton('View in Specimens'));
      await tester.pumpAndSettle();
      expect(find.byType(IntakeScreen), findsNothing);
      expect(find.text('All specimens'), findsOneWidget);
      expect(controller.query, isEmpty);
      expect(controller.filters, isEmpty);
      expect(controller.disposition, isEmpty);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets(
    'routed access denial pauses and verified same-user access resumes without Send',
    (tester) async {
      final repo = IntegrationRepository();
      final transfers = await mount(tester, repo);
      repo.allowed = false;
      await tester.tap(uploadButton);
      await tester.pumpAndSettle();
      expect(repo.attempts, 1);
      expect(transfers.signInRequired, isTrue);
      expect(
        transfers.entries.every((e) => e.state == UploadState.ready),
        isTrue,
      );
      expect(
        find.text('Collection access could not be verified'),
        findsOneWidget,
      );
      await tester.tap(uiButton('Check access again'));
      await tester.pumpAndSettle();
      expect(repo.attempts, 1, reason: 'denied access cannot resume sending');
      repo.allowed = true;
      await tester.tap(uiButton('Check access again'));
      await tester.pumpAndSettle();
      expect(repo.sent, hasLength(2));
      expect(transfers.signInRequired, isFalse);
      expect(find.text('All 2 sent'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets(
    'explicit sign-out releases unsent rows instead of resuming them',
    (tester) async {
      final repo = IntegrationRepository();
      final transfers = await mount(tester, repo);
      final controller = WorkspaceScope.of(
        tester.element(find.byType(IntakeScreen)),
      );
      await controller.signOut();
      await tester.pumpAndSettle();
      expect(transfers.entries, isEmpty);
      expect(repo.sent, isEmpty);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
