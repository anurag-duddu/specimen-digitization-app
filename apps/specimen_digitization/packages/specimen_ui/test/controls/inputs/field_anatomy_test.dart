// The proof 11 section 4 asks for: one edge, one ring, one node.
//
// Three defects met in a focused field, and each of them was a layer doing
// another layer's job. The bridge `ThemeData`'s `InputDecorationTheme` painted
// its enabled and focused borders under ours through the collapsed decoration
// inside `FieldCore`; the core painted a ring of its own; the box thickened
// its outline on focus and drew a second ring around it. The counts below are
// what keeps any of that from coming back, and they are taken twice: under a
// bare `WidgetsApp`, which is the package's own world, and under a
// `MaterialApp` carrying the bridge theme, which is the application's.
//
// The bridge theme here is rebuilt from the package's tokens rather than
// imported: `specimenInputTheme` lives in
// `apps/specimen_digitization/lib/src/theme/component_themes.dart`, and a
// package test that imported the application would invert the dependency the
// layering gate exists to hold. What matters is that an
// `InputDecorationTheme` with borders on every state is above the field and
// paints none of them.

import 'package:flutter/material.dart'
    show InputDecorationTheme, InputDecorator, MaterialApp, OutlineInputBorder;
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';
import 'inputs_finders.dart';

const String _label = 'Reason for this decision';
const String _help = 'Kept in the record history.';

/// An equivalent of the application's `specimenInputTheme`: a border on every
/// state, a fill, and a focused border that is wider than the rest.
InputDecorationTheme _bridgeInputTheme(UiThemeData ui) {
  OutlineInputBorder border(Color color, double width) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(ui.shape.field),
    borderSide: BorderSide(color: color, width: width),
  );
  final UiStroke stroke = ui.shape.stroke;
  return InputDecorationTheme(
    filled: true,
    fillColor: ui.color.paper,
    border: border(ui.color.boundary, stroke.boundary),
    enabledBorder: border(ui.color.boundary, stroke.boundary),
    focusedBorder: border(ui.color.ink, stroke.emphasis),
    errorBorder: border(ui.color.status.blocked.content, stroke.boundary),
    focusedErrorBorder: border(
      ui.color.status.blocked.content,
      stroke.emphasis,
    ),
    disabledBorder: border(ui.color.disabledOutline, stroke.boundary),
  );
}

/// The application's world: a `MaterialApp` on the bridge theme.
Widget _bridgeHarness({
  required Widget child,
  UiDensityMode density = UiDensityMode.touch,
}) {
  final UiThemeData ui = UiThemeData.light();
  return MediaQuery(
    data: const MediaQueryData(size: Size(800, 600)),
    child: Density(
      initialMode: density,
      child: UiTheme(
        data: ui,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: ui
              .toThemeData()
              .copyWith(inputDecorationTheme: _bridgeInputTheme(ui)),
          home: Align(child: child),
        ),
      ),
    ),
  );
}

/// The package's own world: a bare `WidgetsApp`, no Material theme at all.
Widget _bareHarness({
  required Widget child,
  UiDensityMode density = UiDensityMode.touch,
}) => uiHarness(density: density, child: child);

typedef _Harness =
    Widget Function({required Widget child, UiDensityMode density});

const Map<String, _Harness> _harnesses = <String, _Harness>{
  'under a bare WidgetsApp': _bareHarness,
  'under the bridge theme': _bridgeHarness,
};

