/// Colour roles (09 sections 3.1, 3.4 and 3.5).
///
/// A role is named for what it does, never for a value. The values live in
/// `palette.dart`; this file is the only place that turns one into a role and
/// the only place that applies an opacity to one.
library;

import 'package:flutter/widgets.dart';

import 'palette.dart';

/// One status token: the triple a component needs to render a state.
///
/// `content` is text, glyphs and borders; `fill` is the container behind them;
/// `onFill` is text placed on that container. A component reads a whole triple
/// so it cannot mix the content colour of one status with the fill of another.
@immutable
class UiStatusTriple {
  /// Binds the three members of one status token.
  const UiStatusTriple({
    required this.content,
    required this.fill,
    required this.onFill,
  });

  /// Text, glyphs and borders. Clears 4.5:1 on every surface in its mode.
  final Color content;

  /// The container behind [content].
  final Color fill;

  /// Text placed on [fill].
  final Color onFill;

  /// Interpolates all three members.
  UiStatusTriple lerp(UiStatusTriple other, double t) => UiStatusTriple(
    content: Color.lerp(content, other.content, t)!,
    fill: Color.lerp(fill, other.fill, t)!,
    onFill: Color.lerp(onFill, other.onFill, t)!,
  );
}

/// The status and evidence triples, carried from v1 unchanged in value.
@immutable
class UiStatusColors {
  /// Binds every status token.
  const UiStatusColors({
    required this.cleared,
    required this.needsReview,
    required this.deferred,
    required this.processing,
    required this.blocked,
    required this.model,
    required this.human,
    required this.authority,
    required this.diffAddedContent,
    required this.diffAddedFill,
    required this.diffChangedContent,
    required this.diffChangedFill,
    required this.diffUnchangedContent,
    required this.riskLow,
    required this.riskMedium,
    required this.riskHigh,
    required this.environmentSyntheticFill,
    required this.environmentSyntheticOnFill,
    required this.regionOverlayStroke,
    required this.regionOverlayCasing,
    required this.regionSelectedCore,
    required this.regionSelectedCasing,
  });

  /// Green. A human affirmed it.
  final UiStatusTriple cleared;

  /// Ochre. Attention, not failure.
  final UiStatusTriple needsReview;

  /// Clay. Shelved, not judged.
  final UiStatusTriple deferred;

  /// Steel. Never a final queue; always paired with a progress affordance.
  final UiStatusTriple processing;

  /// Oxide. Operational, not evidentiary.
  final UiStatusTriple blocked;

  /// Slate. A model reading is an observation, not a decision.
  final UiStatusTriple model;

  /// Green. The only thing in this product allowed to look affirmative.
  final UiStatusTriple human;

  /// Teal. An external reference file.
  final UiStatusTriple authority;

  /// Marker `+` plus a 3 dp leading bar.
  final Color diffAddedContent;

  /// Highlight behind body text. Tuned against `ink`, not against an on-fill.
  final Color diffAddedFill;

  /// Marker `~` plus an underline.
  final Color diffChangedContent;

  /// Highlight behind changed body text.
  final Color diffChangedFill;

  /// No fill, no marker. Equals `ink.secondary`.
  final Color diffUnchangedContent;

  /// Risk bands. Never rendered without the "not calibrated" caveat.
  final Color riskLow;

  /// The middle risk band.
  final Color riskMedium;

  /// The top risk band.
  final Color riskHigh;

  /// Full-bleed band on a test environment, never dismissible.
  final Color environmentSyntheticFill;

  /// Text on [environmentSyntheticFill].
  final Color environmentSyntheticOnFill;

  /// 2 dp stroke over a photograph, with [regionOverlayCasing] outside it.
  final Color regionOverlayStroke;

  /// The casing that keeps a region stroke visible over any pixel.
  final Color regionOverlayCasing;

  /// Selection over the image. Identical in both modes, because it is
  /// transient and lives only over an arbitrary photograph.
  final Color regionSelectedCore;

  /// The casing around [regionSelectedCore].
  final Color regionSelectedCasing;

  /// Every triple, by the key the v1 call sites already use.
  Map<String, UiStatusTriple> get triples => <String, UiStatusTriple>{
    'disposition.cleared': cleared,
    'disposition.needsReview': needsReview,
    'disposition.deferred': deferred,
    'state.processing': processing,
    'state.blocked': blocked,
    'evidence.model': model,
    'evidence.human': human,
    'evidence.authority': authority,
  };

