// The composite contrast gate (09 section 3.7; 10 section 8,
// `contrast_composite`).
//
// The v1 test checked a token against a flat surface. Glass over a field is
// neither, so this composites: every glass level over the lightest and darkest
// point of every field, in both modes, and holds every text role to 4.5:1 and
// every findable edge to 3:1 on the result.
//
// `Color.alphaBlend` is what the engine does for a flat fill. Blur only
// averages neighbouring pixels and cannot push a composite outside the range
// of the two extremes tested, so the extremes are sufficient.
//
// The relative luminance and contrast formulas are written out from the WCAG
// 2.2 definitions rather than taken from a helper, so this is an independent
// check on the numbers in 09 rather than a restatement of them.
// https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html

import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// WCAG 2.2 relative luminance of one sRGB channel.
double _channel(double c) =>
    c <= 0.04045 ? c / 12.92 : math.pow((c + 0.055) / 1.055, 2.4).toDouble();

/// WCAG 2.2 relative luminance. Both colours must be opaque.
double luminance(Color c) =>
    0.2126 * _channel(c.r) + 0.7152 * _channel(c.g) + 0.0722 * _channel(c.b);

/// WCAG 2.2 contrast ratio, from 1 to 21.
double contrast(Color a, Color b) {
  final double la = luminance(a);
  final double lb = luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// Text, and any glyph that carries meaning.
const double textMinimum = 4.5;

/// A boundary the reviewer has to be able to find.
const double nonTextMinimum = 3.0;

/// Every opaque background a role can land on, for one mode.
///
/// The three solid surfaces, then every glass level composited over the two
/// extremes of every field: the field's centre over `ground`, and `ground`
/// itself where the field has fallen to nothing.
Map<String, Color> surfacesFor(UiThemeData ui) {
  final Map<String, Color> extremes = <String, Color>{
    'plain': ui.color.ground,
  };
  ui.field.all.forEach((String name, UiFieldStyle field) {
    extremes['field.$name'] = field.extremeOver(ui.color.ground);
  });

  final Map<String, Color> surfaces = <String, Color>{...ui.color.surfaces};
  ui.glass.all.forEach((String level, UiGlassStyle glass) {
    extremes.forEach((String where, Color background) {
      surfaces['glass.$level over $where'] = Color.alphaBlend(
        glass.fill,
        background,
      );
    });
  });
  return surfaces;
}

void main() {
  group('the WCAG formula itself', () {
    test('reproduces the two ratios everyone knows', () {
      expect(
        contrast(const Color(0xFF000000), const Color(0xFFFFFFFF)),
        closeTo(21.0, 0.001),
      );
      expect(
        contrast(const Color(0xFFFFFFFF), const Color(0xFFFFFFFF)),
        closeTo(1.0, 0.001),
      );
    });
  });

  for (final (String mode, UiThemeData ui) in <(String, UiThemeData)>[
    ('light', UiThemeData.light()),
    ('dark', UiThemeData.dark()),
  ]) {
    final Map<String, Color> surfaces = surfacesFor(ui);

    group('$mode mode', () {
      test('the composite set covers every field at every glass level', () {
        // Three solid surfaces, plus three levels times six extremes.
        expect(surfaces.length, 3 + 3 * 6);
      });

      test('every text role clears 4.5:1 on every surface', () {
        ui.color.textRoles.forEach((String role, Color colour) {
          surfaces.forEach((String where, Color background) {
            expect(
              contrast(colour, background),
              greaterThanOrEqualTo(textMinimum),
              reason: '$mode $role on $where',
            );
          });
        });
      });

      test('a disabled control stays readable on every surface', () {
        // WCAG exempts an inactive control, but a disabled control here
        // carries the reason the server forbids the decision, and that is
        // text (03 section 3.6).
        surfaces.forEach((String where, Color background) {
          expect(
            contrast(ui.color.disabledContent, background),
            greaterThanOrEqualTo(textMinimum),
            reason: '$mode disabled.content on $where',
          );
        });
      });

      test('every findable edge clears 3:1 on every surface', () {
        ui.color.nonTextRoles.forEach((String role, Color colour) {
          surfaces.forEach((String where, Color background) {
            expect(
              contrast(colour, background),
              greaterThanOrEqualTo(nonTextMinimum),
              reason: '$mode $role on $where',
            );
          });
        });
      });

      test('the hairline stays decorative, under 3:1 everywhere', () {
        // The whole point of having both: `boundary` is an edge a reviewer
        // must find, `hairline` is separation they should not have to.
        surfaces.forEach((String where, Color background) {
          expect(
            contrast(ui.color.hairline, background),
            lessThan(nonTextMinimum),
            reason:
                '$mode hairline on $where reads as a boundary, which 09 '
                'section 3.1 forbids',
          );
        });
      });

      test('every status content colour clears 4.5:1 on glass over a field', () {
        ui.color.status.contentColors.forEach((String role, Color colour) {
          surfaces.forEach((String where, Color background) {
            expect(
              contrast(colour, background),
              greaterThanOrEqualTo(textMinimum),
              reason: '$mode $role on $where',
            );
          });
        });
      });

      test('every on-fill clears 4.5:1 on its own fill', () {
        ui.color.status.triples.forEach((String key, UiStatusTriple triple) {
          expect(
            contrast(triple.onFill, triple.fill),
            greaterThanOrEqualTo(textMinimum),
            reason: '$mode $key on-fill',
          );
          expect(
            contrast(triple.content, triple.fill),
            greaterThanOrEqualTo(textMinimum),
            reason: '$mode $key content on its own fill',
          );
        });
      });

      test('the accent carries its own text', () {
        expect(
          contrast(ui.color.onAccent, ui.color.accent),
          greaterThanOrEqualTo(textMinimum),
        );
      });

      test('a region stroke survives the photograph behind it', () {
        final UiStatusColors status = ui.color.status;
        expect(
          contrast(status.regionOverlayStroke, status.regionOverlayCasing),
          greaterThanOrEqualTo(nonTextMinimum),
        );
        expect(
          contrast(status.regionSelectedCore, status.regionSelectedCasing),
          greaterThanOrEqualTo(nonTextMinimum),
        );
      });

      test('the environment band carries its own text', () {
        final UiStatusColors status = ui.color.status;
        expect(
          contrast(
            status.environmentSyntheticOnFill,
            status.environmentSyntheticFill,
          ),
          greaterThanOrEqualTo(textMinimum),
        );
      });

      test('body text on a diff fill clears 4.5:1', () {
        final UiStatusColors status = ui.color.status;
        for (final Color fill in <Color>[
          status.diffAddedFill,
          status.diffChangedFill,
        ]) {
          expect(
            contrast(ui.color.ink, fill),
            greaterThanOrEqualTo(textMinimum),
          );
        }
      });

      test('a disabled control reads as disabled', () {
        // Legible, and still quieter than live supporting text.
        surfaces.forEach((String where, Color background) {
          expect(
            contrast(ui.color.disabledContent, background),
            lessThan(contrast(ui.color.inkSecondary, background)),
            reason: '$mode disabled.content on $where',
          );
        });
      });
    });
  }
}
