// `UiButton` is the reference control of the actions family: four variants,
// three sizes, two glyph slots and a loading state that has to hold its width.

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// The contract rebuilds its subject many times; a shared callback keeps the
/// closure out of the const expression that would otherwise be one.
void _noop() {}

/// Clause 15 for a button. 11 section 3.3 gives it no compact variant, so
/// what a reviewer is given at every width is one button carrying one label.
Future<void> _stillOneButton(WidgetTester tester, double width) async {
  expect(find.byType(UiButton), findsOneWidget, reason: 'at $width dp');
  expect(find.text('Approve record'), findsOneWidget, reason: 'at $width dp');
}

/// The height of the capsule itself, which is smaller than the hit box in
/// `pointer` density and at size `sm`.
Size _visual(WidgetTester tester) => tester.getSize(
  find
      .descendant(
        of: find.byType(UiButton),
        matching: find.byType(DecoratedBox),
      )
      .first,
);

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
      (BuildContext context) =>
          UiButton(label: 'Approve record', onPressed: () {}),
      semanticsLabel: 'Approve record',
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _stillOneButton),
    );
  });

  testWidgets('a disabled button satisfies the contract and states the '
      'reason', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiButton(
        label: 'Approve record',
        disabledReason: 'Confirm label coverage before you approve.',
      ),
      semanticsLabel: 'Approve record',
      disabledWithReason: true,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _stillOneButton),
    );
  });

  testWidgets('its intrinsic width is the width it takes when nobody has '
      'bounded it', (WidgetTester tester) async {
    late double declared;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) {
            const UiButton button = UiButton(
              label: 'Open the next record',
              trailing: UiIcons.next,
              onPressed: _noop,
            );
            declared = button.intrinsicWidth(context);
            return button;
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(UiButton)).width,
      closeTo(declared, 0.5),
      reason:
          'the width a button declares is the width it draws at, or '
          'UiButtonRow is deciding between a row and a column on a guess',
    );
  });

  testWidgets('given less than it needs, the label ellipsises and the whole '
      'of it is on a tooltip', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(200, 600),
        child: const SizedBox(
          width: 140,
          child: UiButton(label: 'Open the next record', onPressed: _noop),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    // Through the `RichText` rather than the `Text`: an overflowing `UiLabel`
    // publishes its whole string as a semantics label, so the element the
    // text finder lands on is the annotation above the paragraph.
    expect(
      tester
          .renderObject<RenderParagraph>(
            find.descendant(
              of: find.byType(UiButton),
              matching: find.byType(RichText),
            ),
          )
          .didExceedMaxLines,
      isTrue,
      reason: 'the label is cut short rather than wrapped (clause 13)',
    );
    expect(
      find.byType(UiTooltip),
      findsOneWidget,
      reason:
          'nothing is lost to the reader: the whole label is one hover away '
          '(11 section 3.3, rule 4)',
    );
    expect(
      tester.getSize(find.byType(UiButton)).width,
      140,
      reason: 'the button keeps the width the parent gave it',
    );
  });

  testWidgets('a height that holds text is derived rather than declared', (
    WidgetTester tester,
  ) async {
    for (final UiSize size in UiSize.values) {
      late UiThemeData ui;
      final Map<double, double> heights = <double, double>{};
      for (final double scale in <double>[1, 2]) {
        await tester.pumpWidget(
          uiHarness(
            textScaler: TextScaler.linear(scale),
            size: const Size(900, 600),
            child: Builder(
              builder: (BuildContext context) {
                ui = context.ui;
                return UiButton(label: 'Approve', size: size, onPressed: _noop);
              },
            ),
          ),
        );
        await tester.pumpAndSettle();
        heights[scale] = _visual(tester).height;
      }
      expect(
        heights[1],
        UiButtonStyle.restingHeightOf(ui, size),
        reason: '${size.name} is the size table at scale 1.0',
      );
      expect(
        heights[2],
        greaterThan(heights[1]!),
        reason:
            '${size.name} at 200 percent text grew with the type rather than '
            'holding a constant (10 section 2 clause 14)',
      );
    }
  });

  testWidgets('every variant paints the fill and the text 10 section 4.1 '
      'names', (WidgetTester tester) async {
    for (final Brightness mode in Brightness.values) {
      final UiThemeData ui = mode == Brightness.dark
          ? UiThemeData.dark()
          : UiThemeData.light();
      const Set<WidgetState> rest = <WidgetState>{};
      final Map<UiButtonVariant, Color> fills = <UiButtonVariant, Color>{
        UiButtonVariant.primary: ui.color.ink,
        UiButtonVariant.secondary: Color.alphaBlend(
          ui.glass.flat.fill,
          ui.color.paper,
        ),
        UiButtonVariant.ghost: ui.color.ground.withValues(alpha: 0),
        UiButtonVariant.danger: ui.color.status.blocked.content,
      };
      for (final UiButtonVariant variant in UiButtonVariant.values) {
        final UiButtonStyle style = UiButtonStyle.resolve(
          ui,
          variant,
          UiSize.md,
        );
        expect(
          style.background.resolve(rest),
          fills[variant],
          reason: '${variant.name} fill in ${mode.name}',
        );
        expect(
          style.foreground.resolve(rest),
          variant == UiButtonVariant.primary ||
                  variant == UiButtonVariant.danger
              ? ui.color.paper
              : ui.color.ink,
          reason: '${variant.name} text in ${mode.name}',
        );
        expect(
          style.side.resolve(rest),
          variant == UiButtonVariant.secondary ? isNotNull : isNull,
          reason: '${variant.name} edge in ${mode.name}',
        );
      }
    }
  });

  testWidgets('primary inverts with the mode, so the disc is never invisible', (
    WidgetTester tester,
  ) async {
    final UiButtonStyle light = UiButtonStyle.resolve(
      UiThemeData.light(),
      UiButtonVariant.primary,
      UiSize.md,
    );
    final UiButtonStyle dark = UiButtonStyle.resolve(
      UiThemeData.dark(),
      UiButtonVariant.primary,
      UiSize.md,
    );
    const Set<WidgetState> rest = <WidgetState>{};
    expect(
      light.background.resolve(rest),
      isNot(dark.background.resolve(rest)),
    );
    expect(
      light.foreground.resolve(rest),
      isNot(dark.foreground.resolve(rest)),
    );
  });

  testWidgets('every disabled variant drops to the disabled tokens', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    const Set<WidgetState> off = <WidgetState>{WidgetState.disabled};
    for (final UiButtonVariant variant in UiButtonVariant.values) {
      final UiButtonStyle style = UiButtonStyle.resolve(ui, variant, UiSize.md);
      expect(style.foreground.resolve(off), ui.color.disabledContent);
      expect(
        style.background.resolve(off),
        variant == UiButtonVariant.ghost
            ? ui.color.ground.withValues(alpha: 0)
            : ui.color.disabledFill,
        reason: 'the ghost variant has no fill in any state',
      );
    }
  });

  testWidgets('sizes draw at 32, the density height and 56', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      final double control = UiDensity.of(density).controlHeight;
      final Map<UiSize, double> expected = <UiSize, double>{
        UiSize.sm: 32,
        UiSize.md: control,
        UiSize.lg: 56,
      };
      for (final UiSize size in UiSize.values) {
        await tester.pumpWidget(
          uiHarness(
            density: density,
            child: UiButton(
              label: 'Approve record',
              size: size,
              onPressed: () {},
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(
          _visual(tester).height,
          expected[size],
          reason: '${size.name} in ${density.name}',
        );
        expect(
          tester.getSize(find.byType(UiButton)).height,
          greaterThanOrEqualTo(UiDensity.hitBox),
          reason: 'the hit box holds at ${size.name} in ${density.name}',
        );
      }
    }
  });

  testWidgets('the label role moves to title at lg', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    expect(
      UiButtonStyle.resolve(ui, UiButtonVariant.primary, UiSize.lg).label,
      ui.type.title,
    );
    for (final UiSize size in <UiSize>[UiSize.sm, UiSize.md]) {
      expect(
        UiButtonStyle.resolve(ui, UiButtonVariant.primary, size).label,
        ui.type.label,
      );
    }
  });

  testWidgets('it presses, and a disabled one does not', (
    WidgetTester tester,
  ) async {
    int pressed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiButton(label: 'Approve record', onPressed: () => pressed++),
      ),
    );
    await tester.tap(find.byType(UiButton));
    await tester.pumpAndSettle();
    expect(pressed, 1);

    await tester.pumpWidget(
      uiHarness(
        child: const UiButton(
          label: 'Approve record',
          disabledReason: 'Confirm label coverage before you approve.',
        ),
      ),
    );
    await tester.tap(find.byType(UiButton));
    await tester.pumpAndSettle();
    expect(pressed, 1);
  });

  testWidgets('a disabled button hands its reason to the overlay that will '
      'show it', (WidgetTester tester) async {
    String? reported;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) => Pressable(
            semanticsLabel: 'Approve record',
            disabledReason: 'Confirm label coverage before you approve.',
            onDisabledReason: (String reason) => reported = reason,
            builder: (BuildContext context, Set<WidgetState> states) =>
                const SizedBox.square(dimension: 48),
          ),
        ),
      ),
    );
    await tester.tap(find.byType(Pressable));
    await tester.pumpAndSettle();
    expect(reported, 'Confirm label coverage before you approve.');
  });

  testWidgets('both glyph slots draw', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: UiButton(
          label: 'Start new run',
          leading: UiIcons.processing,
          trailing: UiIcons.next,
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(UiIcon), findsNWidgets(2));
  });

  testWidgets('loading keeps the width of the button it replaced', (
    WidgetTester tester,
  ) async {
    Widget button({required bool loading}) => uiHarness(
      child: UiButton(
        label: 'Retrying',
        leading: UiIcons.retry,
        loading: loading,
        onPressed: () {},
      ),
    );
    await tester.pumpWidget(button(loading: false));
    await tester.pumpAndSettle();
    final double rest = _visual(tester).width;

    await tester.pumpWidget(button(loading: true));
    await tester.pump();
    expect(_visual(tester).width, rest);
    await tester.pumpWidget(uiHarness(child: const SizedBox.shrink()));
  });

  testWidgets('loading refuses activation, so one decision is sent once', (
    WidgetTester tester,
  ) async {
    int pressed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiButton(
          label: 'Saving',
          loading: true,
          onPressed: () => pressed++,
        ),
      ),
    );
    await tester.pump();
    await tester.tap(find.byType(UiButton), warnIfMissed: false);
    await tester.pump();
    expect(pressed, 0);
    await tester.pumpWidget(uiHarness(child: const SizedBox.shrink()));
  });

  testWidgets('loading keeps the enabled paint, because busy is not '
      'forbidden', (WidgetTester tester) async {
    final UiThemeData ui = UiThemeData.light();
    const Set<WidgetState> off = <WidgetState>{WidgetState.disabled};
    final UiButtonStyle working = UiButtonStyle.resolve(
      ui,
      UiButtonVariant.primary,
      UiSize.md,
      loading: true,
    );
    expect(working.background.resolve(off), ui.color.ink);
    expect(working.foreground.resolve(off), ui.color.paper);
  });

  testWidgets('the ring keeps turning under reduced motion, because an '
      'indeterminate indicator is information', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        disableAnimations: true,
        child: const UiButton(label: 'Saving', loading: true),
      ),
    );
    await tester.pump();
    expect(
      tester.binding.transientCallbackCount,
      greaterThan(0),
      reason:
          '04 section 2.5 keeps indeterminate progress moving; 10 section 4.5 '
          'turns it into an opacity pulse rather than stopping it',
    );
    await tester.pumpWidget(uiHarness(child: const SizedBox.shrink()));
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: UiButton(
          label: 'Start new run',
          leading: UiIcons.processing,
          trailing: UiIcons.next,
          variant: UiButtonVariant.danger,
          onPressed: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    // The leading glyph sits at the reading start, which under RTL is the
    // right, so the trailing glyph is to its left.
    final double leading = tester.getCenter(find.byType(UiIcon).first).dx;
    final double trailing = tester.getCenter(find.byType(UiIcon).last).dx;
    expect(leading, greaterThan(trailing));
  });
}
