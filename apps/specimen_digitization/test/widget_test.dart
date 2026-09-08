import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workbench.dart';

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
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.textContaining('SYNTHETIC ENVIRONMENT'), findsOneWidget);
    await tester.tap(find.text('Synthetic insect label'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Chicago 1912'),
      300,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Chicago 1917'), findsOneWidget);
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
  testWidgets('critical correction requires reason and source support', (
    tester,
  ) async {
    Json? saved;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReviewWorkbench(
            specimen: fixture,
            onChange: (c) async => saved = c,
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      ),
    );
    await tester.scrollUntilVisible(
      find.text('Fields & evidence'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Fields & evidence'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Country *'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Country *'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Correct supported value'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Correct supported value'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save and revalidate'));
    await tester.pumpAndSettle();
    expect(find.text('A reason is required.'), findsOneWidget);
    expect(saved, isNull);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Reason for decision'),
      'No country appears in the original label',
    );
    await tester.tap(find.text('Save and revalidate'));
    await tester.pumpAndSettle();
    expect(saved?['state'], 'unknown');
    expect(saved?['value'], isNull);
    expect(saved?['reason'], contains('No country'));
  });
  testWidgets('future field state remains visible and editing is disabled', (
    tester,
  ) async {
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
      MaterialApp(
        home: Scaffold(
          body: ReviewWorkbench(
            specimen: future,
            onChange: (_) async {},
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      ),
    );
    await tester.scrollUntilVisible(
      find.text('Fields & evidence'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Fields & evidence'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Country *'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Country *'));
    await tester.pumpAndSettle();
    expect(
      find.text(
        'Unsupported field state. Editing is disabled; refresh or update the client.',
      ),
      findsOneWidget,
    );
    expect(
      tester
          .widget<ButtonStyleButton>(
            find
                .ancestor(
                  of: find.text('Correct supported value'),
                  matching: find.byWidgetPredicate(
                    (w) => w is ButtonStyleButton,
                  ),
                )
                .first,
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets('viewer cannot invoke reviewer controls or run retry', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReviewWorkbench(
            specimen: fixture,
            canReview: false,
            canOperate: false,
            onChange: (_) async {},
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      ),
    );
    expect(
      tester
          .widget<ButtonStyleButton>(
            find
                .ancestor(
                  of: find.text('Record review approval'),
                  matching: find.byWidgetPredicate(
                    (w) => w is ButtonStyleButton,
                  ),
                )
                .first,
          )
          .onPressed,
      isNull,
    );
    expect(
      tester
          .widget<ButtonStyleButton>(
            find
                .ancestor(
                  of: find.text('Retry processing'),
                  matching: find.byWidgetPredicate(
                    (w) => w is ButtonStyleButton,
                  ),
                )
                .first,
          )
          .onPressed,
      isNull,
    );
    expect(
      tester
          .widget<ButtonStyleButton>(
            find
                .ancestor(
                  of: find.text('Correct label regions'),
                  matching: find.byWidgetPredicate(
                    (w) => w is ButtonStyleButton,
                  ),
                )
                .first,
          )
          .onPressed,
      isNull,
    );
  });
  testWidgets(
    'transcription editor records unreadable state without inventing text',
    (tester) async {
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
        MaterialApp(
          home: Scaffold(
            body: ReviewWorkbench(
              specimen: specimen,
              onChange: (c) async => saved = c,
              onRetry: (_) async {},
              onRefresh: () {},
            ),
          ),
        ),
      );
      await tester.scrollUntilVisible(
        find.text('Adjudicate literal transcription'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Adjudicate literal transcription'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      expect(find.text('not applicable'), findsNothing);
      await tester.tap(find.text('unreadable').last);
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Reason for decision'),
        'Source damaged; no supported reading',
      );
      await tester.tap(find.text('Save and revalidate'));
      await tester.pumpAndSettle();
      expect(saved?['state'], 'unreadable');
      expect(saved?['value'], isNull);
    },
  );
  testWidgets(
    'server action list restricts reviews while permitting operator retry',
    (tester) async {
      final specimen = Specimen({
        ...fixture.data,
        'available_actions': ['retry'],
      });
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ReviewWorkbench(
              specimen: specimen,
              canReview: true,
              canOperate: true,
              onChange: (_) async {},
              onRetry: (_) async {},
              onRefresh: () {},
            ),
          ),
        ),
      );
      ButtonStyleButton button(String label) =>
          tester.widget<ButtonStyleButton>(
            find
                .ancestor(
                  of: find.text(label),
                  matching: find.byWidgetPredicate(
                    (w) => w is ButtonStyleButton,
                  ),
                )
                .first,
          );
      expect(button('Record review approval').onPressed, isNull);
      expect(button('Confirm label coverage').onPressed, isNull);
      expect(button('Retry processing').onPressed, isNotNull);
    },
  );
}
