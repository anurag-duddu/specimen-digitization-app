/// The raw design primitives, as names over `package:specimen_ui`.
///
/// Every value here now comes from the design system package. The file stays
/// because screens and tests across the application reach for these names, and
/// wave 0 changes the values without changing a single call site. A later wave
/// deletes it as its consumers move to `context.ui`.
///
/// It no longer holds a `Color(0x...)` literal: the one file allowed to is
/// `packages/specimen_ui/lib/src/foundation/palette.dart` (gate
/// `no_color_literals`).
library;

import 'dart:ui' show Color;

import 'package:specimen_ui/specimen_ui.dart';

/// Values that express a policy of the system rather than a colour in it.
abstract final class ThemePolicy {
  /// Fully transparent. M3 blends `surfaceTint` into an elevated surface,
  /// which puts a cast on any panel adjacent to a specimen photograph, so the
  /// tint is switched off everywhere (09 section 3.1).
  static const Color noSurfaceTint = GroundPalette.transparent;
}

/// The seven hue primitives that carry every status token, plus the fixed
/// colours that do not follow a primitive.
///
/// Carried over unchanged in value by 09 section 3.5.
abstract final class ProductPalette {
  /// Green content, light. A human affirmed it.
  static const Color greenContentLight = StatusPalette.greenContentLight;

  /// Green fill, light.
  static const Color greenFillLight = StatusPalette.greenFillLight;

  /// Text on the green fill, light.
  static const Color greenOnFillLight = StatusPalette.greenOnFillLight;

  /// Green content, dark.
  static const Color greenContentDark = StatusPalette.greenContentDark;

  /// Green fill, dark.
  static const Color greenFillDark = StatusPalette.greenFillDark;

  /// Text on the green fill, dark.
  static const Color greenOnFillDark = StatusPalette.greenOnFillDark;

  /// Steel content, light. A machine produced it.
  static const Color steelContentLight = StatusPalette.steelContentLight;

  /// Steel fill, light.
  static const Color steelFillLight = StatusPalette.steelFillLight;

  /// Text on the steel fill, light.
  static const Color steelOnFillLight = StatusPalette.steelOnFillLight;

  /// Steel content, dark.
  static const Color steelContentDark = StatusPalette.steelContentDark;

  /// Steel fill, dark.
  static const Color steelFillDark = StatusPalette.steelFillDark;

  /// Text on the steel fill, dark.
  static const Color steelOnFillDark = StatusPalette.steelOnFillDark;

  /// Teal content, light. An external authority.
  static const Color tealContentLight = StatusPalette.tealContentLight;

  /// Teal fill, light.
  static const Color tealFillLight = StatusPalette.tealFillLight;

  /// Text on the teal fill, light.
  static const Color tealOnFillLight = StatusPalette.tealOnFillLight;

  /// Teal content, dark.
  static const Color tealContentDark = StatusPalette.tealContentDark;

  /// Teal fill, dark.
  static const Color tealFillDark = StatusPalette.tealFillDark;

  /// Text on the teal fill, dark.
  static const Color tealOnFillDark = StatusPalette.tealOnFillDark;

  /// Ochre content, light. Attention, not failure.
  static const Color ochreContentLight = StatusPalette.ochreContentLight;

  /// Ochre fill, light.
  static const Color ochreFillLight = StatusPalette.ochreFillLight;

  /// Text on the ochre fill, light.
  static const Color ochreOnFillLight = StatusPalette.ochreOnFillLight;

  /// Ochre content, dark.
  static const Color ochreContentDark = StatusPalette.ochreContentDark;

  /// Ochre fill, dark.
  static const Color ochreFillDark = StatusPalette.ochreFillDark;

  /// Text on the ochre fill, dark.
  static const Color ochreOnFillDark = StatusPalette.ochreOnFillDark;

  /// Oxide content, light. A stop.
  static const Color oxideContentLight = StatusPalette.oxideContentLight;

  /// Oxide fill, light.
  static const Color oxideFillLight = StatusPalette.oxideFillLight;

  /// Text on the oxide fill, light.
  static const Color oxideOnFillLight = StatusPalette.oxideOnFillLight;

  /// Oxide content, dark.
  static const Color oxideContentDark = StatusPalette.oxideContentDark;

  /// Oxide fill, dark.
  static const Color oxideFillDark = StatusPalette.oxideFillDark;

  /// Text on the oxide fill, dark.
  static const Color oxideOnFillDark = StatusPalette.oxideOnFillDark;

  /// Slate content, light. An observation, not a decision.
  static const Color slateContentLight = StatusPalette.slateContentLight;

  /// Slate fill, light.
  static const Color slateFillLight = StatusPalette.slateFillLight;

