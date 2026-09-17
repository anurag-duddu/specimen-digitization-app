// `Surface`, `GlassSurface`, `Scrim`, `FieldLayer`, `FocusRing` and
// `Squircle`: the primitives that paint rather than the one that reacts.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../harness/control_contract.dart';

void main() {
  group('Surface', () {
    testWidgets('paints the role it was asked for', (
      WidgetTester tester,
    ) async {
      for (final (SurfaceRole role, Color Function(UiColor) expected)
          in <(SurfaceRole, Color Function(UiColor))>[
            (SurfaceRole.ground, (UiColor c) => c.ground),
            (SurfaceRole.paper, (UiColor c) => c.paper),
            (SurfaceRole.matte, (UiColor c) => c.matte),
          ]) {
        await tester.pumpWidget(
          uiHarness(
            child: Surface(
              role: role,
              child: const SizedBox(width: 100, height: 100),
            ),
          ),
        );
        final ShapeDecoration decoration =
            tester
                    .widget<DecoratedBox>(
                      find.descendant(
                        of: find.byType(Surface),
                        matching: find.byType(DecoratedBox),
                      ),
                    )
                    .decoration
                as ShapeDecoration;
        expect(decoration.color, expected(UiColor.light));
      }
    });

    testWidgets('a boundary edge is findable and a hairline is not', (
      WidgetTester tester,
    ) async {
      for (final (bool boundary, Color expected) in <(bool, Color)>[
        (true, UiColor.light.boundary),
        (false, UiColor.light.hairline),
      ]) {
        await tester.pumpWidget(
          uiHarness(
            child: Surface(
              boundary: boundary,
              hairline: !boundary,
              child: const SizedBox(width: 100, height: 100),
            ),
          ),
        );
        final ShapeDecoration decoration =
            tester
                    .widget<DecoratedBox>(
                      find.descendant(
                        of: find.byType(Surface),
                        matching: find.byType(DecoratedBox),
                      ),
                    )
                    .decoration
                as ShapeDecoration;
        expect((decoration.shape as OutlinedBorder).side.color, expected);
      }
    });

    testWidgets('a surface is never a blurred pane', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: const Surface(child: SizedBox(width: 100, height: 100)),
        ),
      );
      expect(glassPaneCount(), 0);
    });
  });

  group('GlassSurface', () {
    testWidgets('blurs at the level it was given', (
      WidgetTester tester,
    ) async {
      for (final GlassLevel level in GlassLevel.values) {
        await tester.pumpWidget(
          uiHarness(
            child: GlassSurface(
              level: level,
              child: const SizedBox(width: 200, height: 100),
            ),
          ),
        );
        expect(glassPaneCount(), 1, reason: level.name);
        final BackdropFilter filter = tester.widget<BackdropFilter>(
          find.byType(BackdropFilter),
        );
        expect(
          filter.filter.toString(),
          contains(UiGlass.light[level].sigma.toStringAsFixed(1)),
          reason: '${level.name} should blur at its own sigma',
        );
      }
    });

    testWidgets('the quality setting is what decides the blur', (
      WidgetTester tester,
    ) async {
      final UiGlassStyle flat = UiGlass.light.flat;
      expect(flat.sigmaFor(GlassQuality.full), flat.sigma);
      expect(flat.sigmaFor(GlassQuality.reduced), flat.sigma / 2);
      expect(flat.sigmaFor(GlassQuality.off), 0);
      expect(flat.fillFor(GlassQuality.off), flat.opaqueFallback);

      await tester.pumpWidget(
        uiHarness(
          child: Builder(
            builder: (BuildContext context) => UiTheme(
              data: UiThemeData.light(quality: GlassQuality.off),
              child: const GlassSurface(
                child: SizedBox(width: 200, height: 100),
              ),
            ),
          ),
        ),
      );
      expect(
        glassPaneCount(),
        0,
        reason:
            'with the blur off the pane is a paper fill, so there is no save '
            'layer left to pay for',
      );
    });

    testWidgets('a pane inside a list item fails in debug', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            height: 300,
            width: 300,
            child: ListView.builder(
              itemCount: 3,
              itemBuilder: (BuildContext context, int index) =>
                  const GlassSurface(child: SizedBox(height: 80)),
            ),
          ),
        ),
      );
      expect(
        tester.takeException(),
        isAssertionError,
        reason:
            '09 section 3.3 forbids glass on repeated items: the list '
            'container may be glass, its rows are paper or transparent',
      );
    });

    testWidgets('the escape hatch lets one pane scroll as one object', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            height: 300,
            width: 300,
            child: ListView.builder(
              itemCount: 1,
              itemBuilder: (BuildContext context, int index) =>
                  const GlassSurface(
                    allowInList: true,
                    child: SizedBox(height: 80),
                  ),
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
    });
  });

  group('FieldLayer', () {
    testWidgets('paints one preset and nothing else', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(child: const FieldLayer(preset: SkyPreset.home)),
      );
      expect(find.byType(CustomPaint), findsWidgets);
      expect(
        UiFields.light.sky(SkyPreset.home).length,
        3,
        reason: 'sky.home is sun, violet and rose',
      );
      expect(UiFields.light.sky(SkyPreset.work).length, 1);
      expect(UiFields.light.sky(SkyPreset.none), isEmpty);
    });

    testWidgets('a sheet gets no field of its own', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(child: const FieldLayer(preset: SkyPreset.none)),
      );
      // sky.none is a plain ground: a sheet blurs what is beneath it instead.
      expect(find.byType(CustomPaint), findsNothing);
    });

    test('the alpha falls off on a curve, never linearly', () {
      // A two-stop linear gradient leaves a visible ring where the falloff
      // changes rate, which is what gives a field a visible edge.
      expect(FieldPainter.stopCount, greaterThan(2));
    });

    test('a field over the ground is the extreme the contrast gate uses', () {
      final Color centre = UiFields.light.sun.extremeOver(UiColor.light.ground);
      expect(centre, isNot(UiColor.light.ground));
      expect(centre.a, 1.0, reason: 'the composite is opaque');
    });
  });

  group('Scrim', () {
    testWidgets('an inert scrim takes no pointer', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: const Scrim()));
      expect(find.byType(IgnorePointer), findsWidgets);
    });

    testWidgets('a dismissible scrim announces what a tap does', (
      WidgetTester tester,
    ) async {
      int dismissed = 0;
      await tester.pumpWidget(
        uiHarness(
          child: Scrim(
            onDismiss: () => dismissed++,
            dismissLabel: 'Close the sheet',
          ),
        ),
      );
      await tester.tap(find.byType(Scrim));
      await tester.pumpAndSettle();
      expect(dismissed, 1);
      expect(find.bySemanticsLabel('Close the sheet'), findsOneWidget);
    });
  });

  group('Squircle', () {
    test('a radius at least half the height is a capsule', () {
      expect(Squircle.isCapsule(24, 48), isTrue);
      expect(Squircle.isCapsule(20, 48), isFalse);
      expect(Squircle.border(24, height: 48), isA<StadiumBorder>());
      expect(Squircle.border(20, height: 48), isA<RoundedSuperellipseBorder>());
    });

    test('a zero radius is still a superellipse border, not a rectangle', () {
      final OutlinedBorder border = Squircle.border(0);
      expect(border, isA<RoundedSuperellipseBorder>());
    });

    testWidgets('clip uses the superellipse clipper', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: Squircle.clip(
            radius: 20,
            child: const SizedBox(width: 100, height: 100),
          ),
        ),
      );
      expect(find.byType(ClipRSuperellipse), findsOneWidget);
    });
  });

  group('FocusRing', () {
    testWidgets('paints only when it is told to', (WidgetTester tester) async {
      for (final bool visible in <bool>[true, false]) {
        await tester.pumpWidget(
          uiHarness(
            child: FocusRing(
              visible: visible,
              child: const SizedBox(width: 100, height: 40),
            ),
          ),
        );
        final CustomPaint paint = tester.widget<CustomPaint>(
          find.descendant(
            of: find.byType(FocusRing),
            matching: find.byType(CustomPaint),
          ),
        );
        expect(paint.foregroundPainter != null, visible);
      }
    });

    testWidgets('a superellipse is ringed by a superellipse', (
      WidgetTester tester,
    ) async {
      const Size box = Size(160, 48);
      await tester.pumpWidget(
        uiHarness(
          child: Builder(
            builder: (BuildContext context) => FocusRing(
              visible: true,
              radius: context.ui.shape.field,
              child: const SizedBox(width: 160, height: 48),
            ),
          ),
        ),
      );
      final UiThemeData ui = tester.element(find.byType(FocusRing)).ui;
      final UiStroke stroke = ui.shape.stroke;
      expect(
        find.byType(FocusRing),
        paints
          ..rsuperellipse(
            rsuperellipse: RSuperellipse.fromRectAndRadius(
              (Offset.zero & box).inflate(stroke.focusGap + stroke.focus / 2),
              Radius.circular(ui.shape.field + stroke.focusRadiusOffset),
            ),
            color: ui.color.focusRing,
            strokeWidth: stroke.focus,
          ),
        reason:
            'a circular rounded rectangle around a superellipse meets the '
            'edge along a corner and parts from it at the ends, which reads '
            'as a second outline (11 section 0)',
      );
    });

    testWidgets('a capsule is ringed by a stadium', (
      WidgetTester tester,
    ) async {
      const Size box = Size(160, 48);
      await tester.pumpWidget(
        uiHarness(
          child: const FocusRing(
            visible: true,
            shape: FocusRingShape.stadium,
            child: SizedBox(width: 160, height: 48),
          ),
        ),
      );
      final UiThemeData ui = tester.element(find.byType(FocusRing)).ui;
      final UiStroke stroke = ui.shape.stroke;
      final Rect bounds = (Offset.zero & box).inflate(
        stroke.focusGap + stroke.focus / 2,
      );
      expect(
        find.byType(FocusRing),
        paints
          ..rrect(
            rrect: RRect.fromRectAndRadius(
              bounds,
              Radius.circular(bounds.shortestSide / 2),
            ),
            color: ui.color.focusRing,
            strokeWidth: stroke.focus,
          ),
        reason: 'what StadiumBorder draws is what rings a capsule',
      );
    });

    testWidgets('a disc is ringed by a circle', (WidgetTester tester) async {
      const Size box = Size.square(20);
      await tester.pumpWidget(
        uiHarness(
          child: const FocusRing(
            visible: true,
            shape: FocusRingShape.circle,
            child: SizedBox(width: 20, height: 20),
          ),
        ),
      );
      final UiThemeData ui = tester.element(find.byType(FocusRing)).ui;
      final UiStroke stroke = ui.shape.stroke;
      final double radius =
          box.shortestSide / 2 + stroke.focusGap + stroke.focus / 2;
      expect(
        find.byType(FocusRing),
        paints
          ..circle(
            x: box.width / 2,
            y: box.height / 2,
            radius: radius,
            color: ui.color.focusRing,
            strokeWidth: stroke.focus,
          ),
      );
    });

    test('the ring geometry is the one 09 section 3.6 specifies', () {
      final UiStroke stroke = UiShape.standard.stroke;
      expect(stroke.focus, 2);
      expect(stroke.focusGap, 2);
      expect(stroke.focusRadiusOffset, 4);
      expect(
        UiColor.light.focusRing,
        UiColor.light.ink,
        reason: 'the v1 blue is retired; a monochrome ring reads as ours',
      );
    });
  });
}
