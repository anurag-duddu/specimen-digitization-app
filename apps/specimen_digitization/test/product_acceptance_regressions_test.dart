import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestRepository, TestSession, fixture;
import 'workbench_harness.dart';

class MutableReviewSession extends TestSession implements VerifiedEmailAccess {
  Completer<void>? verificationRefresh;
  String identity = 'reviewer-a';
  @override
  String get userId => identity;
  @override
  bool emailVerified = true;
  @override
  Future<void> sendVerification() async {}
  @override
  Future<void> refreshVerification() async {
    emailVerified = true;
    controller.add(true);
    await verificationRefresh?.future;
  }
}

class ReviewRepository extends TestRepository {
  ReviewRepository(this.session);
  final MutableReviewSession session;
  int scopeRequests = 0;
  int reviewRequests = 0;
  final List<String> keys = <String>[];
  ApiFailure? failure;
  int? failOnRequest;
  bool returnUnchanged = false;
  Completer<Specimen>? save;
  Specimen current = fixture;

  @override
  Future<List<CollectionScope>> scopes() async {
    scopeRequests++;
    return <CollectionScope>[
      CollectionScope(
        organizationId: 'org',
        collectionId: 'insects',
        name: session.identity,
        permissions: const <String>['reviewer'],
      ),
    ];
  }

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async => current;

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    reviewRequests++;
    keys.add(key);
    if (failure != null &&
        (failOnRequest == null || failOnRequest == reviewRequests)) {
      throw failure!;
    }
    if (returnUnchanged) return current;
    if (save != null) return save!.future;
    current = Specimen(<String, dynamic>{
      ...current.data,
      'revision': current.revision + 1,
      'fields': [
        for (final field in current.fields)
          if (change['kind'] == 'field_correction' &&
              field['field_key'] == change['target_id'])
            {
              ...field,
              'literal_value': change['value'],
              'state': change['state'],
              'parsed_value': change['parsed'],
              'normalized': change['normalized'],
              'authority_id': change['authority_id'],
              'evidence_ids': change['evidence_ids'],
            }
          else
            field,
      ],
    });
    return current;
  }
}

