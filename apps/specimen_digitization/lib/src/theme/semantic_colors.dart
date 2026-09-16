/// Product colour tokens that do not exist in `ColorScheme` at all
/// (09 sections 3.4 and 3.5), as names over `package:specimen_ui`.
///
/// Each product token is a triple: `content` for text, icons and borders,
/// `fill` for the container behind them, and `onFill` for text placed on that
/// container. Every `content` value clears 4.5:1 on every surface in its mode,
/// so a call site never has to know which surface it landed on.
library;

import 'package:flutter/material.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'tokens.dart';

/// One product token: the color triple a component needs to render a state.
typedef TokenTriple = ({Color content, Color fill, Color onFill});

/// A named fill and the color that is legible on it. Used by the contrast test.
typedef FillPair = ({String name, Color fill, Color onFill});

@immutable
class SpecimenColors extends ThemeExtension<SpecimenColors> {
  const SpecimenColors({
    required this.clearedContent,
    required this.clearedFill,
    required this.clearedOnFill,
    required this.needsReviewContent,
    required this.needsReviewFill,
    required this.needsReviewOnFill,
    required this.deferredContent,
    required this.deferredFill,
    required this.deferredOnFill,
    required this.processingContent,
    required this.processingFill,
    required this.processingOnFill,
    required this.blockedContent,
    required this.blockedFill,
    required this.blockedOnFill,
    required this.evidenceModelContent,
    required this.evidenceModelFill,
    required this.evidenceModelOnFill,
    required this.evidenceHumanContent,
    required this.evidenceHumanFill,
    required this.evidenceHumanOnFill,
    required this.evidenceAuthorityContent,
    required this.evidenceAuthorityFill,
    required this.evidenceAuthorityOnFill,
    required this.diffAddedContent,
    required this.diffAddedFill,
    required this.diffChangedContent,
    required this.diffChangedFill,
    required this.diffUnchangedContent,
    required this.regionOverlayStroke,
    required this.regionOverlayCasing,
    required this.regionSelectedCore,
    required this.regionSelectedCasing,
    required this.riskLowContent,
    required this.riskMediumContent,
    required this.riskHighContent,
    required this.environmentSyntheticFill,
    required this.environmentSyntheticOnFill,
    required this.focusRing,
    required this.disabledContent,
    required this.disabledOutline,
    required this.disabledContainer,
  });

  /// Green. A human affirmed it.
  final Color clearedContent;
  final Color clearedFill;
  final Color clearedOnFill;

  /// Ochre. Attention, not failure.
  final Color needsReviewContent;
  final Color needsReviewFill;
  final Color needsReviewOnFill;

  /// Clay. Shelved, not judged.
  final Color deferredContent;
  final Color deferredFill;
  final Color deferredOnFill;

  /// Steel. Never a final queue; always paired with a progress affordance.
  final Color processingContent;
  final Color processingFill;
  final Color processingOnFill;

  /// Oxide. Operational, not evidentiary.
  final Color blockedContent;
  final Color blockedFill;
  final Color blockedOnFill;

  /// Slate. A model reading is an observation, not a decision.
  final Color evidenceModelContent;
  final Color evidenceModelFill;
  final Color evidenceModelOnFill;

  /// Green. The only thing in this product allowed to look affirmative.
  final Color evidenceHumanContent;
  final Color evidenceHumanFill;
  final Color evidenceHumanOnFill;

  /// Teal. An external reference file.
  final Color evidenceAuthorityContent;
  final Color evidenceAuthorityFill;
  final Color evidenceAuthorityOnFill;

  /// Marker `+` plus a 3dp leading bar.
  final Color diffAddedContent;

  /// Highlight behind body text. Tuned against `onSurface`, not an on-fill.
  final Color diffAddedFill;

  /// Marker `~` plus an underline.
  final Color diffChangedContent;
  final Color diffChangedFill;

  /// No fill, no marker. Equals `onSurfaceVariant`.
  final Color diffUnchangedContent;

  /// 2dp stroke over a photograph, with [regionOverlayCasing] on the outside.
  final Color regionOverlayStroke;
  final Color regionOverlayCasing;

  /// Selection over the image. Identical in both modes, because it is
  /// transient and lives only over an arbitrary photograph.
  final Color regionSelectedCore;
  final Color regionSelectedCasing;

  final Color riskLowContent;
  final Color riskMediumContent;
  final Color riskHighContent;

  /// Full-bleed band, never dismissible.
  final Color environmentSyntheticFill;
  final Color environmentSyntheticOnFill;

