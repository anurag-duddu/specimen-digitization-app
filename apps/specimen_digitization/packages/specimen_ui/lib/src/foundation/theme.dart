/// The theme: every token in one object, reachable as `context.ui`
/// (10 sections 1.4 and 1.5).
///
/// This is one of the three files in the package allowed to import
/// `material.dart`, because [UiThemeData.toThemeData] exists precisely to feed
/// the carrier `MaterialApp` a `ThemeData` derived from these tokens. Product
/// code reads `context.ui`, never `Theme.of`.
library;

import 'package:flutter/material.dart';

import 'color.dart';
import 'density.dart';
import 'fields.dart';
import 'fonts.dart';
import 'glass.dart';
import 'icons.dart';
import 'motion.dart';
import 'palette.dart';
import 'shape.dart';
import 'space.dart';
import 'type.dart';

/// Every token the product has.
@immutable
class UiThemeData {
  /// Binds every token group. Prefer [UiThemeData.light] and
  /// [UiThemeData.dark].
  const UiThemeData({
    required this.color,
    required this.field,
    required this.glass,
    required this.type,
    required this.shape,
    required this.space,
    required this.motion,
    required this.quality,
    required this.density,
  });

  /// Colour roles and the status triples.
  final UiColor color;

  /// The five light fields and the three sky presets.
  final UiFields field;

  /// The three glass levels.
  final UiGlass glass;

  /// The type scale and the monospace roles.
  final UiType type;

  /// Radii, strokes and the superellipse helpers.
  final UiShape shape;

  /// The 4 px grid and the fixed sizes.
  final UiSpace space;

  /// Durations and curves, with reduced motion folded in.
  final MotionTokens motion;

  /// How much blur this device can afford.
  final GlassQuality quality;

  /// The resolved density. [UiTheme.of] replaces this with the live value.
  final UiDensity density;

  /// The icon registry. One instance, so `ui.icons.cleared` reads like the
  /// other token groups even though the registry has no per-mode state.
  UiIconRegistry get icons => const UiIconRegistry();

  /// The light theme.
  ///
  /// Building a theme is also where the font licence is declared, so an
  /// application cannot ship the faces without their SIL Open Font License
  /// text in its about dialog.
  factory UiThemeData.light({
    GlassQuality quality = GlassQuality.full,
    UiDensity density = UiDensity.touch,
    MotionTokens motion = const MotionTokens(),
  }) {
    UiFonts.registerLicense();
    return UiThemeData(
      color: UiColor.light,
      field: UiFields.light,
      glass: UiGlass.light,
      type: UiType.standard,
      shape: UiShape.standard,
      space: UiSpace.standard,
      motion: motion,
      quality: quality,
      density: density,
    );
  }

  /// The dark theme.
  factory UiThemeData.dark({
    GlassQuality quality = GlassQuality.full,
    UiDensity density = UiDensity.touch,
    MotionTokens motion = const MotionTokens(),
  }) {
    UiFonts.registerLicense();
    return UiThemeData(
      color: UiColor.dark,
      field: UiFields.dark,
      glass: UiGlass.dark,
      type: UiType.standard,
      shape: UiShape.standard,
      space: UiSpace.standard,
      motion: motion,
      quality: quality,
      density: density,
    );
  }

  /// The product's ambient text style: `type.body` in [UiColor.ink], with
  /// the decoration cleared (11 section 5).
  ///
  /// [UiTheme] publishes this around its child, and every overlay frame that
  /// can be built in a host of its own, a modal route, a popover, a tooltip
  /// and a toast, publishes it again from `context.ui`. One recipe, so a
  /// second overlay cannot drift from the first.
  ///
  /// The decoration is cleared rather than left unset because `Text` merges
  /// its own style onto the ambient one: a style that names only a colour
  /// keeps whatever underline the host left in scope, which is exactly how a
  /// dialog came to draw its title in a double yellow underline.
  TextStyle get defaultTextStyle =>
      type.body.copyWith(color: color.ink, decoration: TextDecoration.none);

  /// True for the dark column.
  bool get isDark => color.isDark;

  /// A copy with the named members replaced.
  UiThemeData copyWith({
    UiColor? color,
    UiFields? field,
    UiGlass? glass,
    UiType? type,
    UiShape? shape,
    UiSpace? space,
    MotionTokens? motion,
    GlassQuality? quality,
    UiDensity? density,
  }) => UiThemeData(
    color: color ?? this.color,
    field: field ?? this.field,
    glass: glass ?? this.glass,
    type: type ?? this.type,
    shape: shape ?? this.shape,
    space: space ?? this.space,
    motion: motion ?? this.motion,
    quality: quality ?? this.quality,
    density: density ?? this.density,
  );

