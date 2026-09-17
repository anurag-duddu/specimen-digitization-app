// `UiTooltip` (10 section 4.3).

import 'package:flutter/gestures.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const String _message = 'Rotate view 90 degrees';

Widget _tooltip({PopoverPlacement placement = PopoverPlacement.above}) =>
    UiTooltip(
      message: _message,
      placement: placement,
      child: const UiButton(
        label: 'Rotate view',
        variant: UiButtonVariant.secondary,
        onPressed: _noop,
      ),
    );

void _noop() {}

/// Moves a mouse onto [finder] and leaves it there.
Future<TestGesture> _hover(WidgetTester tester, Finder finder) async {
  final TestGesture pointer = await tester.createGesture(
    kind: PointerDeviceKind.mouse,
  );
  await pointer.addPointer(location: Offset.zero);
  addTearDown(pointer.removePointer);
  await tester.pump();
  await pointer.moveTo(tester.getCenter(finder));
  await tester.pump();
  return pointer;
}

void main() {
  testWidgets('hovering shows it after the delay and not before', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _tooltip()));
    await _hover(tester, find.text('Rotate view'));

    await tester.pump(const Duration(milliseconds: 399));
    expect(
      find.text(_message),
      findsNothing,
      reason: 'a tooltip that fires on entry fires on every pass over a row',
    );

    await tester.pump(const Duration(milliseconds: 2));
    await tester.pumpAndSettle();
    expect(find.text(_message), findsOneWidget);
  });

  testWidgets('the pointer leaving hides it', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: _tooltip()));
    final TestGesture pointer = await _hover(tester, find.text('Rotate view'));
    await tester.pump(UiTooltipStyle.hoverDelay);
    await tester.pumpAndSettle();
    expect(find.text(_message), findsOneWidget);

    await pointer.moveTo(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(find.text(_message), findsNothing);
  });

  testWidgets('a long press shows it and it clears itself', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _tooltip()));
    await tester.longPress(find.text('Rotate view'));
    await tester.pumpAndSettle();
    expect(find.text(_message), findsOneWidget);

    await tester.pump(UiTooltipStyle.touchDuration);
    await tester.pumpAndSettle();
    expect(find.text(_message), findsNothing);
  });

  testWidgets('the pane is paper, not glass, and carries the tooltip role', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: _tooltip()));
    await tester.longPress(find.text('Rotate view'));
    await tester.pumpAndSettle();

    expect(
      glassPaneCount(),
      0,
      reason:
          'tooltips are small and frequent, so the pane is paper and costs no '
          'save layer (10 section 4.3)',
    );
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel(_message))
        .getSemanticsData();
    expect(
      data.tooltip,
      _message,
      reason:
          'the pane carries the tooltip property, because the role of the '
          'same name has no debug checks in this SDK and throws',
    );
    expect(
      data.hint,
      'Dismiss',
      reason:
          'a tooltip revealed by a long press names the way out, in the '
          'localised word (10 section 1.3)',
    );
    handle.dispose();
  });

  testWidgets('it never takes focus from the control it describes', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _tooltip()));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final FocusNode? before = FocusManager.instance.primaryFocus;

    await _hover(tester, find.text('Rotate view'));
    await tester.pump(UiTooltipStyle.hoverDelay);
    await tester.pumpAndSettle();
    expect(find.text(_message), findsOneWidget);
    expect(
      FocusManager.instance.primaryFocus,
      before,
      reason: 'a passive overlay describes the control and does not take over',
    );
  });

  testWidgets('a disabled control reports its reason through the tooltip', (
    WidgetTester tester,
  ) async {
    const String reason = 'Confirm label coverage before you approve';
    await tester.pumpWidget(
      uiHarness(
        child: UiTooltip.reason(
          builder: (BuildContext context, ValueChanged<String> report) =>
              Pressable(
                semanticsLabel: 'Approve record',
                disabledReason: reason,
                onDisabledReason: report,
                capsule: true,
                builder:
                    (BuildContext context, Set<WidgetState> states) =>
                        const SizedBox(width: 160, height: 48),
              ),
        ),
      ),
    );
    expect(find.text(reason), findsNothing);

    await tester.tap(find.bySemanticsLabel('Approve record'));
    await tester.pumpAndSettle();
    expect(
      find.text(reason),
      findsOneWidget,
      reason:
          'a control the server forbids owes the reviewer the reason '
          '(03 section 3.6)',
    );
  });

  testWidgets('every placement builds, right to left and at 200 percent', (
    WidgetTester tester,
  ) async {
    for (final PopoverPlacement placement in PopoverPlacement.values) {
      await tester.pumpWidget(
        uiHarness(
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: _tooltip(placement: placement),
        ),
      );
      await tester.longPress(find.text('Rotate view'));
      await tester.pumpAndSettle();
      expect(find.text(_message), findsOneWidget, reason: placement.name);
      await tester.pump(UiTooltipStyle.touchDuration);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('nothing animates under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: _tooltip()),
    );
    await tester.longPress(find.text('Rotate view'));
    await tester.pump();
    expect(find.text(_message), findsOneWidget);
    expect(tester.binding.transientCallbackCount, 0);
    await tester.pump(UiTooltipStyle.touchDuration);
    await tester.pumpAndSettle();
  });

  testWidgets('the control it wraps satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _tooltip(),
      semanticsLabel: 'Rotate view',
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(find.bySemanticsLabel('Rotate view'), findsOneWidget);
        },
      ),
    );
  });
}
