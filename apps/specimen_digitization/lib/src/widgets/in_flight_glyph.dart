/// A control's leading glyph while a request is out
/// (04 section 4, rows 27, 44, 49 and 70).
///
/// Four rows of the catalog ask for the same thing in the same words: the
/// button keeps its footprint and reports the request inline, so the layout
/// does not move while the reviewer waits. There is never a full screen
/// blocking overlay behind it, and the record is never dimmed: a reviewer
/// must still be able to read the evidence they just judged.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The glyph, cross-faded at `quick` between resting and in flight.
class InFlightGlyph extends StatelessWidget {
  const InFlightGlyph({super.key, required this.busy, required this.resting});

  /// True while the request is out.
  final bool busy;

  /// The glyph shown when it is not. Null for a button with no leading icon,
  /// where the indicator claims its own space only while it is needed.
  ///
  /// Still an `IconData` rather than an `IconSpec`: the controls that pass one
  /// belong to the slots that move in wave 3, and a glyph named here is drawn
  /// through `UiIcon` either way.
  final IconData? resting;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget indicator = Padding(
      key: const ValueKey<String>('in-flight'),
      padding: EdgeInsetsDirectional.only(end: ui.space.s2),
      child: const UiProgress.ring(
        semanticsLabel: 'Working',
        size: UiProgressSize.small,
      ),
    );
    final IconData? icon = resting;
    final Widget rest = icon == null
        ? const SizedBox.shrink(key: ValueKey<String>('resting-none'))
        : UiIcon(
            IconSpec(icon),
            key: const ValueKey<String>('resting'),
            size: UiIconSize.inline,
          );

    return AnimatedSwitcher(
      duration: ui.motion.quick,
      switchInCurve: MotionTokens.standardCurve,
      child: busy ? indicator : rest,
    );
  }
}
