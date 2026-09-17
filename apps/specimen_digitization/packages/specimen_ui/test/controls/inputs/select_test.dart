// UiSelect (10 section 4.2).
//
// Opening, picking by pointer and by keyboard, type to filter, the expanded
// state a screen reader reads, and Escape returning focus to the trigger.

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';
import 'inputs_finders.dart';

const String _label = 'Disposition';
const String _placeholder = 'Pick a disposition';

const List<UiSelectOption<String>> _few = <UiSelectOption<String>>[
  UiSelectOption<String>(value: 'cleared', label: 'Cleared'),
  UiSelectOption<String>(value: 'review', label: 'Needs human review'),
  UiSelectOption<String>(value: 'deferred', label: 'Deferred'),
];

List<UiSelectOption<String>> get _many => <UiSelectOption<String>>[
  for (int i = 1; i <= 9; i++)
    UiSelectOption<String>(value: 'c$i', label: 'Collection $i'),
];

Widget _select({
  String? value,
  List<UiSelectOption<String>>? options,
  ValueChanged<String>? onChanged,
  String? disabledReason,
  String? helpText,
}) => SizedBox(
  width: 320,
  child: UiSelect<String>(
    label: _label,
    placeholder: _placeholder,
    value: value,
    options: options ?? _few,
    onChanged: onChanged,
    disabledReason: disabledReason,
    helpText: helpText,
  ),
);

SemanticsData _trigger(WidgetTester tester) =>
    tester.getSemantics(find.bySemanticsLabel(_label)).getSemanticsData();

