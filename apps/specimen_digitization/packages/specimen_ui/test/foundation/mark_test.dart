// The supplied interlocking brand mark: semantics, responsive geometry,
// transparent negative space and the approved colour treatments. These pixel
// assertions check the anatomy rather than reproducing its vector path.

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

  /// The colour at (`x`, `y`), including transparent negative space.
  ui.Color at(int x, int y) {
    final int offset = (y * width + x) * 4;
    return ui.Color.fromARGB(
      _bytes.getUint8(offset + 3),
      _bytes.getUint8(offset),
      _bytes.getUint8(offset + 1),
      _bytes.getUint8(offset + 2),
    );
  }

  List<int> get bytes => _bytes.buffer.asUint8List();

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
Future<_Pixels> _render(
  WidgetTester tester,
  Widget child, {
  Brightness brightness = Brightness.light,
}) async {
  await tester.pumpWidget(
    uiHarness(
      brightness: brightness,
      child: RepaintBoundary(child: child),
    ),
  );
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

/// Connected regions of painted or transparent pixels. Four-way connectivity
/// keeps the distinct ribbons and the enclosed counter independently testable.
List<({int area, Rect bounds, bool touchesEdge})> _regions(
  _Pixels pixels, {
  required bool painted,
}) {
  final seen = Uint8List(pixels.width * pixels.height);
  final result = <({int area, Rect bounds, bool touchesEdge})>[];
  bool belongs(int offset) =>
      (pixels.at(offset % pixels.width, offset ~/ pixels.width).a > .5) ==
      painted;
  for (var start = 0; start < seen.length; start++) {
    if (seen[start] != 0 || !belongs(start)) continue;
    var area = 0;
    var left = pixels.width;
    var top = pixels.height;
    var right = 0;
    var bottom = 0;
    var touchesEdge = false;
    final queue = <int>[start];
    seen[start] = 1;
    while (queue.isNotEmpty) {
      final offset = queue.removeLast();
      final x = offset % pixels.width;
      final y = offset ~/ pixels.width;
      area++;
      if (x < left) left = x;
      if (y < top) top = y;
      if (x > right) right = x;
      if (y > bottom) bottom = y;
      if (x == 0 || x == pixels.width - 1 || y == 0 || y == pixels.height - 1) {
        touchesEdge = true;
      }
      for (final neighbor in <int>[
        if (x > 0) offset - 1,
        if (x + 1 < pixels.width) offset + 1,
        if (y > 0) offset - pixels.width,
        if (y + 1 < pixels.height) offset + pixels.width,
      ]) {
        if (seen[neighbor] == 0 && belongs(neighbor)) {
          seen[neighbor] = 1;
          queue.add(neighbor);
        }
      }
    }
    result.add((
      area: area,
      bounds: Rect.fromLTRB(
        left.toDouble(),
        top.toDouble(),
        (right + 1).toDouble(),
        (bottom + 1).toDouble(),
      ),
      touchesEdge: touchesEdge,
    ));
  }
  return result;
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
              UiMark.appIcon(label: 'app icon default'),
              UiMark.appIcon(label: 'app icon larger', size: 96),
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
      expect(UiMark.defaultSize, 24);
      expect(
        tester.getSize(find.bySemanticsLabel('app icon default')),
        const Size(UiMark.defaultSize, UiMark.defaultSize),
      );
      expect(
        tester.getSize(find.bySemanticsLabel('app icon larger')),
        const Size(96, 96),
      );
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
      for (final mark in const [
        UiMark(label: 'Specimen Digitization', size: 96),
        UiMark.mono(label: 'Specimen Digitization', size: 96),
        UiMark.appIcon(label: 'Specimen Digitization', size: 96),
      ]) {
        final _Pixels ltr = await _render(tester, mark);
        await tester.pumpWidget(const SizedBox.shrink());
        final _Pixels rtl = await _render(
          tester,
          Directionality(textDirection: TextDirection.rtl, child: mark),
        );
        expect(
          rtl.bytes,
          ltr.bytes,
          reason: 'The brand geometry and gradient never mirror in RTL.',
        );
      }
    });

    testWidgets('three separate pieces and one open counter scale together', (
      WidgetTester tester,
    ) async {
      for (final size in <double>[24, 40, 96]) {
        final pixels = await _render(
          tester,
          UiMark.mono(label: 'Specimen Digitization', size: size),
        );
        expect(pixels.width, size);
        expect(pixels.height, size);
        final pieces = _regions(pixels, painted: true);
        expect(
          pieces,
          hasLength(3),
          reason: 'Three distinct interlocking pieces',
        );
        expect(pieces.every((piece) => piece.area > size), isTrue);
        final counters = _regions(
          pixels,
          painted: false,
        ).where((region) => !region.touchesEdge).toList();
        expect(
          counters,
          hasLength(1),
          reason: 'The lower piece has an open counter',
        );
        expect(counters.single.bounds.center.dx, greaterThan(size / 2));
        expect(counters.single.bounds.center.dy, greaterThan(size / 2));
        expect(
          counters.single.bounds.width,
          greaterThan(counters.single.bounds.height),
        );
        for (final point in <(int, int)>[
          (0, 0),
          (pixels.width - 1, 0),
          (0, pixels.height - 1),
          (pixels.width - 1, pixels.height - 1),
        ]) {
          expect(
            pixels.at(point.$1, point.$2).a,
            0,
            reason: 'No background disc',
          );
        }
      }
    });

    testWidgets(
      'monochrome uses theme ink for every piece and repaints by mode',
      (WidgetTester tester) async {
        for (final brightness in Brightness.values) {
          final theme = brightness == Brightness.dark
              ? UiThemeData.dark()
              : UiThemeData.light();
          final pixels = await _render(
            tester,
            const UiMark.mono(label: 'Specimen Digitization', size: 96),
            brightness: brightness,
          );
          var opaquePixels = 0;
          for (var y = 0; y < pixels.height; y++) {
            for (var x = 0; x < pixels.width; x++) {
              if (pixels.at(x, y).a < .999) continue;
              opaquePixels++;
              expect(pixels.isNear(x, y, theme.color.ink), isTrue);
            }
          }
          expect(opaquePixels, greaterThan(1000));
        }
      },
    );

    testWidgets('accent keeps neutral outer pieces and the warm to Iris fold', (
      WidgetTester tester,
    ) async {
      for (final brightness in Brightness.values) {
        final theme = brightness == Brightness.dark
            ? UiThemeData.dark()
            : UiThemeData.light();
        final ink = brightness == Brightness.dark
            ? theme.brand.paper
            : theme.brand.obsidian;
        final pixels = await _render(
          tester,
          const UiMark(label: 'Specimen Digitization', size: 512),
          brightness: brightness,
        );
        // These interior samples are taken from the supplied primary mark,
        // with the shared vector's (1, 42) placement in its square canvas.
        for (final point in [(80, 190), (240, 290), (350, 120)]) {
          expect(pixels.isNear(point.$1 + 1, point.$2 + 42, ink), isTrue);
        }
        final warm = pixels.at(151 + 1, 210 + 42);
        final cool = pixels.at(149 + 1, 302 + 42);
        expect(warm.a, 1);
        expect(cool.a, 1);
        expect(warm.r, greaterThan(warm.b), reason: 'Amber at the upper fold');
        expect(cool.b, greaterThan(cool.r), reason: 'Iris at the lower fold');
        expect(warm.r, greaterThan(cool.r));
        expect(cool.b, greaterThan(warm.b));
        expect(pixels.at(335 + 1, 266 + 42).a, 0, reason: 'Open lower counter');
      }
    });

    testWidgets('all variants preserve identical cutouts and silhouettes', (
      WidgetTester tester,
    ) async {
      final accent = await _render(
        tester,
        const UiMark(label: 'Specimen Digitization', size: 96),
      );
      final mono = await _render(
        tester,
        const UiMark.mono(label: 'Specimen Digitization', size: 96),
      );
      final appIcon = await _render(
        tester,
        const UiMark.appIcon(label: 'Specimen Digitization', size: 96),
      );
      for (var y = 0; y < accent.height; y++) {
        for (var x = 0; x < accent.width; x++) {
          expect(accent.at(x, y).a, mono.at(x, y).a);
          expect(accent.at(x, y).a, appIcon.at(x, y).a);
        }
      }
    });

    testWidgets(
      'app icon retains Obsidian on Paper and its distinct Amber tip',
      (WidgetTester tester) async {
        final theme = UiThemeData.light();
        final primary = await _render(
          tester,
          const UiMark(label: 'Specimen Digitization', size: 512),
        );
        final primaryTip = primary.at(388 + 1, 116 + 42);
        for (final brightness in Brightness.values) {
          final icon = await _render(
            tester,
            const UiMark.appIcon(label: 'Specimen app icon', size: 512),
            brightness: brightness,
          );
          for (final point in [(80, 190), (240, 290)]) {
            expect(
              icon.isNear(point.$1 + 1, point.$2 + 42, theme.brand.obsidian),
              isTrue,
              reason: 'Paper-plate artwork retains Obsidian in dark mode too.',
            );
          }
          final iconTip = icon.at(388 + 1, 116 + 42);
          expect(iconTip.a, 1);
          expect(
            iconTip.r,
            greaterThan(iconTip.b),
            reason: 'The app tip is Amber.',
          );
          expect(iconTip.r, greaterThan(primaryTip.r + .3));
          expect(
            iconTip.computeLuminance(),
            greaterThan(primaryTip.computeLuminance()),
          );
          final lowerFold = icon.at(149 + 1, 302 + 42);
          expect(lowerFold.b, greaterThan(lowerFold.r));
          expect(icon.at(335 + 1, 266 + 42).a, 0);
          expect(
            tester
                .getSemantics(find.byType(UiMark))
                .getSemanticsData()
                .flagsCollection
                .isImage,
            isTrue,
          );
        }
      },
    );
  });
}
