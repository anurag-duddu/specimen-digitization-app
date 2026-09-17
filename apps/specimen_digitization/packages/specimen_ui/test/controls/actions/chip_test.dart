// `UiChip` is three controls in one class: a static tag, a toggle and a
// removable value. The remove glyph is the interesting part, because its 48 dp
// target is larger than the 32 dp capsule it sits in.

import 'dart:ui' show SemanticsFlags, Tristate;

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// The contract rebuilds its subject many times; a shared callback keeps the
/// closure out of the const expression that would otherwise be one.
void _noop() {}

/// Clause 15 for a chip. 11 section 3.3 gives it no compact variant either:
/// one capsule carrying one label, ellipsised at the bottom of the ladder.
Future<void> _stillOneChip(WidgetTester tester, double width) async {
  expect(find.byType(UiChip), findsOneWidget, reason: 'at $width dp');
  expect(
    find.byType(UiLabel),
    findsOneWidget,
    reason: 'one label and one line of it, at $width dp',
  );
}

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('a filter chip satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiChip(
        label: 'Blocked runs',
        variant: UiChipVariant.filter,
        onPressed: () {},
      ),
      semanticsLabel: 'Blocked runs',
      hasRole: (SemanticsFlags flags) => flags.isToggled != Tristate.none,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _stillOneChip),
    );
  });

  testWidgets('a disabled filter chip satisfies the contract and states the '
      'reason', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiChip(
        label: 'Saved filters',
        variant: UiChipVariant.filter,
        disabledReason: 'Save a filter to reuse it here.',
      ),
      semanticsLabel: 'Saved filters',
      disabledWithReason: true,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _stillOneChip),
    );
  });

  testWidgets('a remove glyph satisfies the control contract on its own', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiChip(
        label: 'Coleoptera',
        variant: UiChipVariant.input,
        onRemove: _noop,
      ),
      semanticsLabel: 'Remove Coleoptera',
      hasRole: (SemanticsFlags flags) => flags.isButton,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _stillOneChip),
    );
  });

  testWidgets('a tag is static: no role, one merged node', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiChip(
          label: 'Needs human review',
          icon: UiIcons.needsReview,
          semanticsLabel: 'Queue: needs human review',
        ),
      ),
    );
    await tester.pumpAndSettle();
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel('Queue: needs human review'))
        .getSemanticsData();
    expect(data.flagsCollection.isButton, isFalse);
    expect(
      data.label,
      'Queue: needs human review',
      reason:
          'status is never colour alone: the label carries it in words '
          '(02 section 4.16)',
    );
    handle.dispose();
  });

  testWidgets('a status triple tints the fill and the content', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    const Set<WidgetState> rest = <WidgetState>{};
    final UiChipStyle plain = UiChipStyle.resolve(ui, UiChipVariant.tag);
    final UiChipStyle tinted = UiChipStyle.resolve(
      ui,
      UiChipVariant.tag,
      status: ui.color.status.cleared,
    );
    expect(plain.background.resolve(rest), ui.color.paper);
    expect(plain.foreground.resolve(rest), ui.color.ink);
    expect(tinted.background.resolve(rest), ui.color.status.cleared.fill);
    expect(tinted.foreground.resolve(rest), ui.color.status.cleared.onFill);
    expect(
      plain.side.resolve(rest).color,
      ui.color.hairline,
      reason: 'a tag is separated, not bounded (10 section 4.1)',
    );
  });

  testWidgets('a selected filter chip fills ink at the state layer opacity '
      'and takes the emphasis stroke', (WidgetTester tester) async {
    final UiThemeData ui = UiThemeData.light();
    final UiChipStyle style = UiChipStyle.resolve(ui, UiChipVariant.filter);
    const Set<WidgetState> on = <WidgetState>{WidgetState.selected};
    const Set<WidgetState> off = <WidgetState>{};
    expect(
      style.background.resolve(on),
      ui.color.stateLayer(ui.color.hoverOpacity),
    );
    expect(style.background.resolve(off), ui.color.paper);
    expect(style.side.resolve(on).width, ui.shape.stroke.emphasis);
    expect(style.side.resolve(on).color, ui.color.ink);
    expect(style.side.resolve(off).width, ui.shape.stroke.boundary);
  });

  testWidgets('a filter chip toggles and reports checked', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    int pressed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiChip(
          label: 'Oldest first',
          variant: UiChipVariant.filter,
          selected: true,
          onPressed: () => pressed++,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Oldest first'))
          .getSemanticsData()
          .flagsCollection
          .isToggled,
      Tristate.isTrue,
    );
    await tester.tap(find.byType(UiChip));
    await tester.pumpAndSettle();
    expect(pressed, 1);
    handle.dispose();
  });

  testWidgets('the remove glyph keeps a 48 dp target while the capsule stays '
      'at sm', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: UiChip(
          label: 'Coleoptera',
          variant: UiChipVariant.input,
          onRemove: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    final Size target = tester.getSize(
      find.bySemanticsLabel('Remove Coleoptera'),
    );
    expect(target.width, greaterThanOrEqualTo(UiDensity.hitBox));
    expect(target.height, greaterThanOrEqualTo(UiDensity.hitBox));
    expect(
      tester.getSize(find.byType(UiChip)).height,
      UiDensity.hitBox,
      reason: 'the row is as tall as the target it has to contain',
    );
    expect(
      tester
          .getSize(
            find
                .descendant(
                  of: find.byType(UiChip),
                  matching: find.byType(DecoratedBox),
                )
                .first,
          )
          .height,
      UiChipStyle.resolve(UiThemeData.light(), UiChipVariant.input).height,
      reason: 'the capsule itself is still drawn at sm',
    );
  });

  testWidgets('removing reports once, and the label of the remove glyph '
      'stands alone', (WidgetTester tester) async {
    int removed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiChip(
          label: 'Illinois',
          variant: UiChipVariant.input,
          onRemove: () => removed++,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Remove Illinois'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Remove Illinois'));
    await tester.pumpAndSettle();
    expect(removed, 1);
  });

  testWidgets('the remove label may be written out', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: UiChip(
          label: 'Latn',
          variant: UiChipVariant.input,
          removeSemanticsLabel: 'Remove the Latin script declaration',
          onRemove: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel('Remove the Latin script declaration'),
      findsOneWidget,
    );
  });

  testWidgets('the remove glyph sits at the reading end in both directions', (
    WidgetTester tester,
  ) async {
    Future<double> gap(TextDirection direction) async {
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: UiChip(
            label: 'Coleoptera',
            variant: UiChipVariant.input,
            onRemove: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      return tester.getCenter(find.bySemanticsLabel('Remove Coleoptera')).dx -
          tester.getCenter(find.text('Coleoptera')).dx;
    }

    expect(await gap(TextDirection.ltr), greaterThan(0));
    expect(await gap(TextDirection.rtl), lessThan(0));
  });

  testWidgets('the leading slot draws where the glyph would, in an inline '
      'box', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) => UiChip(
            label: 'Uploading',
            leading: const UiProgress.ring(
              semanticsLabel: 'Uploading',
              value: 0.4,
              size: UiProgressSize.small,
            ),
            status: context.ui.color.status.processing,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final UiChipStyle style = UiChipStyle.resolve(
      UiThemeData.light(),
      UiChipVariant.tag,
    );
    final Size slot = tester.getSize(
      find
          .ancestor(
            of: find.byType(UiProgress),
            matching: find.byType(SizedBox),
          )
          .first,
    );
    expect(
      slot,
      Size.square(style.leadingSize),
      reason:
          'the slot is the inline glyph box, so a chip with a ring and a '
          'chip with a glyph are the same shape',
    );
    expect(
      tester.getTopLeft(find.byType(UiProgress)).dx,
      lessThan(tester.getTopLeft(find.text('Uploading')).dx),
      reason: 'what stands before the label is drawn before it',
    );
  });

  testWidgets('a glyph and a leading widget at once is a defect', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        // Built through the theme, so the assertion is reached at run time
        // rather than evaluated away as a const expression by the analyzer,
        // which is the other half of the proof that it holds.
        child: Builder(
          builder: (BuildContext context) => UiChip(
            label: 'Coleoptera',
            icon: UiIcons.record,
            leading: SizedBox.square(dimension: context.ui.space.iconInline),
          ),
        ),
      ),
    );
    expect(tester.takeException(), isAssertionError);
  });

  testWidgets('given less than it needs, the label ellipsises and the whole '
      'of it is on a tooltip', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(200, 600),
        child: const SizedBox(
          width: 90,
          child: UiChip(label: 'Needs human review'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      tester
          .renderObject<RenderParagraph>(
            find.descendant(
              of: find.byType(UiChip),
              matching: find.byType(RichText),
            ),
          )
          .didExceedMaxLines,
      isTrue,
      reason: 'a label is cut short rather than wrapped (clause 13)',
    );
    expect(find.byType(UiTooltip), findsOneWidget);
  });

  testWidgets('the capsule grows with the type rather than holding 32', (
    WidgetTester tester,
  ) async {
    final Map<double, double> heights = <double, double>{};
    for (final double scale in <double>[1, 2]) {
      await tester.pumpWidget(
        uiHarness(
          textScaler: TextScaler.linear(scale),
          size: const Size(600, 600),
          child: const UiChip(label: 'Coleoptera'),
        ),
      );
      await tester.pumpAndSettle();
      heights[scale] = tester.getSize(find.byType(UiChip)).height;
    }
    expect(
      heights[1],
      UiButtonStyle.smallHeight,
      reason: 'the `sm` row of the size table at scale 1.0',
    );
    expect(
      heights[2],
      greaterThan(heights[1]!),
      reason: 'and the scaled line box above it (10 section 2 clause 14)',
    );
  });

  testWidgets('it builds at 200 percent text', (WidgetTester tester) async {
    for (final UiChipVariant variant in UiChipVariant.values) {
      await tester.pumpWidget(
        uiHarness(
          textScaler: const TextScaler.linear(2),
          size: const Size(420, 600),
          child: UiChip(
            label: 'Needs human review',
            variant: variant,
            icon: UiIcons.needsReview,
            onPressed: variant == UiChipVariant.filter ? () {} : null,
            onRemove: variant == UiChipVariant.input ? () {} : null,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: variant.name);
    }
  });
}