Future<void> openReview(
  WidgetTester tester,
  MutableReviewSession session,
  ReviewRepository repository,
) async {
  useWindow(tester, const Size(1700, 1100));
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(
      session: session,
      repository: repository,
      initialLocation: AppRoutes.specimenOf(
        encodeCollectionKey('org/insects'),
        fixture.id,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> stageCountry(WidgetTester tester) async {
  await tester.tap(find.text('Fields'));
  await tester.pumpAndSettle();
  await scrollAndTap(tester, find.byTooltip('Edit as written').first);
  await scrollAndTap(tester, find.text('Keep this correction'));
  expect(
    tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
    hasLength(1),
  );
}

Future<void> confirmReason(
  WidgetTester tester,
  String action, {
  bool settle = true,
}) async {
  await tester.tap(find.text(action).last);
  await tester.pumpAndSettle();
  await tester.enterText(
    find.widgetWithText(TextField, 'Reason'),
    'Compared the original label and retained readings',
  );
  await tester.pumpAndSettle();
  await tester.tap(
    find.descendant(
      of: find.byType(ReasonForm),
      matching: find.widgetWithText(FilledButton, action),
    ),
  );
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
  }
}

void main() {
  testWidgets('failed field save retains the pending correction', (
    tester,
  ) async {
    final session = MutableReviewSession();
    final repository = ReviewRepository(session)
      ..failure = const ApiFailure('Disconnected', code: 'network');
    await openReview(tester, session, repository);
    await stageCountry(tester);
    await confirmReason(tester, 'Save 1 pending change');
    expect(repository.reviewRequests, 1);
    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      hasLength(1),
    );
    expect(find.text('Save not confirmed'), findsOneWidget);
    expect(repository.current.revision, fixture.revision);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('failed coverage is reported as unconfirmed', (tester) async {
    final session = MutableReviewSession();
    final repository = ReviewRepository(session)
      ..failure = const ApiFailure('Unavailable', status: 503);
    await openReview(tester, session, repository);
    await confirmReason(tester, 'Confirm label coverage');
    expect(repository.reviewRequests, 1);
    expect(find.text('Save not confirmed'), findsOneWidget);
    expect(repository.current.revision, fixture.revision);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'sign-out clears cached collection and record access immediately',
    (tester) async {
      final session = MutableReviewSession();
      final repository = ReviewRepository(session);
      await openReview(tester, session, repository);
      final controller = WorkspaceScope.read(
        tester.element(find.byType(Scaffold).first),
      );
      expect(controller.scopes, isNotEmpty);
      expect(controller.selected, isNotNull);
      await session.signOut();
      await tester.pumpAndSettle();
      expect(controller.scopes, isEmpty);
      expect(controller.items, isEmpty);
      expect(controller.selected, isNull);
      expect(controller.scope, isNull);
      session.identity = 'reviewer-b';
      await session.signIn('', '');
      await tester.pumpAndSettle();
      expect(repository.scopeRequests, 2);
      expect(controller.scopes.single.name, 'reviewer-b');
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'identity change while signed in reloads collection permissions',
    (tester) async {
      final session = MutableReviewSession();
      final repository = ReviewRepository(session);
      await openReview(tester, session, repository);
      session.identity = 'reviewer-b';
      session.controller.add(true);
      await tester.pumpAndSettle();
      expect(repository.scopeRequests, 2);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('successful verification starts the previously gated workspace', (
    tester,
  ) async {
    final session = MutableReviewSession()..emailVerified = false;
    final repository = ReviewRepository(session);
    await openReview(tester, session, repository);
    expect(repository.scopeRequests, 0);
    await tester.tap(find.text('Check verification again'));
    await tester.pumpAndSettle();
    expect(repository.scopeRequests, 1);
    expect(find.text('Checking collection access'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('no pending edit clears before a delayed acknowledgement', (
    tester,
  ) async {
    final session = MutableReviewSession();
    final repository = ReviewRepository(session)..save = Completer<Specimen>();
    await openReview(tester, session, repository);
    await stageCountry(tester);
    await confirmReason(tester, 'Save 1 pending change', settle: false);
    expect(repository.reviewRequests, 1);
    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      hasLength(1),
    );
    repository.current = Specimen({...fixture.data, 'revision': 4});
    repository.save!.complete(repository.current);
    await tester.pumpAndSettle();
    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      isEmpty,
    );
    expect(find.text('Save not confirmed'), findsNothing);
    await tester.tap(find.byTooltip('Refresh this record'));
    await tester.pumpAndSettle();
    final controller = WorkspaceScope.read(
      tester.element(find.byType(Scaffold).first),
    );
    expect(controller.selected!.revision, 4);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a partial batch keeps the unsaved correction and retry key', (
    tester,
  ) async {
    final session = MutableReviewSession();
    final repository = ReviewRepository(session)
      ..current = Specimen({
        ...fixture.data,
        'fields': [
          ...fixture.fields,
          {
            'field_key': 'collector',
            'display_name': 'Collector',
            'state': 'unknown',
            'literal_value': null,
          },
        ],
      })
      ..failure = const ApiFailure('Disconnected', code: 'network')
      ..failOnRequest = 2;
    await openReview(tester, session, repository);
    await stageCountry(tester);
    await scrollAndTap(tester, find.byTooltip('Edit as written').last);
    await scrollAndTap(tester, find.text('Keep this correction'));
    await confirmReason(tester, 'Save 2 pending changes');
    final pending = tester
        .widget<WorkbenchFields>(find.byType(WorkbenchFields))
        .pending;
    expect(repository.reviewRequests, 2);
    expect(pending.map((p) => p.fieldKey), ['collector']);
    expect(find.text('Save not confirmed'), findsOneWidget);
    await tester.tap(find.text('Keep working'));
    await tester.pumpAndSettle();
    repository.failure = null;
    await confirmReason(tester, 'Save 1 pending change');
    expect(repository.reviewRequests, 3);
    expect(repository.keys[2], repository.keys[1]);
    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      isEmpty,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('an unchanged response does not acknowledge a field save', (
    tester,
  ) async {
    final session = MutableReviewSession();
    final repository = ReviewRepository(session)..returnUnchanged = true;
    await openReview(tester, session, repository);
    await stageCountry(tester);
    await confirmReason(tester, 'Save 1 pending change');
    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      hasLength(1),
    );
    expect(find.text('Save not confirmed'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a verified-user event cannot outrun a failed token refresh', (
    tester,
  ) async {
    final session = MutableReviewSession()
      ..emailVerified = false
      ..verificationRefresh = Completer<void>();
    final repository = ReviewRepository(session);
    await openReview(tester, session, repository);
    await tester.tap(find.text('Check verification again'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(session.emailVerified, isTrue);
    expect(repository.scopeRequests, 0);
    session.verificationRefresh!.completeError(
      StateError('Token refresh failed'),
    );
    await tester.pumpAndSettle();
    expect(repository.scopeRequests, 0);
    expect(find.text('Check verification again'), findsOneWidget);
    session.verificationRefresh = null;
    await tester.tap(find.text('Check verification again'));
    await tester.pumpAndSettle();
    expect(repository.scopeRequests, 1);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('an old account save response cannot repopulate a new session', (
    tester,
  ) async {
    final session = MutableReviewSession();
    final repository = ReviewRepository(session)..save = Completer<Specimen>();
    await openReview(tester, session, repository);
    final controller = WorkspaceScope.read(
      tester.element(find.byType(Scaffold).first),
    );
    final pending = controller.mutate({
      'kind': 'coverage',
      'reason': 'reviewed',
    }, null);
    await tester.pump();
    await session.signOut();
    await tester.pumpAndSettle();
    session.identity = 'reviewer-b';
    await session.signIn('', '');
    await tester.pumpAndSettle();
    repository.save!.complete(Specimen({...fixture.data, 'revision': 9}));
    expect(await pending, isFalse);
    await tester.pumpAndSettle();
    expect(controller.scopes.single.name, 'reviewer-b');
    expect(controller.selected?.revision, isNot(9));
    expect(controller.mutating, isFalse);
    await tester.pumpWidget(const SizedBox());
  });
}
