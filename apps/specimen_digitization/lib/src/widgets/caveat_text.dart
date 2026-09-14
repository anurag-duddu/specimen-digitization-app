/// The caveat pattern (UX writing, section 4.15).
///
/// A caveat is never a paragraph in the flow of the page. It is a short
/// negative label that is true and sufficient on its own, a "Why" affordance,
/// and a short body behind it. Caveats are statements of scope, not failures,
/// so they are never in `colorScheme.error` and never carry a warning
/// triangle.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import '../theme/motion.dart';

/// A short boundary statement with an inline "Why" disclosure.
class CaveatText extends StatefulWidget {
  const CaveatText({super.key, required this.label, required this.body});

  /// The boundary, 40 characters or fewer, negative and specific. A reader
  /// who never opens "Why" must not be misled by it alone.
  final String label;

  /// At most 300 characters and at most three sentences.
  final String body;

  /// The longest label the pattern allows.
  static const int labelBudget = 40;

  /// The longest body the pattern allows.
  static const int bodyBudget = 300;

  @override
  State<CaveatText> createState() => _CaveatTextState();
}

class _CaveatTextState extends State<CaveatText> {
  /// Expansion is per caveat and is deliberately not remembered across
  /// sessions: these are the statements a reviewer should re-read when a
  /// record is unusual.
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    assert(
      widget.label.length <= CaveatText.labelBudget,
      'a caveat label is ${CaveatText.labelBudget} characters or fewer',
    );
    assert(
      widget.body.length <= CaveatText.bodyBudget,
      'a caveat body is ${CaveatText.bodyBudget} characters or fewer',
    );
    final ThemeData theme = Theme.of(context);
    final MotionTokens motion = context.motion;
    final Color quiet = theme.colorScheme.onSurfaceVariant;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Flexible(
              child: Text(
                widget.label,
                style: theme.textTheme.bodySmall?.copyWith(color: quiet),
              ),
            ),
            SizedBox(width: context.space.space1),
            MergeSemantics(
              child: Semantics(
                expanded: _open,
                child: TextButton.icon(
                  onPressed: () => setState(() => _open = !_open),
                  icon: AnimatedRotation(
                    turns: _open ? _halfTurn : 0,
                    duration: motion.quick,
                    curve: MotionTokens.standardCurve,
                    child: Icon(
                      Symbols.expand_more,
                      size: context.sizes.iconInline,
                    ),
                  ),
                  label: const Text('Why'),
                ),
              ),
            ),
          ],
        ),
        // `AnimatedSize` with a zero duration re-dirties itself during its
        // own layout, so under reduced motion the region is rendered
        // directly instead of being animated to nowhere.
        _maybeAnimated(
          motion,
          _open
              ? Padding(
                  padding: EdgeInsets.only(
                    top: context.space.space1,
                    bottom: context.space.space2,
                  ),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      maxWidth: context.sizes.readingMax,
                    ),
                    child: Text(
                      widget.body,
                      style: theme.textTheme.bodySmall?.copyWith(color: quiet),
                    ),
                  ),
                )
              : const SizedBox(width: double.infinity),
        ),
      ],
    );
  }

  /// Wraps [child] in an `AnimatedSize`, unless motion is off.
  Widget _maybeAnimated(MotionTokens motion, Widget child) => motion.reduced
      ? child
      : AnimatedSize(
          duration: motion.standard,
          curve: MotionTokens.standardCurve,
          alignment: Alignment.topLeft,
          child: child,
        );

  /// A chevron points down when closed and up when open.
  static const double _halfTurn = 0.5;
}
