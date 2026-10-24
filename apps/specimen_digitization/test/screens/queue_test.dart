// The queue (screen blueprints, section 3).
//
// Empty and loading states, queue choices, and the keyboard map.

import 'dart:async';

import 'package:flutter/foundation.dart' show defaultTargetPlatform;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/shell.dart' show AppShell;
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_digitization/src/widgets/status_chip.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../widget_test.dart' show TestRepository, TestSession, fixture;
import '../ui_finders.dart';
import '../widgets/harness.dart' show pumpComponent;

/// A collection that answers whatever the test set on it.
class ScriptedRepository extends TestRepository {
  List<Specimen> results = <Specimen>[];
  Completer<void>? gate;
  final List<Map<String, String>> requests = <Map<String, String>>[];

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async => Specimen(
    {...fixture.data, ...results.firstWhere((record) => record.id == id).data},
  );

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
  Size window = queueWindow,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
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
  group('queue issue summaries', () {
    for (final entry in {
      'mandatory_unresolved:taxon': 'Taxon needs a supported value',
      'mandatory_unresolved:date_visited_from':
          'Collection start date needs a supported value',
      'mandatory_unresolved:collection_code':
          'Collection code needs a supported value',
      'mandatory_evidence_unresolved:collectors':
          'Collectors need supporting evidence',
      'a_future_check:internal_field': 'Review the recorded issue',
    }.entries) {
      test(
        'list-only ${entry.key} has readable copy without field payloads',
        () {
          final record = Specimen({
            'specimen_id': 'list-only',
            'disposition': 'needs_human_review',
            'reason_codes': ['human_approval_required', entry.key],
          });
          expect(queueReason(record), entry.value);
        },
      );
    }
    test('blocking correction precedes a nonblocking finding', () {
      final record = Specimen({
        'specimen_id': 'prioritized',
        'validation_findings': [
          {'severity': 'warning', 'message': 'Check the spelling'},
          {'severity': 'hard', 'reason_code': 'mandatory_unresolved:country'},
        ],
      });
      expect(queueReason(record), 'Country needs a supported value');
    });
    test('shared queue disposition is not repeated as an issue', () {
      expect(
        queueReason(
          const Specimen({
            'specimen_id': 'baseline',
            'reason_codes': ['human_approval_required', 'needs_human_review'],
          }),
        ),
        isEmpty,
      );
    });
  });

