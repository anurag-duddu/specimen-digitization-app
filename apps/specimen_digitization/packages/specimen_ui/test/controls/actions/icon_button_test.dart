// `UiIconButton` is the one control in the family with no visible text, so
// its label and its tooltip are the whole of what a reviewer who cannot see
// the glyph is given.

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// Clause 15 for an icon button. It has no label to arrange, so the clause
/// asks only that the disc and its target survive every width.
Future<void> _stillOneDisc(WidgetTester tester, double width) async {
  expect(find.byType(UiIconButton), findsOneWidget, reason: 'at $width dp');
  expect(
    tester.getSize(find.byType(Pressable)).height,
    greaterThanOrEqualTo(UiDensity.hitBox),
    reason: 'the disc keeps its 48 dp target at $width dp',
  );
}

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
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiIconButton(
        icon: UiIcons.rotateView,
        semanticsLabel: 'Rotate the view',
        onPressed: () {},
      ),
      semanticsLabel: 'Rotate the view',
      hasRole: (SemanticsFlags flags) => flags.isButton,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _stillOneDisc),
    );
  });

  testWidgets('a disabled icon button satisfies the contract and states the '
      'reason', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiIconButton(
        icon: UiIcons.correctRegions,
        semanticsLabel: 'Correct label regions',
        disabledReason: 'Label regions can be corrected once processing ends.',
      ),
      semanticsLabel: 'Correct label regions',
      disabledWithReason: true,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _stillOneDisc),
    );
  });

  testWidgets('the tooltip defaults to the label, so the two never disagree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: UiIconButton(
          icon: UiIcons.rotateView,
          semanticsLabel: 'Rotate the view',
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel('Rotate the view'))
        .getSemanticsData();
    expect(data.tooltip, 'Rotate the view');
    expect(data.label, 'Rotate the view');
    handle.dispose();
  });

  testWidgets('a tooltip may say more than the label', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: UiIconButton(
          icon: UiIcons.retry,
          semanticsLabel: 'Retry processing',
          tooltip: 'Retry processing from the last checkpoint',
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel('Retry processing'))
        .getSemanticsData();
    expect(data.tooltip, 'Retry processing from the last checkpoint');
    handle.dispose();
  });

  testWidgets('the disc is 48 at touch and 40 at pointer, and the hit box is '
      '48 in both', (WidgetTester tester) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: UiIconButton(
            icon: UiIcons.rotateView,
            semanticsLabel: 'Rotate the view',
            onPressed: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .getSize(
              find
                  .descendant(
                    of: find.byType(UiIconButton),
                    matching: find.byType(SizedBox),
                  )
                  .first,
            )
            .height,
        UiDensity.of(density).controlHeight,
        reason: 'the visual disc in ${density.name}',
      );
      expect(
        tester.getSize(find.byType(UiIconButton)).height,
        greaterThanOrEqualTo(UiDensity.hitBox),
      );
    }
  });

  testWidgets('both variants paint what 10 section 4.1 names', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    const Set<WidgetState> rest = <WidgetState>{};
    final UiIconButtonStyle ghost = UiIconButtonStyle.resolve(
      ui,
      UiIconButtonVariant.ghost,
    );
    final UiIconButtonStyle secondary = UiIconButtonStyle.resolve(
      ui,
      UiIconButtonVariant.secondary,
    );
    expect(ghost.background.resolve(rest).a, 0);
    expect(ghost.side.resolve(rest), isNull);
    expect(
      secondary.background.resolve(rest),
      Color.alphaBlend(ui.glass.flat.fill, ui.color.paper),
    );
    expect(secondary.side.resolve(rest)?.color, ui.color.boundary);
    expect(ghost.foreground.resolve(rest), ui.color.ink);
    expect(
      ghost.foreground.resolve(const <WidgetState>{WidgetState.disabled}),
      ui.color.disabledContent,
    );
  });

  testWidgets('a current destination draws the fill form of its glyph', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: UiIconButton(
          icon: UiIcons.queue,
          semanticsLabel: 'Open the queue',
          current: true,
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.widget<Icon>(find.byType(Icon)).icon,
      UiIcons.queue.resolve(current: true),
    );
    expect(
      UiIcons.queue.resolve(current: true),
      isNot(UiIcons.queue.resolve()),
    );
  });

  testWidgets('it presses, and a disabled one does not', (
    WidgetTester tester,
  ) async {
    int pressed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiIconButton(
          icon: UiIcons.reload,
          semanticsLabel: 'Reload the queue',
          onPressed: () => pressed++,
        ),
      ),
    );
    await tester.tap(find.byType(UiIconButton));
    await tester.pumpAndSettle();
    expect(pressed, 1);

    await tester.pumpWidget(
      uiHarness(
        child: const UiIconButton(
          icon: UiIcons.reload,
          semanticsLabel: 'Reload the queue',
          disabledReason: 'The queue is loading.',
        ),
      ),
    );
    await tester.tap(find.byType(UiIconButton));
    await tester.pumpAndSettle();
    expect(pressed, 1);
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: UiIconButton(
          icon: UiIcons.back,
          semanticsLabel: 'Go back to the queue',
          variant: UiIconButtonVariant.secondary,
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    // A glyph is not text: the disc holds its size while the type around it
    // grows, which is what keeps a row of actions from reflowing.
    expect(
      tester
          .getSize(
            find
                .descendant(
                  of: find.byType(UiIconButton),
                  matching: find.byType(SizedBox),
                )
                .first,
          )
          .height,
      UiDensity.touch.controlHeight,
    );
  });

  testWidgets('hovering draws the tooltip, so the words are visible too', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: UiIconButton(
          icon: UiIcons.reload,
          semanticsLabel: 'Reload the queue',
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Reload the queue'), findsNothing);

    final TestGesture pointer = await _hover(tester, find.byType(UiIconButton));
    await tester.pump(UiTooltipStyle.hoverDelay);
    await tester.pumpAndSettle();
    expect(
      find.text('Reload the queue'),
      findsOneWidget,
      reason:
          'the label doubles as the tooltip and the tooltip is drawn, not '
          'only published to the platform (10 section 4.1)',
    );

    await pointer.moveTo(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(find.text('Reload the queue'), findsNothing);
  });

  testWidgets('a disabled button draws the reason rather than its label', (
    WidgetTester tester,
  ) async {
    const String reason =
        'Label regions can be corrected once processing ends.';
    await tester.pumpWidget(
      uiHarness(
        child: const UiIconButton(
          icon: UiIcons.edit,
          semanticsLabel: 'Correct the label regions',
          disabledReason: reason,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text(reason), findsNothing);

    // Reaching for a control the server forbids is what asks for the reason.
    // `FocusableActionDetector` does not report a hover while it is disabled,
    // so the press and the long press are the two ways in, exactly as the
    // overlays slot built the carrier.
    await tester.tap(find.byType(UiIconButton));
    await tester.pumpAndSettle();
    expect(
      find.text(reason),
      findsOneWidget,
      reason:
          'the reason flows through Pressable.onDisabledReason into '
          'UiTooltip.reason, which is the carrier 10 section 4.3 names',
    );
    expect(
      find.text('Correct the label regions'),
      findsNothing,
      reason: 'the reason is what the reviewer needs, not the button name',
    );
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Correct the label regions'))
          .getSemanticsData()
          .hint,
      reason,
      reason: 'the hint carries it too, for a reviewer with no pointer',
    );
  });
}
