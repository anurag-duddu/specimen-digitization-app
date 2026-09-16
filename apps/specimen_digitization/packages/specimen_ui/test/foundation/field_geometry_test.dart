// The light field geometry (09 section 3.2), measured rather than eyeballed.
//
// The presets were first written with the radius bound to the window's
// shorter side and a quadratic falloff. Rendered at real windows that reads
// as three spots on a ground: on a 390 by 844 phone the sun field's half
// intensity point sat 7 percent of the way down the window. These assertions
// pin the shape that replaced it, so the next change to it is deliberate.

import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The fraction of its radius at which a field carries [share] of its centre
/// alpha.
double _radiusAt(double share) {
  double low = 0;
  double high = 1;
  for (int i = 0; i < 60; i++) {
    final double mid = (low + high) / 2;
    if (FieldPainter.profile(mid) > share) {
      low = mid;
    } else {
      high = mid;
    }
  }
  return (low + high) / 2;
}

void main() {
  test('the profile is one at the centre and zero at the radius', () {
    expect(FieldPainter.profile(0), 1);
    expect(FieldPainter.profile(1), closeTo(0, 1e-12));
  });

  test('the profile never rises', () {
    double previous = FieldPainter.profile(0);
    for (int i = 1; i <= 200; i++) {
      final double value = FieldPainter.profile(i / 200);
      expect(value, lessThanOrEqualTo(previous));
      previous = value;
    }
  });

  test('it holds near the centre and thins out over a long tail', () {
    // Held: still nine tenths of the centre a fifth of the way out.
    expect(FieldPainter.profile(0.2), greaterThan(0.8));
    // Thinned: under a tenth by two thirds of the way out, and still not zero,
    // which is what leaves the field without a visible edge.
    expect(FieldPainter.profile(0.8), lessThan(0.1));
    expect(FieldPainter.profile(0.95), greaterThan(0));
  });

  test('half the centre alpha is past a third of the radius', () {
    // The number the window reads as the field's size. The quadratic falloff
    // this replaced put it at 0.293, which is what made the field a spot.
    expect(_radiusAt(0.5), greaterThan(0.33));
    expect(_radiusAt(0.5), closeTo(0.411, 0.01));
  });

  test('the stop count keeps the drawn gradient under half a level', () {
    // The engine interpolates linearly between stops. The worst distance
    // between that line and the curve, times the widest channel span in the
    // preset table, is the banding a reviewer could see.
    const int span = 0xF4 - 0x66; // sun, blue channel, over ground
    double worst = 0;
    for (int i = 0; i < FieldPainter.stopCount - 1; i++) {
      final double a = i / (FieldPainter.stopCount - 1);
      final double b = (i + 1) / (FieldPainter.stopCount - 1);
      for (int j = 1; j < 100; j++) {
        final double t = a + (b - a) * j / 100;
        final double line =
            FieldPainter.profile(a) +
            (FieldPainter.profile(b) - FieldPainter.profile(a)) *
                (t - a) /
                (b - a);
        worst = math.max(worst, (FieldPainter.profile(t) - line).abs());
      }
    }
    expect(worst * UiFields.light.sun.centreAlpha * span, lessThan(0.5));
  });

  test('every placement stays inside the 45 to 70 percent band', () {
    for (final SkyPreset preset in SkyPreset.values) {
      for (final UiFieldPlacement placement in UiFields.light.sky(preset)) {
        expect(placement.radius, greaterThanOrEqualTo(0.45));
        expect(placement.radius, lessThanOrEqualTo(0.70));
      }
    }
  });

  test('dark holds its share of every light alpha', () {
    // 09 section 3.2: dark is not an inversion. The alphas drop by more than
    // half so the fields read as light in a dark room. The tuning changed the
    // geometry and left every alpha where it was, and this is what says so.
    for (final UiFieldName name in UiFieldName.values) {
      final double light = UiFields.light[name].centreAlpha;
      final double dark = UiFields.dark[name].centreAlpha;
      expect(
        dark,
        lessThan(light / 2),
        reason: 'field.${name.name} is not darker by more than half',
      );
    }
  });
}