  testWidgets(
    'wide queue gives the working list the main area and opens a record',
    (tester) async {
      final repository = ScriptedRepository()
        ..results = const [
          Specimen({
            'specimen_id': 'SD-1',
            'filename': 'First record',
            'disposition': 'needs_human_review',
          }),
          Specimen({
            'specimen_id': 'SD-2',
            'filename': 'Second record',
            'disposition': 'needs_human_review',
          }),
        ];
      await pumpQueue(tester, repository, window: const Size(1440, 900));
      expect(find.byType(UiBrandHero), findsNothing);
      expect(find.text('#First record'), findsOneWidget);
      expect(find.text('Review queue'), findsOneWidget);
      final heading = tester.getRect(find.text('Review queue'));
      final search = tester.getRect(find.byType(UiSearchField));
      final ui = tester.element(find.byType(QueuePane)).ui;
      expect(search.left, heading.left);
      expect(search.width, ui.space.readingMax);
      final selector = tester.getRect(
        find.byKey(const ValueKey<String>('queue-view')),
      );
      expect(selector.width, lessThan(search.width));
      final command = tester.getRect(uiIconButton('Select specimens'));
      expect(command.top, heading.top);
      await tester.tap(find.text('#First record'));
      await tester.pumpAndSettle();
      expect(locationOf(tester), endsWith('/queue/SD-1'));
      expect(find.byType(WorkbenchScreen), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('a loading wide queue does not claim the collection is empty', (
    tester,
  ) async {
    final repository = ScriptedRepository()..gate = Completer<void>();
    await pumpQueue(
      tester,
      repository,
      window: const Size(1440, 900),
      settle: false,
    );
    await tester.pump();
    await tester.pump();
    expect(find.byType(UiSkeleton), findsWidgets);
    expect(find.text('Open first record'), findsNothing);
    expect(find.text('No specimens yet'), findsNothing);
    repository.gate!.complete();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  for (final width in [320.0, 390.0, 768.0, 1180.0, 1440.0]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('a populated queue remains readable at $width and $scale', (
        tester,
      ) async {
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final repository = ScriptedRepository()
          ..results = const [
            Specimen({
              'specimen_id': 'SD-summary',
              'filename': 'Collection specimen with a long reference',
              'disposition': 'needs_human_review',
              'reason_codes': [
                'human_approval_required',
                'mandatory_unresolved:taxon',
              ],
              'updated_at': '2026-10-20T13:45:00Z',
            }),
          ];
        await pumpQueue(tester, repository, window: Size(width, 1000));
        expect(find.byType(UiBrandHero), findsNothing);
        final view = find.byKey(const ValueKey<String>('queue-view'));
        expect(view.hitTestable(), findsOneWidget);
        final row = find.byKey(const ValueKey<String>('queue-row-SD-summary'));
        await tester.ensureVisible(row);
        await tester.pumpAndSettle();
        expect(row.hitTestable(), findsOneWidget);
        expect(find.text('Taxon needs a supported value'), findsOneWidget);
        expect(find.textContaining('mandatory_unresolved'), findsNothing);
        expect(find.textContaining('Updated '), findsNothing);
        expect(find.byType(StatusChip), findsNothing);
        expect(
          tester.getSize(row).height,
          greaterThanOrEqualTo(UiDensity.hitBox),
        );
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
      });
    }
  }

  group('queue status controls', () {
    testWidgets('All specimens to Cleared keeps the view in keyboard order', (
      tester,
    ) async {
      final repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      final controller = WorkspaceScope.read(
        tester.element(find.byType(QueuePane)),
      );
      await controller.selectDisposition('');
      await tester.pumpAndSettle();
      FocusNode viewNode(String label) => tester
          .widget<Pressable>(
            find.byWidgetPredicate(
              (widget) => widget is Pressable && widget.semanticsLabel == label,
            ),
          )
          .focusNode!;
      viewNode('All specimens').requestFocus();
      await tester.pumpAndSettle();
      for (var i = 0; i < 3; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
        await tester.pump();
      }
      final cleared = viewNode('Cleared');
      expect(FocusManager.instance.primaryFocus, same(cleared));
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(repository.requests.last['disposition'], 'cleared');
      expect(find.text('All specimens'), findsNothing);
      expect(FocusManager.instance.primaryFocus, same(cleared));
      expect(
        [
          'Needs review',
          'Deferred',
          'Cleared',
        ].where((label) => !viewNode(label).skipTraversal),
        ['Cleared'],
      );
      tester
          .widget<EditableText>(find.byType(EditableText))
          .focusNode
          .requestFocus();
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus, same(cleared));
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(repository.requests.last['disposition'], 'deferred');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('supported status controls retain their backend meanings', (
      tester,
    ) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      expect(repository.requests.last['disposition'], 'needs_human_review');
      for (final entry in {
        'needs_human_review': 'Needs review',
        'deferred': 'Deferred',
        'cleared': 'Cleared',
      }.entries) {
        await pickSpecimenQueue(tester, entry.value);
        expect(repository.requests.last['disposition'], entry.key);
        expect(repository.requests.last.containsKey('state'), isFalse);
        expect(find.text(entry.value), findsOneWidget);
      }
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('status views can be selected with the keyboard', (
      tester,
    ) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      final semantics = tester.ensureSemantics();
      final target = find.byWidgetPredicate(
        (widget) =>
            widget is Pressable && widget.semanticsLabel == 'Needs review',
      );
      tester.widget<Pressable>(target).focusNode!.requestFocus();
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(repository.requests.last['disposition'], 'deferred');
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(repository.requests.last['disposition'], 'cleared');
      expect(
        tester.getSemantics(find.bySemanticsLabel('Cleared')),
        containsSemantics(isChecked: true, isInMutuallyExclusiveGroup: true),
      );
      semantics.dispose();
      await tester.pumpWidget(const SizedBox());
    });
  });

  testWidgets('empty review views name the absence with no action', (
    tester,
  ) async {
    await pumpQueue(tester, ScriptedRepository());
    final pane = find.byType(QueuePane);
    for (final view in {
      'Needs a human': 'No specimens need a human',
      'Deferred': 'No deferred specimens',
      'Cleared': 'No cleared specimens',
    }.entries) {
      await pickSpecimenQueue(tester, view.key);
      expect(find.text(view.value), findsOneWidget);
      // The one empty state component, as every other absence in the app
      // (10 section 4.5), rather than a bare line of text.
      expect(
        find.descendant(
          of: pane,
          matching: find.ancestor(
            of: find.text(view.value),
            matching: find.byType(UiEmptyState),
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(of: pane, matching: find.byType(UiButton)),
        findsNothing,
      );
      expect(find.text('Add specimens or choose another view.'), findsNothing);
      expect(find.text('0 records loaded'), findsNothing);
    }
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('an unfiltered empty collection retains its add action', (
    tester,
  ) async {
    await pumpQueue(tester, ScriptedRepository());
    final controller = WorkspaceScope.read(
      tester.element(find.byType(QueuePane)),
    );
    await controller.selectDisposition('');
    await tester.pumpAndSettle();
    expect(find.text('No specimens yet'), findsOneWidget);
    expect(find.text('Add specimens'), findsOneWidget);
    expect(find.text('Reset search'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'a search with no match names the absence without technical filters',
    (tester) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      await tester.enterText(find.byType(UiSearchField), '105526321');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      expect(find.text('No matching records'), findsOneWidget);
      expect(find.text('Reset search'), findsWidgets);
      expect(repository.requests.last['display_reference'], '105526321');
      await tester.tap(find.text('Reset search'));
      await tester.pumpAndSettle();
      expect(find.text('No specimens need a human'), findsOneWidget);
      expect(find.text('Reset search'), findsNothing);
      expect(
        repository.requests.last.containsKey('display_reference'),
        isFalse,
      );
      expect(repository.requests.last['disposition'], 'needs_human_review');
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'the search keeps UUID input separate from displayed references',
    (tester) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpQueue(tester, repository);
      await tester.enterText(
        find.byType(UiSearchField),
        '10000000-0000-4000-8000-000000000001',
      );
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      expect(
        repository.requests.last['specimen_id'],
        '10000000-0000-4000-8000-000000000001',
      );
      expect(
        repository.requests.last.containsKey('display_reference'),
        isFalse,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

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

  testWidgets('existing filter API remains compatible without a Queue form', (
    tester,
  ) async {
    final repository = ScriptedRepository();
    await pumpQueue(tester, repository);
    final controller = WorkspaceScope.read(
      tester.element(find.byType(QueuePane)),
    );
    await controller.applyFilters({'batch_id': 'batch-7'});
    await tester.pumpAndSettle();
    expect(repository.requests.last['batch_id'], 'batch-7');
    expect(find.byType(SearchFilters), findsNothing);
    expect(find.text('Upload batch: batch-7'), findsNothing);
    await controller.clearFilters();
    await tester.pumpAndSettle();
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
    expect(
      find.text(repository.results.first.displayReference),
      findsOneWidget,
    );

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

  testWidgets('record status presentation retains operational states', (
    tester,
  ) async {
    // Lean specimen rows omit status chips. Keep the record-to-presentation
    // contract here without restoring repeated labels to every queue row.
    const records = <Specimen>[
      Specimen({'specimen_id': 'SD-1', 'status': 'retry_scheduled'}),
      Specimen({'specimen_id': 'SD-2', 'status': 'paused'}),
      Specimen({'specimen_id': 'SD-3'}),
    ];
    final semantics = tester.ensureSemantics();
    try {
      await pumpComponent(
        tester,
        Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final record in records)
              StatusChip(
                SpecimenStatus.ofRecord(
                  disposition: record.disposition,
                  state: record.state,
                ),
              ),
          ],
        ),
      );
      for (final label in ['Retry scheduled', 'Paused', 'State unknown']) {
        expect(find.text(label), findsOneWidget);
      }
      // Only glossary terms advertise a definition. These two operational
      // states remain plain status announcements; State unknown has a term.
      for (final label in [
        'Run: retry scheduled',
        'Run: paused',
        'Queue: state unknown, term, double tap for definition',
      ]) {
        expect(find.bySemanticsLabel(label), findsOneWidget);
      }
      expect(find.text('Unknown'), findsNothing);
      expect(
        find.bySemanticsLabel(RegExp(r'^Field: unknown(?:,|$)')),
        findsNothing,
      );
    } finally {
      semantics.dispose();
    }
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('slash moves focus into the search field', (tester) async {
    await pumpQueue(tester, ScriptedRepository());
    await tester.sendKeyEvent(LogicalKeyboardKey.slash);
    await tester.pump();
    final FocusNode? focused = FocusManager.instance.primaryFocus;
    expect(focused?.debugLabel, 'Specimen search');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('F does not open an obsolete filter workflow', (tester) async {
    await pumpQueue(tester, ScriptedRepository());
    await tester.sendKeyEvent(LogicalKeyboardKey.keyF);
    await tester.pumpAndSettle();
    expect(find.byType(SearchFilters), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a queue row fits the primary work area', (tester) async {
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
    final pane = find.byType(QueuePane);
    final row = find.descendant(
      of: find.byKey(const ValueKey<String>('queue-row-SD-1')),
      matching: find.byType(UiListRow),
    );
    expect(row.hitTestable(), findsOneWidget);
    final Rect paneBounds = tester.getRect(pane);
    final Rect rowBounds = tester.getRect(row);
    final Rect searchBounds = tester.getRect(find.byType(UiSearchField));
    final Rect idBounds = tester.getRect(
      find.text(repository.results.first.displayReference),
    );
    expect(paneBounds.width, greaterThan(800));
    expect(rowBounds.width, lessThan(paneBounds.width));
    expect(rowBounds.left, closeTo(searchBounds.left, 0.01));
    expect(
      paneBounds.right - rowBounds.right,
      rowBounds.left - paneBounds.left,
      reason:
          'the queue uses symmetric page insets; search has its own measure',
    );
    expect(rowBounds.left, greaterThanOrEqualTo(paneBounds.left));
    expect(rowBounds.right, lessThanOrEqualTo(paneBounds.right));
    expect(idBounds.left, greaterThanOrEqualTo(rowBounds.left));
    expect(idBounds.right, lessThanOrEqualTo(rowBounds.right));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  // Search, supported views and selection remain reachable on phones.
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

    testWidgets('primary views remain reachable above the compact list', (
      tester,
    ) async {
      final ScriptedRepository repository = ScriptedRepository();
      await pumpPhone(tester, repository);

      expect(
        find.byKey(const ValueKey('queue-view')).hitTestable(),
        findsOneWidget,
      );
      await pickSpecimenQueue(tester, 'Cleared');
      expect(repository.requests.last['disposition'], 'cleared');
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets(
      'a chosen disposition shows its label in the state navigation',
      (tester) async {
        final ScriptedRepository repository = ScriptedRepository();
        await pumpPhone(tester, repository);
        final WorkspaceController controller = WorkspaceScope.read(
          tester.element(find.byType(QueuePane)),
        );
        await controller.selectDisposition('cleared');
        await tester.pumpAndSettle();

        expect(
          find.text('Cleared'),
          findsOneWidget,
          reason: 'the current supported view remains named',
        );
        expect(
          repository.requests.last['disposition'],
          'cleared',
          reason: 'the selected queue is the filter the server was asked for',
        );
        await tester.pumpWidget(const SizedBox());
      },
    );
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

    /// Detect any sticky ancestor, including one retained offstage.
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

    Future<void> expectSearchToScroll(WidgetTester tester) async {
      final list = find.byKey(const PageStorageKey<String>('queue-list'));
      // The sliver remains laid out after scrolling out of view, but the
      // default finder skips its offstage subtree. Include it for geometry.
      final search = find.byType(UiSearchField, skipOffstage: false);
      expect(search.hitTestable(), findsOneWidget);
      final scroll = tester.state<ScrollableState>(
        find.descendant(of: list, matching: find.byType(Scrollable)).first,
      );
      expect(scroll.position.maxScrollExtent, greaterThan(200));
      final double beforeOffset = scroll.position.pixels;
      final double beforeTop = tester.getTopLeft(search).dy;
      await tester.drag(list, const Offset(0, -200));
      await tester.pumpAndSettle();
      final double moved = scroll.position.pixels - beforeOffset;
      expect(moved, greaterThan(100));
      expect(
        tester.getTopLeft(search).dy,
        closeTo(beforeTop - moved, 0.5),
        reason: 'search moves with the list rather than pinning above it',
      );
      expect(search.hitTestable(), findsNothing);
      expect(stuckSearch(), findsNothing);
      expect(tester.takeException(), isNull);
    }

    testWidgets('medium search scrolls with content at every text scale', (
      tester,
    ) async {
      for (final scale in [1.0, 1.3, 2.0]) {
        await pumpAt(
          tester,
          ScriptedRepository()..results = page(30),
          const Size(768, 1024),
          textScale: scale,
        );
        await expectSearchToScroll(tester);
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('scrolls at compact and from expanded up', (tester) async {
      for (final Size window in <Size>[
        const Size(390, 844),
        const Size(1180, 820),
        const Size(1440, 900),
      ]) {
        await pumpAt(tester, ScriptedRepository()..results = page(30), window);
        await expectSearchToScroll(tester);
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('pins nothing under a record pushed over it', (tester) async {
      await pumpAt(
        tester,
        ScriptedRepository()..results = page(1),
        const Size(768, 1024),
      );
      expect(stuckSearch(), findsNothing);
      await tester.tap(
        find.descendant(
          of: find.byKey(const ValueKey<String>('queue-row-SD-1')),
          matching: find.byType(UiListRow),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(WorkbenchScreen), findsOneWidget);
      // The queue stays mounted beneath the record, and a region a covered
      // screen pins is height the reader never sees and height the record's
      // own chrome budget would be charged for.
      expect(
        find.byType(UiSearchField).hitTestable(),
        findsNothing,
        reason: 'the preserved queue is offstage and consumes no visible space',
      );
      await tester.pumpWidget(const SizedBox());
    });
  });

  // Motion catalog row 21 as the owner confirmed it on 2026-10-17: pull to
  // refresh in the iOS and Android apps, and the account menu's reload
  // control everywhere, so a desktop window is never left without a refresh.
  // The web runs the desktop path; `kIsWeb` is a compile-time constant, so a
  // widget test cannot be the web.
  testWidgets(
    'phones and tablets pull to refresh; every window reloads from the menu',
    (tester) async {
      final ScriptedRepository repository = ScriptedRepository()
        ..results = <Specimen>[
          const Specimen({
            'specimen_id': 'SD-1',
            'filename': 'First record',
            'disposition': 'cleared',
          }),
        ];
      await pumpQueue(tester, repository);
      final bool app =
          defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.android;
      expect(
        find.byKey(QueueScreen.pullToRefreshKey),
        app ? findsOneWidget : findsNothing,
      );

      final int loads = repository.requests.length;
      await tester.tap(uiMenuTrigger(RegExp('^${AppShell.accountLabel}')));
      await tester.pumpAndSettle();
      await tester.tap(find.text(AppShell.reloadLabel));
      await tester.pumpAndSettle();
      expect(
        repository.requests.length,
        greaterThan(loads),
        reason: 'the reload control asks the collection again',
      );
      await tester.pumpWidget(const SizedBox());
    },
    variant: TargetPlatformVariant.all(),
  );
}