  /// Every colour that can carry text or a meaningful glyph on a surface.
  Map<String, Color> get contentColors => <String, Color>{
    for (final MapEntry<String, UiStatusTriple> e in triples.entries)
      e.key: e.value.content,
    'diff.added': diffAddedContent,
    'diff.changed': diffChangedContent,
    'diff.unchanged': diffUnchangedContent,
    'risk.low': riskLow,
    'risk.medium': riskMedium,
    'risk.high': riskHigh,
  };

  /// The light table.
  static const UiStatusColors light = UiStatusColors(
    cleared: UiStatusTriple(
      content: StatusPalette.greenContentLight,
      fill: StatusPalette.greenFillLight,
      onFill: StatusPalette.greenOnFillLight,
    ),
    needsReview: UiStatusTriple(
      content: StatusPalette.ochreContentLight,
      fill: StatusPalette.ochreFillLight,
      onFill: StatusPalette.ochreOnFillLight,
    ),
    deferred: UiStatusTriple(
      content: StatusPalette.clayContentLight,
      fill: StatusPalette.clayFillLight,
      onFill: StatusPalette.clayOnFillLight,
    ),
    processing: UiStatusTriple(
      content: StatusPalette.steelContentLight,
      fill: StatusPalette.steelFillLight,
      onFill: StatusPalette.steelOnFillLight,
    ),
    blocked: UiStatusTriple(
      content: StatusPalette.oxideContentLight,
      fill: StatusPalette.oxideFillLight,
      onFill: StatusPalette.oxideOnFillLight,
    ),
    model: UiStatusTriple(
      content: StatusPalette.slateContentLight,
      fill: StatusPalette.slateFillLight,
      onFill: StatusPalette.slateOnFillLight,
    ),
    human: UiStatusTriple(
      content: StatusPalette.greenContentLight,
      fill: StatusPalette.greenFillLight,
      onFill: StatusPalette.greenOnFillLight,
    ),
    authority: UiStatusTriple(
      content: StatusPalette.tealContentLight,
      fill: StatusPalette.tealFillLight,
      onFill: StatusPalette.tealOnFillLight,
    ),
    diffAddedContent: StatusPalette.greenContentLight,
    diffAddedFill: StatusPalette.diffAddedFillLight,
    diffChangedContent: StatusPalette.ochreContentLight,
    diffChangedFill: StatusPalette.diffChangedFillLight,
    diffUnchangedContent: GroundPalette.inkSecondaryLight,
    riskLow: StatusPalette.greenContentLight,
    riskMedium: StatusPalette.ochreContentLight,
    riskHigh: StatusPalette.oxideContentLight,
    environmentSyntheticFill: StatusPalette.environmentFillLight,
    environmentSyntheticOnFill: StatusPalette.environmentOnFillLight,
    regionOverlayStroke: StatusPalette.steelContentLight,
    regionOverlayCasing: StatusPalette.regionCasingLight,
    regionSelectedCore: StatusPalette.regionSelectedCore,
    regionSelectedCasing: StatusPalette.regionSelectedCasing,
  );

  /// The dark table.
  static const UiStatusColors dark = UiStatusColors(
    cleared: UiStatusTriple(
      content: StatusPalette.greenContentDark,
      fill: StatusPalette.greenFillDark,
      onFill: StatusPalette.greenOnFillDark,
    ),
    needsReview: UiStatusTriple(
      content: StatusPalette.ochreContentDark,
      fill: StatusPalette.ochreFillDark,
      onFill: StatusPalette.ochreOnFillDark,
    ),
    deferred: UiStatusTriple(
      content: StatusPalette.clayContentDark,
      fill: StatusPalette.clayFillDark,
      onFill: StatusPalette.clayOnFillDark,
    ),
    processing: UiStatusTriple(
      content: StatusPalette.steelContentDark,
      fill: StatusPalette.steelFillDark,
      onFill: StatusPalette.steelOnFillDark,
    ),
    blocked: UiStatusTriple(
      content: StatusPalette.oxideContentDark,
      fill: StatusPalette.oxideFillDark,
      onFill: StatusPalette.oxideOnFillDark,
    ),
    model: UiStatusTriple(
      content: StatusPalette.slateContentDark,
      fill: StatusPalette.slateFillDark,
      onFill: StatusPalette.slateOnFillDark,
    ),
    human: UiStatusTriple(
      content: StatusPalette.greenContentDark,
      fill: StatusPalette.greenFillDark,
      onFill: StatusPalette.greenOnFillDark,
    ),
    authority: UiStatusTriple(
      content: StatusPalette.tealContentDark,
      fill: StatusPalette.tealFillDark,
      onFill: StatusPalette.tealOnFillDark,
    ),
    diffAddedContent: StatusPalette.greenContentDark,
    diffAddedFill: StatusPalette.diffAddedFillDark,
    diffChangedContent: StatusPalette.ochreContentDark,
    diffChangedFill: StatusPalette.diffChangedFillDark,
    diffUnchangedContent: GroundPalette.inkSecondaryDark,
    riskLow: StatusPalette.greenContentDark,
    riskMedium: StatusPalette.ochreContentDark,
    riskHigh: StatusPalette.oxideContentDark,
    environmentSyntheticFill: StatusPalette.environmentFillDark,
    environmentSyntheticOnFill: StatusPalette.environmentOnFillDark,
    regionOverlayStroke: StatusPalette.steelContentDark,
    regionOverlayCasing: StatusPalette.regionCasingDark,
    regionSelectedCore: StatusPalette.regionSelectedCore,
    regionSelectedCasing: StatusPalette.regionSelectedCasing,
  );

