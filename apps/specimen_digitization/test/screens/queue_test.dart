// The queue (screen blueprints, section 3).
//
// Empty and loading states, active filter chips, and the keyboard map.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_digitization/src/workspace.dart';

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
    // 13 section 4.2: the header states the count as a numeral with its unit
    // and what the loaded page is made of under it. The whole sentence is
    // still what the live region announces, which is the line a screen reader
    // hears when the count moves.
    expect(find.text('0'), findsOneWidget);
    expect(find.text('RECORDS'), findsOneWidget);
    expect(find.text('0 need review, 0 blocked.'), findsOneWidget);
    expect(
      tester.getSemantics(find.text('0 need review, 0 blocked.')).label,
      '0 records loaded. 0 need review, 0 blocked.',
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a search with no match names the filters, not the collection', (
    tester,
  ) async {
    final ScriptedRepository repository = ScriptedRepository();
    await pumpQueue(tester, repository);
    await tester.enterText(find.byType(UiSearchField), 'SD-does-not-exist');
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
    expect(find.byType(UiSkeleton), findsWidgets);
    expect(
      find.descendant(
        of: find.byType(QueueScreen),
        matching: find.byType(UiProgress),
      ),
      findsNothing,
      reason:
          'a first load is placeholders in the shape of the rows; the '
          'shell above the screen may show its own collection indicator',
    );
    repository.gate!.complete();
    await tester.pumpAndSettle();
    expect(find.byType(UiSkeleton), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('an active filter is a chip, and removing the chip refilters', (
    tester,
  ) async {
    final ScriptedRepository repository = ScriptedRepository();
    await pumpQueue(tester, repository);
    await tester.tap(find.text('Filters'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.descendant(
        of: find.byWidgetPredicate(
          (Widget widget) =>
              widget is UiField && widget.label == 'Upload batch',
        ),
        matching: find.byType(EditableText),
      ),
      'batch-7',
    );
    await tester.tap(find.text('Apply'));
    await tester.pumpAndSettle();

    expect(find.text('Upload batch: batch-7'), findsOneWidget);
    // The count is on the badge beside the button, so the button keeps one
    // name and a reader hears the count once.
    expect(find.bySemanticsLabel('1 filter active'), findsOneWidget);
    expect(repository.requests.last['batch_id'], 'batch-7');

    await tester.tap(find.bySemanticsLabel('Remove the Upload batch filter'));
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

  // The queue at compact (13 section 4.2). A phone has room for a header, a
  // search row and the rows: six disposition chips above the list are the
  // region that pushed the first row to 763 of 844 at 200 percent text, so
  // they are in the filter sheet there, with the chosen one on a chip that
  // survives the sheet closing (pass criterion 6.4).
  group('at compact', () {
    Future<TestSession> pumpPhone(
      WidgetTester tester,
      ScriptedRepository repository,
    ) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.reset);
      final TestSession session = TestSession();
      addTearDown(session.controller.close);
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: repository),
      );
      await tester.pumpAndSettle();
      return session;
    }

    testWidgets('the dispositions are in the sheet, not above the list', (
      tester,
    ) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpPhone(tester, repository);

      expect(
        find.text('Needs review'),
        findsNothing,
        reason: 'the six chips are not a region of the page on a phone',
      );

      await tester.tap(find.text('Filters'));
      await tester.pumpAndSettle();
      expect(find.text(searchFiltersTitle), findsOneWidget);
      expect(
        find.text(queueDispositionLabel),
        findsWidgets,
        reason: 'the sheet is where a phone chooses the disposition',
      );
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a chosen disposition stays visible once the sheet closes', (
      tester,
    ) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpPhone(tester, repository);
      final WorkspaceController controller = WorkspaceScope.read(
        tester.element(find.byType(QueuePane)),
      );
      await controller.selectDisposition('cleared');
      // Single frames, not a settle: the header ages its own freshness line
      // once a second for as long as there is an answer to age, so a queue
      // that has been answered never reaches a still frame.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(
        find.text('$queueDispositionLabel: Cleared'),
        findsOneWidget,
        reason:
            'a filter must never be invisible once the sheet closes (audit, '
            'pass criterion 6.4)',
      );
      expect(
        repository.requests.last['disposition'],
        'cleared',
        reason: 'the chip is the filter the server was asked for',
      );
      await tester.pumpWidget(const SizedBox());
    });
  });
}