  /// Reserved. Never used for status, and never for more than one element.
  final Color focusRing;

  /// A disabled control carries information, so it stays legible at a named
  /// neutral rather than Material's 38% (design system, section 3.6).
  final Color disabledContent;

  /// The border of a disabled outlined control. A step quieter than
  /// [disabledContent] and still over the 3:1 non-text floor, so the control
  /// reads as disabled without the boundary disappearing.
  final Color disabledOutline;

  final Color disabledContainer;

  static final SpecimenColors light = SpecimenColors(
    clearedContent: ProductPalette.greenContentLight,
    clearedFill: ProductPalette.greenFillLight,
    clearedOnFill: ProductPalette.greenOnFillLight,
    needsReviewContent: ProductPalette.ochreContentLight,
    needsReviewFill: ProductPalette.ochreFillLight,
    needsReviewOnFill: ProductPalette.ochreOnFillLight,
    deferredContent: ProductPalette.clayContentLight,
    deferredFill: ProductPalette.clayFillLight,
    deferredOnFill: ProductPalette.clayOnFillLight,
    processingContent: ProductPalette.steelContentLight,
    processingFill: ProductPalette.steelFillLight,
    processingOnFill: ProductPalette.steelOnFillLight,
    blockedContent: ProductPalette.oxideContentLight,
    blockedFill: ProductPalette.oxideFillLight,
    blockedOnFill: ProductPalette.oxideOnFillLight,
    evidenceModelContent: ProductPalette.slateContentLight,
    evidenceModelFill: ProductPalette.slateFillLight,
    evidenceModelOnFill: ProductPalette.slateOnFillLight,
    evidenceHumanContent: ProductPalette.greenContentLight,
    evidenceHumanFill: ProductPalette.greenFillLight,
    evidenceHumanOnFill: ProductPalette.greenOnFillLight,
    evidenceAuthorityContent: ProductPalette.tealContentLight,
    evidenceAuthorityFill: ProductPalette.tealFillLight,
    evidenceAuthorityOnFill: ProductPalette.tealOnFillLight,
    diffAddedContent: ProductPalette.greenContentLight,
    diffAddedFill: ProductPalette.diffAddedFillLight,
    diffChangedContent: ProductPalette.ochreContentLight,
    diffChangedFill: ProductPalette.diffChangedFillLight,
    diffUnchangedContent: GroundPalette.inkSecondaryLight,
    regionOverlayStroke: ProductPalette.steelContentLight,
    regionOverlayCasing: ProductPalette.regionCasingLight,
    regionSelectedCore: ProductPalette.regionSelectedCore,
    regionSelectedCasing: ProductPalette.regionSelectedCasing,
    riskLowContent: ProductPalette.greenContentLight,
    riskMediumContent: ProductPalette.ochreContentLight,
    riskHighContent: ProductPalette.oxideContentLight,
    environmentSyntheticFill: ProductPalette.environmentFillLight,
    environmentSyntheticOnFill: ProductPalette.environmentOnFillLight,
    focusRing: ProductPalette.focusRingLight,
    disabledContent: ProductPalette.disabledContentLight,
    disabledOutline: ProductPalette.disabledOutlineLight,
    disabledContainer: UiColor.light.disabledFill,
  );