  /// Interpolates every member, so a theme cross-fade is well defined.
  UiStatusColors lerp(UiStatusColors other, double t) => UiStatusColors(
    cleared: cleared.lerp(other.cleared, t),
    needsReview: needsReview.lerp(other.needsReview, t),
    deferred: deferred.lerp(other.deferred, t),
    processing: processing.lerp(other.processing, t),
    blocked: blocked.lerp(other.blocked, t),
    model: model.lerp(other.model, t),
    human: human.lerp(other.human, t),
    authority: authority.lerp(other.authority, t),
    diffAddedContent: Color.lerp(diffAddedContent, other.diffAddedContent, t)!,
    diffAddedFill: Color.lerp(diffAddedFill, other.diffAddedFill, t)!,
    diffChangedContent: Color.lerp(
      diffChangedContent,
      other.diffChangedContent,
      t,
    )!,
    diffChangedFill: Color.lerp(diffChangedFill, other.diffChangedFill, t)!,
    diffUnchangedContent: Color.lerp(
      diffUnchangedContent,
      other.diffUnchangedContent,
      t,
    )!,
    riskLow: Color.lerp(riskLow, other.riskLow, t)!,
    riskMedium: Color.lerp(riskMedium, other.riskMedium, t)!,
    riskHigh: Color.lerp(riskHigh, other.riskHigh, t)!,
    environmentSyntheticFill: Color.lerp(
      environmentSyntheticFill,
      other.environmentSyntheticFill,
      t,
    )!,
    environmentSyntheticOnFill: Color.lerp(
      environmentSyntheticOnFill,
      other.environmentSyntheticOnFill,
      t,
    )!,
    regionOverlayStroke: Color.lerp(
      regionOverlayStroke,
      other.regionOverlayStroke,
      t,
    )!,
    regionOverlayCasing: Color.lerp(
      regionOverlayCasing,
      other.regionOverlayCasing,
      t,
    )!,
    regionSelectedCore: Color.lerp(
      regionSelectedCore,
      other.regionSelectedCore,
      t,
    )!,
    regionSelectedCasing: Color.lerp(
      regionSelectedCasing,
      other.regionSelectedCasing,
      t,
    )!,
  );
}

/// Every colour role in the product.
@immutable
class UiColor {
  /// Binds every role. Prefer [UiColor.light] and [UiColor.dark].
  const UiColor({
    required this.brightness,
    required this.ground,
    required this.paper,
    required this.matte,
    required this.ink,
    required this.inkSecondary,
    required this.inkTertiary,
    required this.hairline,
    required this.boundary,
    required this.disabledContent,
    required this.disabledOutline,
    required this.disabledFill,
    required this.scrim,
    required this.accent,
    required this.onAccent,
    required this.focusRing,
    required this.status,
  });

  /// Which column of every table in 09 this instance came from.
  final Brightness brightness;

  /// The window background.
  final Color ground;

  /// Solid surface where glass is not warranted.
  final Color paper;

  /// The letterbox behind a photograph.
  final Color matte;

  /// Primary text, glyphs, the filled navigation disc, primary buttons.
  final Color ink;

  /// Supporting text, labels above fields, timestamps.
  final Color inkSecondary;

  /// Units, hints, placeholder text.
  final Color inkTertiary;

  /// Decorative separation. Never a boundary.
  final Color hairline;

  /// Any edge a user must be able to find.
  final Color boundary;

  /// Text and glyphs of a disabled control.
  final Color disabledContent;

  /// Edge of a disabled control.
  final Color disabledOutline;

  /// Behind a disabled control.
  final Color disabledFill;

  /// Behind modal glass.
  final Color scrim;

  /// The mark. Never a fill, never a status, never text.
  final Color accent;

