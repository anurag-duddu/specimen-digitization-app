/// Corner radii and stroke widths (09 section 5).
///
/// The values only. The shapes built from them are `Squircle`, in the
/// primitives layer, because a shape is geometry and a token is not.
library;

import 'package:flutter/widgets.dart';

/// The four stroke widths, plus the focus ring geometry.
@immutable
class UiStroke {
  /// Binds the stroke widths.
  const UiStroke();

  /// 1 dp. Decorative separation only.
  double get hairline => 1;

  /// 1 dp. Any edge a user must be able to find.
  double get boundary => 1;

  /// 2 dp. A selected region, a selected chip.
  double get emphasis => 2;

  /// 2 dp, with [focusGap] of the parent surface outside the component.
  double get focus => 2;

  /// The gap between a component's edge and its focus ring.
  double get focusGap => 2;

  /// The ring's radius is the component's radius plus this.
  double get focusRadiusOffset => 4;

  /// The caret's corner. The caret is [emphasis] wide and as tall as the
  /// scaled line box, so its ends are rounded rather than cut square
  /// (11 section 4).
  ///
  /// Deliberately absent from [UiShape.strokes]: that map is the widths the
  /// foundation gallery page walks, and this is a corner.
  double get caretRadius => 1;

  /// 3 dp. The leading bar of a selected row and of a diff addition.
  double get bar => 3;
}

/// Corner radii and the shapes built from them.
@immutable
class UiShape {
  /// Binds the radii. Prefer [UiShape.standard].
  const UiShape({required this.stroke});

  /// The stroke widths.
  final UiStroke stroke;

  /// The standard set. Identical in both modes.
  static const UiShape standard = UiShape(stroke: UiStroke());

  /// Sheets, dialogs, large panes, the photograph matte.
  double get sheet => 28;

  /// Data tiles, cards, tile groups, popovers, toasts.
  double get tile => 20;

  /// Text fields, selects, text areas.
  double get field => 14;

  /// Nested elements: thumbnails inside rows, key caps, swatches.
  double get inner => 8;

  /// Diff spans, table cells, region overlays, the environment banner.
  double get none => 0;

  /// Buttons, toggles, chips, the navigation and its discs, search fields,
  /// badges. Drawn as a `StadiumBorder`, never as a large radius.
  OutlinedBorder get capsule => const StadiumBorder();

  /// Every radius, by the name 09 gives it. The gallery page walks this.
  Map<String, double> get radii => <String, double>{
    'radius.sheet': sheet,
    'radius.tile': tile,
    'radius.field': field,
    'radius.inner': inner,
    'radius.none': none,
  };

  /// Every stroke width, by name.
  Map<String, double> get strokes => <String, double>{
    'hairline': stroke.hairline,
    'boundary': stroke.boundary,
    'emphasis': stroke.emphasis,
    'focus': stroke.focus,
    'bar': stroke.bar,
  };

  /// An inner element's radius: its parent's minus the inset between them,
  /// floored at [inner].
  ///
  /// Optical nesting, stated as a constraint rather than a suggestion. A tile
  /// at 20 with 12 dp of padding gives its children 8.
  double nested(double parentRadius, double inset) {
    final double value = parentRadius - inset;
    return value < inner ? inner : value;
  }
}
