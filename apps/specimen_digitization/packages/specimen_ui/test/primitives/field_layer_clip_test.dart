import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Verification report v2, V2-1: the sky must not paint outside the layer
/// that owns it, or whatever sits above the layer (the environment band on
/// every entry screen) loses its contrast to a field it never asked for.
void main() {
  test('the field painter paints nothing outside its own bounds', () async {
    final UiThemeData tokens = UiThemeData.light();
    final ui.PictureRecorder recorder = ui.PictureRecorder();
    final Canvas canvas = Canvas(recorder);
    const Size size = Size(100, 100);
    FieldPainter(
      fields: tokens.field,
      placements: tokens.field.sky(SkyPreset.home),
    ).paint(canvas, size);
    // Rasterise a canvas twice the painter's size, so anything that spilled
    // past the bounds lands on pixels the test can read.
    final ui.Image image = await recorder.endRecording().toImage(200, 200);
    final ByteData bytes = (await image.toByteData())!;
    int alphaAt(int x, int y) => bytes.getUint8((y * 200 + x) * 4 + 3);
    expect(
      <int>[
        alphaAt(150, 50),
        alphaAt(50, 150),
        alphaAt(150, 150),
        alphaAt(101, 0),
      ],
      everyElement(0),
      reason: 'a pixel outside the 100 by 100 bounds carries paint',
    );
    expect(
      <int>[alphaAt(50, 50), alphaAt(0, 99)].any((int a) => a > 0),
      isTrue,
      reason: 'the sky did not paint inside its bounds at all',
    );
  });
}