  /// The Material bridge (09 section 4.3).
  ///
  /// `ThemeData.textTheme` still exists for the infrastructure widgets that
  /// read it: text selection and the default `DefaultTextStyle`. It is
  /// derived from [type], never the other way round, and product code reads
  /// `context.ui.type.*` instead.
  TextTheme toTextTheme() => TextTheme(
    displayLarge: type.displayLarge,
    displayMedium: type.displayMedium,
    displaySmall: type.headline,
    headlineLarge: type.headline,
    headlineMedium: type.titleLarge,
    headlineSmall: type.title,
    titleLarge: type.titleLarge,
    titleMedium: type.title,
    titleSmall: type.label,
    bodyLarge: type.bodyLarge,
    bodyMedium: type.body,
    bodySmall: type.bodySmall,
    labelLarge: type.label,
    labelMedium: type.label,
    labelSmall: type.labelSmall,
  );

  /// The `ColorScheme` the carrier `MaterialApp` expects.
  ///
  /// Derived from the roles above, never edited directly. The v2 ground is two
  /// surfaces, not a six-step ramp: everything that is not the window itself
  /// is `paper`, which is what 09 section 3.1 says a solid surface is. In dark
  /// the ramp has three steps because `ground`, `paper` and `matte` are three
  /// distinct values there.
  ColorScheme toColorScheme() {
    final UiStatusColors s = color.status;
    final Color lifted = isDark ? color.matte : color.paper;
    return ColorScheme(
      brightness: color.brightness,
      primary: color.ink,
      onPrimary: color.paper,
      primaryContainer: color.paper,
      onPrimaryContainer: color.ink,
      secondary: s.processing.content,
      onSecondary: isDark ? color.ground : color.paper,
      secondaryContainer: s.processing.fill,
      onSecondaryContainer: s.processing.onFill,
      tertiary: s.authority.content,
      onTertiary: isDark ? color.ground : color.paper,
      tertiaryContainer: s.authority.fill,
      onTertiaryContainer: s.authority.onFill,
      error: s.blocked.content,
      onError: isDark ? color.ground : color.paper,
      errorContainer: s.blocked.fill,
      onErrorContainer: s.blocked.onFill,
      surface: color.ground,
      onSurface: color.ink,
      onSurfaceVariant: color.inkSecondary,
      surfaceContainerLowest: isDark ? color.ground : color.paper,
      surfaceContainerLow: color.paper,
      surfaceContainer: color.paper,
      surfaceContainerHigh: lifted,
      surfaceContainerHighest: lifted,
      surfaceBright: lifted,
      surfaceDim: color.ground,
      outline: color.boundary,
      outlineVariant: color.hairline,
      inverseSurface: color.ink,
      onInverseSurface: isDark ? color.ground : color.paper,
      inversePrimary: isDark ? color.ground : color.paper,
      scrim: GroundPalette.scrim,
      shadow: GroundPalette.scrim,
      surfaceTint: GroundPalette.transparent,
    );
  }

  /// The `ThemeData` the carrier `MaterialApp` runs on.
  ///
  /// Everything a Material widget still on a screen reads comes from here.
  /// The component themes that shape those widgets live in the application,
  /// beside the screens that still use them, and are applied over this with
  /// `copyWith`.
  ThemeData toThemeData() {
    final ColorScheme scheme = toColorScheme();
    return ThemeData(
      useMaterial3: true,
      brightness: scheme.brightness,
      colorScheme: scheme,
      textTheme: toTextTheme(),
      scaffoldBackgroundColor: color.ground,
      canvasColor: color.ground,
      // The ink ripple is Material anatomy and 09 section 11 rejects it
      // outright. Removing it here removes it from every Material widget on
      // every screen in this wave, before a single call site changes.
      splashFactory: NoSplash.splashFactory,
      splashColor: GroundPalette.transparent,
      highlightColor: GroundPalette.transparent,
      visualDensity: VisualDensity.standard,
    );
  }
}

/// The icon registry, as a token group.
@immutable
class UiIconRegistry {
  /// The registry has no per-mode state, so one const instance serves.
  const UiIconRegistry();

