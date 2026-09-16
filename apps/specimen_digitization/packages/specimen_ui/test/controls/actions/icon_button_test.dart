// `UiIconButton` is the one control in the family with no visible text, so
// its label and its tooltip are the whole of what a reviewer who cannot see
// the glyph is given.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

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
}
