/// Google's published specification of the "Sign in with Google" button, kept
/// in one place (10 section 4.1, `UiGoogleSignInButton`).
///
/// A third party's brand is the one thing in this product whose measurements
/// are not ours to choose, so they are not tokens of ours either: they are
/// written here, each with the figure of Google's page it comes from, and
/// every other file reads them by name. The foundation is the one place the
/// package gates allow a size to be written as a number
/// (`test/gates/no_literal_geometry_test.dart`), and
/// `palette.dart`'s [GoogleSignInPalette] already holds the colours of the same
/// button, so the brand has two files and the gates have one allowance for it.
///
/// Source: Google Identity, "Sign in with Google branding guidelines",
/// <https://developers.google.com/identity/branding-guidelines>, page last
/// updated 2026-07-07 UTC, the section "Create a custom Sign in with Google
/// Button". Its figure for Android and web,
/// <https://developers.google.com/static/identity/images/branding_guide_android_web_spec.png>,
/// gives the 40 high pill, the paddings of 12, 10 and 12, the 20 by 20 "G" and
/// "Google Sans Medium 14/20". The page prints a second figure for iOS
/// (`branding_guide_ios_spec.png`: 44 high, paddings of 16, 12 and 16,
/// Roboto Medium) and nothing here reads it: the owner decided that the button
/// looks the same on every platform, so one figure is drawn on all of them:
/// the Android and web one, which the page labels "Android & Web (mobile +
/// desktop)". Whether Google's brand review accepts that figure in an iPhone
/// app is not something the page says.
library;

import 'package:flutter/widgets.dart' show FontWeight;

/// What Google's page fixes about the button.
abstract final class GoogleSignInBrand {
  /// Where the specification is published.
  static const String guidelinesUrl =
      'https://developers.google.com/identity/branding-guidelines';

  /// The "Last updated" line of [guidelinesUrl] when these figures were read.
  static const String guidelinesUpdated = '2026-07-07';

  /// The call to action. One of the three the page recommends ("Sign in with
  /// Google", "Sign up with Google", "Continue with Google"); never "Google"
  /// alone, which the page forbids. It states that the person is signing in to
  /// this app with a Google credential, which is the page's other requirement
  /// of the text.
  static const String label = 'Sign in with Google';

  /// The button's height at normal text size: 40.
  ///
  /// The visual only. The hit box around it is the system's 48 dp, which the
  /// page leaves to the app: a transparent 4 dp on each side.
  static const double height = 40;

  /// The "G" logo's box: 20 by 20. The page says the logo's size and colour
  /// are not to be changed, so it does not scale with the text.
  static const double iconSize = 20;

  /// The padding before the "G" in the reading direction: 12.
  static const double paddingStart = 12;

  /// The space between the "G" and the text: 10.
  static const double iconGap = 10;

  /// The padding after the text in the reading direction: 12.
  static const double paddingEnd = 12;

  /// The width of the outline of the light and dark themes: 1, drawn inside
  /// the button's edge.
  static const double strokeWidth = 1;

  /// The label's size: the 14 of "14/20".
  static const double fontSize = 14;

  /// The label's line box: the 20 of "14/20".
  static const double lineHeight = 20;

  /// The label's weight: Medium.
  static const FontWeight fontWeight = FontWeight.w500;

  /// The family the bundled Google Sans Medium is declared under in this
  /// package's `pubspec.yaml`. It is Google's face for Google's button and is
  /// read by nothing else.
  static const String fontFamily = 'GoogleSignInSans';

  /// The package that owns the font and the logo.
  static const String package = 'specimen_ui';

  /// The family name Flutter resolves the bundled face under: the same
  /// `packages/<package>/` prefix `UiFonts.prefixed` gives Geist.
  static const String prefixedFontFamily = 'packages/$package/$fontFamily';

  /// The asset path of Google Sans Medium inside this package. Provenance and
  /// licence are in `assets/google-sign-in/README.md` and `OFL.txt`.
  static const String fontAsset = 'assets/google-sign-in/GoogleSans-Medium.ttf';

  /// The asset path of Google's unmodified standard colour "G" inside this
  /// package (<https://developers.google.com/static/identity/images/g-logo.png>).
  static const String logoAsset = 'assets/google-sign-in/google-g.png';

  /// The share of its paint a disabled button keeps: 0.38, Material 3's
  /// disabled content opacity.
  ///
  /// The page does not describe a disabled button. It tells a custom button to
  /// follow Google's Material guidelines for its boundary and colour scheme,
  /// and 0.38 is the figure Material gives disabled content. It is applied to
  /// the whole button, so the "G" keeps its colours and only fades.
  static const double disabledOpacity = 0.38;
}
