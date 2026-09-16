// The mark (09 section 9).
//
// Not a control, so the control contract does not apply: what the mark owes
// is a label a reviewer can act on, a size that comes from its call site and
// from nothing else, two variants that read their colours as roles, and a
// geometry that is the same 24 dp statement the rasters are rendered from.
//
// The geometry assertions sample the rendered pixels rather than the widget
// tree, because the numbers in 09 are about what is drawn. A golden proves
// the whole picture has not moved; these prove which rule it is drawn by.

import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/rendering.dart' show RenderRepaintBoundary;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// The rendered pixels of the first repaint boundary in the tree.
class _Pixels {
  const _Pixels(this._bytes, this.width, this.height);

  final ByteData _bytes;

  /// The image's width in pixels.
  final int width;

  /// The image's height in pixels.
  final int height;

  /// The colour at (`x`, `y`), opaque.
  ui.Color at(int x, int y) =>
      ui.Color(_bytes.getUint32((y * width + x) * 4, Endian.big) >> 8 |
          0xFF000000);

  /// Whether (`x`, `y`) is closer to `colour` than to anything else drawn.
  bool isNear(int x, int y, ui.Color colour) {
    final ui.Color found = at(x, y);
    return (found.r - colour.r).abs() < 0.02 &&
        (found.g - colour.g).abs() < 0.02 &&
        (found.b - colour.b).abs() < 0.02;
  }
}

/// Rasterises [child] and hands back its pixels.
///
/// The rasteriser runs outside the fake async zone, which is why the capture
/// is inside `runAsync`: `toImage` completes on a real frame, and awaited
/// under the test's own clock it never completes at all. This is the same
/// route `matchesGoldenFile` takes.
Future<_Pixels> _render(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(uiHarness(child: RepaintBoundary(child: child)));
  await tester.pumpAndSettle();
  final RenderRepaintBoundary boundary = tester.renderObject(
    find.byType(RepaintBoundary).last,
  );
  return (await tester.runAsync(() async {
    final ui.Image image = await boundary.toImage();
    final int width = image.width;
    final int height = image.height;
    final ByteData bytes = (await image.toByteData(
      format: ui.ImageByteFormat.rawRgba,
    ))!;
    image.dispose();
    return _Pixels(bytes, width, height);
  }))!;
}

/// The topmost and bottommost rows carrying the pin, along the mark's axis.
({int top, int bottom}) _pinExtent(_Pixels pixels, ui.Color pin) {
  final int axis = pixels.width ~/ 2;
  int? top;
  int bottom = 0;
  for (int y = 0; y < pixels.height; y++) {
    if (pixels.isNear(axis, y, pin)) {
      top ??= y;
      bottom = y;
    }
  }
  return (top: top!, bottom: bottom);
}