  /// Anything drawn on [accent].
  final Color onAccent;

  /// The keyboard focus ring (09 section 3.6). Monochrome, so it reads as
  /// part of this system and clears 3:1 on every surface and every field.
  final Color focusRing;

  /// The status and evidence triples.
  final UiStatusColors status;

  /// The light column of every table in 09 section 3.
  static const UiColor light = UiColor(
    brightness: Brightness.light,
    ground: GroundPalette.groundLight,
    paper: GroundPalette.paperLight,
    matte: GroundPalette.matteLight,
    ink: GroundPalette.inkLight,
    inkSecondary: GroundPalette.inkSecondaryLight,
    inkTertiary: GroundPalette.inkTertiaryLight,
    hairline: GroundPalette.hairlineLight,
    boundary: GroundPalette.boundaryLight,
    disabledContent: GroundPalette.disabledContentLight,
    disabledOutline: GroundPalette.disabledOutlineLight,
    disabledFill: Color.fromRGBO(
      0x11,
      0x12,
      0x14,
      GroundPalette.disabledFillOpacityLight,
    ),
    scrim: Color.fromRGBO(0, 0, 0, GroundPalette.scrimOpacityLight),
    accent: AccentPalette.accent,
    onAccent: AccentPalette.onAccent,
    focusRing: GroundPalette.inkLight,
    status: UiStatusColors.light,
  );

  /// The dark column of every table in 09 section 3.
  static const UiColor dark = UiColor(
    brightness: Brightness.dark,
    ground: GroundPalette.groundDark,
    paper: GroundPalette.paperDark,
    matte: GroundPalette.matteDark,
    ink: GroundPalette.inkDark,
    inkSecondary: GroundPalette.inkSecondaryDark,
    inkTertiary: GroundPalette.inkTertiaryDark,
    hairline: GroundPalette.hairlineDark,
    boundary: GroundPalette.boundaryDark,
    disabledContent: GroundPalette.disabledContentDark,
    disabledOutline: GroundPalette.disabledOutlineDark,
    disabledFill: Color.fromRGBO(
      0xF2,
      0xF2,
      0xEF,
      GroundPalette.disabledFillOpacityDark,
    ),
    scrim: Color.fromRGBO(0, 0, 0, GroundPalette.scrimOpacityDark),
    accent: AccentPalette.accent,
    onAccent: AccentPalette.onAccent,
    focusRing: GroundPalette.inkDark,
    status: UiStatusColors.dark,
  );

  /// True for the dark column.
  bool get isDark => brightness == Brightness.dark;

  /// Every text role, by the name 09 gives it. The contrast gate walks this.
  Map<String, Color> get textRoles => <String, Color>{
    'ink': ink,
    'ink.secondary': inkSecondary,
    'ink.tertiary': inkTertiary,
  };

  /// Every role held to the 3:1 non-text floor.
  Map<String, Color> get nonTextRoles => <String, Color>{
    'boundary': boundary,
    'disabled.outline': disabledOutline,
    'focus.ring': focusRing,
  };

  /// The three opaque surfaces a role can land on without glass.
  Map<String, Color> get surfaces => <String, Color>{
    'ground': ground,
    'paper': paper,
    'matte': matte,
  };

  /// Opacity of the state layer on hover (10 section 2 clause 6).
  double get hoverOpacity => isDark ? 0.10 : 0.08;

  /// Opacity of the state layer while pressed.
  double get pressedOpacity => isDark ? 0.14 : 0.12;

  /// Opacity of the selection behind the characters a reviewer has
  /// highlighted inside a field (11 section 4).
  double get selectionOpacity => 0.35;

  /// Behind the characters a reviewer has selected inside a field.
  ///
  /// [accent] at [selectionOpacity]. The accent is the product's one
  /// non-status colour, so a selection reads as this system rather than as
  /// the platform's blue, and at this opacity [ink] on the composite clears
  /// 4.5:1 over every opaque surface in both modes, which the composite
  /// contrast gate holds.
  Color get selection => accent.withValues(alpha: selectionOpacity);

  /// The hover or press overlay over any surface.
  ///
  /// 10 section 2 clause 6 names `ink` in light and `paper` in dark. Both
  /// tokens follow the mode, and in dark `paper` is `#17181B`, which is
  /// darker than `ground`: painting it over a dark surface would hide the
  /// control rather than lift it. [ink] is the light member of the pair in
  /// dark mode, so one token gives the effect the clause describes in both:
  /// the layer always moves the surface toward its opposite.
  Color stateLayer(double opacity) => ink.withValues(alpha: opacity);
}
