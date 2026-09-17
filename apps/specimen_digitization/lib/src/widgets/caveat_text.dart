/// The caveat pattern (02 section 4.15).
///
/// A caveat is never a paragraph in the flow of the page. It is a short label
/// that is true on its own, a "Why" affordance, and an expandable body that
/// carries the rest of the honesty. Nothing is deleted by using this widget;
/// the long half is relocated.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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

  /// The boundary, stated so it stands alone. Never in the blocked role.
  final String label;

  /// The expanded body. At most three sentences.
  final String why;

  /// The affordance's word, in both states.
  ///
  /// One name open and closed, with `expanded` carrying which state it is in:
  /// a control that renames itself when it is pressed reads as two controls.
  static const String affordance = 'Why';

  @override
  State<CaveatText> createState() => _CaveatTextState();
}

class _CaveatTextState extends State<CaveatText> {
  bool _expanded = false;

  void _toggle() => setState(() => _expanded = !_expanded);

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // A caveat is a statement of scope, not a failure: no status colour and
    // no warning glyph (02 section 4.15).
    final Widget body = _expanded
        ? Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
            child: Text(
              widget.why,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          )
        : const SizedBox(width: double.infinity);

    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(widget.label, style: ui.type.body.copyWith(color: ui.color.ink)),
          Align(
            alignment: AlignmentDirectional.centerStart,
            // One node, so a screen reader reads "Why, button, collapsed"
            // rather than two fragments.
            child: MergeSemantics(
              child: Semantics(
                expanded: _expanded,
                child: UiButton(
                  label: CaveatText.affordance,
                  variant: UiButtonVariant.ghost,
                  trailing: _expanded ? UiIcons.collapse : UiIcons.expand,
                  onPressed: _toggle,
                ),
              ),
            ),
          ),
          // Reduced motion skips the transition outright: a zero-duration
          // AnimatedSize resolves inside its own layout.
          if (ui.motion.reduced)
            body
          else
            AnimatedSize(
              duration: MotionTokens.standardRaw,
              curve: MotionTokens.standardCurve,
              alignment: AlignmentDirectional.topStart,
              child: body,
            ),
        ],
      ),
    );
  }
}
