// The shared selection components (`lib/src/widgets/selection_bar.dart`).
//
// Three things are load bearing here and each has a test: the count is always
// on screen and announced, a select all says how far it reached, and an action
// that half worked names every record that did not change.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'harness.dart';

SelectionAction action(String label, {VoidCallback? onPressed}) =>
    (label: label, icon: Symbols.check_circle, onPressed: onPressed ?? () {});

Widget bar({
  int count = 3,
  int loadedCount = 6,
  bool moreToLoad = false,
  bool allLoadedSelected = false,
  bool busy = false,
  VoidCallback? onSelectAllLoaded,
  VoidCallback? onClear,
  List<SelectionAction>? actions,
}) => SelectionBar(
  count: count,
  loadedCount: loadedCount,
  moreToLoad: moreToLoad,
  allLoadedSelected: allLoadedSelected,
  busy: busy,
  onSelectAllLoaded: onSelectAllLoaded ?? () {},
  onClear: onClear ?? () {},
  actions: actions ?? <SelectionAction>[action('Approve')],
);

/// `FilledButton.icon` builds a private subclass, so an exact type finder
/// misses it. Every button in the bar is matched by role instead.
final Finder actionButtons = find.byWidgetPredicate(
  (Widget widget) => widget is FilledButton,
);

BulkDecisionResult applied(String id) =>
    BulkDecisionResult(specimenId: id, outcome: BulkOutcome.applied);

BulkDecisionResult refused(String id, String message) => BulkDecisionResult(
  specimenId: id,
  outcome: BulkOutcome.refused,
  code: 'revision_or_idempotency_conflict',
  message: message,
);

BulkDecisionResult skipped(String id) =>
    BulkDecisionResult(specimenId: id, outcome: BulkOutcome.skipped);