void main() {
  group('UiMark', () {
    testWidgets('says what it is, as an image', (WidgetTester tester) async {
      await tester.pumpWidget(
        uiHarness(child: const UiMark(label: 'Specimen Digitization')),
      );
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('Specimen Digitization'), findsOneWidget);
      expect(
        tester
            .getSemantics(find.byType(UiMark))
            .getSemanticsData()
            .flagsCollection
            .isImage,
        isTrue,
        reason:
            'a screen reader that is told this is an image reads the label '
            'and stops, which is the whole of what a mark has to say',
      );
    });

    testWidgets('is square, at 24 unless asked otherwise', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: const Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              UiMark(label: 'default'),
              UiMark(label: 'larger', size: 96),
              UiMark.mono(label: 'mono default'),
              UiMark.mono(label: 'mono larger', size: 40),
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getSize(find.bySemanticsLabel('default')),
        const Size(UiMark.defaultSize, UiMark.defaultSize),
      );
      expect(
        tester.getSize(find.bySemanticsLabel('larger')),
        const Size(96, 96),
      );
      expect(
        tester.getSize(find.bySemanticsLabel('mono default')),
        const Size(UiMark.defaultSize, UiMark.defaultSize),
      );
      expect(
        tester.getSize(find.bySemanticsLabel('mono larger')),
        const Size(40, 40),
      );
      expect(UiMark.defaultSize, 24, reason: '09 section 9 states it at 24');
    });

    testWidgets('200 percent text leaves it alone', (
      WidgetTester tester,
    ) async {
      for (final TextScaler scaler in <TextScaler>[
        TextScaler.noScaling,
        const TextScaler.linear(2),
      ]) {
        await tester.pumpWidget(
          uiHarness(
            textScaler: scaler,
            child: const UiMark(label: 'Specimen Digitization'),
          ),
        );
        await tester.pumpAndSettle();
        expect(
          tester.getSize(find.byType(UiMark)),
          const Size(UiMark.defaultSize, UiMark.defaultSize),
          reason:
              'the mark carries no text, so a reviewer who has doubled the '
              'type size has not asked for a bigger mark',
        );
      }
    });

    testWidgets('right to left draws the same mark', (
      WidgetTester tester,
    ) async {
      final _Pixels ltr = await _render(
        tester,
        const UiMark(label: 'Specimen Digitization', size: 96),
      );
      await tester.pumpWidget(const SizedBox.shrink());
      final _Pixels rtl = await _render(
        tester,
        const Directionality(
          textDirection: TextDirection.rtl,
          child: UiMark(label: 'Specimen Digitization', size: 96),
        ),
      );
      final ({int top, int bottom}) left = _pinExtent(
        ltr,
        UiThemeData.light().color.onAccent,
      );
      final ({int top, int bottom}) right = _pinExtent(
        rtl,
        UiThemeData.light().color.onAccent,
      );
      expect(
        right,
        left,
        reason:
            'the mark is symmetric about its axis and carries no direction, '
            'so it does not mirror',
      );
    });

    testWidgets('each variant reads its two roles', (
      WidgetTester tester,
    ) async {
      for (final UiThemeData ui in <UiThemeData>[
        UiThemeData.light(),
        UiThemeData.dark(),
      ]) {
        expect(UiMarkVariant.accent.disc(ui), ui.color.accent);
        expect(UiMarkVariant.accent.pin(ui), ui.color.onAccent);
        expect(UiMarkVariant.mono.disc(ui), ui.color.paper);
        expect(UiMarkVariant.mono.pin(ui), ui.color.ink);
      }

      final _Pixels accent = await _render(
        tester,
        const UiMark(label: 'accent', size: 96),
      );
      final UiThemeData light = UiThemeData.light();
      expect(
        accent.isNear(8, 48, light.color.accent),
        isTrue,
        reason: 'the disc fills the box, so the left edge of it is accent',
      );
      expect(
        accent.isNear(48, 48, light.color.onAccent),
        isTrue,
        reason: 'the shaft runs through the geometric centre',
      );

      await tester.pumpWidget(const SizedBox.shrink());
      final _Pixels mono = await _render(
        tester,
        const UiMark.mono(label: 'mono', size: 96),
      );
      expect(mono.isNear(8, 48, light.color.paper), isTrue);
      expect(mono.isNear(48, 48, light.color.ink), isTrue);
    });

    testWidgets('the pin is 09 section 9, scaled', (WidgetTester tester) async {
      // At 96 the unit is 4 px, so every number in 09 lands on a whole pixel
      // and the assertions can be exact rather than approximate.
      const double size = 96;
      const double unit = size / 24;
      final _Pixels pixels = await _render(
        tester,
        const UiMark(label: 'Specimen Digitization', size: size),
      );
      final ({int top, int bottom}) extent = _pinExtent(
        pixels,
        UiThemeData.light().color.onAccent,
      );

      // The pin is 16 dp tall, and it sits 1 dp above the geometric centre:
      // 9 dp of it above the centre and 7 dp below.
      expect(
        extent.bottom - extent.top + 1,
        closeTo(16 * unit, 2),
        reason: 'the pin is 16 dp tall at 24 dp overall',
      );
      expect(
        size / 2 - extent.top,
        closeTo(9 * unit, 2),
        reason: 'the head reaches 9 dp above the centre, not 8',
      );
      expect(
        extent.bottom - size / 2,
        closeTo(7 * unit, 2),
        reason: 'and the tip stops 7 dp below it, which is the 1 dp rise',
      );

      // The head is 5 dp across and the shaft 2 dp, measured on the rows that
      // carry each.
      int widthAt(int y) {
        int count = 0;
        for (int x = 0; x < pixels.width; x++) {
          if (pixels.isNear(x, y, UiThemeData.light().color.onAccent)) count++;
        }
        return count;
      }

      expect(
        widthAt((size / 2 - 6.5 * unit).round()),
        closeTo(5 * unit, 2),
        reason: 'the head is 5 dp across at its centre, 6.5 dp above the mark',
      );
      expect(
        widthAt((size / 2 + 4 * unit).round()),
        closeTo(2 * unit, 2),
        reason: 'and the shaft below it is the 2 dp stroke',
      );
    });
  });
}