  /// Text on the slate fill, light.
  static const Color slateOnFillLight = StatusPalette.slateOnFillLight;

  /// Slate content, dark.
  static const Color slateContentDark = StatusPalette.slateContentDark;

  /// Slate fill, dark.
  static const Color slateFillDark = StatusPalette.slateFillDark;

  /// Text on the slate fill, dark.
  static const Color slateOnFillDark = StatusPalette.slateOnFillDark;

  /// Clay content, light. Shelved, not judged.
  static const Color clayContentLight = StatusPalette.clayContentLight;

  /// Clay fill, light.
  static const Color clayFillLight = StatusPalette.clayFillLight;

  /// Text on the clay fill, light.
  static const Color clayOnFillLight = StatusPalette.clayOnFillLight;

  /// Clay content, dark.
  static const Color clayContentDark = StatusPalette.clayContentDark;

  /// Clay fill, dark.
  static const Color clayFillDark = StatusPalette.clayFillDark;

  /// Text on the clay fill, dark.
  static const Color clayOnFillDark = StatusPalette.clayOnFillDark;

  /// The highlight behind an added diff span, light.
  static const Color diffAddedFillLight = StatusPalette.diffAddedFillLight;

  /// The highlight behind an added diff span, dark.
  static const Color diffAddedFillDark = StatusPalette.diffAddedFillDark;

  /// The highlight behind a changed diff span, light.
  static const Color diffChangedFillLight = StatusPalette.diffChangedFillLight;

  /// The highlight behind a changed diff span, dark.
  static const Color diffChangedFillDark = StatusPalette.diffChangedFillDark;

  /// The casing that keeps a region stroke visible, light.
  static const Color regionCasingLight = StatusPalette.regionCasingLight;

  /// The casing that keeps a region stroke visible, dark.
  static const Color regionCasingDark = StatusPalette.regionCasingDark;

  /// The selected region's core. The same in both modes.
  static const Color regionSelectedCore = StatusPalette.regionSelectedCore;

  /// The selected region's casing.
  static const Color regionSelectedCasing = StatusPalette.regionSelectedCasing;

  /// The synthetic environment band, light.
  static const Color environmentFillLight = StatusPalette.environmentFillLight;

  /// Text on the synthetic environment band, light.
  static const Color environmentOnFillLight =
      StatusPalette.environmentOnFillLight;

  /// The synthetic environment band, dark.
  static const Color environmentFillDark = StatusPalette.environmentFillDark;

  /// Text on the synthetic environment band, dark.
  static const Color environmentOnFillDark =
      StatusPalette.environmentOnFillDark;

  /// The focus ring, light. Monochrome since 09 section 3.6 retired the blue.
  static const Color focusRingLight = GroundPalette.inkLight;

  /// The focus ring, dark.
  static const Color focusRingDark = GroundPalette.inkDark;

  /// A disabled control's text, light.
  static const Color disabledContentLight =
      GroundPalette.disabledContentLight;

  /// A disabled control's text, dark.
  static const Color disabledContentDark = GroundPalette.disabledContentDark;

  /// A disabled control's edge, light.
  static const Color disabledOutlineLight =
      GroundPalette.disabledOutlineLight;

  /// A disabled control's edge, dark.
  static const Color disabledOutlineDark = GroundPalette.disabledOutlineDark;

  /// Opacity of the fill behind a disabled control.
  static const double disabledContainerOpacity =
      GroundPalette.disabledFillOpacityLight;
}

/// The 4 px base grid (09 section 6).
abstract final class SpaceScale {
  /// Flush.
  static final double space0 = UiSpace.standard.s0;

  /// Glyph to label inside a chip; gap between stacked metadata lines.
  static final double space1 = UiSpace.standard.s1;

  /// Gap between related controls.
  static final double space2 = UiSpace.standard.s2;

  /// Internal padding of a chip or a dense list row.
  static final double space3 = UiSpace.standard.s3;

  /// Default padding inside a pane; compact-window screen gutter.
  static final double space4 = UiSpace.standard.s4;

  /// Optical corrections, and the touch-density gutter.
  static final double space5 = UiSpace.standard.s5;

  /// Gap between panes; medium and expanded screen gutter.
  static final double space6 = UiSpace.standard.s6;

  /// Gap between major sections in a pane.
  static final double space8 = UiSpace.standard.s8;

  /// Space above a screen title.
  static final double space10 = UiSpace.standard.s10;

  /// Empty-state vertical rhythm.
  static final double space12 = UiSpace.standard.s12;

  /// Maximum. Above this, the layout is wrong.
  static final double space16 = UiSpace.standard.s16;
}

/// Fixed sizes (09 section 6; 03 section 5.2).
abstract final class SizeScale {
  /// Glyph on a `body` baseline.
  static final double iconInline = UiSpace.standard.iconInline;