void main() {
  group('SelectionBar', () {
    testWidgets('states the count, and agrees with itself on the plural', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, bar(count: 3));
      expect(find.text('3 records selected'), findsOneWidget);
      await pumpComponent(tester, bar(count: 1));
      expect(find.text('1 record selected'), findsOneWidget);
    });

    testWidgets('the count is announced, not only drawn', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(tester, bar(count: 4));
      expect(
        tester
            .getSemantics(find.text('4 records selected'))
            .flagsCollection
            .isLiveRegion,
        isTrue,
      );
      handle.dispose();
    });

    testWidgets('the select all says which records it reaches', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, bar());
      expect(find.text(SelectionBar.selectAllLabel), findsOneWidget);
      expect(
        find.textContaining('Select all matching'),
        findsNothing,
        reason: 'the list API answers a page, so no control may claim the '
            'whole filter',
      );
    });

    testWidgets('once everything loaded is picked, it says what it missed', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        bar(count: 6, allLoadedSelected: true, moreToLoad: true),
      );
      await tester.pumpAndSettle();
      expect(find.text(SelectionBar.recordsMoreMatch), findsOneWidget);
      expect(
        find.text(SelectionBar.selectAllLabel),
        findsNothing,
        reason: 'there is nothing loaded left to select',
      );
    });

    testWidgets('with nothing left to load it claims nothing', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        bar(count: 6, allLoadedSelected: true),
      );
      await tester.pumpAndSettle();
      expect(find.text(SelectionBar.recordsMoreMatch), findsNothing);
    });

    testWidgets('a list of things that are not records says so', (
      WidgetTester tester,
    ) async {
      // The queue's rows are records. A browse screen over a storage source
      // lists objects that nothing has imported yet, and calling one of those
      // a record names the very thing that screen exists to distinguish.
      await pumpComponent(
        tester,
        SelectionBar(
          count: 6,
          loadedCount: 6,
          moreToLoad: true,
          allLoadedSelected: true,
          onSelectAllLoaded: () {},
          onClear: () {},
          actions: <SelectionAction>[action('Run processing')],
          countLabel: (int count) => count == 1 ? '1 object' : '$count objects',
          moreMatchLabel:
              'More objects match this filter. Load more to select them.',
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('6 objects selected'), findsOneWidget);
      expect(
        find.text('More objects match this filter. Load more to select them.'),
        findsOneWidget,
      );
      expect(
        find.textContaining('record'),
        findsNothing,
        reason: 'one bar must not use two nouns for one thing',
      );
    });

    testWidgets('a bulk action in flight holds every control', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, bar(busy: true));
      final Iterable<ButtonStyleButton> buttons = tester
          .widgetList<ButtonStyleButton>(
            find.byWidgetPredicate((Widget w) => w is ButtonStyleButton),
          );
      expect(buttons, isNotEmpty);
      for (final ButtonStyleButton button in buttons) {
        expect(button.onPressed, isNull);
      }
      expect(
        find.text('3 records selected'),
        findsOneWidget,
        reason: 'the bar keeps its count while the call is out',
      );
    });

    testWidgets('a list whose server permits nothing shows a count only', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, bar(actions: <SelectionAction>[]));
      expect(find.text('3 records selected'), findsOneWidget);
      expect(actionButtons, findsNothing);
    });

    testWidgets('clear and select all reach their callbacks', (
      WidgetTester tester,
    ) async {
      int cleared = 0;
      int all = 0;
      await pumpComponent(
        tester,
        bar(onClear: () => cleared++, onSelectAllLoaded: () => all++),
      );
      await tester.tap(find.text('Clear selection'));
      await tester.tap(find.text(SelectionBar.selectAllLabel));
      expect(<int>[cleared, all], <int>[1, 1]);
    });

    testWidgets('every control is reachable and named', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, bar());
      await expectAccessible(tester);
    });

    testWidgets('it fits a 360dp list pane without overflowing', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        SizedBox(
          width: 360,
          child: bar(
            count: 12,
            allLoadedSelected: true,
            moreToLoad: true,
            actions: <SelectionAction>[
              action('Approve'),
              action('Confirm coverage'),
            ],
          ),
        ),
        size: const Size(360, 900),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  });

  group('SelectableRow', () {
    Widget row({
      bool selected = false,
      bool showCheckbox = true,
      VoidCallback? onToggle,
      VoidCallback? onExtend,
      VoidCallback? onLongPress,
    }) => SelectableRow(
      selected: selected,
      label: 'Pinned beetle 1',
      showCheckbox: showCheckbox,
      onToggle: onToggle ?? () {},
      onExtend: onExtend,
      onLongPress: onLongPress,
      child: const SizedBox(height: 48, child: Text('Pinned beetle 1')),
    );

    testWidgets('the checkbox names the record it selects', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, row());
      expect(
        tester.widget<Checkbox>(find.byType(Checkbox)).semanticLabel,
        'Pinned beetle 1',
      );
      await expectAccessible(tester);
    });

    testWidgets('the checkbox toggles', (WidgetTester tester) async {
      int toggles = 0;
      await pumpComponent(tester, row(onToggle: () => toggles++));
      await tester.tap(find.byType(Checkbox));
      expect(toggles, 1);
    });

    testWidgets('a long press starts a selection', (
      WidgetTester tester,
    ) async {
      int started = 0;
      await pumpComponent(
        tester,
        row(showCheckbox: false, onLongPress: () => started++),
      );
      expect(find.byType(Checkbox), findsNothing);
      await tester.longPress(find.text('Pinned beetle 1'));
      expect(started, 1);
    });

    testWidgets('the row keeps its own body', (WidgetTester tester) async {
      await pumpComponent(tester, row());
      expect(find.text('Pinned beetle 1'), findsOneWidget);
    });
  });

  group('BulkOutcomeReport', () {
    testWidgets('names every record that did not change, and why', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        BulkOutcomeReport(
          report: BulkDecisionReport(<BulkDecisionResult>[
            applied('a'),
            refused('b', 'Wrong base record version'),
            skipped('c'),
          ]),
          nameOf: (String id) => 'Pinned beetle $id',
        ),
      );
      expect(find.text('1 of 3 records changed'), findsOneWidget);
      expect(find.text('Pinned beetle b'), findsOneWidget);
      expect(find.text('Wrong base record version'), findsOneWidget);
      expect(find.text('Pinned beetle c'), findsOneWidget);
      expect(
        find.text(BulkOutcomeReport.skippedReason),
        findsOneWidget,
        reason: 'never attempted and refused are different outcomes',
      );
      expect(
        find.text('Pinned beetle a'),
        findsNothing,
        reason: 'the records that changed are the queue\'s to show, not a '
            'list to read back',
      );
    });

    testWidgets('never reads an identifier back as a name', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        BulkOutcomeReport(
          report: BulkDecisionReport(<BulkDecisionResult>[
            refused('0f2c-9911', 'Access denied'),
          ]),
          nameOf: (String id) => 'Pinned beetle, Chicago 1912',
        ),
      );
      expect(find.text('Pinned beetle, Chicago 1912'), findsOneWidget);
      expect(find.text('0f2c-9911'), findsNothing);
    });
  });
}
