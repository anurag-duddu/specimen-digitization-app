import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/capture_quality.dart';

void main() {
  Uint8List pixels(List<int> values) =>
      Uint8List.fromList(values.expand((v) => [v, v, v, 255]).toList());
  test('measured exposure and detail respond to controlled degradation', () {
    final sharp = CaptureQuality.measure(
      pixels([0, 255, 0, 255, 0, 255, 0, 255, 0]),
      3,
      3,
    );
    final blurred = CaptureQuality.measure(pixels(List.filled(9, 128)), 3, 3);
    final dark = CaptureQuality.measure(pixels(List.filled(9, 0)), 3, 3);
    final bright = CaptureQuality.measure(pixels(List.filled(9, 255)), 3, 3);
    expect(sharp.gradient, greaterThan(blurred.gradient));
    expect(sharp.contrast, greaterThan(blurred.contrast));
    expect(blurred.gradient, 0);
    expect(dark.darkFraction, 1);
    expect(bright.brightFraction, 1);
    expect(bright.mean, closeTo(255, .0001));
    expect(dark.mean, 0);
  });
  test(
    'transparent pixels composite on the preview background and bounds are enforced',
    () {
      final transparent = CaptureQuality.measure(
        Uint8List.fromList([0, 0, 0, 0]),
        1,
        1,
      );
      expect(transparent.mean, 255);
      expect(
        () => CaptureQuality.measure(Uint8List(0), 257, 1),
        throwsArgumentError,
      );
      expect(
        () => CaptureQuality.measure(Uint8List(3), 1, 1),
        throwsArgumentError,
      );
    },
  );
  testWidgets('feedback states unmeasured limits and cannot certify an image', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CaptureQualityView(
            quality: CaptureQuality.measure(pixels([0, 255, 0, 255]), 2, 2),
          ),
        ),
      ),
    );
    expect(find.text('Measured thumbnail · uncalibrated'), findsOneWidget);
    expect(
      find.textContaining(
        'Focus, glare, framing and label coverage are not determined',
      ),
      findsOneWidget,
    );
    expect(find.textContaining('Near-black pixels 50.0%'), findsOneWidget);
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: CaptureQualityView(quality: null)),
      ),
    );
    expect(find.text('Measurements unavailable'), findsOneWidget);
    expect(find.textContaining('server must decode'), findsOneWidget);
  });
}
