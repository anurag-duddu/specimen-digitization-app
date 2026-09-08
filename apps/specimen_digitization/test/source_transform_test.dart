import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/source_pixels.dart';

void main() {
  final bytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();
  const width = 1000.0, height = 520.0;
  const transforms = [
    [1, 0, 0, 0, 1, 0],
    [-1, 0, 1000, 0, 1, 0],
    [-1, 0, 1000, 0, -1, 520],
    [1, 0, 0, 0, -1, 520],
    [0, 1, 0, 1, 0, 0],
    [0, -1, 520, 1, 0, 0],
    [0, -1, 520, -1, 0, 1000],
    [0, 1, 0, -1, 0, 1000],
  ];
  testWidgets(
    'all eight EXIF affine derivatives return their pixel corners to original coordinates',
    (tester) async {
      for (var orientation = 1; orientation <= 8; orientation++) {
        final m = transforms[orientation - 1];
        final vw = orientation >= 5 ? height : width;
        final vh = orientation >= 5 ? width : height;
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Center(
                child: SizedBox(
                  width: 500,
                  height: 260,
                  child: SourcePixels(
                    asset: {
                      'preview_bytes': bytes,
                      'preview_is_derivative': true,
                      'view_derivative': {
                        'transform': {
                          'matrix': m,
                          'original_width': width,
                          'original_height': height,
                          'view_width': vw,
                          'view_height': vh,
                        },
                      },
                    },
                    semanticLabel: 'geometry',
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        final root = tester.renderObject<RenderBox>(find.byType(SourcePixels));
        final image = tester.renderObject<RenderBox>(find.byType(Image));
        final origin = root.localToGlobal(Offset.zero);
        for (final p in [
          Offset.zero,
          const Offset(width, 0),
          const Offset(0, height),
          const Offset(width, height),
          const Offset(100, 52),
        ]) {
          final view = Offset(
            (m[0] * p.dx + m[1] * p.dy + m[2]) * .5,
            (m[3] * p.dx + m[4] * p.dy + m[5]) * .5,
          );
          final original = image.localToGlobal(view) - origin;
          expect(
            original.dx,
            closeTo(p.dx * .5, .001),
            reason: 'EXIF $orientation x',
          );
          expect(
            original.dy,
            closeTo(p.dy * .5, .001),
            reason: 'EXIF $orientation y',
          );
        }
        expect(tester.takeException(), isNull);
      }
    },
  );
}
