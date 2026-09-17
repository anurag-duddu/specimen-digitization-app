// `UiSkeleton` is not interactive, so the control contract does not apply to
// it: no role, nothing to focus, no hit box. What it owes instead is a shape
// that matches the content it stands for, a pulse that stops under reduced
// motion, and silence in the semantics tree.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('a block lifts the surface it sits on, in both modes', (
    WidgetTester tester,
  ) async {
    for (final Brightness mode in Brightness.values) {
      final UiThemeData ui = mode == Brightness.dark
          ? UiThemeData.dark()
          : UiThemeData.light();
      final UiSkeletonStyle style = UiSkeletonStyle.resolve(ui);
      expect(
        style.block,
        ui.color.stateLayer(UiSkeletonStyle.restOpacityOf(ui)),
        reason:
            'a placeholder drawn in paper on a paper list body cannot be '
            'seen at all; the state layer moves the surface toward its '
            'opposite in both modes',
      );
      expect(
        UiSkeletonStyle.pulseFloorFraction,
        lessThan(1),
        reason: 'the pulse dims the block rather than brightening it',
      );
      expect(
        UiSkeletonStyle.restOpacityOf(ui),
        ui.color.hoverOpacity,
        reason: 'one number for ink over a surface, written in one place',
      );
    }
  });

  testWidgets('placeholders are outside the semantics tree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: const SizedBox.shrink()));
    await tester.pump();
    final int empty = _semanticsNodes(tester);

    await tester.pumpWidget(
      uiHarness(
        child: const Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            UiSkeleton.row(),
            UiSkeleton.row(),
            UiSkeleton.line(widthFactor: 0.5),
          ],
        ),
      ),
    );
    await tester.pump();
    expect(
      _semanticsNodes(tester),
      empty,
      reason:
          'a screen of hidden boxes says nothing; the one live "Loading" node '
          'beside them is what a screen reader hears (06 section 3.1)',
    );
    handle.dispose();
  });

  testWidgets('the pulse runs, and stops dead under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const UiSkeleton.line(widthFactor: 0.5)),
    );
    await tester.pump();
    expect(
      tester.binding.transientCallbackCount,
      greaterThan(0),
      reason: 'a placeholder pulses while it waits',
    );

    await tester.pumpWidget(
      uiHarness(
        disableAnimations: true,
        child: const UiSkeleton.line(widthFactor: 0.5),
      ),
    );
    await tester.pump();
    expect(
      tester.binding.transientCallbackCount,
      0,
      reason:
          'a repeating animation is the one thing Flutter does not shorten '
          'for you, so reduced motion has to stop it by hand (04 section 2.5)',
    );
    // Nothing is left mid pulse: the block sits at its resting alpha.
    final UiThemeData ui = UiThemeData.light();
    expect(
      _blockColour(tester),
      ui.color.stateLayer(UiSkeletonStyle.restOpacityOf(ui)),
    );
  });

  testWidgets('there is no shimmer to sweep', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: const UiSkeleton.row()));
    await tester.pump();
    final Iterable<ShaderMask> masks = tester.widgetList<ShaderMask>(
      find.byType(ShaderMask),
    );
    expect(
      masks,
      isEmpty,
      reason: 'a sweep is a gradient, and only FieldLayer paints one',
    );
  });

  testWidgets('a row placeholder is the height of the row it stands for', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(density: density, child: const UiSkeleton.row()),
      );
      await tester.pump();
      final UiThemeData ui = UiThemeData.light(density: UiDensity.of(density));
      expect(
        tester.getSize(find.byType(UiSkeleton)).height,
        UiListRowStyle.heightOf(ui),
        reason: 'the list does not move when the rows arrive',
      );
    }
  });

  testWidgets('a tile placeholder is the height of the tile it stands for', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const SizedBox(width: 240, child: UiSkeleton.tile())),
    );
    await tester.pump();
    expect(
      tester.getSize(find.byType(UiSkeleton)).height,
      UiDataTileStyle.labelAndNumeralHeight(UiThemeData.light()),
    );
  });

  testWidgets('a line takes the fraction of the width it was given', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 400,
          child: UiSkeleton.line(widthFactor: 0.25),
        ),
      ),
    );
    await tester.pump();
    expect(
      _blockSize(tester).width,
      100,
      reason: 'the block is a quarter of the width; the slot keeps the rest',
    );
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: const SizedBox(width: 400, child: UiSkeleton.row()),
      ),
    );
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}

/// How many nodes the semantics tree holds right now.
int _semanticsNodes(WidgetTester tester) =>
    find.semantics.byPredicate((SemanticsNode node) => true).evaluate().length;

/// The first block a placeholder paints.
Finder _block = find.descendant(
  of: find.byType(UiSkeleton),
  matching: find.byType(DecoratedBox),
);

/// The size of that block, which is what a reviewer sees; the placeholder's
/// own slot is as wide as the content it is holding open.
Size _blockSize(WidgetTester tester) => tester.getSize(_block.first);

/// The colour that block is painted.
Color _blockColour(WidgetTester tester) =>
    (tester.widgetList<DecoratedBox>(_block).first.decoration
            as ShapeDecoration)
        .color!;
