/// One navigation destination (10 section 4.4).
///
/// The pill, the rail and the sidebar draw the same destinations, so the three
/// controls take one value rather than three shapes of the same thing. A
/// destination is data: it carries no state and no callback, and the control
/// that draws it owns which one is current.
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';

/// A place the reviewer can navigate to.
///
/// [label] is required rather than optional because none of the three
/// navigation controls draws it at every size: the pill never draws it and a
/// collapsed rail does not either, so the label is the only thing a screen
/// reader has (10 section 11, last rule).
@immutable
class UiNavDestination {
  /// Binds a destination's words to its glyph.
  const UiNavDestination({required this.label, required this.icon});

  /// The destination's name, in sentence case, one or two words.
  ///
  /// Read by a screen reader on every control, shown as the tooltip on a pill
  /// disc, drawn under the glyph on an extended rail and beside it in the
  /// sidebar.
  final String label;

  /// The glyph, from the registry.
  ///
  /// Drawn in `regular` weight, and in `fill` for the destination the reviewer
  /// is on (09 section 7).
  final IconSpec icon;

  @override
  bool operator ==(Object other) =>
      other is UiNavDestination && other.label == label && other.icon == icon;

  @override
  int get hashCode => Object.hash(label, icon);
}