  static final SpecimenColors dark = SpecimenColors(
    clearedContent: ProductPalette.greenContentDark,
    clearedFill: ProductPalette.greenFillDark,
    clearedOnFill: ProductPalette.greenOnFillDark,
    needsReviewContent: ProductPalette.ochreContentDark,
    needsReviewFill: ProductPalette.ochreFillDark,
    needsReviewOnFill: ProductPalette.ochreOnFillDark,
    deferredContent: ProductPalette.clayContentDark,
    deferredFill: ProductPalette.clayFillDark,
    deferredOnFill: ProductPalette.clayOnFillDark,
    processingContent: ProductPalette.steelContentDark,
    processingFill: ProductPalette.steelFillDark,
    processingOnFill: ProductPalette.steelOnFillDark,
    blockedContent: ProductPalette.oxideContentDark,
    blockedFill: ProductPalette.oxideFillDark,
    blockedOnFill: ProductPalette.oxideOnFillDark,
    evidenceModelContent: ProductPalette.slateContentDark,
    evidenceModelFill: ProductPalette.slateFillDark,
    evidenceModelOnFill: ProductPalette.slateOnFillDark,
    evidenceHumanContent: ProductPalette.greenContentDark,
    evidenceHumanFill: ProductPalette.greenFillDark,
    evidenceHumanOnFill: ProductPalette.greenOnFillDark,
    evidenceAuthorityContent: ProductPalette.tealContentDark,
    evidenceAuthorityFill: ProductPalette.tealFillDark,
    evidenceAuthorityOnFill: ProductPalette.tealOnFillDark,
    diffAddedContent: ProductPalette.greenContentDark,
    diffAddedFill: ProductPalette.diffAddedFillDark,
    diffChangedContent: ProductPalette.ochreContentDark,
    diffChangedFill: ProductPalette.diffChangedFillDark,
    diffUnchangedContent: GroundPalette.inkSecondaryDark,
    regionOverlayStroke: ProductPalette.steelContentDark,
    regionOverlayCasing: ProductPalette.regionCasingDark,
    regionSelectedCore: ProductPalette.regionSelectedCore,
    regionSelectedCasing: ProductPalette.regionSelectedCasing,
    riskLowContent: ProductPalette.greenContentDark,
    riskMediumContent: ProductPalette.ochreContentDark,
    riskHighContent: ProductPalette.oxideContentDark,
    environmentSyntheticFill: ProductPalette.environmentFillDark,
    environmentSyntheticOnFill: ProductPalette.environmentOnFillDark,
    focusRing: ProductPalette.focusRingDark,
    disabledContent: ProductPalette.disabledContentDark,
    disabledOutline: ProductPalette.disabledOutlineDark,
    disabledContainer: UiColor.dark.disabledFill,
  );

  /// The state triples, by token name. A component reads a whole triple so it
  /// cannot mix the content color of one status with the fill of another.
  Map<String, TokenTriple> get triples => <String, TokenTriple>{
    'disposition.cleared': (
      content: clearedContent,
      fill: clearedFill,
      onFill: clearedOnFill,
    ),
    'disposition.needsReview': (
      content: needsReviewContent,
      fill: needsReviewFill,
      onFill: needsReviewOnFill,
    ),
    'disposition.deferred': (
      content: deferredContent,
      fill: deferredFill,
      onFill: deferredOnFill,
    ),
    'state.processing': (
      content: processingContent,
      fill: processingFill,
      onFill: processingOnFill,
    ),
    'state.blocked': (
      content: blockedContent,
      fill: blockedFill,
      onFill: blockedOnFill,
    ),
    'evidence.model': (
      content: evidenceModelContent,
      fill: evidenceModelFill,
      onFill: evidenceModelOnFill,
    ),
    'evidence.human': (
      content: evidenceHumanContent,
      fill: evidenceHumanFill,
      onFill: evidenceHumanOnFill,
    ),
    'evidence.authority': (
      content: evidenceAuthorityContent,
      fill: evidenceAuthorityFill,
      onFill: evidenceAuthorityOnFill,
    ),
  };

  /// Every product color that can carry text or an icon on a surface. The
  /// contrast test walks this against all eight surface roles.
  Map<String, Color> get allContentColors => <String, Color>{
    for (final entry in triples.entries) entry.key: entry.value.content,
    'diff.added': diffAddedContent,
    'diff.changed': diffChangedContent,
    'diff.unchanged': diffUnchangedContent,
    'risk.low': riskLowContent,
    'risk.medium': riskMediumContent,
    'risk.high': riskHighContent,
  };

  /// Every fill and the color that has to stay legible on it.
  List<FillPair> get fillPairs => <FillPair>[
    for (final entry in triples.entries)
      (name: entry.key, fill: entry.value.fill, onFill: entry.value.onFill),
    (
      name: 'environment.synthetic',
      fill: environmentSyntheticFill,
      onFill: environmentSyntheticOnFill,
    ),
    (
      name: 'region.selected',
      fill: regionSelectedCasing,
      onFill: regionSelectedCore,
    ),
  ];

  /// The disabled-state colors, by token name.
  ///
  /// WCAG 2.2 exempts inactive components from both 1.4.3 and 1.4.11, but a
  /// disabled control in this product carries the reason the server forbids
  /// the decision, so the contrast test holds both of these to the 3:1
  /// non-text floor on every surface (design system, section 3.6).
  Map<String, Color> get disabledColors => <String, Color>{
    'disabled.content': disabledContent,
    'disabled.outline': disabledOutline,
  };

