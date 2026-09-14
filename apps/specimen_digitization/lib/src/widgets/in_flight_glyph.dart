/// A control's leading glyph while a request is out
/// (motion and microinteractions, catalog rows 27, 44, 49 and 70).
///
/// Four rows of the catalog ask for the same thing in the same words: the
/// button keeps its footprint and reports the request inline, so the layout
/// does not move while the reviewer waits. There is never a full screen
/// blocking overlay behind it, and the record is never dimmed: a reviewer
/// must still be able to read the evidence they just judged.
library;

import 'package:flutter/material.dart';

import '../theme/icons.dart';
import '../theme/motion.dart';

/// The glyph, cross-faded at `quick` between resting and in flight.
class InFlightGlyph extends StatelessWidget {
  const InFlightGlyph({super.key, required this.busy, required this.resting});

  /// True while the request is out.
  final bool busy;

  /// The glyph shown when it is not. Null for a button with no leading icon,
  /// where the indicator claims its own space only while it is needed.
  final IconData? resting;

  @override
  Widget build(BuildContext context) {
    final double size = context.sizes.iconInline;
    final Widget indicator = Padding(
      key: const ValueKey<String>('in-flight'),
      padding: EdgeInsetsDirectional.only(end: context.space.space2),
      child: SizedBox.square(
        dimension: size,
        child: CircularProgressIndicator(
          strokeWidth: context.shape.strokeEmphasis,
          semanticsLabel: 'Working',
        ),
      ),
    );
    final IconData? icon = resting;
    final Widget rest = icon == null
        ? const SizedBox.shrink(key: ValueKey<String>('resting-none'))
        : Icon(icon, key: const ValueKey<String>('resting'), size: size);

    return AnimatedSwitcher(
      duration: context.motion.quick,
      switchInCurve: MotionTokens.standardCurve,
      child: busy ? indicator : rest,
    );
  }
}
