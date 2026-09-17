// `UiDecisionBar` and `UiDecisionSwipe` (13 section 3.3).

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const String _clear = 'Clear record';
const String _defer = 'Defer record';
const String _count = '1 of 4';

Widget _bar({
  VoidCallback? onPrimary,
  VoidCallback? onSecondary,
  VoidCallback? onPrevious,
  VoidCallback? onNext,
  bool withSecondary = true,
}) => UiDecisionBar(
  primary: UiButton(label: _clear, onPressed: onPrimary ?? () {}),
  secondary: withSecondary
      ? UiButton(label: _defer, onPressed: onSecondary ?? () {})
      : null,
  count: _count,
  onPrevious: onPrevious,
  onNext: onNext,
);

Future<void> _pump(
  WidgetTester tester,
  Widget bar, {
  double width = 1180,
  TextDirection direction = TextDirection.ltr,
}) async {
  await tester.pumpWidget(
    uiHarness(
      size: Size(width, 800),
      textDirection: direction,
      child: SizedBox(width: width, child: bar),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('satisfies the control contract through its decision', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _bar(),
      semanticsLabel: _clear,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          // The decision is on the bar at every width. What moves is the
          // other one, and where it moves to is the next test.
          expect(find.bySemanticsLabel(_clear), findsOneWidget);
        },
      ),
    );
  });

  testWidgets('is one row of the density height', (WidgetTester tester) async {
    await _pump(tester, _bar());

    // `density.controlHeight` grown by the type it holds, floored at the hit
    // box: 48 here, and 64 on screen once the scaffold's action bar pane has
    // padded it (13 section 2.3).
    expect(tester.getSize(find.byType(UiDecisionBar)).height, 48);
  });

  testWidgets('the secondary sits beside the primary while the line holds it', (
    WidgetTester tester,
  ) async {
    await _pump(tester, _bar());

    expect(find.text(_defer), findsOneWidget);
    expect(
      find.bySemanticsLabel(UiDecisionBar.defaultOverflowLabel),
      findsNothing,
    );
    expect(
      tester.getRect(find.text(_defer)).left,
      lessThan(tester.getRect(find.text(_clear)).left),
      reason: 'the primary is last in the line (11 section 3.4)',
    );
  });

  testWidgets('the secondary moves into the overflow rather than going away', (
    WidgetTester tester,
  ) async {
    int deferred = 0;
    await _pump(tester, _bar(onSecondary: () => deferred++), width: 280);

    expect(find.text(_defer), findsNothing);
    final Finder trigger = find.bySemanticsLabel(
      UiDecisionBar.defaultOverflowLabel,
    );
    expect(trigger, findsOneWidget);

    await tester.tap(trigger);
    await tester.pumpAndSettle();
    expect(find.text(_defer), findsOneWidget);

    await tester.tap(find.text(_defer));
    await tester.pumpAndSettle();
    expect(
      deferred,
      1,
      reason:
          'a decision unreachable at 360 dp is a decision the product '
          'does not offer on a phone',
    );
  });

  testWidgets('previous and next are edge buttons from medium up', (
    WidgetTester tester,
  ) async {
    int moved = 0;
    await _pump(
      tester,
      _bar(onPrevious: () => moved--, onNext: () => moved++),
      width: 700,
    );

    final Finder previous = find.bySemanticsLabel(
      UiDecisionBar.defaultPreviousLabel,
    );
    final Finder next = find.bySemanticsLabel(UiDecisionBar.defaultNextLabel);
    expect(previous, findsOneWidget);
    expect(next, findsOneWidget);
    expect(
      tester.getRect(previous).left,
      lessThan(tester.getRect(find.text(_count)).left),
      reason: 'previous holds the leading edge and next the trailing one',
    );
    expect(
      tester.getRect(next).right,
      greaterThan(tester.getRect(previous).right),
    );

    await tester.tap(next);
    await tester.pumpAndSettle();
    expect(moved, 1);
  });

  testWidgets('a compact window draws no edge buttons', (
    WidgetTester tester,
  ) async {
    await _pump(tester, _bar(onPrevious: () {}, onNext: () {}), width: 390);

    // Five controls do not fit a phone's line, and the two the thumb can do
    // without are the two that move between records (13 section 2.3).
    expect(
      find.bySemanticsLabel(UiDecisionBar.defaultPreviousLabel),
      findsNothing,
    );
    expect(find.bySemanticsLabel(UiDecisionBar.defaultNextLabel), findsNothing);
    expect(
      UiDecisionBar.edgesAt(tester.element(find.byType(UiDecisionBar))),
      isFalse,
    );
  });

  group('UiDecisionSwipe', () {
    testWidgets('a fling against the reading direction moves forward', (
      WidgetTester tester,
    ) async {
      int moved = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: SizedBox(
            width: 390,
            height: 400,
            child: UiDecisionSwipe(
              onPrevious: () => moved--,
              onNext: () => moved++,
              child: const ColoredBox(color: Color(0xFF000000)),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.fling(
        find.byType(UiDecisionSwipe),
        const Offset(-300, 0),
        800,
      );
      await tester.pumpAndSettle();
      expect(moved, 1);

      await tester.fling(
        find.byType(UiDecisionSwipe),
        const Offset(300, 0),
        800,
      );
      await tester.pumpAndSettle();
      expect(moved, 0);
    });

    testWidgets('right to left means the same thing in the same direction', (
      WidgetTester tester,
    ) async {
      int moved = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          textDirection: TextDirection.rtl,
          child: SizedBox(
            width: 390,
            height: 400,
            child: UiDecisionSwipe(
              onNext: () => moved++,
              child: const ColoredBox(color: Color(0xFF000000)),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Forward is against the reading direction in both scripts, so the
      // gesture reads the same way to a reviewer in either.
      await tester.fling(
        find.byType(UiDecisionSwipe),
        const Offset(300, 0),
        800,
      );
      await tester.pumpAndSettle();
      expect(moved, 1);
    });

    testWidgets('a slow drag is not a move', (WidgetTester tester) async {
      int moved = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: SizedBox(
            width: 390,
            height: 400,
            child: UiDecisionSwipe(
              onNext: () => moved++,
              child: const ColoredBox(color: Color(0xFF000000)),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.drag(find.byType(UiDecisionSwipe), const Offset(-200, 0));
      await tester.pumpAndSettle();
      expect(
        moved,
        0,
        reason:
            'a drag that ends where it stopped is a reviewer changing '
            'their mind, not a record move',
      );
    });

    testWidgets('both moves reach a screen reader as named actions', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await tester.pumpWidget(
        uiHarness(
          child: UiDecisionSwipe(
            onPrevious: () {},
            onNext: () {},
            child: const SizedBox(width: 200, height: 200),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final SemanticsNode node = tester.getSemantics(
        find.byType(UiDecisionSwipe),
      );
      final List<String?> labels = node
          .getSemanticsData()
          .customSemanticsActionIds!
          .map((int id) => CustomSemanticsAction.getAction(id)?.label)
          .toList();
      expect(
        labels,
        containsAll(<String?>[
          UiDecisionBar.defaultPreviousLabel,
          UiDecisionBar.defaultNextLabel,
        ]),
        reason:
            'a swipe with no visible control is exactly what the custom '
            'action list exists for',
      );
      handle.dispose();
    });
  });
}
