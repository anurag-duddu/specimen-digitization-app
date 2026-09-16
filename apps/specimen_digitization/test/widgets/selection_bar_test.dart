// The shared selection components (`lib/src/widgets/selection_bar.dart`).
//
// Three things are load bearing here and each has a test: the count is always
// on screen and announced, a select all says how far it reached, and an action
// that half worked names every record that did not change.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'harness.dart';

SelectionAction action(String label, {VoidCallback? onPressed}) =>
    (label: label, icon: UiIcons.cleared.defaultGlyph, onPressed: onPressed ?? () {});

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

/// The bulk actions, matched by role rather than by label.
///
/// The bar also carries a ghost button that clears the selection and a
/// checkbox that takes all of it, so "an action" is the primary variant.
final Finder actionButtons = find.byWidgetPredicate(
  (Widget widget) =>
      widget is UiButton && widget.variant == UiButtonVariant.primary,
);

/// The select all box, wherever the bar drew it.
final Finder selectAllBox = find.byWidgetPredicate(
  (Widget widget) =>
      widget is UiCheckbox && widget.label == SelectionBar.selectAllLabel,
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
        tester.widget<UiCheckbox>(selectAllBox).value,
        isTrue,
        reason: 'there is nothing loaded left to select, and the box says so',
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
      final Iterable<UiButton> buttons = tester.widgetList<UiButton>(
        find.byType(UiButton),
      );
      expect(buttons, isNotEmpty);
      for (final UiButton button in buttons) {
        expect(button.onPressed, isNull);
      }
      expect(
        tester.widget<UiCheckbox>(selectAllBox).onChanged,
        isNull,
        reason: 'the select all is held with the rest of the bar',
      );
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
      bool enabled = true,
      VoidCallback? onToggle,
      VoidCallback? onExtend,
      VoidCallback? onLongPress,
    }) => SelectableRow(
      selected: selected,
      label: 'Pinned beetle 1',
      showCheckbox: showCheckbox,
      enabled: enabled,
      onToggle: onToggle ?? () {},
      onExtend: onExtend,
      onLongPress: onLongPress,
      child: const SizedBox(height: 48, child: Text('Pinned beetle 1')),
    );

    /// Where the row's own content starts, which is the edge a reviewer
    /// scans a long list down.
    double contentLeft(WidgetTester tester) =>
        tester.getTopLeft(find.text('Pinned beetle 1')).dx;

    testWidgets('the checkbox names the record it selects', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, row());
      expect(
        tester.widget<UiCheckbox>(find.byType(UiCheckbox)).label,
        'Pinned beetle 1',
      );
      await expectAccessible(tester);
    });

    testWidgets('the checkbox toggles', (WidgetTester tester) async {
      int toggles = 0;
      await pumpComponent(tester, row(onToggle: () => toggles++));
      await tester.tap(find.byType(UiCheckbox));
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
      expect(find.byType(UiCheckbox), findsNothing);
      await tester.longPress(find.text('Pinned beetle 1'));
      expect(started, 1);
    });

    testWidgets('the row keeps its own body', (WidgetTester tester) async {
      await pumpComponent(tester, row());
      expect(find.text('Pinned beetle 1'), findsOneWidget);
    });

    testWidgets('the long press names what it does, in the list\'s own noun', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(
        tester,
        SelectableRow(
          selected: false,
          label: 'Slide 0041',
          showCheckbox: false,
          onToggle: () {},
          onLongPress: () {},
          longPressHint: 'Select this object',
          child: const SizedBox(height: 48, child: Text('Slide 0041')),
        ),
      );
      // The hint is what a reader speaks instead of "double tap and hold".
      // It defaults to the record wording and takes the list's own noun,
      // exactly as the bar's count label does.
      expect(
        find.byWidgetPredicate(
          (Widget widget) =>
              widget is Semantics &&
              widget.properties.hintOverrides?.onLongPressHint ==
                  'Select this object',
        ),
        findsOneWidget,
      );
      expect(
        find.byWidgetPredicate(
          (Widget widget) =>
              widget is Semantics &&
              widget.properties.hintOverrides?.onLongPressHint ==
                  SelectableRow.recordLongPressHint,
        ),
        findsNothing,
        reason: 'a list of objects must not be told to select a record',
      );
      expect(SelectableRow.recordLongPressHint, 'Select this record');
      handle.dispose();
    });

    testWidgets('a row that cannot be picked keeps the column', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, row());
      final double picked = contentLeft(tester);
      await pumpComponent(tester, row(enabled: false));
      expect(
        contentLeft(tester),
        picked,
        reason: 'a list needs only one unselectable row for every row below '
            'it to be read against a different left edge',
      );
      // Drawn and unavailable, rather than absent. A reader told nothing
      // cannot tell a row it may not pick from a row it missed.
      expect(find.byType(UiCheckbox), findsOneWidget);
      expect(
        tester.widget<UiCheckbox>(find.byType(UiCheckbox)).onChanged,
        isNull,
      );
    });

    testWidgets('a row that cannot be picked takes no long press', (
      WidgetTester tester,
    ) async {
      int started = 0;
      await pumpComponent(
        tester,
        row(enabled: false, onLongPress: () => started++),
      );
      await tester.longPress(find.text('Pinned beetle 1'));
      expect(
        started,
        0,
        reason: 'a gesture that picks a record the server will refuse is '
            'worse than no gesture',
      );
    });

    testWidgets('an unavailable checkbox says so to a reader', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(tester, row(enabled: false));
      expect(
        tester
            .getSemantics(find.byType(UiCheckbox))
            .flagsCollection
            .isEnabled
            .toBoolOrNull(),
        isFalse,
      );
      handle.dispose();
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

    testWidgets('states the count in the title, before the list', (
      WidgetTester tester,
    ) async {
      // The count is the last honest moment of a bulk decision, so it is the
      // first thing the surface says rather than a line inside it.
      await pumpComponent(
        tester,
        Builder(
          builder: (BuildContext context) => UiButton(
            label: 'Open',
            onPressed: () => showBulkOutcome(
              context,
              report: BulkDecisionReport(<BulkDecisionResult>[
                applied('a'),
                refused('b', 'Wrong base record version'),
                skipped('c'),
              ]),
              nameOf: (String id) => 'Pinned beetle $id',
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      expect(find.text('1 of 3 records changed'), findsOneWidget);
      expect(find.text(BulkOutcomeReport.dismissLabel), findsOneWidget);
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
