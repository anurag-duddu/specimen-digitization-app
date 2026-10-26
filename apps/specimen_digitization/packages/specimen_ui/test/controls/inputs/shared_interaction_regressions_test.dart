import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

Finder command(String label) => find.byWidgetPredicate(
  (widget) => widget is Pressable && widget.semanticsLabel == label,
);
FocusNode commandFocus(WidgetTester tester, String label) =>
    tester.widget<Pressable>(command(label)).focusNode!;

void main() {
  for (final direction in TextDirection.values) {
    testWidgets('collapsed range taps expand either bound in $direction', (
      tester,
    ) async {
      for (final collapseThumb in [-1, 0, 1]) {
        for (final change in [-20.0, 20.0]) {
          var values = collapseThumb < 0
              ? const UiRangeValues(50, 50)
              : const UiRangeValues(25, 75);
          final completed = <UiRangeValues>[];
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              child: StatefulBuilder(
                builder: (_, setState) => SizedBox(
                  width: 320,
                  child: UiRangeSlider(
                    label: 'Range',
                    min: 0,
                    max: 100,
                    values: values,
                    onChanged: (next) => setState(() => values = next),
                    onChangeEnd: completed.add,
                  ),
                ),
              ),
            ),
          );
          if (collapseThumb >= 0) {
            final nodes = tester
                .widgetList<FocusableActionDetector>(
                  find.descendant(
                    of: find.byType(UiRangeSlider),
                    matching: find.byType(FocusableActionDetector),
                  ),
                )
                .map((widget) => widget.focusNode!)
                .toList();
            nodes[collapseThumb].requestFocus();
            await tester.pump();
            await tester.sendKeyEvent(
              collapseThumb == 0
                  ? LogicalKeyboardKey.end
                  : LogicalKeyboardKey.home,
            );
            await tester.pump();
          }
          final collapsed = values.start;
          expect(values.end, collapsed);
          completed.clear();
          final track = tester.getRect(
            find.descendant(
              of: find.byType(UiRangeSlider),
              matching: find.byWidgetPredicate(
                (widget) =>
                    widget is GestureDetector &&
                    widget.onHorizontalDragStart != null,
              ),
            ),
          );
          final target = collapsed + change;
          final physical = direction == TextDirection.ltr
              ? target
              : 100 - target;
          await tester.tapAt(
            Offset(
              track.left + 24 + physical / 100 * (track.width - 48),
              track.center.dy,
            ),
          );
          await tester.pump();
          expect(values.start, closeTo(change < 0 ? target : collapsed, .0001));
          expect(values.end, closeTo(change > 0 ? target : collapsed, .0001));
          expect(completed, [values]);
          await tester.pumpWidget(const SizedBox());
        }
      }
    });

    testWidgets('coincident range drag chooses direction once in $direction', (
      tester,
    ) async {
      for (final (initial, collapseThumb) in [
        (0.0, -1),
        (33.3, -1),
        (100.0, -1),
        (75.0, 0),
        (25.0, 1),
      ]) {
        for (final increasing in [false, true]) {
          if ((initial == 0 && !increasing) || (initial == 100 && increasing)) {
            continue;
          }
          var values = collapseThumb < 0
              ? UiRangeValues(initial, initial)
              : const UiRangeValues(25, 75);
          final completed = <UiRangeValues>[];
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              child: StatefulBuilder(
                builder: (_, setState) => SizedBox(
                  width: 320,
                  child: UiRangeSlider(
                    label: 'Range',
                    min: 0,
                    max: 100,
                    values: values,
                    onChanged: (next) => setState(() => values = next),
                    onChangeEnd: completed.add,
                  ),
                ),
              ),
            ),
          );
          if (collapseThumb >= 0) {
            final nodes = tester
                .widgetList<FocusableActionDetector>(
                  find.descendant(
                    of: find.byType(UiRangeSlider),
                    matching: find.byType(FocusableActionDetector),
                  ),
                )
                .map((widget) => widget.focusNode!)
                .toList();
            nodes[collapseThumb].requestFocus();
            await tester.pump();
            await tester.sendKeyEvent(
              collapseThumb == 0
                  ? LogicalKeyboardKey.end
                  : LogicalKeyboardKey.home,
            );
            await tester.pump();
            expect(values, UiRangeValues(initial, initial));
            completed.clear();
          }
          final track = tester.getRect(
            find.descendant(
              of: find.byType(UiRangeSlider),
              matching: find.byWidgetPredicate(
                (widget) =>
                    widget is GestureDetector &&
                    widget.onHorizontalDragStart != null,
              ),
            ),
          );
          final physical = direction == TextDirection.ltr
              ? initial
              : 100 - initial;
          final origin = Offset(
            track.left + 24 + physical / 100 * (track.width - 48),
            track.center.dy,
          );
          final sign =
              (increasing ? 1.0 : -1.0) *
              (direction == TextDirection.ltr ? 1 : -1);
          final gesture = await tester.startGesture(origin);
          await gesture.moveBy(Offset(sign * 30, 0));
          await tester.pump();
          await gesture.moveBy(Offset(sign * 30, 0));
          await tester.pump();
          expect(
            increasing ? values.end : values.start,
            increasing ? greaterThan(initial) : lessThan(initial),
          );
          expect(increasing ? values.start : values.end, initial);
          await gesture.moveTo(origin - Offset(sign * 60, 0));
          await tester.pump();
          expect(
            values,
            UiRangeValues(initial, initial),
            reason: 'Reversing clamps the chosen thumb without switching it.',
          );
          await gesture.up();
          await tester.pump();
          expect(completed, [values]);
          await tester.pumpWidget(const SizedBox());
        }
      }
    });

    for (final vertical in [false, true]) {
      testWidgets(
        'joined commands skip unavailable targets $direction vertical=$vertical',
        (tester) async {
          final calls = <String>[];
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              child: SizedBox(
                width: vertical ? 150 : 700,
                child: UiButtonGroup(
                  label: 'Commands',
                  items: [
                    const UiButtonGroupItem(label: 'First unavailable'),
                    UiButtonGroupItem(
                      label: 'A',
                      onPressed: () => calls.add('A'),
                    ),
                    const UiButtonGroupItem(label: 'B'),
                    UiButtonGroupItem(
                      label: 'C',
                      onPressed: () => calls.add('C'),
                    ),
                    const UiButtonGroupItem(label: 'Last unavailable'),
                  ],
                ),
              ),
            ),
          );
          commandFocus(tester, 'A').requestFocus();
          await tester.pump();
          final forward = vertical
              ? LogicalKeyboardKey.arrowDown
              : direction == TextDirection.ltr
              ? LogicalKeyboardKey.arrowRight
              : LogicalKeyboardKey.arrowLeft;
          final backward = vertical
              ? LogicalKeyboardKey.arrowUp
              : direction == TextDirection.ltr
              ? LogicalKeyboardKey.arrowLeft
              : LogicalKeyboardKey.arrowRight;
          await tester.sendKeyEvent(forward);
          await tester.pump();
          expect(commandFocus(tester, 'C').hasFocus, isTrue);
          await tester.sendKeyEvent(forward);
          await tester.pump();
          expect(commandFocus(tester, 'A').hasFocus, isTrue);
          await tester.sendKeyEvent(backward);
          await tester.pump();
          expect(commandFocus(tester, 'C').hasFocus, isTrue);
          await tester.sendKeyEvent(LogicalKeyboardKey.home);
          await tester.pump();
          expect(commandFocus(tester, 'A').hasFocus, isTrue);
          await tester.sendKeyEvent(LogicalKeyboardKey.end);
          await tester.pump();
          expect(commandFocus(tester, 'C').hasFocus, isTrue);
          expect(calls, isEmpty);
          await tester.sendKeyEvent(LogicalKeyboardKey.enter);
          expect(calls, ['C']);
          expect(tester.takeException(), isNull);
        },
      );
    }
  }

  testWidgets(
    'reason-bearing disabled commands stay discoverable and all-disabled groups terminate',
    (tester) async {
      final after = FocusNode();
      addTearDown(after.dispose);
      await tester.pumpWidget(
        uiHarness(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              UiButtonGroup(
                label: 'Commands',
                items: [
                  UiButtonGroupItem(label: 'A', onPressed: () {}),
                  const UiButtonGroupItem(
                    label: 'B',
                    disabledReason: 'Requires permission',
                  ),
                  const UiButtonGroupItem(label: 'C'),
                ],
              ),
              UiButton(label: 'After', focusNode: after, onPressed: () {}),
            ],
          ),
        ),
      );
      commandFocus(tester, 'A').requestFocus();
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pump();
      expect(commandFocus(tester, 'B').hasFocus, isTrue);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(commandFocus(tester, 'B').hasFocus, isTrue);
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pump();
      expect(commandFocus(tester, 'A').hasFocus, isTrue);
      await tester.pumpWidget(
        uiHarness(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              UiButtonGroup(
                label: 'Commands',
                items: const [
                  UiButtonGroupItem(label: 'A'),
                  UiButtonGroupItem(label: 'B'),
                ],
              ),
              UiButton(label: 'After', focusNode: after, onPressed: () {}),
            ],
          ),
        ),
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.home);
      await tester.sendKeyEvent(LogicalKeyboardKey.end);
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();
      expect(after.hasFocus, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  for (final dismissal in ['escape', 'selection', 'outside']) {
    testWidgets('pointer combobox returns to its trigger after $dismissal', (
      tester,
    ) async {
      final previous = FocusNode();
      addTearDown(previous.dispose);
      Set<String> selected = {};
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 360,
            child: StatefulBuilder(
              builder: (_, setState) => Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  UiField(label: 'Previous field', focusNode: previous),
                  UiCombobox<String>(
                    label: 'Collection',
                    selected: selected,
                    options: const [
                      UiComboboxOption(value: 'a', label: 'Alpha'),
                    ],
                    onChanged: (next) => setState(() => selected = next),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      previous.requestFocus();
      await tester.pump();
      expect(previous.hasFocus, isTrue);
      await tester.tap(command('Collection'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<UiField>(find.widgetWithText(UiField, 'Search options'))
            .focusNode!
            .hasFocus,
        isTrue,
      );
      if (dismissal == 'escape') {
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      } else if (dismissal == 'selection') {
        await tester.tap(command('Alpha'));
      } else {
        await tester.tapAt(const Offset(10, 10));
      }
      await tester.pumpAndSettle();
      expect(commandFocus(tester, 'Collection').hasFocus, isTrue);
      expect(previous.hasFocus, isFalse);
      expect(selected, dismissal == 'selection' ? {'a'} : isEmpty);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('combobox close never focuses a disabled or detached trigger', (
    tester,
  ) async {
    final other = FocusNode();
    addTearDown(other.dispose);
    var enabled = true;
    var shown = true;
    late StateSetter update;
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 360,
          child: StatefulBuilder(
            builder: (_, setState) {
              update = setState;
              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  UiField(label: 'Other', focusNode: other),
                  if (shown)
                    UiCombobox<String>(
                      label: 'Collection',
                      selected: const {},
                      options: const [
                        UiComboboxOption(value: 'a', label: 'Alpha'),
                      ],
                      onChanged: enabled
                          ? (_) => update(() => shown = false)
                          : null,
                    ),
                ],
              );
            },
          ),
        ),
      ),
    );
    await tester.tap(command('Collection'));
    await tester.pumpAndSettle();
    update(() => enabled = false);
    await tester.pumpAndSettle();
    expect(commandFocus(tester, 'Collection').hasFocus, isFalse);
    update(() => enabled = true);
    await tester.pump();
    await tester.tap(command('Collection'));
    await tester.pumpAndSettle();
    await tester.tap(command('Alpha'));
    await tester.pumpAndSettle();
    other.requestFocus();
    await tester.pump();
    expect(other.hasFocus, isTrue);
    expect(find.byType(UiCombobox<String>), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'adjacent range calendars retain months while selecting and navigate together',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1000, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final proposals = <UiDateRange>[];
      await tester.pumpWidget(
        uiHarness(
          size: const Size(1000, 1000),
          child: SizedBox(
            width: 960,
            child: UiDateRangePicker(
              label: 'Dates',
              value: null,
              firstDate: DateTime.utc(2026, 10),
              lastDate: DateTime.utc(2027, 6, 30),
              showActions: true,
              onChanged: proposals.add,
            ),
          ),
        ),
      );
      void months(String first, String second) {
        expect(find.text(first), findsOneWidget);
        expect(find.text(second), findsOneWidget);
      }

      months('October 2026', 'November 2026');
      await tester.tap(command('22 October 2026'));
      await tester.pumpAndSettle();
      months('October 2026', 'November 2026');
      expect(commandFocus(tester, '22 October 2026').hasFocus, isTrue);
      await tester.tap(command('5 November 2026'));
      await tester.pumpAndSettle();
      months('October 2026', 'November 2026');
      await tester.tap(find.widgetWithText(UiButton, 'Apply dates'));
      expect(proposals, [
        UiDateRange(DateTime.utc(2026, 10, 22), DateTime.utc(2026, 11, 5)),
      ]);
      await tester.tap(command('18 November 2026'));
      await tester.pumpAndSettle();
      months('October 2026', 'November 2026');
      await tester.tap(command('28 October 2026'));
      await tester.pumpAndSettle();
      months('October 2026', 'November 2026');
      await tester.tap(
        find
            .byWidgetPredicate(
              (widget) =>
                  widget is UiIconButton &&
                  widget.semanticsLabel == 'Next month',
            )
            .last,
      );
      await tester.pumpAndSettle();
      months('November 2026', 'December 2026');
      await tester.tap(
        find
            .byWidgetPredicate(
              (widget) =>
                  widget is UiIconButton &&
                  widget.semanticsLabel == 'Previous month',
            )
            .first,
      );
      await tester.pumpAndSettle();
      months('October 2026', 'November 2026');
      commandFocus(tester, '31 October 2026, in selected range').requestFocus();
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      months('November 2026', 'December 2026');
      expect(
        commandFocus(tester, '1 November 2026, in selected range').hasFocus,
        isTrue,
      );
      commandFocus(tester, '31 December 2026').requestFocus();
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      months('December 2026', 'January 2027');
      expect(commandFocus(tester, '1 January 2027').hasFocus, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'range host values, presets, typed endpoints and Cancel reveal coordinated months',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1000, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      UiDateRange? accepted;
      late StateSetter update;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(1000, 1000),
          child: StatefulBuilder(
            builder: (_, setState) {
              update = setState;
              return SizedBox(
                width: 960,
                child: UiDateRangePicker(
                  label: 'Dates',
                  value: accepted,
                  firstDate: DateTime.utc(2026, 1),
                  lastDate: DateTime.utc(2027, 12, 31),
                  presets: [
                    UiDateRangePreset(
                      label: 'Winter',
                      range: UiDateRange(
                        DateTime.utc(2027, 1, 5),
                        DateTime.utc(2027, 2, 6),
                      ),
                    ),
                  ],
                  showActions: true,
                  onChanged: (_) {},
                ),
              );
            },
          ),
        ),
      );
      update(
        () => accepted = UiDateRange(
          DateTime.utc(2026, 10, 22),
          DateTime.utc(2026, 11, 5),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('October 2026'), findsOneWidget);
      expect(find.text('November 2026'), findsOneWidget);
      await tester.tap(find.widgetWithText(UiButton, 'Winter'));
      await tester.pumpAndSettle();
      expect(find.text('January 2027'), findsOneWidget);
      expect(find.text('February 2027'), findsOneWidget);
      final editors = find.byType(EditableText);
      await tester.enterText(editors.first, '2027-04-10');
      await tester.enterText(editors.last, '2027-05-12');
      await tester.pumpAndSettle();
      expect(find.text('April 2027'), findsOneWidget);
      expect(find.text('May 2027'), findsOneWidget);
      await tester.tap(find.widgetWithText(UiButton, 'Cancel'));
      await tester.pumpAndSettle();
      expect(find.text('October 2026'), findsOneWidget);
      expect(find.text('November 2026'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
