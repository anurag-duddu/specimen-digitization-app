// The font gate (10 section 8, `fonts_bundled`).
//
// The v1 rebuild shipped no fonts at all: the flag was false, there were no
// assets, and every screenshot and every golden rendered in the platform sans
// (09 section 0). This holds the two facts that would have caught it.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

void main() {
  test('both faces are bundled as package assets', () {
    for (final String asset in <String>[
      'packages/specimen_ui/${UiFonts.sansAsset}',
      'packages/specimen_ui/${UiFonts.monoAsset}',
    ]) {
      final File file = File(asset);
      expect(file.existsSync(), isTrue, reason: '$asset is missing');
      expect(
        file.lengthSync(),
        greaterThan(1000),
        reason: '$asset is too small to be a typeface',
      );
    }
  });

  test('the package declares both families', () {
    final String pubspec = File(
      'packages/specimen_ui/pubspec.yaml',
    ).readAsStringSync();
    expect(pubspec, contains('family: ${UiFonts.sans}'));
    expect(pubspec, contains('family: ${UiFonts.mono}'));
    expect(pubspec, contains(UiFonts.sansAsset));
    expect(pubspec, contains(UiFonts.monoAsset));
  });

  test('the licence text ships with the faces', () {
    final File licence = File(
      'packages/specimen_ui/LICENSES/OFL-Geist.txt',
    );
    expect(licence.existsSync(), isTrue);
    expect(
      licence.readAsStringSync(),
      contains('SIL OPEN FONT LICENSE Version 1.1'),
    );
  });

  test('every type role resolves to a packaged family', () {
    UiType.standard.all.forEach((String role, TextStyle style) {
      expect(
        style.fontFamily,
        UiFonts.sansFamily,
        reason: '$role should be set in Geist',
      );
    });
    UiType.standard.mono.all.forEach((String role, TextStyle style) {
      expect(
        style.fontFamily,
        UiFonts.monoFamily,
        reason: '$role should be set in Geist Mono',
      );
    });
  });

  test('every text theme slot carries the packaged family', () {
    for (final ThemeData theme in <ThemeData>[
      AppTheme.light(),
      AppTheme.dark(),
    ]) {
      final TextTheme text = theme.textTheme;
      for (final TextStyle? style in <TextStyle?>[
        text.displayLarge,
        text.displayMedium,
        text.displaySmall,
        text.headlineLarge,
        text.headlineMedium,
        text.headlineSmall,
        text.titleLarge,
        text.titleMedium,
        text.titleSmall,
        text.bodyLarge,
        text.bodyMedium,
        text.bodySmall,
        text.labelLarge,
        text.labelMedium,
        text.labelSmall,
      ]) {
        expect(style?.fontFamily, UiFonts.sansFamily);
      }
    }
  });

  test('google_fonts is gone from the dependency graph', () {
    expect(
      File('pubspec.yaml').readAsStringSync(),
      isNot(contains('google_fonts')),
    );
    expect(
      File('pubspec.lock').readAsStringSync(),
      isNot(contains('google_fonts')),
      reason:
          'runtime font fetching is rejected outright (09 section 11); the '
          'package must not be resolvable at all',
    );
  });

  test('weight is set on the variable axis, with a mirrored fallback', () {
    // 09 section 4.1: the axis carries the weight, and `fontWeight` mirrors it
    // so a fallback face with no axis still renders at the right density.
    for (final TextStyle style in UiType.standard.all.values) {
      expect(style.fontVariations, isNotNull);
      expect(style.fontVariations!.single.axis, 'wght');
      expect(style.fontWeight, isNotNull);
    }
    expect(UiType.standard.displayHero.fontVariations!.single.value, 200);
    expect(UiType.standard.body.fontVariations!.single.value, 400);
    expect(UiType.standard.label.fontVariations!.single.value, 500);
  });

  test('the literal roles switch ligatures off', () {
    // A ligature replaces two characters with one glyph, which is exactly
    // wrong for verbatim evidence (09 section 4.1).
    for (final TextStyle style in <TextStyle>[
      UiType.standard.mono.literal,
      UiType.standard.mono.literalDense,
    ]) {
      final List<String> features = style.fontFeatures!
          .map((FontFeature f) => '${f.feature}=${f.value}')
          .toList();
      expect(features, contains('liga=0'));
      expect(features, contains('calt=0'));
    }
  });
}
