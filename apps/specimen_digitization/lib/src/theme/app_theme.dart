/// The bridge `ThemeData` the carrier `MaterialApp` runs on.
///
/// The product reads `context.ui` and never `Theme.of`. This file exists for
/// the infrastructure below `MaterialApp` that cannot:
/// `UiThemeData.toThemeData` derives the colour scheme, the Geist text theme
/// (09 section 4.3) and the ground from the tokens; this adds the selection
/// colours the editing infrastructure paints with and the page transitions
/// 10 section 1.3 keeps; and `MaterialApp` itself supplies the
/// `MaterialLocalizations` the package's tooltip reads its dismissal strings
/// from. That is the whole bridge.
///
/// Nothing here shapes a component any more. The fifteen v1 component themes,
/// the `InputDecorationTheme` beneath every field and the four product
/// `ThemeExtension`s left with the last Material widget on a screen: no call
/// site reads `Theme.of` for a token, and `FieldCore` builds no
/// `InputDecorator` for a decoration theme to paint through (11 section 4).
///
/// Light and dark are both first class; `themeMode` follows the platform.
library;

import 'package:flutter/material.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Assembles the tokens into the `ThemeData` the carrier expects.
abstract final class AppTheme {
  static ThemeData? _light;
  static ThemeData? _dark;

  /// The light theme.
  static ThemeData light() => _light ??= _build(UiThemeData.light());

  /// The dark theme.
  static ThemeData dark() => _dark ??= _build(UiThemeData.dark());

  static ThemeData _build(UiThemeData ui) => ui.toThemeData().copyWith(
    // The caret and the highlight behind selected characters are published
    // from inside the field as well, through `DefaultSelectionStyle`, so a
    // field is right in a bare `WidgetsApp` too. The drag handles are not:
    // they are drawn by the Material selection controls above the editor,
    // which read them here. Same two tokens, stated where the infrastructure
    // looks for them (11 section 4).
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: ui.color.ink,
      selectionColor: ui.color.selection,
      selectionHandleColor: ui.color.ink,
    ),
    pageTransitionsTheme: specimenPageTransitions,
  );
}

/// The page transitions the motion document specifies (section 6.1).
///
/// The mobile entries restate Flutter's own defaults so a future SDK change is
/// a visible diff; the desktop and web entries move off the zoom transition
/// onto the Material 3 forward transition.
const PageTransitionsTheme specimenPageTransitions = PageTransitionsTheme(
  builders: <TargetPlatform, PageTransitionsBuilder>{
    TargetPlatform.android: PredictiveBackPageTransitionsBuilder(),
    TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
    TargetPlatform.windows: FadeForwardsPageTransitionsBuilder(),
    TargetPlatform.linux: FadeForwardsPageTransitionsBuilder(),
    TargetPlatform.fuchsia: FadeForwardsPageTransitionsBuilder(),
  },
);
