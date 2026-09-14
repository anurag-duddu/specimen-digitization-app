/// Spacing, sizing and shape as theme extensions
/// (design system, sections 5.1, 5.2, 5.3 and 5.9).
///
/// These values are identical in light and dark, so their `lerp` is a discrete
/// switch: a half-way spacing is not a value this system has.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

/// The 4px base grid.
@immutable
class SpecimenSpacing extends ThemeExtension<SpecimenSpacing> {
  const SpecimenSpacing();

  /// Flush.
  double get space0 => SpaceScale.space0;

  /// Icon to label inside a chip; gap between stacked metadata lines.
  double get space1 => SpaceScale.space1;

  /// Gap between related controls; chip to chip.
  double get space2 => SpaceScale.space2;

  /// Internal padding of a chip or a dense list row.
  double get space3 => SpaceScale.space3;

  /// Default padding inside a card; compact-window screen gutter.
  double get space4 => SpaceScale.space4;

  /// Reserved for optical corrections only.
  double get space5 => SpaceScale.space5;

  /// Gap between cards; medium and expanded screen gutter.
  double get space6 => SpaceScale.space6;

  /// Gap between major sections in a pane.
  double get space8 => SpaceScale.space8;

  /// Space above a screen title.
  double get space10 => SpaceScale.space10;

  /// Empty-state vertical rhythm.
  double get space12 => SpaceScale.space12;

  /// Maximum. Above this, the layout is wrong.
  double get space16 => SpaceScale.space16;

  @override
  SpecimenSpacing copyWith() => const SpecimenSpacing();

  @override
  SpecimenSpacing lerp(SpecimenSpacing? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}

/// Fixed sizes: icons, hit boxes, row heights, pane minimums.
@immutable
class SpecimenSizing extends ThemeExtension<SpecimenSizing> {
  const SpecimenSizing();

  /// Icons sitting on a `bodyMedium` or `labelMedium` baseline.
  double get iconInline => SizeScale.iconInline;

  /// Icon buttons and navigation destinations.
  double get iconAction => SizeScale.iconAction;

  /// Empty states only.
  double get iconDisplay => SizeScale.iconDisplay;

  /// Hit box for every interactive element, on every platform, always.
  /// Density changes visual size and padding; it never shrinks this.
  double get targetMin => SizeScale.targetMin;

  /// Smallest a control may look. Below this, pad the hit box transparently.
  double get targetVisualMin => SizeScale.targetVisualMin;

  double get rowCompact => SizeScale.rowCompact;
  double get rowMedium => SizeScale.rowMedium;
  double get rowExpanded => SizeScale.rowExpanded;
  double get appBar => SizeScale.appBar;
  double get rail => SizeScale.rail;

  /// Minimum width for the workbench content pane before it stacks.
  double get paneDetailMin => SizeScale.paneDetailMin;

  /// Maximum measure for prose.
  double get readingMax => SizeScale.readingMax;

  @override
  SpecimenSizing copyWith() => const SpecimenSizing();

  @override
  SpecimenSizing lerp(SpecimenSizing? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}

/// Corner radii and stroke widths.
@immutable
class SpecimenShape extends ThemeExtension<SpecimenShape> {
  const SpecimenShape();

  /// Table cells, diff spans, region overlays, dividers, the image matte.
  double get radiusNone => ShapeScale.radiusNone;

  /// Chips, badges, input fields, tags, key caps.
  double get radiusXs => ShapeScale.radiusXs;

  /// Cards, queue rows, menus, tooltips, buttons.
  double get radiusSm => ShapeScale.radiusSm;

  /// Sheets, dialogs, panels.
  double get radiusMd => ShapeScale.radiusMd;

  /// Top corners of a bottom sheet.
  double get radiusLg => ShapeScale.radiusLg;

  /// Avatars and the progress ring cap only.
  double get radiusFull => ShapeScale.radiusFull;

  /// 1dp `outlineVariant`. Decorative separation only.
  double get strokeHairline => ShapeScale.strokeHairline;

  /// 1dp `outline`. Any container the user must be able to find.
  double get strokeBoundary => ShapeScale.strokeBoundary;

  /// 2dp. Selected chip, region overlay, focus ring.
  double get strokeEmphasis => ShapeScale.strokeEmphasis;

  /// 3dp. Selected region, selected row leading bar.
  double get strokeStrong => ShapeScale.strokeStrong;

  double get focusRingStroke => ShapeScale.focusRingStroke;
  double get focusRingGap => ShapeScale.focusRingGap;
  double get focusRingRadiusOffset => ShapeScale.focusRingRadiusOffset;

  /// A nested container's radius is its parent's radius minus its own inset
  /// padding, floored at zero. M3's optical roundness formula, applied as a
  /// constraint rather than a suggestion (design system, section 5.3).
  double nested(double parentRadius, double padding) {
    final double inner = parentRadius - padding;
    return inner < ShapeScale.radiusNone ? ShapeScale.radiusNone : inner;
  }

  @override
  SpecimenShape copyWith() => const SpecimenShape();

  @override
  SpecimenShape lerp(SpecimenShape? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}
