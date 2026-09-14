/// The caveat pattern (UX writing guidelines, section 4.15).
///
/// A caveat is never a paragraph in the flow of the page. It is a short label
/// that is true on its own, a "Why" affordance, and an expandable body that
/// carries the rest of the honesty. Nothing is deleted by using this widget;
/// the long half is relocated.
library;

import 'package:flutter/material.dart';

import '../theme/motion.dart';
import '../theme/spacing.dart';

/// A short caveat label with an expandable "Why".
///
/// The label states the boundary and must be true for a reader who never
/// expands it. The body says why, in at most three sentences.
///
/// Expansion is per-caveat and is deliberately not remembered across
/// sessions: these are the statements a reviewer should re-read when a record
/// is unusual.
class CaveatText extends StatefulWidget {
  const CaveatText({super.key, required this.label, required this.why});

  /// The boundary, stated so it stands alone. Never in `colorScheme.error`.
  final String label;

  /// The expanded body. At most three sentences.
  final String why;

  @override
  State<CaveatText> createState() => _CaveatTextState();
}

class _CaveatTextState extends State<CaveatText> {
  bool _expanded = false;

  void _toggle() => setState(() => _expanded = !_expanded);

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final MotionTokens motion = MotionTokens.of(context);
    final SpecimenSpacing spacing =
        theme.extension<SpecimenSpacing>() ?? const SpecimenSpacing();
    // A caveat is a statement of scope, not a failure: no error colour and no
    // warning glyph (guideline 4.15).
    final Color bodyColor = theme.colorScheme.onSurfaceVariant;
    final Widget body = _expanded
        ? Padding(
            padding: EdgeInsets.only(bottom: spacing.space2),
            child: Text(
              widget.why,
              style: theme.textTheme.bodySmall?.copyWith(color: bodyColor),
            ),
          )
        : const SizedBox(width: double.infinity);
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(widget.label, style: theme.textTheme.bodyMedium),
          Align(
            alignment: Alignment.centerLeft,
            // One node, so a screen reader reads "Why, button, collapsed"
            // rather than two fragments.
            child: MergeSemantics(
              child: Semantics(
                expanded: _expanded,
                child: TextButton.icon(
                  onPressed: _toggle,
                  iconAlignment: IconAlignment.end,
                  icon: Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    color: theme.colorScheme.primary,
                  ),
                  label: const Text('Why'),
                ),
              ),
            ),
          ),
          // Reduced motion skips the transition outright: a zero-duration
          // AnimatedSize resolves inside its own layout.
          if (motion.reduced)
            body
          else
            AnimatedSize(
              duration: MotionTokens.standardRaw,
              curve: MotionTokens.standardCurve,
              alignment: Alignment.topLeft,
              child: body,
            ),
        ],
      ),
    );
  }
}
