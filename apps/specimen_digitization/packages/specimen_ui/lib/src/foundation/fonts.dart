/// How Geist ships and how its licence is declared (09 section 4.1).
///
/// The files are package assets, not a runtime fetch: runtime font fetching is
/// rejected outright, and a collection room's network is not something a
/// reviewer should have to wait on to read a label.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show FontLoader, rootBundle;

/// The two families and the assets behind them.
abstract final class UiFonts {
  /// The package that owns the font assets.
  static const String package = 'specimen_ui';

  /// Everything proportional. Variable, `wght` 100 to 900.
  static const String sans = 'Geist';

  /// Literal, identifier, digest and code. Variable, `wght` 100 to 900.
  static const String mono = 'Geist Mono';

  /// The asset path of the proportional face inside this package.
  static const String sansAsset = 'assets/fonts/GeistVF.ttf';

  /// The asset path of the monospaced face inside this package.
  static const String monoAsset = 'assets/fonts/GeistMonoVF.ttf';

  /// The family name Flutter resolves a package font under.
  ///
  /// `TextStyle(fontFamily: 'Geist', package: 'specimen_ui')` and
  /// `TextStyle(fontFamily: 'packages/specimen_ui/Geist')` are the same
  /// family. Tests that load the files with a `FontLoader` must register them
  /// under this prefixed name or a golden renders in the platform sans.
  static String prefixed(String family) => 'packages/$package/$family';

  /// The prefixed name of [sans].
  static String get sansFamily => prefixed(sans);

  /// The prefixed name of [mono].
  static String get monoFamily => prefixed(mono);

  /// The asset paths of both faces, under the package prefix a bundle uses.
  static List<String> get bundleAssets => <String>[
    'packages/$package/$sansAsset',
    'packages/$package/$monoAsset',
  ];

  static bool _licenceRegistered = false;

  /// Declares the SIL Open Font License 1.1 for both families.
  ///
  /// Called once from `UiThemeData` construction, so an application that uses
  /// the theme cannot ship the faces without their licence. Repeat calls are
  /// ignored: `LicenseRegistry` has no way to withdraw an entry, and the
  /// about dialog would otherwise list the text once per theme build.
  static void registerLicense() {
    if (_licenceRegistered) return;
    _licenceRegistered = true;
    LicenseRegistry.addLicense(() async* {
      final String text = await rootBundle.loadString(
        'packages/$package/LICENSES/OFL-Geist.txt',
      );
      yield LicenseEntryWithLineBreaks(const <String>[sans, mono], text);
    });
  }

  /// Undoes the guard in [registerLicense]. For tests only.
  @visibleForTesting
  static void resetLicenseRegistrationForTest() => _licenceRegistered = false;

  /// Loads both faces into the current binding under their prefixed names.
  ///
  /// Used by `flutter_test_config.dart` in this package and in the
  /// application, so that every golden renders in the product typeface. The
  /// v1 goldens rendered in the platform sans, which is the defect this
  /// closes.
  static Future<void> loadForTest(
    Future<ByteData> Function(String path) load,
  ) async {
    for (final (String family, String asset) in <(String, String)>[
      (sansFamily, sansAsset),
      (monoFamily, monoAsset),
    ]) {
      final FontLoader loader = FontLoader(family);
      loader.addFont(load(asset));
      await loader.load();
    }
  }
}
