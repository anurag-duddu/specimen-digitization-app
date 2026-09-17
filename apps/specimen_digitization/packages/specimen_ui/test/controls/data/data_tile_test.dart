// `UiDataTile` is not interactive, so the control contract does not apply. Its
// obligations are elsewhere: one sentence in the semantics tree, a tint that
// never varies with the value, a numeral whose width holds, and a tick that
// keeps its cross fade under reduced motion while losing its slide.

import 'package:flutter/rendering.dart' show RenderParagraph;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

Widget _tile({
  String value = '128',
  String? unit = 'OF 240',
  String? footer,
  Widget? child,
  bool hero = false,
  String? semanticsLabel,
}) => SizedBox(
  width: 320,
  child: UiDataTile(
    label: 'Cleared today',
    value: value,
    unit: unit,
    footer: footer,
    hero: hero,
    semanticsLabel: semanticsLabel,
    child: child,
  ),
);

void main() {
  testWidgets('a paper tile draws no frosted pane and reads the same', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 320,
          child: UiDataTile(
            label: 'In this manifest',
            value: '312',
            unit: 'FILES',
            surface: UiDataTileSurface.paper,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      glassPaneCount(),
      0,
      reason:
          'the whole point of the variant: three counts in a list header '
          'would spend the four pane glass budget on one row of chrome',
    );
    expect(find.byType(Surface), findsOneWidget);
    expect(
      find.bySemanticsLabel('In this manifest, 312 FILES'),
      findsOneWidget,
    );
  });

  testWidgets('a paper tile may sit inside a scrolling list item', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: ListView.builder(
          itemCount: 3,
          itemBuilder: (BuildContext context, int index) => UiDataTile(
            label: 'Batch $index',
            value: '$index',
            surface: UiDataTileSurface.paper,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.takeException(),
      isNull,
      reason:
          'GlassSurface asserts inside a sliver list item, and 09 section 3.3 '
          'is why; a tile that has to live there takes the solid pane',
    );
    expect(glassPaneCount(), 0);
  });

  testWidgets('the tile reads as one sentence', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: _tile()));
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel('Cleared today, 128 OF 240'),
      findsOneWidget,
      reason:
          'one node reading label, value and unit, not three fragments a '
          'screen reader user has to assemble',
    );
  });

  testWidgets('a caller that knows better writes the sentence itself', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: _tile(semanticsLabel: 'Cleared today, 128 of 240 records'),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel('Cleared today, 128 of 240 records'),
      findsOneWidget,
    );
  });

  testWidgets('a measurement nobody made is drawn as the words it is', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _tile(value: 'Not measured', unit: null)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Not measured'), findsOneWidget);
    expect(find.text('0'), findsNothing);
    expect(
      find.bySemanticsLabel('Cleared today, Not measured'),
      findsOneWidget,
    );
  });

  testWidgets('the numeral steps down a role at a time rather than wrapping', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    final List<TextStyle> steps = UiDataTileStyle.resolve(ui).numeralSteps;
    expect(
      steps.map((TextStyle role) => role.fontSize).toList(),
      <double?>[ui.type.displayLarge.fontSize, ui.type.displayMedium.fontSize],
      reason: '11 section 3.3: down to display.medium and no further',
    );

    // Wide enough for `display.large`, then narrow enough that it is not.
    final List<double> drawn = <double>[];
    for (final double width in <double>[600, 240]) {
      await tester.pumpWidget(
        uiHarness(
          size: Size(width, 600),
          child: SizedBox(
            width: width,
            child: const UiDataTile(
              label: 'Cleared today',
              value: 'Not measured',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final RenderParagraph numeral = tester.renderObject<RenderParagraph>(
        find.text('Not measured'),
      );
      expect(
        numeral.text.style!.fontSize,
        isNotNull,
        reason: 'the numeral is set in a display role at every width',
      );
      drawn.add(numeral.text.style!.fontSize!);
      expect(
        numeral.maxLines,
        1,
        reason:
            'a numeral never wraps: the tile steps the role down and then '
            'scales, which is what replaced the two line reading of '
            '02 section 4.14',
      );
    }
    expect(
      drawn.last,
      lessThan(drawn.first),
      reason: 'the narrow tile is set a role smaller than the wide one',
    );
  });

  testWidgets('the last resort scales the numeral and its unit together', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(120, 600),
        child: const SizedBox(
          width: 120,
          child: UiDataTile(
            label: 'Cleared today',
            value: 'Not measured',
            unit: 'OF 240',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.byType(FittedBox),
      findsOneWidget,
      reason: 'below display.medium the measurement is scaled, not resized',
    );
    expect(
      find.descendant(
        of: find.byType(FittedBox),
        matching: find.text('OF 240'),
      ),
      findsOneWidget,
      reason:
          'the unit is inside the box, because a scaled box reports its '
          'unscaled baseline and a unit aligned to that would float',
    );
    expect(
      UiDataTileStyle.resolve(UiThemeData.light()).unit.fontSize,
      UiThemeData.light().type.unit.fontSize,
      reason: 'the unit role itself never steps down',
    );
  });

  testWidgets('a hero tile starts one role higher and ends in the same place', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    expect(
      UiDataTileStyle.resolve(
        ui,
        hero: true,
      ).numeralSteps.map((TextStyle role) => role.fontSize).toList(),
      <double?>[
        ui.type.displayHero.fontSize,
        ui.type.displayLarge.fontSize,
        ui.type.displayMedium.fontSize,
      ],
    );
  });

  testWidgets('the tint is the same whatever the value says', (
    WidgetTester tester,
  ) async {
    final List<BackdropFilter> panes = <BackdropFilter>[];
    for (final String value in <String>['3', '128', 'Not measured']) {
      await tester.pumpWidget(uiHarness(child: _tile(value: value)));
      await tester.pumpAndSettle();
      panes.add(tester.widget<BackdropFilter>(find.byType(BackdropFilter)));
    }
    expect(
      panes.map((BackdropFilter pane) => pane.filter.toString()).toSet(),
      hasLength(1),
      reason:
          'a record count tile is not redder when the count is higher '
          '(09 section 3.2)',
    );
    final UiThemeData ui = UiThemeData.light();
    expect(UiDataTileStyle.resolve(ui).radius, ui.shape.tile);
    expect(
      UiDataTileStyle.resolve(ui).padding,
      EdgeInsetsDirectional.all(ui.density.tilePadding),
    );
  });

  testWidgets('the tile is one pane, and only one', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _tile()));
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 1);
    expect(modalGlassPaneCount(), 0);
  });

  testWidgets('hero takes the display hero role and nothing else does', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    expect(
      UiDataTileStyle.resolve(ui).numeral.fontSize,
      ui.type.displayLarge.fontSize,
    );
    expect(
      UiDataTileStyle.resolve(ui, hero: true).numeral.fontSize,
      ui.type.displayHero.fontSize,
    );
    expect(
      UiDataTileStyle.resolve(ui).label.color,
      ui.color.inkSecondary,
      reason: 'the label sits behind the numeral, not beside it in weight',
    );
    expect(UiDataTileStyle.resolve(ui).unit.color, ui.color.inkTertiary);
  });

  testWidgets('the numeral is tabular, so a changed digit moves nothing', (
    WidgetTester tester,
  ) async {
    expect(
      UiDataTileStyle.resolve(UiThemeData.light()).numeral.fontFeatures,
      contains(const FontFeature.tabularFigures()),
    );
    Future<double> widthOf(String value) async {
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 320,
            child: UiDataTile(
              key: ValueKey<String>(value),
              label: 'Cleared today',
              value: value,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      return tester.getSize(find.text(value)).width;
    }

    expect(await widthOf('111'), closeTo(await widthOf('888'), 0.01));
  });

  testWidgets('the unit sits on the numeral baseline', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _tile()));
    await tester.pumpAndSettle();
    final Rect numeral = tester.getRect(find.text('128'));
    final Rect unit = tester.getRect(find.text('OF 240'));
    expect(
      unit.bottom,
      lessThanOrEqualTo(numeral.bottom),
      reason: 'the unit is small and quiet beside the numeral, not below it',
    );
    expect(unit.left, greaterThan(numeral.right - 1));
  });

  testWidgets('the numeral ticks, and cross fades only under reduced motion', (
    WidgetTester tester,
  ) async {
    for (final bool reduced in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: _tile(value: '128'),
        ),
      );
      await tester.pumpAndSettle();
      // Where a numeral sits when nothing is happening to it, measured
      // before the tick starts so that the moving values are read against a
      // line that is not itself moving.
      final double rest = tester.getTopLeft(find.text('128')).dy;

      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: _tile(value: '129'),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 40));
      expect(
        find.text('128'),
        findsOneWidget,
        reason: 'the old value is still fading out mid tick',
      );
      expect(find.text('129'), findsOneWidget);
      final double arriving = tester.getTopLeft(find.text('129')).dy;
      final double leaving = tester.getTopLeft(find.text('128')).dy;
      if (reduced) {
        expect(
          arriving,
          rest,
          reason: 'under reduced motion the numeral cross fades in place',
        );
        expect(leaving, rest);
      } else {
        expect(
          arriving,
          greaterThan(rest),
          reason: 'the arriving value rises the last of 6 dp into its slot',
        );
        expect(
          arriving - rest,
          lessThanOrEqualTo(MotionTokens.numeralTickRise),
        );
        expect(
          leaving,
          lessThan(rest),
          reason: 'the value it replaces rises out of the slot the same way',
        );
      }
      await tester.pumpAndSettle();
      expect(find.text('128'), findsNothing);
      expect(tester.getTopLeft(find.text('129')).dy, rest);
    }
  });

  testWidgets('the footer and the child slot sit under the numeral', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: _tile(
          footer: 'Up from 96 yesterday',
          child: const UiArcIndicator(
            value: 0.53,
            semanticsLabel: 'Share of the collection',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final double numeral = tester.getBottomLeft(find.text('128')).dy;
    final double footer = tester
        .getTopLeft(find.text('Up from 96 yesterday'))
        .dy;
    final double slot = tester.getTopLeft(find.byType(UiArcIndicator)).dy;
    expect(numeral, lessThanOrEqualTo(footer));
    expect(footer, lessThan(slot));
    expect(
      find.bySemanticsLabel('Share of the collection'),
      findsNothing,
      reason: 'the tile publishes one node, and the child is inside it',
    );
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: _tile(footer: 'Up from 96 yesterday'),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('a tile at rest holds no ticker', (WidgetTester tester) async {
    for (final bool reduced in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(disableAnimations: reduced, child: _tile()),
      );
      await tester.pumpAndSettle();
      expect(tester.binding.transientCallbackCount, 0);
    }
  });
}
