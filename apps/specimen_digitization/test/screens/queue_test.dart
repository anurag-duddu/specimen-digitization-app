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
import 'package:specimen_digitization/src/theme/app_theme.dart';
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

  // PLAN section 3, "Client": a record with no disposition is drawn from the
  // `status` the search endpoint sends, and a record that sends nothing is a
  // record state the client cannot name, never the field state "Unknown".
  testWidgets('a row with no disposition shows the operational state', (
    tester,
  ) async {
    final ScriptedRepository repository = ScriptedRepository()
      ..results = <Specimen>[
        const Specimen({
          'specimen_id': 'SD-1',
          'filename': 'Waiting record',
          'status': 'retry_scheduled',
          'disposition': null,
        }),
        const Specimen({
          'specimen_id': 'SD-2',
          'filename': 'Paused record',
          'status': 'paused',
          'disposition': null,
        }),
        const Specimen({'specimen_id': 'SD-3', 'filename': 'Silent record'}),
      ];
    await pumpQueue(tester, repository);
    expect(find.text('Retry scheduled'), findsOneWidget);
    expect(find.text('Paused'), findsOneWidget);
    expect(find.text('State unknown'), findsOneWidget);
    expect(
      find.text('Unknown'),
      findsNothing,
      reason: 'a field state is never drawn as a record state',
    );
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

  group('the search row', () {
    Future<void> pumpAt(
      WidgetTester tester,
      ScriptedRepository repository,
      Size window, {
      double textScale = 1.0,
    }) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = window;
      addTearDown(tester.view.reset);
      tester.platformDispatcher.textScaleFactorTestValue = textScale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final TestSession session = TestSession();
      addTearDown(session.controller.close);
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: repository),
      );
      await tester.pumpAndSettle();
    }

    /// The search row inside the bar that sticks, wherever the route is.
    Finder stuckSearch() => find.ancestor(
      of: find.byType(UiSearchField, skipOffstage: false),
      matching: find.byType(UiStickyBar, skipOffstage: false),
    );

    List<Specimen> page(int count) => <Specimen>[
      for (int i = 1; i <= count; i++)
        Specimen(<String, dynamic>{
          'specimen_id': 'SD-$i',
          'filename': 'Record $i',
          'disposition': 'cleared',
        }),
    ];

    testWidgets('sticks at medium at every text scale, at its own height', (
      tester,
    ) async {
      // 13 sections 3.5 and 4.2, and the arithmetic on `searchRowSticks`: a
      // portrait tablet pins 124 dp at default type and 137.75 at 200 percent
      // of the 245.76 its 24 percent allows, so the row fits at every size.
      for (final double scale in <double>[1.0, 1.3, 2.0]) {
        await pumpAt(
          tester,
          ScriptedRepository()..results = page(30),
          const Size(768, 1024),
          textScale: scale,
        );
        expect(stuckSearch(), findsOneWidget, reason: 'at x$scale');
        // The extent is the row's own height and nothing around it: a sticky
        // bar shorter than its row clips the field, and one taller spends
        // budget on air.
        final UiStickyBar bar = tester.widget<UiStickyBar>(stuckSearch());
        expect(
          bar.extent,
          closeTo(tester.getSize(find.byType(UiSearchField)).height, 0.5),
          reason: 'the extent is the row at x$scale',
        );
        // Scrolled to the end, the row is still on screen, at the top of
        // the list, which is what stuck means.
        final ScrollableState state = tester.state<ScrollableState>(
          find
              .descendant(
                of: find.byType(CustomScrollView).first,
                matching: find.byType(Scrollable),
              )
              .first,
        );
        state.position.jumpTo(state.position.maxScrollExtent);
        await tester.pumpAndSettle();
        expect(
          tester.getRect(find.byType(UiSearchField)).top,
          closeTo(tester.getRect(find.byType(CustomScrollView).first).top, 0.5),
          reason: 'the row is stuck under the header at x$scale',
        );
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('scrolls at compact and from expanded up', (tester) async {
      // Compact is slot A3's decision: 185.75 of 236.3 already pinned at 200
      // percent on a phone, and the row is 69.75. Expanded and large are 20
      // percent of a landscape window, 191.5 of 164 and 191 of 180 at 200
      // percent with the row stuck, and a variant is chosen per class.
      for (final Size window in <Size>[
        const Size(390, 844),
        const Size(1180, 820),
        const Size(1440, 900),
      ]) {
        await pumpAt(tester, ScriptedRepository()..results = page(3), window);
        expect(find.byType(UiSearchField), findsOneWidget, reason: '$window');
        expect(stuckSearch(), findsNothing, reason: '$window');
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('pins nothing under a record pushed over it', (tester) async {
      await pumpAt(
        tester,
        ScriptedRepository()..results = page(1),
        const Size(768, 1024),
      );
      expect(stuckSearch(), findsOneWidget);
      await tester.tap(find.text('Record 1'));
      await tester.pumpAndSettle();
      expect(find.byType(WorkbenchScreen), findsOneWidget);
      // The queue stays mounted beneath the record, and a region a covered
      // screen pins is height the reader never sees and height the record's
      // own chrome budget would be charged for.
      expect(
        stuckSearch(),
        findsNothing,
        reason: 'a covered screen holds no viewport height',
      );
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('run states in the filter sheet (UI.md T3.3)', () {
    WorkspaceController controllerOf(WidgetTester tester) =>
        WorkspaceScope.read(tester.element(find.byType(QueuePane)));

    testWidgets('a run state from the sheet returns a state chip to All', (
      tester,
    ) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      final WorkspaceController controller = controllerOf(tester);
      await controller.selectDisposition('running');
      await controller.applyFilters(<String, String>{'state': 'paused'});
      await tester.pump();
      expect(controller.disposition, isEmpty);
      expect(repository.requests.last, <String, String>{'state': 'paused'});
    });

    testWidgets("a state chip clears the sheet's run state", (tester) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      final WorkspaceController controller = controllerOf(tester);
      await controller.applyFilters(<String, String>{'state': 'paused'});
      await controller.selectDisposition('processing_blocked');
      await tester.pump();
      expect(controller.filters.containsKey('state'), isFalse);
      expect(repository.requests.last, <String, String>{
        'state': 'processing_blocked',
      });
    });

    testWidgets("a queue chip keeps the sheet's run state", (tester) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      final WorkspaceController controller = controllerOf(tester);
      await controller.applyFilters(<String, String>{'state': 'paused'});
      await controller.selectDisposition('needs_human_review');
      await tester.pump();
      expect(repository.requests.last, <String, String>{
        'state': 'paused',
        'disposition': 'needs_human_review',
      });
    });

    testWidgets('an active filter names its value in words', (tester) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      final WorkspaceController controller = controllerOf(tester);
      await controller.applyFilters(<String, String>{
        'state': 'retry_scheduled',
        'reason_code': 'human_approval_required',
      });
      // Single frames, not a settle: the header ages its freshness line.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Run state: Retry scheduled'), findsOneWidget);
      expect(find.text('Issue: Reviewer approval needed'), findsOneWidget);
      expect(find.textContaining('retry_scheduled'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the sheet offers every run state the search filters', (
      tester,
    ) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1000, 2400);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(
            body: SingleChildScrollView(
              child: SearchFilters(initial: <String, String>{}),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final UiSelect<String> state = tester.widget<UiSelect<String>>(
        find.byWidgetPredicate(
          (Widget w) => w is UiSelect<String> && w.label == 'Run state',
        ),
      );
      expect(
        <String, String>{
          for (final UiSelectOption<String> option in state.options)
            if (option.value.isNotEmpty) option.value: option.label,
        },
        <String, String>{
          'running': 'Processing',
          'completed': 'Completed',
          'processing_blocked': 'Blocked',
          'retry_scheduled': 'Retry scheduled',
          'paused': 'Paused',
          'cancelled': 'Cancelled',
        },
      );
    });
  });
}