void main() {
  _harnesses.forEach((String where, _Harness harness) {
    group('a focused field $where', () {
      testWidgets('draws one edge and one ring', (WidgetTester tester) async {
        final FocusNode node = FocusNode();
        addTearDown(node.dispose);
        for (final UiDensityMode density in UiDensityMode.values) {
          await tester.pumpWidget(
            harness(
              density: density,
              child: SizedBox(
                width: 320,
                child: UiField(
                  label: _label,
                  helpText: _help,
                  focusNode: node,
                  hintText: 'Say what you saw on the label',
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          final Finder field = find.byType(UiField);

          expect(
            visibleEdges(tester, field),
            1,
            reason: 'a field at rest has one edge in ${density.name}',
          );
          expect(visibleRings(tester, field), 0);

          node.requestFocus();
          await tester.pumpAndSettle();
          expect(
            visibleEdges(tester, field),
            1,
            reason:
                'a focused field has the same one edge in ${density.name}. '
                'Two means the outline thickened and a ring came with it, or '
                'a decorator painted one underneath.',
          );
          expect(
            visibleRings(tester, field),
            1,
            reason: 'one ring, and it is the whole focus treatment',
          );
          expect(
            ringPainters(tester, field),
            1,
            reason:
                'counted from the painting side as well: one foreground '
                'painter over the field, which is the ring',
          );

          node.unfocus();
          await tester.pumpAndSettle();
        }
      });

      testWidgets('has no decorator to paint through', (
        WidgetTester tester,
      ) async {
        await tester.pumpWidget(
          harness(
            density: UiDensityMode.touch,
            child: const SizedBox(width: 320, child: UiField(label: _label)),
          ),
        );
        await tester.pumpAndSettle();
        expect(
          find.byType(InputDecorator),
          findsNothing,
          reason:
              'the decoration is absent rather than collapsed, so the bridge '
              'theme has nothing to paint through (11 section 4)',
        );
      });

      testWidgets('carries the same edge either way', (
        WidgetTester tester,
      ) async {
        await tester.pumpWidget(
          harness(
            density: UiDensityMode.touch,
            child: const SizedBox(width: 320, child: UiField(label: _label)),
          ),
        );
        await tester.pumpAndSettle();
        final UiThemeData ui = uiOf(tester);
        expect(fieldSide(tester).color, ui.color.boundary);
        expect(fieldSide(tester).width, ui.shape.stroke.boundary);
        expect(fieldFill(tester), ui.color.paper);
      });
    });
  });

  group('the field publishes one node', () {
    testWidgets('and it is the size a finger has to hit', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle semantics = tester.ensureSemantics();
      final TextEditingController controller = TextEditingController(
        text: 'The date on the label reads 1946',
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
                helpText: _help,
                clearLabel: 'Clear the reason',
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        // Wave 2 recorded the defect: the editor published a node 22 dp tall
        // inside the 48 dp control, so every one of these failed on a field.
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));

        final SemanticsNode node = tester.getSemantics(
          find.bySemanticsLabel(_label),
        );
        final SemanticsData data = node.getSemanticsData();
        expect(
          data.flagsCollection.isTextField,
          isTrue,
          reason: 'the merged node is still a text field',
        );
        expect(data.label, _label);
        expect(
          data.value,
          'The date on the label reads 1946',
          reason: 'the editor\'s value comes up with it, and comes up once',
        );
        expect(data.hint, _help);
        expect(
          node.rect.size,
          tester.getSize(find.byType(UiFieldBox)),
          reason:
              'the node is the box, in ${density.name}: 48 dp of hit box '
              'rather than 22 dp of line',
        );
        expect(
          data.hasAction(SemanticsAction.tap),
          isTrue,
          reason: 'the merged node is what a screen reader taps to edit',
        );

        await tester.tap(find.bySemanticsLabel(_label));
        await tester.pumpAndSettle();
        final SemanticsData editing = tester
            .getSemantics(find.bySemanticsLabel(_label))
            .getSemanticsData();
        expect(
          editing.hasAction(SemanticsAction.setSelection),
          isTrue,
          reason:
              'merging keeps the editor\'s own actions, which is why it is a '
              'merge rather than an exclusion: a braille display and voice '
              'control both drive a field through these',
        );
        expect(editing.hasAction(SemanticsAction.setText), isTrue);
      }
      semantics.dispose();
    });

    testWidgets('and the clear control keeps its own', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle semantics = tester.ensureSemantics();
      final TextEditingController controller = TextEditingController(
        text: 'Chicago',
      );
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        uiHarness(
          density: UiDensityMode.pointer,
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
      expect(
        find.bySemanticsLabel('Clear the reason'),
        findsOneWidget,
        reason:
            'the trailing action sits outside the merge. Inside it the field '
            'would read "Reason for this decision Clear the reason" and the '
            'reviewer would have no way to press just the one.',
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel(_label)).getSemanticsData()
            .label,
        _label,
      );
      semantics.dispose();
    });
  });
}
