// `UiButtonRow` is the one arrangement every screen needs (11 section 3.4):
// actions on one line with the primary last, becoming a column with the
// primary on top when the line does not fit or the window is compact. It is
// an arrangement rather than a control and has no role of its own; the
// buttons inside it run the control contract in `button_test.dart`, and the
// contract is run once here to prove the arrangement does not cost them it.

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// A shared callback, so the specimens below stay const expressions.
void _noop() {}

const UiButtonRow _actions = UiButtonRow(
  primary: UiButton(label: 'Approve record', onPressed: _noop),
  secondary: UiButton(
    label: 'Cancel',
    variant: UiButtonVariant.ghost,
    onPressed: _noop,
  ),
  tertiary: <UiButton>[
    UiButton(
      label: 'Save a draft',
      variant: UiButtonVariant.secondary,
      onPressed: _noop,
    ),
  ],
);

/// Every action, in the order a row draws them.
const List<String> _inRowOrder = <String>[
  'Save a draft',
  'Cancel',
  'Approve record',
];

/// Clause 15 through the arrangement: whatever it chose, all three actions
/// are still on the screen and still read.
Future<void> _everyActionStillReads(WidgetTester tester, double width) async {
  for (final String label in _inRowOrder) {
    expect(find.text(label), findsOneWidget, reason: '$label at $width dp');
  }
}

/// The row in a [window] wide window, in a column [column] wide.
///
/// Both, because the arrangement reads one of each: the window class decides
/// whether a row is offered at all, and the constraints decide whether the
/// one it offers fits.
Future<void> _pump(
  WidgetTester tester, {
  required double window,
  required double column,
}) async {
  await tester.pumpWidget(
    uiHarness(
      size: Size(window, 800),
      child: SizedBox(width: column, child: _actions),
    ),
  );
  await tester.pumpAndSettle();
}

Rect _rect(WidgetTester tester, String label) =>
    tester.getRect(find.widgetWithText(UiButton, label));

/// The label of the button holding the keyboard focus.
String? _focused() {
  final BuildContext? context = FocusManager.instance.primaryFocus?.context;
  return context?.findAncestorWidgetOfExactType<UiButton>()?.label;
}

/// Tabs through the arrangement and reports the labels in the order it
/// reached them.
Future<List<String>> _tabOrder(WidgetTester tester) async {
  final List<String> reached = <String>[];
  for (int i = 0; i < _inRowOrder.length; i++) {
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final String? label = _focused();
    if (label != null) reached.add(label);
  }
  return reached;
}

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('the actions in it still satisfy the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _actions,
      semanticsLabel: 'Approve record',
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _everyActionStillReads),
    );
  });

  testWidgets('one line reads tertiary, secondary, primary, and ends at the '
      'end', (WidgetTester tester) async {
    await _pump(tester, window: 900, column: 900);
    expect(find.byType(UiButton), findsNWidgets(3));
    expect(
      _rect(tester, 'Save a draft').left,
      lessThan(_rect(tester, 'Cancel').left),
    );
    expect(
      _rect(tester, 'Cancel').left,
      lessThan(_rect(tester, 'Approve record').left),
    );
    expect(
      _rect(tester, 'Cancel').top,
      _rect(tester, 'Approve record').top,
      reason: 'one line',
    );
    expect(
      _rect(tester, 'Approve record').right,
      closeTo(tester.getRect(find.byType(UiButtonRow)).right, 0.5),
      reason: 'the primary sits at the end the reviewer reads toward',
    );
  });

  testWidgets('a line that does not fit becomes a column with the primary on '
      'top', (WidgetTester tester) async {
    await _pump(tester, window: 900, column: 200);
    expect(tester.takeException(), isNull);
    expect(
      _rect(tester, 'Approve record').top,
      lessThan(_rect(tester, 'Cancel').top),
    );
    expect(
      _rect(tester, 'Cancel').top,
      lessThan(_rect(tester, 'Save a draft').top),
    );
    final double centre = tester.getRect(find.byType(UiButtonRow)).center.dx;
    for (final String label in _inRowOrder) {
      expect(
        _rect(tester, label).center.dx,
        closeTo(centre, 0.5),
        reason: '$label sits on the column centre line',
      );
    }
  });

  testWidgets('a compact window stacks the actions even where the line would '
      'fit', (WidgetTester tester) async {
    await _pump(tester, window: 500, column: 900);
    expect(
      _rect(tester, 'Approve record').top,
      lessThan(_rect(tester, 'Cancel').top),
      reason:
          'below 600 the window is compact, and 11 section 3.4 stacks a '
          'compact window whatever the arithmetic says',
    );
  });

  testWidgets('the keyboard follows the screen in both arrangements', (
    WidgetTester tester,
  ) async {
    await _pump(tester, window: 900, column: 900);
    expect(
      await _tabOrder(tester),
      _inRowOrder,
      reason: 'left to right, which puts the primary last',
    );

    await _pump(tester, window: 900, column: 200);
    expect(
      await _tabOrder(tester),
      _inRowOrder.reversed.toList(),
      reason: 'top to bottom, which puts the primary first',
    );
  });

  testWidgets('a row of one is the primary on its own', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(900, 800),
        child: const UiButtonRow(
          primary: UiButton(label: 'Approve record', onPressed: _noop),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byType(UiButton), findsOneWidget);
  });
}