  /// Diff fills carry body text in `onSurface`, not in an on-fill color, so
  /// they are checked against `onSurface` instead of against [fillPairs].
  List<FillPair> diffFillPairs(Color onSurface) => <FillPair>[
    (name: 'diff.added fill', fill: diffAddedFill, onFill: onSurface),
    (name: 'diff.changed fill', fill: diffChangedFill, onFill: onSurface),
  ];

  @override
  SpecimenColors copyWith({
    Color? clearedContent,
    Color? clearedFill,
    Color? clearedOnFill,
    Color? needsReviewContent,
    Color? needsReviewFill,
    Color? needsReviewOnFill,
    Color? deferredContent,
    Color? deferredFill,
    Color? deferredOnFill,
    Color? processingContent,
    Color? processingFill,
    Color? processingOnFill,
    Color? blockedContent,
    Color? blockedFill,
    Color? blockedOnFill,
    Color? evidenceModelContent,
    Color? evidenceModelFill,
    Color? evidenceModelOnFill,
    Color? evidenceHumanContent,
    Color? evidenceHumanFill,
    Color? evidenceHumanOnFill,
    Color? evidenceAuthorityContent,
    Color? evidenceAuthorityFill,
    Color? evidenceAuthorityOnFill,
    Color? diffAddedContent,
    Color? diffAddedFill,
    Color? diffChangedContent,
    Color? diffChangedFill,
    Color? diffUnchangedContent,
    Color? regionOverlayStroke,
    Color? regionOverlayCasing,
    Color? regionSelectedCore,
    Color? regionSelectedCasing,
    Color? riskLowContent,
    Color? riskMediumContent,
    Color? riskHighContent,
    Color? environmentSyntheticFill,
    Color? environmentSyntheticOnFill,
    Color? focusRing,
    Color? disabledContent,
    Color? disabledOutline,
    Color? disabledContainer,
  }) => SpecimenColors(
    clearedContent: clearedContent ?? this.clearedContent,
    clearedFill: clearedFill ?? this.clearedFill,
    clearedOnFill: clearedOnFill ?? this.clearedOnFill,
    needsReviewContent: needsReviewContent ?? this.needsReviewContent,
    needsReviewFill: needsReviewFill ?? this.needsReviewFill,
    needsReviewOnFill: needsReviewOnFill ?? this.needsReviewOnFill,
    deferredContent: deferredContent ?? this.deferredContent,
    deferredFill: deferredFill ?? this.deferredFill,
    deferredOnFill: deferredOnFill ?? this.deferredOnFill,
    processingContent: processingContent ?? this.processingContent,
    processingFill: processingFill ?? this.processingFill,
    processingOnFill: processingOnFill ?? this.processingOnFill,
    blockedContent: blockedContent ?? this.blockedContent,
    blockedFill: blockedFill ?? this.blockedFill,
    blockedOnFill: blockedOnFill ?? this.blockedOnFill,
    evidenceModelContent: evidenceModelContent ?? this.evidenceModelContent,
    evidenceModelFill: evidenceModelFill ?? this.evidenceModelFill,
    evidenceModelOnFill: evidenceModelOnFill ?? this.evidenceModelOnFill,
    evidenceHumanContent: evidenceHumanContent ?? this.evidenceHumanContent,
    evidenceHumanFill: evidenceHumanFill ?? this.evidenceHumanFill,
    evidenceHumanOnFill: evidenceHumanOnFill ?? this.evidenceHumanOnFill,
    evidenceAuthorityContent:
        evidenceAuthorityContent ?? this.evidenceAuthorityContent,
    evidenceAuthorityFill: evidenceAuthorityFill ?? this.evidenceAuthorityFill,
    evidenceAuthorityOnFill:
        evidenceAuthorityOnFill ?? this.evidenceAuthorityOnFill,
    diffAddedContent: diffAddedContent ?? this.diffAddedContent,
    diffAddedFill: diffAddedFill ?? this.diffAddedFill,
    diffChangedContent: diffChangedContent ?? this.diffChangedContent,
    diffChangedFill: diffChangedFill ?? this.diffChangedFill,
    diffUnchangedContent: diffUnchangedContent ?? this.diffUnchangedContent,
    regionOverlayStroke: regionOverlayStroke ?? this.regionOverlayStroke,
    regionOverlayCasing: regionOverlayCasing ?? this.regionOverlayCasing,
    regionSelectedCore: regionSelectedCore ?? this.regionSelectedCore,
    regionSelectedCasing: regionSelectedCasing ?? this.regionSelectedCasing,
    riskLowContent: riskLowContent ?? this.riskLowContent,
    riskMediumContent: riskMediumContent ?? this.riskMediumContent,
    riskHighContent: riskHighContent ?? this.riskHighContent,
    environmentSyntheticFill:
        environmentSyntheticFill ?? this.environmentSyntheticFill,
    environmentSyntheticOnFill:
        environmentSyntheticOnFill ?? this.environmentSyntheticOnFill,
    focusRing: focusRing ?? this.focusRing,
    disabledContent: disabledContent ?? this.disabledContent,
    disabledOutline: disabledOutline ?? this.disabledOutline,
    disabledContainer: disabledContainer ?? this.disabledContainer,
  );

