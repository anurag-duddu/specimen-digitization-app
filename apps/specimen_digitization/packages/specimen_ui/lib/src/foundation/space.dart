/// Eight-point structural spacing with a four-point optical half step.
library;

import 'package:flutter/widgets.dart';

/// The spacing grid and the sizes built on it.
@immutable
class UiSpace {
  /// Binds the grid. Prefer [UiSpace.standard].
  const UiSpace();

  /// The standard grid.
  static const UiSpace standard = UiSpace();

  /// Flush.
  double get s0 => 0;

  /// Optical spacing between a glyph and its label, or compact metadata.
  double get s1 => 4;

  /// Gap between related controls; chip to chip.
  double get s2 => 8;

  /// Compatibility alias for compact internal spacing, now on the 8 dp grid.
  double get s3 => s2;

  /// Default padding inside a pane; compact-window screen gutter.
  double get s4 => 16;

  /// Compatibility alias for standard padding, now on the 8 dp grid.
  double get s5 => s4;

  /// Gap between panes; medium and expanded screen gutter.
  double get s6 => 24;

  /// Gap between major sections in a pane.
  double get s8 => 32;

  /// Space above a screen title.
  double get s10 => 40;

  /// Empty-state vertical rhythm.
  double get s12 => 48;

  /// Maximum. Above this, the layout is wrong.
  double get s16 => 64;

  /// Glyph sitting on a `label.small` baseline.
  double get iconSmall => 16;

  /// Glyph sitting on a `body` baseline.
  double get iconInline => 20;

  /// Actions, rows, navigation.
  double get iconAction => 24;

  /// Empty states and the help screen.
  double get iconDisplay => 40;

  /// Hit box for every interactive element, on every platform, always.
  /// Density changes the visual size and the padding; it never shrinks this.
  double get targetMin => 48;

  /// The least width a one line label or title is worth drawing in
  /// (11 section 3.3, rule 3).
  ///
  /// Two hit boxes, which is about eight characters of `body` at scale 1.0.
  /// Below it an ellipsis leaves a word fragment rather than a word, so a
  /// control that has a compact variant switches to it here rather than
  /// shrinking its words any further. A control with no variant left keeps
  /// its label and ellipsises, which is rule 4.
  double get labelMin => targetMin * 2;

  /// Smallest a control may look. Below this, pad the hit box transparently.
  double get targetVisualMin => 40;

  /// Row heights carried from v1, still used by the screens this wave leaves
  /// in place.
  double get rowCompact => 72;

  /// The medium-window row height.
  double get rowMedium => 64;

  /// The expanded-window row height.
  double get rowExpanded => 56;

  /// The top bar at touch density.
  double get topBar => 56;

  /// The navigation rail.
  double get rail => 80;

  /// Minimum width for the workbench content pane before it stacks.
  double get paneDetailMin => 400;

  /// Maximum measure for prose.
  double get readingMax => 640;

  /// Maximum width of a centred dialog (10 section 3).
  double get dialogMax => 560;

  /// Every step of the grid, by name. The gallery page walks this.
  Map<String, double> get steps => <String, double>{
    's0': s0,
    's1': s1,
    's2': s2,
    's3': s3,
    's4': s4,
    's5': s5,
    's6': s6,
    's8': s8,
    's10': s10,
    's12': s12,
    's16': s16,
  };
}
