// UiField (10 section 4.2).
//
// Every state transition the field owns: focus, error, clear, submit and
// disabled with a reason, plus the control contract.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';
import 'inputs_finders.dart';

const String _label = 'Reason for this decision';
const String _help = 'Kept in the record history.';
const String _error = 'Enter a reason for this decision.';
const String _reason = 'Sign in again before you record a decision.';

void main() {
  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const SizedBox(
        width: 320,
        child: UiField(label: _label, helpText: _help),
      ),
      semanticsLabel: _label,
      activation: ControlActivation.textEditing,
    );
  });

  testWidgets('a disabled field carries the reason on its hint', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const SizedBox(
        width: 320,
        child: UiField(label: _label, enabled: false, disabledReason: _reason),
      ),
      semanticsLabel: _label,
      disabledWithReason: true,
    );
  });

  testWidgets('the edge holds and the ring is the whole focus treatment', (
    WidgetTester tester,
  ) async {
    final FocusNode node = FocusNode();
    addTearDown(node.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiField(label: _label, focusNode: node),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final UiThemeData ui = uiOf(tester);

    expect(fieldSide(tester).color, ui.color.boundary);
    expect(fieldSide(tester).width, ui.shape.stroke.boundary);
    expect(visibleRings(tester), 0);

    node.requestFocus();
    await tester.pumpAndSettle();
    expect(
      fieldSide(tester).color,
      ui.color.boundary,
      reason:
          'the edge does not change colour on focus (09 section 3.6, fit '
          'amendment)',
    );
    expect(
      fieldSide(tester).width,
      ui.shape.stroke.boundary,
      reason:
          'the edge used to thicken to 2 dp and then take a ring as well, '
          'which is two of the three edges a focused field drew',
    );
    expect(
      visibleRings(tester),
      1,
      reason: 'the ring is the whole of it, and there is one',
    );

    node.unfocus();
    await tester.pumpAndSettle();
    expect(fieldSide(tester).color, ui.color.boundary);
    expect(visibleRings(tester), 0);
  });

  testWidgets('a pointer tap rings the field, as the keyboard does', (
    WidgetTester tester,
  ) async {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTouch;
    addTearDown(
      () => FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.automatic,
    );
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(width: 320, child: UiField(label: _label)),
      ),
    );
    await tester.pumpAndSettle();
    expect(visibleRings(tester), 0);

    await tester.tap(find.byType(FieldCore));
    await tester.pumpAndSettle();
    expect(
      visibleRings(tester),
      1,
      reason:
          'a reviewer who clicked into a field is owed the same "you are '
          'here" the keyboard gives: a caret does not say which of several '
          'fields holds it (09 section 3.6, fit amendment)',
    );
  });

  testWidgets('the box height derives from the text, not from a constant', (
    WidgetTester tester,
  ) async {
    Future<double> boxHeight(double scale, UiDensityMode density) async {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          textScaler: TextScaler.linear(scale),
          child: const SizedBox(width: 320, child: UiField(label: _label)),
        ),
      );
      await tester.pumpAndSettle();
      return tester.getSize(find.byType(UiFieldBox)).height;
    }

    for (final UiDensityMode density in UiDensityMode.values) {
      final double plain = await boxHeight(1, density);
      final double medium = await boxHeight(1.3, density);
      final double large = await boxHeight(2, density);
      final UiThemeData ui = uiOf(tester);
      expect(
        plain,
        greaterThanOrEqualTo(UiDensity.hitBox),
        reason: 'the hit box is 48 at every scale and in both densities',
      );
      expect(
        medium,
        greaterThanOrEqualTo(plain),
        reason: 'a height that holds text is never a constant (11 section 2.2)',
      );
      expect(
        large,
        greaterThan(medium),
        reason:
            'at 200 percent the line box is taller than the density height, '
            'so the box grows with it in ${density.name}',
      );
      // The inset that reproduces the density height at scale 1.0, kept on
      // both sides as the text grows.
      final TextStyle role = ui.type.body;
      final double line = role.fontSize! * role.height!;
      final double inset = (ui.density.controlHeight - line) / 2;
      expect(
        large,
        greaterThanOrEqualTo(line * 2 + 2 * inset),
        reason: 'the scaled line box plus its two insets is the floor',
      );
    }
  });

  testWidgets('the fill does not change on focus', (WidgetTester tester) async {
    final FocusNode node = FocusNode();
    addTearDown(node.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiField(label: _label, focusNode: node),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final Color rest = fieldFill(tester);
    node.requestFocus();
    await tester.pumpAndSettle();
    expect(
      fieldFill(tester),
      rest,
      reason: '10 section 4.2 forbids a fill change on focus',
    );
  });

  testWidgets('an error paints the edge, draws its glyph and is announced', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    Widget build(String? error) => uiHarness(
      child: SizedBox(
        width: 320,
        child: UiField(label: _label, helpText: _help, errorText: error),
      ),
    );

    await tester.pumpWidget(build(null));
    await tester.pumpAndSettle();
    expect(find.text(_help), findsOneWidget);
    expect(liveRegions(tester), isEmpty);

    await tester.pumpWidget(build(_error));
    await tester.pumpAndSettle();
    final UiThemeData ui = uiOf(tester);
    expect(fieldSide(tester).color, ui.color.status.blocked.content);
    expect(find.text(_error), findsOneWidget);
    expect(
      find.text(_help),
      findsNothing,
      reason: 'the error replaces the help line rather than stacking on it',
    );
    expect(
      liveRegions(tester),
      <String>[_error],
      reason:
          'the error is announced once through Announcer when it appears '
          '(10 section 4.2)',
    );
    semantics.dispose();
  });

  testWidgets('the node reads the label, the value and the help line', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    final TextEditingController controller = TextEditingController(
      text: 'The date reads 1946',
    );
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiField(
            label: _label,
            helpText: _help,
            controller: controller,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel(_label))
        .getSemanticsData();
    expect(data.label, _label);
    expect(data.value, 'The date reads 1946');
    expect(data.hint, _help);
    expect(data.flagsCollection.isTextField, isTrue);
    expect(
      find.bySemanticsLabel(_label),
      findsOneWidget,
      reason: 'the visible label is excluded, so the words are read once',
    );
    semantics.dispose();
  });

  testWidgets('the clear control appears with content and empties the field', (
    WidgetTester tester,
  ) async {
    final TextEditingController controller = TextEditingController();
    addTearDown(controller.dispose);
    final List<String> changes = <String>[];
    int cleared = 0;
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiField(
            label: _label,
            controller: controller,
            clearLabel: 'Clear the reason',
            onChanged: changes.add,
            onClear: () => cleared++,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel('Clear the reason'),
      findsNothing,
      reason: 'there is nothing to clear yet',
    );

    await tester.enterText(find.byType(FieldCore), 'Chicago');
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Clear the reason'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('Clear the reason'));
    await tester.pumpAndSettle();
    expect(controller.text, isEmpty);
    expect(changes.last, isEmpty);
    expect(cleared, 1);
    expect(find.bySemanticsLabel('Clear the reason'), findsNothing);
  });

  testWidgets('the clear control has its own 48 dp hit box in both densities', (
    WidgetTester tester,
  ) async {
    final TextEditingController controller = TextEditingController(
      text: 'Chicago',
    );
    addTearDown(controller.dispose);
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: SizedBox(
            width: 320,
            child: UiField(
              label: _label,
              controller: controller,
              clearLabel: 'Clear the reason',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final Size size = tester.getSize(
        find.bySemanticsLabel('Clear the reason'),
      );
      expect(
        size.height,
        greaterThanOrEqualTo(UiDensity.hitBox),
        reason:
            'the clear control is ${size.height} tall in ${density.name}. A '
            '40 dp field still owes its action a 48 dp box, which is what '
            'the slop around the field is for.',
      );
      expect(size.width, greaterThanOrEqualTo(UiDensity.hitBox));
    }
  });

  testWidgets('it submits what the reviewer typed', (
    WidgetTester tester,
  ) async {
    final List<String> submitted = <String>[];
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiField(label: _label, onSubmitted: submitted.add),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(FieldCore), 'Chicago, 1946');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(submitted, <String>['Chicago, 1946']);
  });

  testWidgets('the counter counts what is there', (WidgetTester tester) async {
    final TextEditingController controller = TextEditingController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiField(
            label: 'Catalogue number',
            controller: controller,
            maxLength: 24,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('0 / 24'), findsOneWidget);
    await tester.enterText(find.byType(FieldCore), 'FMNH 1946');
    await tester.pumpAndSettle();
    expect(find.text('9 / 24'), findsOneWidget);
  });

  testWidgets('the visual is the control height and the hit box is 48', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: const SizedBox(width: 320, child: UiField(label: _label)),
        ),
      );
      await tester.pumpAndSettle();
      final UiThemeData ui = uiOf(tester);
      expect(
        tester.getSize(find.byType(FieldCore).hitTestable()).height,
        lessThanOrEqualTo(ui.density.controlHeight),
      );
      expect(
        tester.getSize(find.bySemanticsLabel(_label)).height,
        greaterThanOrEqualTo(UiDensity.hitBox),
      );
    }
  });

  testWidgets('it grows rather than clips at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 320,
          child: UiField(label: _label, helpText: _help),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final double plain = tester.getSize(find.byType(UiField)).height;

    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const SizedBox(
          width: 320,
          child: UiField(label: _label, helpText: _help),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(UiField)).height,
      greaterThan(plain),
      reason: 'heights grow and widths wrap (10 section 2 clause 7)',
    );
  });

  testWidgets('the leading glyph sits at the reading start under RTL', (
    WidgetTester tester,
  ) async {
    Future<double> glyphCentre(TextDirection direction) async {
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: const SizedBox(
            width: 320,
            child: UiField(label: _label, leading: UiIcons.record),
          ),
        ),
      );
      await tester.pumpAndSettle();
      return tester.getCenter(find.byType(UiIcon)).dx;
    }

    final double ltr = await glyphCentre(TextDirection.ltr);
    final double rtl = await glyphCentre(TextDirection.rtl);
    expect(
      rtl,
      greaterThan(ltr),
      reason: 'the start of the row moves to the right under RTL',
    );
  });
}