  /// Glyph in an action, a row or the navigation.
  static final double iconAction = UiSpace.standard.iconAction;

  /// Glyph in an empty state.
  static final double iconDisplay = UiSpace.standard.iconDisplay;

  /// Hit box for every interactive element, on every platform, always.
  static const double targetMin = UiDensity.hitBox;

  /// Smallest a control may look.
  static final double targetVisualMin = UiSpace.standard.targetVisualMin;

  /// Row height on a compact window.
  static final double rowCompact = UiSpace.standard.rowCompact;

  /// Row height on a medium window.
  static final double rowMedium = UiSpace.standard.rowMedium;

  /// Row height on an expanded window.
  static final double rowExpanded = UiSpace.standard.rowExpanded;

  /// The top bar.
  static final double appBar = UiSpace.standard.topBar;

  /// The navigation rail.
  static final double rail = UiSpace.standard.rail;

  /// Minimum width for the workbench content pane before it stacks.
  static final double paneDetailMin = UiSpace.standard.paneDetailMin;

  /// Maximum measure for prose.
  static final double readingMax = UiSpace.standard.readingMax;
}

/// Corner radii and stroke widths (09 section 5).
///
/// The v1 six-step ramp is gone. These names map onto the v2 tokens so the
/// screens that still hold a radius keep compiling; each one now draws the
/// superellipse radius its role calls for.
abstract final class ShapeScale {
  /// Diff spans, table cells, region overlays, the environment banner.
  static final double radiusNone = UiShape.standard.none;

  /// Badges and swatches. Maps onto `radius.inner`.
  static final double radiusXs = UiShape.standard.inner;

  /// Nested elements. `radius.inner`.
  static final double radiusSm = UiShape.standard.inner;

  /// Fields and selects. `radius.field`.
  static final double radiusMd = UiShape.standard.field;

  /// Tiles, cards and popovers. `radius.tile`.
  static final double radiusLg = UiShape.standard.tile;

  /// Sheets and dialogs. `radius.sheet`.
  static final double radiusXl = UiShape.standard.sheet;

  /// Effectively full. Prefer a `StadiumBorder` where the API takes a shape.
  static const double radiusFull = 999;

  /// 1 dp. Decorative separation only.
  static final double strokeHairline = UiShape.standard.stroke.hairline;

  /// 1 dp. Any container the user must be able to find.
  static final double strokeBoundary = UiShape.standard.stroke.boundary;

  /// 2 dp. Selected chip, selected region.
  static final double strokeEmphasis = UiShape.standard.stroke.emphasis;

  /// 3 dp. Selected row leading bar, diff addition bar.
  static final double strokeStrong = UiShape.standard.stroke.bar;

  /// The focus ring's stroke.
  static final double focusRingStroke = UiShape.standard.stroke.focus;

  /// The gap between a control and its focus ring.
  static final double focusRingGap = UiShape.standard.stroke.focusGap;

  /// The ring's radius is the component's plus this.
  static final double focusRingRadiusOffset =
      UiShape.standard.stroke.focusRadiusOffset;
}

/// The type scale (09 section 4.2), in logical pixels.
///
/// These are the sizes the Material bridge in 09 section 4.3 puts in each
/// `TextTheme` slot, so a test that reads `textTheme.bodyLarge?.fontSize`
/// still has a name to compare against.
abstract final class TypeScale {
  /// `display.large`.
  static const double displayLargeSize = 48;

  /// `display.medium`.
  static const double displayMediumSize = 36;

  /// `headline`.
  static const double displaySmallSize = 28;

  /// `headline`.
  static const double headlineLargeSize = 28;

  /// `title.large`.
  static const double headlineMediumSize = 22;

  /// `title`.
  static const double headlineSmallSize = 17;

  /// `title.large`.
  static const double titleLargeSize = 22;

  /// `title`.
  static const double titleMediumSize = 17;

  /// `label`.
  static const double titleSmallSize = 13;

  /// `body.large`.
  static const double bodyLargeSize = 17;

  /// `body`.
  static const double bodyMediumSize = 15;

  /// `body.small`.
  static const double bodySmallSize = 13;

  /// `label`.
  static const double labelLargeSize = 13;

  /// `label`.
  static const double labelMediumSize = 13;

  /// `label.small`.
  static const double labelSmallSize = 11;

  /// `mono.literal`.
  static const double monoLiteralSize = 15;

  /// `mono.literalDense`.
  static const double monoLiteralDenseSize = 13;

  /// `mono.identifier`.
  static const double monoIdentifierSize = 13;

  /// `mono.digest`.
  static const double monoDigestSize = 12;

  /// `mono.code`.
  static const double monoCodeSize = 13;
}
