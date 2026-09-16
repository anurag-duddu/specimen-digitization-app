// UiSearchField (10 section 4.2).
//
// The capsule, the clear control, and the two keys the control owns: Escape
// clears and then unfocuses, Enter submits.

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';
import 'inputs_finders.dart';

const String _label = 'Search the queue';
const String _clear = 'Clear the search';

void main() {
  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const SizedBox(
        width: 320,
        child: UiSearchField(label: _label, clearLabel: _clear),
      ),
      semanticsLabel: _label,
      activation: ControlActivation.textEditing,
    );
  });

  testWidgets('a disabled search field carries the reason on its hint', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const SizedBox(
        width: 320,
        child: UiSearchField(
          label: _label,
          clearLabel: _clear,
          enabled: false,
          disabledReason: 'Open a collection before you search it.',
        ),
      ),
      semanticsLabel: _label,
      disabledWithReason: true,
    );
  });

  testWidgets('it is a capsule with the search glyph leading', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 320,
          child: UiSearchField(label: _label, clearLabel: _clear),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.widget<UiFieldBox>(find.byType(UiFieldBox)).style.capsule,
      isTrue,
    );
    expect(
      tester.widget<UiIcon>(find.byType(UiIcon).first).spec,
      UiIcons.search,
    );
    expect(
      find.text(_label),
      findsNothing,
      reason: 'the label is carried in semantics, not drawn, by default',
    );
  });

  testWidgets('Escape clears, and then unfocuses', (WidgetTester tester) async {
    final TextEditingController controller = TextEditingController();
    final FocusNode node = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(node.dispose);
    final List<String> changes = <String>[];
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiSearchField(
            label: _label,
            clearLabel: _clear,
            controller: controller,
            focusNode: node,
            onChanged: changes.add,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(FieldCore), 'Chicago');
    await tester.pumpAndSettle();
    expect(node.hasFocus, isTrue);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(controller.text, isEmpty, reason: 'the first Escape clears');
    expect(changes.last, isEmpty);
    expect(
      node.hasFocus,
      isTrue,
      reason: 'clearing a query is not the same as leaving the field',
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(
      node.hasFocus,
      isFalse,
      reason: 'the second Escape, with nothing left to clear, unfocuses',
    );
  });

  testWidgets('Enter submits the query', (WidgetTester tester) async {
    final List<String> submitted = <String>[];
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiSearchField(
            label: _label,
            clearLabel: _clear,
            onSubmitted: submitted.add,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(FieldCore), 'Chicago');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(submitted, <String>['Chicago']);
  });

  testWidgets('the clear control appears only with something to clear', (
    WidgetTester tester,
  ) async {
    final TextEditingController controller = TextEditingController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiSearchField(
            label: _label,
            clearLabel: _clear,
            controller: controller,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(_clear), findsNothing);

    await tester.enterText(find.byType(FieldCore), 'Chicago');
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(_clear), findsOneWidget);

    await tester.tap(find.bySemanticsLabel(_clear));
    await tester.pumpAndSettle();
    expect(controller.text, isEmpty);
    expect(find.bySemanticsLabel(_clear), findsNothing);
  });

  testWidgets('the capsule reads the error edge like any other field', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 320,
          child: UiSearchField(
            label: _label,
            clearLabel: _clear,
            helpText: 'Matches the specimen id and the collector.',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(fieldSide(tester).color, uiOf(tester).color.boundary);
    expect(
      find.text('Matches the specimen id and the collector.'),
      findsOneWidget,
    );
  });
}
