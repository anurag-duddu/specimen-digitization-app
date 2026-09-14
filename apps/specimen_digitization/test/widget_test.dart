import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';

import 'workbench_harness.dart';

class TestSession implements SessionAccess {
  TestSession({this.signedIn = true});
  @override
  bool signedIn;
  final controller = StreamController<bool>.broadcast();
  @override
  Stream<bool> get changes => controller.stream;
  @override
  String get displayName => 'Synthetic reviewer';
  @override
  String get userId => 'fixture-user';
  @override
  Future<String?> token() async => 'fixture-token';
  @override
  Future<void> signIn(String email, String password) async {
    signedIn = true;
    controller.add(true);
  }

  @override
  Future<void> signOut() async {
    signedIn = false;
    controller.add(false);
  }

  @override
  Future<void> resetPassword(String email) async {}
}

const fixture = Specimen({
  'specimen_id': 'fixture-001',
  'available_actions': [
    'field',
    'transcription',
    'coverage',
    'approve',
    'classification',
    'regions',
    'retry',
  ],
  'display_name': 'Synthetic insect label',
  'revision': 3,
  'operational_state': 'completed',
  'disposition': 'needs_human_review',
  'profile_version': 'fixture-v1',
  'observations': [
    {
      'observation_id': 'o1',
      'model_id': 'Synthetic reading A',
      'region_id': 'r1',
      'literal_text': 'Chicago 1912',
    },
    {
      'observation_id': 'o2',
      'model_id': 'Synthetic reading B',
      'region_id': 'r1',
      'literal_text': 'Chicago 1917',
    },
  ],
  'disagreements': [
    {
      'region_id': 'r1',
      'alternatives': ['1912', '1917'],
      'resolved': false,
    },
  ],
  'fields': [
    {
      'field_key': 'country',
      'display_name': 'Country',
      'required': true,
      'state': 'unknown',
      'literal_value': null,
    },
  ],
  'validation_findings': [
    {
      'field_key': 'country',
      'message': 'A supported country is required',
      'severity': 'hard',
    },
  ],
  'audit_events': [
    {
      'action': 'intake',
      'actor_id': 'fixture-user',
      'created_at': '2026-09-07',
    },
  ],
});

class TestRepository implements SpecimenRepository {
  @override
  Future<Json> preflight(CollectionScope scope, IntakeFile file) async => {};
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async => SpecimenPage(
    await specimens(
      scope,
      query: filters['specimen_id'] ?? '',
      status: filters['disposition'] ?? filters['state'] ?? '',
    ),
  );

  @override
  Future<Json> artifact(
    CollectionScope scope,
    Specimen specimen,
    ArtifactRequest artifact,
  ) async => {};
  @override
  Future<HistoryPage> historyPage(
    CollectionScope scope,
    String id, {
    required int throughRevision,
    int afterRevision = 0,
  }) async => HistoryPage(items: [], throughRevision: throughRevision);
  @override
  Future<Specimen> historicalSpecimen(
    CollectionScope scope,
    String id,
    int revision, {
    String? runId,
    String? runSha256,
  }) async => fixture;
  @override
  String mode = 'synthetic';
  @override
  List<dynamic> blockers = [];
  bool conflict = false;
  Json? lastChange;
  @override
  Future<List<CollectionScope>> scopes() async => [
    const CollectionScope(
      organizationId: 'org',
      collectionId: 'insects',
      name: 'Synthetic Insects',
      permissions: ['reviewer'],
    ),
  ];
  @override
  Future<List<Json>> profiles(CollectionScope scope) async => [];
  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => query == 'missing' ? [] : [fixture];
  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async => fixture;
  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    if (conflict) throw const ApiFailure('Stale', status: 409);
    lastChange = change;
    return Specimen({...fixture.data, 'revision': 4});
  }

  @override
  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  ) async => fixture;
  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => {};
  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async => {};
  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {}
  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => {};
}

