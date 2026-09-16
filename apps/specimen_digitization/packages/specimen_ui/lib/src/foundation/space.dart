/// The 4 px grid and the fixed sizes (09 section 6; 03 sections 5.1 and 5.2).
///
/// Unchanged from v1. The grid is the one thing in the visual system the
/// refactor did not need to move.
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

  /// Glyph to label inside a chip; gap between stacked metadata lines.
  double get s1 => 4;

  /// Gap between related controls; chip to chip.
  double get s2 => 8;

  /// Internal padding of a chip or a dense list row.
  double get s3 => 12;

  /// Default padding inside a pane; compact-window screen gutter.
  double get s4 => 16;

  /// Reserved for optical corrections, and the touch-density gutter.
  double get s5 => 20;

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
