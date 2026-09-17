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
    TargetPlatform.android: _ReducedMotionTransitions(
      PredictiveBackPageTransitionsBuilder(),
    ),
    TargetPlatform.iOS: _ReducedMotionTransitions(
      CupertinoPageTransitionsBuilder(),
    ),
    TargetPlatform.macOS: _ReducedMotionTransitions(
      CupertinoPageTransitionsBuilder(),
    ),
    TargetPlatform.windows: _ReducedMotionTransitions(
      FadeForwardsPageTransitionsBuilder(),
    ),
    TargetPlatform.linux: _ReducedMotionTransitions(
      FadeForwardsPageTransitionsBuilder(),
    ),
    TargetPlatform.fuchsia: _ReducedMotionTransitions(
      FadeForwardsPageTransitionsBuilder(),
    ),
  },
);

/// A platform's page transition, collapsed under reduced motion.
///
/// 04 section 2.5 has every transition collapse when the platform or the
/// reviewer asks for less motion; the Cupertino slide alone travelled the
/// full 450 ms on iOS (verification report v2, V2-6). The route appears in
/// place instead, and the platform's own builder runs otherwise.
class _ReducedMotionTransitions extends PageTransitionsBuilder {
  const _ReducedMotionTransitions(this.inner);

  final PageTransitionsBuilder inner;

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    if (MotionTokens.of(context).reduced) return child;
    return inner.buildTransitions<T>(
      route,
      context,
      animation,
      secondaryAnimation,
      child,
    );
  }
}
