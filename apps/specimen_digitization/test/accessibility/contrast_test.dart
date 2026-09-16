// WCAG 2.2 contrast, computed rather than estimated.
//
// design/06-accessibility.md section 2.3 tabulates the disposition colors and
// the environment-banner pair with hand-computed ratios. Section 4.1 asks for
// this test so the computation, not the table, is the source of truth: a seed
// or token change that regresses contrast fails here instead of shipping.
//
// Formula: https://www.w3.org/WAI/WCAG22/quickref/#contrast-minimum

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The scaffold background the client renders behind all of these, `main.dart`.
const scaffoldBackground = Color(0xfff4f6f3);

/// WCAG AA minimum for body text.
const aaText = 4.5;

/// Disposition colors, design/06-accessibility.md section 2.3.
const dispositionColors = <String, Color>{
  'Cleared': Color(0xff14513d),
  'Needs review': Color(0xff754300),
  'Deferred': Color(0xff594d7c),
  'Default or unknown': Color(0xff374b60),
};

/// Environment banner, design/06-accessibility.md section 2.3.
const environmentBannerForeground = Color(0xff483500);
const environmentBannerBackground = Color(0xffffe7a3);

/// Relative luminance of one sRGB channel, expressed as 0.0 to 1.0.
double _linearize(double channel) => channel <= 0.03928
    ? channel / 12.92
    : math.pow((channel + 0.055) / 1.055, 2.4).toDouble();

/// WCAG relative luminance. Alpha is ignored: both arguments must be opaque,
/// which is what a token pair being checked for contrast always is.
double relativeLuminance(Color color) =>
    0.2126 * _linearize(color.r) +
    0.7152 * _linearize(color.g) +
    0.0722 * _linearize(color.b);

/// WCAG contrast ratio between two opaque colors. Ordering does not matter;
/// the result runs from 1.0 (identical) to 21.0 (black against white).
double contrastRatio(Color a, Color b) {
  final first = relativeLuminance(a);
  final second = relativeLuminance(b);
  final lighter = math.max(first, second);
  final darker = math.min(first, second);
  return (lighter + 0.05) / (darker + 0.05);
}

void main() {
  group('contrastRatio', () {
    test('matches the two anchors the formula defines', () {
      expect(
        contrastRatio(const Color(0xff000000), const Color(0xffffffff)),
        closeTo(21, 0.01),
      );
      expect(
        contrastRatio(const Color(0xff777777), const Color(0xff777777)),
        closeTo(1, 0.0001),
      );
    });

    test('is symmetric in its arguments', () {
      expect(
        contrastRatio(dispositionColors['Cleared']!, scaffoldBackground),
        closeTo(
          contrastRatio(scaffoldBackground, dispositionColors['Cleared']!),
          0.0001,
        ),
      );
    });

    test('agrees with a known third-party value', () {
      // #767676 on white is the canonical 4.54:1 example used by WebAIM and by
      // the WCAG understanding document for the AA text minimum.
      expect(
        contrastRatio(const Color(0xff767676), const Color(0xffffffff)),
        closeTo(4.54, 0.01),
      );
    });
  });

  group('design/06-accessibility.md section 2.3', () {
    dispositionColors.forEach((name, color) {
      test('$name disposition color meets 4.5:1 on the scaffold background', () {
        expect(
          contrastRatio(color, scaffoldBackground),
          greaterThanOrEqualTo(aaText),
          reason:
              '$name is used as a status tint and is a candidate for chip text '
              '(section 3.1). It must clear AA text contrast, not only the 3:1 '
              'non-text minimum.',
        );
      });
    });

    test('the environment banner pair meets 4.5:1', () {
      expect(
        contrastRatio(environmentBannerForeground, environmentBannerBackground),
        greaterThanOrEqualTo(aaText),
        reason:
            'The environment banner is body text on a filled background and is '
            'the one element that is always on screen in a synthetic build.',
      );
    });

    test('the banner foreground also clears 4.5:1 on the scaffold', () {
      // The banner does not span the full width at every size class, so its
      // text can land on the scaffold rather than the fill.
      expect(
        contrastRatio(environmentBannerForeground, scaffoldBackground),
        greaterThanOrEqualTo(aaText),
      );
    });
  });

  test('generated onSurface meets 4.5:1 on the scaffold background', () {
    // Section 2.3: the default body-text color is not a literal. It is computed
    // by ColorScheme.fromSeed at runtime, so a seed change is the regression
    // this asserts against, using the same seed and surface as main.dart.
    final theme = ThemeData(
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xff174f3b),
        surface: const Color(0xfff9fbf7),
      ),
    );
    expect(
      contrastRatio(theme.colorScheme.onSurface, scaffoldBackground),
      greaterThanOrEqualTo(aaText),
    );
  });
}
