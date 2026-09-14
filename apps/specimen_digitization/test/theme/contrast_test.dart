// Layer one of the contrast gate (design system, section 8.4): the token
// table, checked in pure Dart so a failure names the exact pair.
//
// The relative luminance and contrast formulas are implemented here from the
// WCAG 2.2 definitions rather than taken from a helper, so the test is an
// independent check on the numbers printed in the design system.
// https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/theme/semantic_colors.dart';

/// WCAG 2.2 relative luminance, on a channel in the range 0 to 1.
double _channel(double c) =>
    c <= 0.04045 ? c / 12.92 : math.pow((c + 0.055) / 1.055, 2.4).toDouble();

double luminance(Color c) =>
    0.2126 * _channel(c.r) + 0.7152 * _channel(c.g) + 0.0722 * _channel(c.b);

double contrast(Color a, Color b) {
  final double la = luminance(a);
  final double lb = luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// Text and any icon that carries meaning.
const double textMinimum = 4.5;

/// Non-text contrast: a boundary the user must be able to find.
/// https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
const double nonTextMinimum = 3.0;

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

  for (final (String name, ThemeData theme, SpecimenColors tokens)
      in <(String, ThemeData, SpecimenColors)>[
        ('light', AppTheme.light(), SpecimenColors.light),
        ('dark', AppTheme.dark(), SpecimenColors.dark),
      ]) {
    final ColorScheme scheme = theme.colorScheme;
    final Map<String, Color> surfaces = <String, Color>{
      'surface': scheme.surface,
      'surfaceContainerLowest': scheme.surfaceContainerLowest,
      'surfaceContainerLow': scheme.surfaceContainerLow,
      'surfaceContainer': scheme.surfaceContainer,
      'surfaceContainerHigh': scheme.surfaceContainerHigh,
      'surfaceContainerHighest': scheme.surfaceContainerHighest,
      'surfaceDim': scheme.surfaceDim,
      'surfaceBright': scheme.surfaceBright,
    };

    group('$name scheme', () {
      test('text roles clear 4.5:1 on every surface', () {
        for (final MapEntry<String, Color> text in <String, Color>{
          'onSurface': scheme.onSurface,
          'onSurfaceVariant': scheme.onSurfaceVariant,
        }.entries) {
          for (final MapEntry<String, Color> s in surfaces.entries) {
            expect(
              contrast(text.value, s.value),
              greaterThanOrEqualTo(textMinimum),
              reason: '$name ${text.key} on ${s.key}',
            );
          }
        }
      });

      test('every on-color clears 4.5:1 on its own role', () {
        final Map<String, (Color, Color)> pairs = <String, (Color, Color)>{
          'primary': (scheme.primary, scheme.onPrimary),
          'primaryContainer': (
            scheme.primaryContainer,
            scheme.onPrimaryContainer,
          ),
          'secondary': (scheme.secondary, scheme.onSecondary),
          'secondaryContainer': (
            scheme.secondaryContainer,
            scheme.onSecondaryContainer,
          ),
          'tertiary': (scheme.tertiary, scheme.onTertiary),
          'tertiaryContainer': (
            scheme.tertiaryContainer,
            scheme.onTertiaryContainer,
          ),
          'error': (scheme.error, scheme.onError),
          'errorContainer': (scheme.errorContainer, scheme.onErrorContainer),
          'inverseSurface': (scheme.inverseSurface, scheme.onInverseSurface),
          'inverseSurface and inversePrimary': (
            scheme.inverseSurface,
            scheme.inversePrimary,
          ),
        };
        for (final MapEntry<String, (Color, Color)> pair in pairs.entries) {
          expect(
            contrast(pair.value.$1, pair.value.$2),
            greaterThanOrEqualTo(textMinimum),
            reason: '$name ${pair.key}',
          );
        }
      });

      test('outline clears 3:1 on every surface', () {
        for (final MapEntry<String, Color> s in surfaces.entries) {
          expect(
            contrast(scheme.outline, s.value),
            greaterThanOrEqualTo(nonTextMinimum),
            reason: '$name outline on ${s.key}',
          );
        }
      });

      test('outlineVariant stays decorative, under 3:1 everywhere', () {
        for (final MapEntry<String, Color> s in surfaces.entries) {
          expect(
            contrast(scheme.outlineVariant, s.value),
            lessThan(nonTextMinimum),
            reason:
                '$name outlineVariant on ${s.key} is a boundary a user could '
                'be asked to find, which section 5.9 forbids',
          );
        }
      });

      test('every product content token clears 4.5:1 on every surface', () {
        for (final MapEntry<String, Color> t
            in tokens.allContentColors.entries) {
          for (final MapEntry<String, Color> s in surfaces.entries) {
            expect(
              contrast(t.value, s.value),
              greaterThanOrEqualTo(textMinimum),
              reason: '$name ${t.key} on ${s.key}',
            );
          }
        }
      });

      test('every on-fill clears 4.5:1 on its fill', () {
        for (final FillPair pair in tokens.fillPairs) {
          expect(
            contrast(pair.onFill, pair.fill),
            greaterThanOrEqualTo(textMinimum),
            reason: '$name ${pair.name}',
          );
        }
      });

      test('body text on a diff fill clears 4.5:1', () {
        for (final FillPair pair in tokens.diffFillPairs(scheme.onSurface)) {
          expect(
            contrast(pair.onFill, pair.fill),
            greaterThanOrEqualTo(textMinimum),
            reason: '$name ${pair.name}',
          );
        }
      });

      test('content is legible on its own fill', () {
        for (final MapEntry<String, TokenTriple> t in tokens.triples.entries) {
          expect(
            contrast(t.value.content, t.value.fill),
            greaterThanOrEqualTo(textMinimum),
            reason: '$name ${t.key} content on its own fill',
          );
        }
      });

      test('focus ring clears 3:1 on every surface', () {
        for (final MapEntry<String, Color> s in surfaces.entries) {
          expect(
            contrast(tokens.focusRing, s.value),
            greaterThanOrEqualTo(nonTextMinimum),
            reason: '$name focus ring on ${s.key}',
          );
        }
      });

      // Finding V-8. Material draws a disabled control at 38 percent of the
      // content color, which measured 2.38:1 and 2.25:1 on the two controls
      // the verification report caught. Both disabled tokens are now held to
      // the 3:1 non-text floor on every surface, in both modes, and the
      // theme passes them to every button, chip and field rather than
      // leaving Material's default in place.
      test('both disabled tokens clear 3:1 on every surface', () {
        for (final MapEntry<String, Color> t in tokens.disabledColors.entries) {
          for (final MapEntry<String, Color> s in surfaces.entries) {
            expect(
              contrast(t.value, s.value),
              greaterThanOrEqualTo(nonTextMinimum),
              reason: '$name ${t.key} on ${s.key}',
            );
          }
        }
      });

      test('disabled content clears 4.5:1, because it is a sentence', () {
        for (final MapEntry<String, Color> s in surfaces.entries) {
          expect(
            contrast(tokens.disabledContent, s.value),
            greaterThanOrEqualTo(textMinimum),
            reason: '$name disabled content on ${s.key}',
          );
        }
      });

      test('disabled content clears 3:1 on the disabled container', () {
        for (final MapEntry<String, Color> s in surfaces.entries) {
          final Color filled = Color.alphaBlend(
            tokens.disabledContainer,
            s.value,
          );
          expect(
            contrast(tokens.disabledContent, filled),
            greaterThanOrEqualTo(nonTextMinimum),
            reason: '$name disabled content on its container over ${s.key}',
          );
        }
      });

      test('disabled content beats the 38 percent default it replaces', () {
        for (final MapEntry<String, Color> s in surfaces.entries) {
          final Color material = Color.alphaBlend(
            scheme.onSurface.withValues(alpha: 0.38),
            s.value,
          );
          expect(
            contrast(material, s.value),
            lessThan(contrast(tokens.disabledContent, s.value)),
            reason:
                '$name: Material draws a disabled control at 38 percent on '
                '${s.key}, which is what finding V-8 measured at 2.3:1',
          );
        }
      });

      test('disabled content is quieter than live body text', () {
        for (final MapEntry<String, Color> s in surfaces.entries) {
          expect(
            contrast(tokens.disabledContent, s.value),
            lessThan(contrast(scheme.onSurfaceVariant, s.value)),
            reason:
                '$name: a disabled control has to be legible and still read '
                'as disabled on ${s.key}',
          );
        }
      });

      test('a region stroke survives the photograph behind it', () {
        expect(
          contrast(tokens.regionOverlayStroke, tokens.regionOverlayCasing),
          greaterThanOrEqualTo(nonTextMinimum),
          reason: '$name region overlay against its casing',
        );
        expect(
          contrast(tokens.regionSelectedCore, tokens.regionSelectedCasing),
          greaterThanOrEqualTo(nonTextMinimum),
          reason: '$name selected region against its casing',
        );
      });
    });
  }
}