  /// The queue destination.
  IconSpec get queue => UiIcons.queue;

  /// The intake destination.
  IconSpec get intake => UiIcons.intake;

  /// The registered sources destination.
  IconSpec get sources => UiIcons.sources;

  /// Cleared.
  IconSpec get cleared => UiIcons.cleared;

  /// Needs human review.
  IconSpec get needsReview => UiIcons.needsReview;

  /// Deferred.
  IconSpec get deferred => UiIcons.deferred;

  /// Processing.
  IconSpec get processing => UiIcons.processing;

  /// Processing blocked.
  IconSpec get blocked => UiIcons.blocked;

  /// State unknown.
  IconSpec get unknown => UiIcons.unknown;

  /// A model produced this reading.
  IconSpec get modelReading => UiIcons.modelReading;

  /// A reviewer decided this.
  IconSpec get reviewer => UiIcons.reviewer;

  /// An external authority matched this value.
  IconSpec get authority => UiIcons.authority;

  /// The test environment banner.
  IconSpec get synthetic => UiIcons.synthetic;

  /// Every entry, by registry key.
  Map<String, IconSpec> get byKey => UiIcons.byKey;

  /// The entry for [key], or null when the registry has none.
  IconSpec? operator [](String key) => UiIcons.spec(key);
}

/// Publishes [UiThemeData] and the product's ambient text style to the tree.
///
/// One of these wraps the application in `main.dart`. `Theme.of` keeps
/// working for the infrastructure widgets because `toThemeData()` feeds
/// `MaterialApp.theme` and `darkTheme`.
///
/// The tokens come with a `DefaultTextStyle` of `type.body` in `ink` with the
/// decoration cleared, so every subtree under this widget, including every
/// route pushed on the root navigator, reads the system's text style rather
/// than the framework's fallback (11 section 5). `MaterialApp` installs that
/// fallback through `WidgetsApp.textStyle`, red monospace with a double
/// yellow underline, and `Material` is what normally replaces it; a design
/// system built on `widgets.dart` has to publish its own or every pane
/// outside a `Material` draws in it. This is the one source: the application
/// no longer patches it at its root and a product modal no longer patches it
/// at its call site.
class UiTheme extends InheritedWidget {
  /// Publishes [data], and the text style it implies, to [child].
  UiTheme({super.key, required this.data, required Widget child})
    : super(child: _publish(data, child));

  /// The ambient text style [data] implies, wrapped around [child].
  ///
  /// Built in the constructor rather than in a `build`, so [UiTheme] stays an
  /// `InheritedWidget` and `dependOnInheritedWidgetOfExactType` keeps finding
  /// it in one hop.
  static Widget _publish(UiThemeData data, Widget child) =>
      DefaultTextStyle(style: data.defaultTextStyle, child: child);

  /// The tokens, before the live density is folded in.
  final UiThemeData data;

  /// The tokens for this context.
  ///
  /// Density and reduced motion are read live rather than stored, so a
  /// reviewer who picks up a tablet or turns on Reduce Motion mid-session
  /// gets the new value without a restart.
  static UiThemeData? _fallbackLight;
  static UiThemeData? _fallbackDark;

  /// The tokens a context with no [UiTheme] above it falls back to.
  ///
  /// A component test that pumps a bare application is the normal case for
  /// this, not an error. Built once per mode, because rebuilding the whole
  /// token set on every lookup would put the type scale in a hot path.
  static UiThemeData _fallback(Brightness brightness) =>
      brightness == Brightness.dark
      ? (_fallbackDark ??= UiThemeData.dark())
      : (_fallbackLight ??= UiThemeData.light());

  /// The tokens for [context], with the live density and reduced-motion
  /// state folded in.
  static UiThemeData of(BuildContext context) {
    final UiTheme? scope = context
        .dependOnInheritedWidgetOfExactType<UiTheme>();
    final UiThemeData base =
        scope?.data ?? _fallback(Theme.of(context).brightness);
    return base.copyWith(
      density: Density.of(context),
      motion: MotionTokens.of(context),
    );
  }

  @override
  bool updateShouldNotify(UiTheme oldWidget) => oldWidget.data != data;
}

/// Reads the tokens from a `BuildContext`.
extension UiThemeContext on BuildContext {
  /// Every token, with the live density and reduced-motion state folded in.
  UiThemeData get ui => UiTheme.of(this);
}
