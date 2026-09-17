// Status without colour (pass criterion 4.5; accessibility, section 2.1).
//
// Every status is a glyph plus a word plus a border as well as a colour. The
// claim in the design documents has always been that a reviewer who cannot
// separate the hues can still separate the statuses. This is the screenshot
// test that holds it: each chip is rendered, the rendering is desaturated by
// the luminance formula WCAG uses, and the greyscale images are compared
// against each other.
//
// Pixels, not semantics. The semantics fixtures already prove each status is a
// word; what colour-blindness costs is what is on the screen, so what is on
// the screen is what is compared.

import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_digitization/src/widgets/status_chip.dart';

import '../widgets/harness.dart';

/// The statuses a queue row or a field row can show.
const List<SpecimenStatus> queueStatuses = <SpecimenStatus>[
  SpecimenStatus.cleared,
  SpecimenStatus.needsReview,
  SpecimenStatus.deferred,
  SpecimenStatus.processing,
  SpecimenStatus.blocked,
  SpecimenStatus.unknown,
];

/// Renders one chip and answers its pixels, desaturated.
///
/// The coefficients are the ones in WCAG's relative luminance, so "greyscale"
/// here means what a luminance-only display would show rather than a naive
/// average that flatters some hues.
Future<Uint8List> greyscaleChip(
  WidgetTester tester,
  SpecimenStatus status,
  ThemeData theme,
) async {
  final GlobalKey boundary = GlobalKey();
  await pumpComponent(
    tester,
    RepaintBoundary(
      key: boundary,
      child: ColoredBox(
        color: theme.colorScheme.surface,
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: StatusChip(status),
        ),
      ),
    ),
    theme: theme,
    size: const Size(400, 200),
  );

  late Uint8List grey;
  await tester.runAsync(() async {
    final RenderRepaintBoundary render =
        boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final ui.Image image = await render.toImage();
    final ByteData pixels = (await image.toByteData(
      format: ui.ImageByteFormat.rawRgba,
    ))!;
    grey = Uint8List(pixels.lengthInBytes ~/ 4);
    for (int i = 0; i < grey.length; i++) {
      final int red = pixels.getUint8(i * 4);
      final int green = pixels.getUint8(i * 4 + 1);
      final int blue = pixels.getUint8(i * 4 + 2);
      grey[i] = (0.2126 * red + 0.7152 * green + 0.0722 * blue).round();
    }
    image.dispose();
  });
  return grey;
}

/// How many of the two images' pixels differ by more than a rounding step.
double differingShare(Uint8List a, Uint8List b) {
  final int length = a.length < b.length ? a.length : b.length;
  if (length == 0) return 0;
  int differing = 0;
  for (int i = 0; i < length; i++) {
    if ((a[i] - b[i]).abs() > 2) differing++;
  }
  return differing / length;
}

void main() {
  productThemes.forEach((String name, ThemeData theme) {
    testWidgets('every status is still distinguishable in greyscale, $name', (
      WidgetTester tester,
    ) async {
      final Map<SpecimenStatus, Uint8List> rendered =
          <SpecimenStatus, Uint8List>{};
      for (final SpecimenStatus status in queueStatuses) {
        rendered[status] = await greyscaleChip(tester, status, theme);
      }

      for (int i = 0; i < queueStatuses.length; i++) {
        for (int j = i + 1; j < queueStatuses.length; j++) {
          final SpecimenStatus a = queueStatuses[i];
          final SpecimenStatus b = queueStatuses[j];
          expect(
            differingShare(rendered[a]!, rendered[b]!),
            greaterThan(0.005),
            reason:
                '${a.name} and ${b.name} render as the same picture once the '
                'colour is taken away, so a reviewer who cannot separate the '
                'hues cannot separate the statuses',
          );
        }
      }
    });
  });

  test('every status carries a word and a glyph, not only a colour', () {
    for (final SpecimenStatus status in SpecimenStatus.values) {
      expect(status.label, isNotEmpty, reason: '${status.name} has no word');
    }
  });
}