void main() {
  testWidgets(
    'unconfigured build is actionable and never claims Firebase is ready',
    (tester) async {
      await tester.pumpWidget(const SpecimenDigitizationApp());
      expect(find.text('Collection connection required'), findsOneWidget);
      expect(find.textContaining('Firebase is configured'), findsNothing);
    },
  );
  testWidgets('sign in, queue, inspect independent readings and sign out', (
    tester,
  ) async {
    final session = TestSession(signedIn: false);
    final repo = TestRepository();
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repo),
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Email address'),
      'review@example.test',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Password'),
      'fixture-only-password',
    );
    await tester.ensureVisible(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Synthetic environment.'), findsOneWidget);
    // The queue row sits below the fold, so scroll the queue list to it
    // rather than assuming it was laid out. Row heights move with the type
    // scale, so this must not depend on the header happening to be short.
    await tester.scrollUntilVisible(
      find.text('Synthetic insect label'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Synthetic insect label'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Chicago 1912', findRichText: true),
      300,
      scrollable: find
          .descendant(
            of: find.byType(ReviewWorkbench),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    expect(find.text('Chicago 1917', findRichText: true), findsOneWidget);
    await tester.tap(find.byTooltip('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Sign in to your collection'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await session.controller.close();
  });
  testWidgets(
    'narrow layout and large text retain queue and accessible navigation',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final session = TestSession();
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: TestRepository()),
      );
      await tester.pumpAndSettle();
      expect(find.byType(NavigationBar), findsOneWidget);

      final semantics = tester.ensureSemantics();
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      semantics.dispose();
      await tester.pumpWidget(const SizedBox());
      await session.controller.close();
    },
  );
  testWidgets(
    'a correction is made in place, batched, and saved with one reason',
    (tester) async {
      useWindow(tester, largeWindow);
      final saved = <Json>[];
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: fixture,
            onChange: (c) async {
              saved.add(c);
              return true;
            },
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Fields'));
      await tester.pumpAndSettle();
      // Tapping a layer turns it into an editor in place, with the
      // photograph still on screen (audit finding H6.2).
      await scrollAndTap(tester, find.byTooltip('Edit as written').first);
      expect(find.text('Correct Country'), findsOneWidget);
      await tester.tap(find.text('Keep this correction'));
      await tester.pumpAndSettle();
      // Nothing reached the server yet: the correction is pending.
      expect(saved, isEmpty);
      expect(find.text('1 pending change'), findsWidgets);

      await tester.tap(find.text('Save 1 pending change').last);
      await tester.pumpAndSettle();
      final save = find.descendant(
        of: find.byType(ReasonForm),
        matching: find.widgetWithText(FilledButton, 'Save 1 pending change'),
      );
      expect(tester.widget<FilledButton>(save).onPressed, isNull);
      expect(saved, isEmpty);
      await tester.enterText(
        find.widgetWithText(TextField, 'Reason'),
        'No country appears in the original label',
      );
      await tester.pumpAndSettle();
      await tester.tap(save);
      await tester.pumpAndSettle();
      expect(saved, hasLength(1));
      expect(saved.single['state'], 'unknown');
      expect(saved.single['value'], isNull);
      expect(saved.single['target_id'], 'country');
      expect(saved.single['reason'], contains('No country'));
    },
  );

  testWidgets('five corrections save under one reason, in one action', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    final saved = <Json>[];
    final many = Specimen({
      ...fixture.data,
      'fields': [
        for (var i = 0; i < 5; i++)
          {
            'field_key': 'field_$i',
            'display_name': 'Field $i',
            'required': true,
            'state': 'unknown',
            'literal_value': null,
          },
      ],
      'validation_findings': const <Json>[],
    });
    await tester.pumpWidget(
      workbenchHost(
        ReviewWorkbench(
          specimen: many,
          onChange: (c) async {
            saved.add(c);
            return true;
          },
          onRetry: (_) async {},
          onRefresh: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fields'));
    await tester.pumpAndSettle();
    for (var i = 0; i < 5; i++) {
      // One row per field: the nth edit control belongs to the nth field.
      await scrollAndTap(tester, find.byTooltip('Edit as written').at(i));
      await tester.tap(find.text('Keep this correction'));
      await tester.pumpAndSettle();
    }
    expect(find.text('5 pending changes'), findsWidgets);
    await tester.tap(find.text('Save 5 pending changes').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Reason'),
      'Nothing on the label supports these fields',
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(ReasonForm),
        matching: find.widgetWithText(FilledButton, 'Save 5 pending changes'),
      ),
    );
    await tester.pumpAndSettle();
    // One reason, one user action. The wire takes one decision per call, so
    // the batch is five calls carrying the same reason.
    expect(saved, hasLength(5));
    expect(saved.map((c) => c['reason']).toSet(), {
      'Nothing on the label supports these fields',
    });
    expect(saved.map((c) => c['target_id']).toSet(), {
      'field_0',
      'field_1',
      'field_2',
      'field_3',
      'field_4',
    });
  });

  testWidgets('future field state remains visible and editing is disabled', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    final future = Specimen({
      ...fixture.data,
      'fields': [
        {
          'field_key': 'country',
          'display_name': 'Country',
          'state': 'future_state',
          'required': true,
        },
      ],
    });
    await tester.pumpWidget(
      workbenchHost(
        ReviewWorkbench(
          specimen: future,
          onChange: (_) async => false,
          onRetry: (_) async {},
          onRefresh: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fields'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Country (required)'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(
      find.text('This field cannot be edited in this version of the app.'),
      findsOneWidget,
    );
    // The rest of the caveat sits behind "Why" and must still be reachable.
    await tester.tap(find.text('Why').last);
    await tester.pumpAndSettle();
    expect(
      find.textContaining(
        'The server sent a field state this app does not recognize.',
      ),
      findsOneWidget,
    );
    expect(find.byTooltip('Edit as written'), findsNothing);
    // The state the server sent is still shown, never swallowed.
    expect(find.text('State unknown'), findsWidgets);
  });

  testWidgets('viewer cannot invoke reviewer controls, and hears why', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    await tester.pumpWidget(
      workbenchHost(
        ReviewWorkbench(
          specimen: fixture,
          canReview: false,
          canOperate: false,
          onChange: (_) async => false,
          onRetry: (_) async {},
          onRefresh: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    for (final label in ['Approve record', 'Confirm label coverage']) {
      expect(buttonWithLabel(tester, label).onPressed, isNull);
      final tooltip = find
          .ancestor(of: find.text(label), matching: find.byType(Tooltip))
          .evaluate()
          .map((e) => (e.widget as Tooltip).message)
          .whereType<String>();
      expect(
        tooltip.any((m) => m.contains('does not include reviewing')),
        isTrue,
        reason: 'the disabled reason must be on the control itself',
      );
    }
    await tester.tap(find.text('Fields'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Retry processing'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(buttonWithLabel(tester, 'Retry processing').onPressed, isNull);
  });

  testWidgets(
    'resolving a transcription keeps both readings on screen and never '
    'invents text',
    (tester) async {
      useWindow(tester, largeWindow);
      Json? saved;
      final specimen = Specimen({
        ...fixture.data,
        'regions': [
          {
            'region_id': 'r1',
            'bbox': [0, 0, 10, 10],
          },
        ],
      });
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: specimen,
            onChange: (c) async {
              saved = c;
              return true;
            },
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      await scrollAndTap(tester, find.text('Resolve transcription'));
      // Both readings are visible beside the field, not behind it.
      expect(find.text('Synthetic reading A'), findsWidgets);
      expect(find.text('Synthetic reading B'), findsWidgets);
      await tester.tap(find.byType(DropdownButtonFormField<String>).last);
      await tester.pumpAndSettle();
      expect(find.text('Not applicable'), findsNothing);
      await tester.tap(find.text('Unreadable').last);
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextField, 'Reason'),
        'Source damaged; no supported reading',
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.widgetWithText(FilledButton, 'Resolve transcription'),
      );
      await tester.pumpAndSettle();
      expect(saved?['state'], 'unreadable');
      expect(saved?['value'], isNull);
    },
  );

  testWidgets(
    'server action list restricts reviews while permitting operator retry',
    (tester) async {
      useWindow(tester, largeWindow);
      final specimen = Specimen({
        ...fixture.data,
        'available_actions': ['retry'],
      });
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: specimen,
            onChange: (_) async => false,
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(buttonWithLabel(tester, 'Approve record').onPressed, isNull);
      expect(
        buttonWithLabel(tester, 'Confirm label coverage').onPressed,
        isNull,
      );
      await tester.tap(find.text('Fields'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Retry processing'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(buttonWithLabel(tester, 'Retry processing').onPressed, isNotNull);
    },
  );
}