void main() {
  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) =>
          _select(value: 'cleared', onChanged: (String _) {}),
      semanticsLabel: _label,
    );
  });

  testWidgets('a disabled select carries the reason on its hint', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) =>
          _select(disabledReason: 'The run is still reading this specimen.'),
      semanticsLabel: _label,
      disabledWithReason: true,
    );
  });

  testWidgets('the trigger reads the placeholder until something is picked', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: _select(onChanged: (String _) {})),
    );
    await tester.pumpAndSettle();
    expect(find.text(_placeholder), findsOneWidget);
    expect(_trigger(tester).value, _placeholder);

    await tester.pumpWidget(
      uiHarness(
        child: _select(value: 'cleared', onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Cleared'), findsOneWidget);
    expect(_trigger(tester).value, 'Cleared');
    semantics.dispose();
  });

  testWidgets('it opens on a press and says so through expanded', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: _select(value: 'cleared', onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(_trigger(tester).flagsCollection.isExpanded, Tristate.isFalse);
    expect(find.text('Deferred'), findsNothing);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(
      _trigger(tester).flagsCollection.isExpanded,
      Tristate.isTrue,
      reason: '10 section 4.2: semantics button with expanded',
    );
    expect(find.text('Deferred'), findsOneWidget);
    semantics.dispose();
  });

  testWidgets('picking an option reports it and closes the list', (
    WidgetTester tester,
  ) async {
    String? picked;
    await tester.pumpWidget(
      uiHarness(
        child: _select(
          value: 'cleared',
          onChanged: (String value) => picked = value,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Needs human review'));
    await tester.pumpAndSettle();
    expect(picked, 'review');
    expect(find.text('Deferred'), findsNothing, reason: 'the list closed');
  });

  testWidgets('the picked option is the one marked selected', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: _select(value: 'deferred', onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Deferred'))
          .getSemanticsData()
          .flagsCollection
          .isSelected,
      Tristate.isTrue,
    );
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Cleared'))
          .getSemanticsData()
          .flagsCollection
          .isSelected,
      isNot(Tristate.isTrue),
    );
    semantics.dispose();
  });

  testWidgets('Down moves into the list and Enter picks', (
    WidgetTester tester,
  ) async {
    String? picked;
    await tester.pumpWidget(
      uiHarness(
        child: _select(
          value: 'cleared',
          onChanged: (String value) => picked = value,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text('Deferred'), findsOneWidget, reason: 'Enter opened it');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(picked, isNotNull);
    expect(find.text('Deferred'), findsNothing);
  });

  testWidgets('Escape closes the list and hands focus back to the trigger', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: _select(value: 'cleared', onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text('Deferred'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text('Deferred'), findsNothing);

    // The proof that focus came back: the same key opens it again, with no
    // Tab in between.
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(
      find.text('Deferred'),
      findsOneWidget,
      reason: 'Escape returns focus to the trigger (10 section 2 clause 3)',
    );
  });

  testWidgets('a press outside closes the list', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: _select(value: 'cleared', onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(find.text('Deferred'), findsOneWidget);

    await tester.tapAt(Offset.zero);
    await tester.pumpAndSettle();
    expect(find.text('Deferred'), findsNothing);
  });

  testWidgets('a short list has no filter', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: _select(value: 'cleared', onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(find.text('Deferred'), findsOneWidget);
    expect(
      find.byType(FieldCore),
      findsNothing,
      reason: 'three options are not worth a filter (10 section 4.2)',
    );
  });

  testWidgets('a list above the threshold gets a filter', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: _select(options: _many, onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(
      find.byType(FieldCore),
      findsOneWidget,
      reason: 'above eight options the list filters (10 section 4.2)',
    );
  });

  testWidgets('typing filters the list and Enter picks what is left', (
    WidgetTester tester,
  ) async {
    String? picked;
    await tester.pumpWidget(
      uiHarness(
        child: _select(
          options: _many,
          onChanged: (String value) => picked = value,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(FieldCore), 'collection 7');
    await tester.pumpAndSettle();
    expect(find.text('Collection 7'), findsOneWidget);
    expect(find.text('Collection 1'), findsNothing);

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(picked, 'c7');
  });

  testWidgets('a filter that matches nothing says so', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: _select(options: _many, onChanged: (String _) {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(FieldCore), 'zzz');
    await tester.pumpAndSettle();
    expect(find.text('Nothing matches that filter.'), findsOneWidget);
    expect(find.text('Collection 1'), findsNothing);
  });

  testWidgets('a disabled select does not open', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: _select(
          value: 'cleared',
          disabledReason: 'The run is still reading this specimen.',
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(find.text('Deferred'), findsNothing);
    expect(
      _trigger(tester).hint,
      'The run is still reading this specimen.',
      reason: 'the reason is on the hint (03 section 3.6)',
    );
  });

  testWidgets('the trigger is the same box a field draws', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: Column(
          children: <Widget>[
            const SizedBox(width: 320, child: UiField(label: 'A field')),
            _select(value: 'cleared', onChanged: (String _) {}),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    final List<UiFieldBox> boxes = tester
        .widgetList<UiFieldBox>(find.byType(UiFieldBox))
        .toList();
    expect(boxes, hasLength(2));
    expect(
      boxes.first.style.radius,
      boxes.last.style.radius,
      reason: 'a select and a field are one object with two behaviours',
    );
    expect(boxes.first.style.minHeight, boxes.last.style.minHeight);
  });

  testWidgets('a pointer press on the trigger draws no ring', (
    WidgetTester tester,
  ) async {
    addTearDown(
      () => FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.automatic,
    );
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTouch;
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: _select(value: 'cleared', onChanged: (String _) {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byType(UiFieldBox));
      await tester.pumpAndSettle();
      expect(
        visibleRings(tester),
        0,
        reason:
            'a select is not being edited, so clause 4 stands unamended for '
            'it: no ring for a pointer, in ${density.name}',
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('keyboard focus rings the trigger on its own edge', (
    WidgetTester tester,
  ) async {
    addTearDown(
      () => FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.automatic,
    );
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: _select(value: 'cleared', onChanged: (String _) {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      expect(
        visibleRings(tester),
        1,
        reason: 'one ring in ${density.name}',
      );
      expect(
        visibleRings(tester, find.byType(UiFieldBox)),
        1,
        reason:
            'the ring is the box\'s own, so it runs concentric with the edge. '
            'A ring around the hit box would miss the edge by the 4 dp of '
            'slop in pointer density (11 section 4).',
      );
    }
  });

  testWidgets('the trigger grows with the text like a field does', (
    WidgetTester tester,
  ) async {
    Future<double> height(double scale) async {
      await tester.pumpWidget(
        uiHarness(
          textScaler: TextScaler.linear(scale),
          child: _select(value: 'cleared', onChanged: (String _) {}),
        ),
      );
      await tester.pumpAndSettle();
      return tester.widget<UiFieldBox>(find.byType(UiFieldBox)).style.minHeight;
    }

    expect(
      await height(2),
      greaterThan(await height(1)),
      reason:
          'the trigger is a field, so its height derives from the type the '
          'same way (11 section 2.2)',
    );
  });

  testWidgets('the options are the real row at sm, not a stand-in', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _select(value: 'deferred', onChanged: (String _) {})),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    final List<UiListRow> rows = tester
        .widgetList<UiListRow>(find.byType(UiListRow))
        .toList();
    expect(rows, hasLength(_few.length));
    expect(
      rows.every((UiListRow row) => row.size == UiSize.sm),
      isTrue,
      reason: 'a menu row is the dense row (10 sections 4.3 and 4.5)',
    );
    expect(
      rows.every((UiListRow row) => row.mode == UiListRowMode.navigate),
      isTrue,
      reason:
          'picking an option moves the trigger rather than ticking a box, so '
          'the row stays a button that is selected',
    );
    expect(rows.where((UiListRow row) => row.selected).single.title, 'Deferred');
  });

  testWidgets('the list stops at seven rows and part of an eighth', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: _select(options: _many, onChanged: (String _) {}),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel(_label));
      await tester.pumpAndSettle();
      final double row = tester
          .getSize(find.byType(UiListRow).first)
          .height;
      expect(
        row,
        greaterThanOrEqualTo(UiDensity.hitBox),
        reason: 'the row is floored at the hit box in both densities',
      );
      final BuildContext context = tester.element(find.byType(UiSelect<String>));
      expect(
        UiSelectStyle.resolve(context.ui).menuMaxHeight,
        row * 7.5,
        reason:
            'the popover still shows seven rows and part of an eighth, so a '
            'list that scrolls says so by cutting one off',
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });
}