  @override
  SpecimenColors lerp(SpecimenColors? other, double t) {
    if (other == null) return this;
    Color mix(Color a, Color b) => Color.lerp(a, b, t)!;
    return SpecimenColors(
      clearedContent: mix(clearedContent, other.clearedContent),
      clearedFill: mix(clearedFill, other.clearedFill),
      clearedOnFill: mix(clearedOnFill, other.clearedOnFill),
      needsReviewContent: mix(needsReviewContent, other.needsReviewContent),
      needsReviewFill: mix(needsReviewFill, other.needsReviewFill),
      needsReviewOnFill: mix(needsReviewOnFill, other.needsReviewOnFill),
      deferredContent: mix(deferredContent, other.deferredContent),
      deferredFill: mix(deferredFill, other.deferredFill),
      deferredOnFill: mix(deferredOnFill, other.deferredOnFill),
      processingContent: mix(processingContent, other.processingContent),
      processingFill: mix(processingFill, other.processingFill),
      processingOnFill: mix(processingOnFill, other.processingOnFill),
      blockedContent: mix(blockedContent, other.blockedContent),
      blockedFill: mix(blockedFill, other.blockedFill),
      blockedOnFill: mix(blockedOnFill, other.blockedOnFill),
      evidenceModelContent: mix(
        evidenceModelContent,
        other.evidenceModelContent,
      ),
      evidenceModelFill: mix(evidenceModelFill, other.evidenceModelFill),
      evidenceModelOnFill: mix(evidenceModelOnFill, other.evidenceModelOnFill),
      evidenceHumanContent: mix(
        evidenceHumanContent,
        other.evidenceHumanContent,
      ),
      evidenceHumanFill: mix(evidenceHumanFill, other.evidenceHumanFill),
      evidenceHumanOnFill: mix(evidenceHumanOnFill, other.evidenceHumanOnFill),
      evidenceAuthorityContent: mix(
        evidenceAuthorityContent,
        other.evidenceAuthorityContent,
      ),
      evidenceAuthorityFill: mix(
        evidenceAuthorityFill,
        other.evidenceAuthorityFill,
      ),
      evidenceAuthorityOnFill: mix(
        evidenceAuthorityOnFill,
        other.evidenceAuthorityOnFill,
      ),
      diffAddedContent: mix(diffAddedContent, other.diffAddedContent),
      diffAddedFill: mix(diffAddedFill, other.diffAddedFill),
      diffChangedContent: mix(diffChangedContent, other.diffChangedContent),
      diffChangedFill: mix(diffChangedFill, other.diffChangedFill),
      diffUnchangedContent: mix(
        diffUnchangedContent,
        other.diffUnchangedContent,
      ),
      regionOverlayStroke: mix(regionOverlayStroke, other.regionOverlayStroke),
      regionOverlayCasing: mix(regionOverlayCasing, other.regionOverlayCasing),
      regionSelectedCore: mix(regionSelectedCore, other.regionSelectedCore),
      regionSelectedCasing: mix(
        regionSelectedCasing,
        other.regionSelectedCasing,
      ),
      riskLowContent: mix(riskLowContent, other.riskLowContent),
      riskMediumContent: mix(riskMediumContent, other.riskMediumContent),
      riskHighContent: mix(riskHighContent, other.riskHighContent),
      environmentSyntheticFill: mix(
        environmentSyntheticFill,
        other.environmentSyntheticFill,
      ),
      environmentSyntheticOnFill: mix(
        environmentSyntheticOnFill,
        other.environmentSyntheticOnFill,
      ),
      focusRing: mix(focusRing, other.focusRing),
      disabledContent: mix(disabledContent, other.disabledContent),
      disabledOutline: mix(disabledOutline, other.disabledOutline),
      disabledContainer: mix(disabledContainer, other.disabledContainer),
    );
  }
}
