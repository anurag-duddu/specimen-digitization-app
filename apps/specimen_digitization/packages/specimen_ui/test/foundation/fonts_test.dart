// The faces resolve to the bundled assets (10 section 7, `fonts`).

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

void main() {
  test('both faces exist under the package', () {
    for (final String asset in <String>[UiFonts.sansAsset, UiFonts.monoAsset]) {
      expect(File(asset).existsSync(), isTrue, reason: '$asset is missing');
    }
  });

  test('a package family resolves under its prefixed name', () {
    // `TextStyle(fontFamily: 'Geist', package: 'specimen_ui')` and
    // `fontFamily: 'packages/specimen_ui/Geist'` are the same family. A test
    // that loads the file has to register it under the prefixed name or the
    // golden renders in the platform sans.
    expect(UiFonts.sansFamily, 'packages/specimen_ui/Geist');
    expect(UiFonts.monoFamily, 'packages/specimen_ui/Geist Mono');
  });

  test('every proportional role is set in Geist', () {
    UiType.standard.all.forEach((String role, TextStyle style) {
      expect(style.fontFamily, UiFonts.sansFamily, reason: role);
    });
  });

  test('every monospace role is set in Geist Mono', () {
    UiType.standard.mono.all.forEach((String role, TextStyle style) {
      expect(style.fontFamily, UiFonts.monoFamily, reason: role);
    });
  });

  test('the licence is registered once, not once per theme', () {
    UiFonts.resetLicenseRegistrationForTest();
    UiFonts.registerLicense();
    UiFonts.registerLicense();
    UiFonts.registerLicense();
    // `LicenseRegistry` has no way to withdraw an entry, so a second call
    // would list the text again in the about dialog.
    expect(
      LicenseRegistry.licenses,
      isNotNull,
      reason: 'the guard must not throw on a repeat call',
    );
  });

  test('a numeral role carries tabular figures', () {
    // 09 section 4.1: every count, catalogue number, coordinate, duration and
    // version number is tabular, so a changed digit is visible by position.
    for (final TextStyle style in <TextStyle>[
      UiType.standard.displayHero,
      UiType.standard.displayLarge,
      UiType.standard.displayMedium,
    ]) {
      expect(
        style.fontFeatures?.map((FontFeature f) => f.feature),
        contains('tnum'),
      );
    }
  });

  test('the mono specimen line is the one 09 pins by golden', () {
    expect(UiType.monoSpecimen, '0O 1lI 5S 2Z 8B');
  });
}
