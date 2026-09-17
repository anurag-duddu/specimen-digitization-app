// UiRadio and UiRadioGroup (10 section 4.2).

import 'dart:ui' show CheckedState, SemanticsRole;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const String _model = 'The model reading';
const String _human = 'The reviewer reading';
const String _neither = 'Neither reading';

Widget _group({
  required String? value,
  ValueChanged<String?>? onChanged,
  bool neitherEnabled = false,
}) => UiRadioGroup<String>(
  label: 'Which reading to keep',
  value: value,
  onChanged: onChanged ?? (String? _) {},
  children: <Widget>[
    const UiRadio<String>(label: _model, value: 'model'),
    const UiRadio<String>(label: _human, value: 'human'),
    UiRadio<String>(
      label: _neither,
      value: 'neither',
      enabled: neitherEnabled,
      disabledReason: neitherEnabled
          ? null
          : 'Record a reason before you reject both readings.',
    ),
  ],
);

SemanticsData _data(WidgetTester tester, String label) =>
    tester.getSemantics(find.bySemanticsLabel(label)).getSemanticsData();

void main() {
  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _group(value: 'model'),
      semanticsLabel: _model,
    );
  });

  testWidgets('a disabled option carries the reason on its hint', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _group(value: 'model'),
      semanticsLabel: _neither,
      disabledWithReason: true,
    );
  });

  testWidgets('the group publishes the radio group role', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: _group(value: 'model')));
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.byType(RadioGroup<String>))
          .getSemanticsData()
          .role,
      SemanticsRole.radioGroup,
    );
    semantics.dispose();
  });

  testWidgets('one option is checked and the others are not', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: _group(value: 'model')));
    await tester.pumpAndSettle();
    expect(
      _data(tester, _model).flagsCollection.isChecked,
      CheckedState.isTrue,
    );
    expect(
      _data(tester, _human).flagsCollection.isChecked,
      CheckedState.isFalse,
    );
    expect(
      _data(tester, _model).flagsCollection.isInMutuallyExclusiveGroup,
      isTrue,
      reason: 'a radio says that choosing it unchooses the others',
    );
    semantics.dispose();
  });

  testWidgets('pressing anywhere on the row chooses that option', (
    WidgetTester tester,
  ) async {
    String? value = 'model';
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) => _group(
            value: value,
            onChanged: (String? next) => setState(() => value = next),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(_human));
    await tester.pumpAndSettle();
    expect(value, 'human');
  });

  testWidgets('the arrow keys move the choice within the group', (
    WidgetTester tester,
  ) async {
    String? value = 'model';
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) => _group(
            value: value,
            neitherEnabled: true,
            onChanged: (String? next) => setState(() => value = next),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Tab lands on the chosen option, which is the WAI-ARIA radio pattern.
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(value, 'human');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(value, 'neither');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
    await tester.pumpAndSettle();
    expect(value, 'human');
  });

  testWidgets('a disabled option cannot be chosen', (
    WidgetTester tester,
  ) async {
    String? value = 'model';
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) => _group(
            value: value,
            onChanged: (String? next) => setState(() => value = next),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(_neither));
    await tester.pumpAndSettle();
    expect(value, 'model');
  });

  testWidgets('the chosen disc fills and the others stay empty', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _group(value: 'model')));
    await tester.pumpAndSettle();
    final UiThemeData ui = tester
        .element(find.byType(UiRadio<String>).first)
        .ui;
    final Iterable<DecoratedBox> discs = tester.widgetList<DecoratedBox>(
      find.descendant(
        of: find.byType(UiRadio<String>).at(0),
        matching: find.byType(DecoratedBox),
      ),
    );
    expect(
      discs.any(
        (DecoratedBox box) =>
            (box.decoration as ShapeDecoration).color == ui.color.ink,
      ),
      isTrue,
      reason: 'the chosen option draws its dot in ink',
    );

    final Iterable<DecoratedBox> unchosen = tester.widgetList<DecoratedBox>(
      find.descendant(
        of: find.byType(UiRadio<String>).at(1),
        matching: find.byType(DecoratedBox),
      ),
    );
    expect(
      unchosen.any(
        (DecoratedBox box) =>
            box.decoration is ShapeDecoration &&
            (box.decoration as ShapeDecoration).color == ui.color.ink,
      ),
      isFalse,
    );
  });

  testWidgets('the focused option is ringed as a circle, around its disc', (
    WidgetTester tester,
  ) async {
    addTearDown(
      () => FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.automatic,
    );
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
    await tester.pumpWidget(
      uiHarness(
        child: _group(value: 'model', onChanged: (String? _) {}),
      ),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final Iterable<FocusRing> rings = tester
        .widgetList<FocusRing>(find.byType(FocusRing))
        .where((FocusRing ring) => ring.visible);
    expect(rings, hasLength(1));
    expect(
      rings.single.shape,
      FocusRingShape.circle,
      reason:
          'a disc is ringed by a circle. The ring used to take the row\'s '
          'corner, which put a rounded rectangle around a circle with 20 dp '
          'of empty label beside it (09 section 3.6, fit amendment).',
    );
    final Size ringed = tester.getSize(
      find.byWidgetPredicate(
        (Widget widget) => widget is FocusRing && widget.visible,
      ),
    );
    expect(
      ringed,
      const Size.square(20),
      reason: 'what is ringed is the disc 10 section 4.2 specifies',
    );
  });

  testWidgets('every option keeps a 48 dp row in both densities', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: _group(value: 'model'),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getSize(find.bySemanticsLabel(_human)).height,
        greaterThanOrEqualTo(UiDensity.hitBox),
        reason: 'density never shrinks a hit box (09 section 6)',
      );
    }
  });
}
