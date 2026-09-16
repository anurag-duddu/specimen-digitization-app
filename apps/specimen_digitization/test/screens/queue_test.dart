// The queue (screen blueprints, section 3).
//
// Empty and loading states, active filter chips, and the keyboard map.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../widget_test.dart' show TestRepository, TestSession;

/// A collection that answers whatever the test set on it.
class ScriptedRepository extends TestRepository {
  List<Specimen> results = <Specimen>[];
  Completer<void>? gate;
  final List<Map<String, String>> requests = <Map<String, String>>[];

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    requests.add(Map<String, String>.from(filters));
    if (gate != null) await gate!.future;
    return SpecimenPage(results);
  }
}

/// The window the queue is tested in: wide enough for a row, narrow enough to
/// stay a single pane.
const Size queueWindow = Size(800, 1400);

Future<TestSession> pumpQueue(
  WidgetTester tester,
  ScriptedRepository repository, {
  bool settle = true,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = queueWindow;
  addTearDown(tester.view.reset);
  final TestSession session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(session: session, repository: repository),
  );
  if (settle) await tester.pumpAndSettle();
  return session;
}

String locationOf(WidgetTester tester) => GoRouter.of(
  tester.element(find.byType(Navigator).first),
).routerDelegate.currentConfiguration.uri.toString();

void main() {
  testWidgets('an empty collection names the absence and offers intake', (
    tester,
  ) async {
    await pumpQueue(tester, ScriptedRepository());
    expect(find.text('No specimens yet'), findsOneWidget);
    expect(find.text('Add photographs'), findsOneWidget);
    expect(
      find.text('0 records loaded. 0 need review, 0 blocked.'),
      findsOneWidget,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a search with no match names the filters, not the collection', (
    tester,
  ) async {
    final ScriptedRepository repository = ScriptedRepository();
    await pumpQueue(tester, repository);
    await tester.enterText(
      find.widgetWithText(TextField, 'Search by specimen ID'),
      'SD-does-not-exist',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.text('No records match these filters'), findsOneWidget);
    expect(find.text('Clear all'), findsWidgets);
    expect(repository.requests.last['specimen_id'], 'SD-does-not-exist');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the first load shows placeholder rows, not a spinner', (
    tester,
  ) async {
    final ScriptedRepository repository = ScriptedRepository()
      ..gate = Completer<void>();
    await pumpQueue(tester, repository, settle: false);
    await tester.pump();
    await tester.pump();
    expect(find.byType(SkeletonRow), findsWidgets);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    repository.gate!.complete();
    await tester.pumpAndSettle();
    expect(find.byType(SkeletonRow), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('an active filter is a chip, and removing the chip refilters', (
    tester,
  ) async {
    final ScriptedRepository repository = ScriptedRepository();
    await pumpQueue(tester, repository);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Filters'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Upload batch'),
      'batch-7',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Apply'));
    await tester.pumpAndSettle();

    expect(find.text('Upload batch: batch-7'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Filters (1)'), findsOneWidget);
    expect(repository.requests.last['batch_id'], 'batch-7');

    await tester.tap(find.byTooltip('Remove the Upload batch filter'));
    await tester.pumpAndSettle();
    expect(find.text('Upload batch: batch-7'), findsNothing);
    expect(repository.requests.last.containsKey('batch_id'), isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('J selects a record and Enter opens it', (tester) async {
    final ScriptedRepository repository = ScriptedRepository()
      ..results = <Specimen>[
        const Specimen({
          'specimen_id': 'SD-1',
          'filename': 'First record',
          'disposition': 'cleared',
        }),
        const Specimen({
          'specimen_id': 'SD-2',
          'filename': 'Second record',
          'disposition': 'cleared',
        }),
      ];
    await pumpQueue(tester, repository);
    expect(find.text('First record'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.keyJ);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.keyJ);
    await tester.pump();
    expect(locationOf(tester), endsWith('/queue'));

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    expect(locationOf(tester), endsWith('/queue/SD-2'));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('slash moves focus into the search field', (tester) async {
    await pumpQueue(tester, ScriptedRepository());
    await tester.sendKeyEvent(LogicalKeyboardKey.slash);
    await tester.pump();
    final FocusNode? focused = FocusManager.instance.primaryFocus;
    expect(focused?.debugLabel, 'Queue search');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('F opens the filter sheet', (tester) async {
    await pumpQueue(tester, ScriptedRepository());
    await tester.sendKeyEvent(LogicalKeyboardKey.keyF);
    await tester.pumpAndSettle();
    expect(find.text('Filter the queue'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a queue row fits the 360 dp list pane', (tester) async {
    final ScriptedRepository repository = ScriptedRepository()
      ..results = <Specimen>[
        const Specimen({
          'specimen_id': 'SD-1',
          'filename': 'First record',
          'disposition': 'needs_human_review',
        }),
      ];
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1300, 1000);
    addTearDown(tester.view.reset);
    final TestSession session = TestSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repository),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
