/// The one line label (10 section 2 clause 13; 11 section 3.3 rules 1 and 4).
///
/// A label is the word a control is: the text on a button, in a segment, on a
/// chip, in a tab. It never wraps. Given less room than it needs it ends in
/// an ellipsis, and the full text goes to the tooltip and to the semantics
/// label, so nothing is lost to the reader and nothing ever grows a second
/// line.
///
/// Content text is not a label. Body copy, a row's title, help text and a
/// banner's sentence wrap as content should, and are drawn with `Text`.
library;

import 'package:flutter/widgets.dart';

import '../foundation/type.dart';
import 'fit.dart';

/// Wraps an overflowing label in whatever carries its full text.
///
/// A drawn tooltip is a control (L3) and this is a primitive (L2), so the
/// pane comes in as a slot rather than as an import: a control passes
/// `(context, message, label) => UiTooltip(message: message, child: label)`.
typedef UiLabelTooltip =
    Widget Function(BuildContext context, String message, Widget label);

/// One line of text that ellipsises rather than wrapping.
class UiLabel extends StatelessWidget {
  /// Draws [text] on one line.
  const UiLabel(
    this.text, {
    super.key,
    this.style,
    this.textAlign,
    this.tooltip,
  });

  /// The label.
  final String text;

  /// The role to draw it in. Merged onto the ambient text style the way
  /// `Text` merges its own, so a control that has already published its
  /// foreground passes only what it changes.
  final TextStyle? style;

  /// How the line sits in the width it is given.
  final TextAlign? textAlign;

  /// What to wrap the label in when it overflows.
  ///
  /// Called only when the text does not fit, so a label that is fully
  /// readable carries no tooltip: a pane that repeats what is already on
  /// screen is noise under the pointer and a second announcement to a screen
  /// reader.
  final UiLabelTooltip? tooltip;

  @override
  Widget build(BuildContext context) {
    final TextStyle resolved = DefaultTextStyle.of(context).style.merge(style);
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double available = constraints.maxWidth;
        final bool overflowing =
            available.isFinite &&
            measureLabel(context, text, resolved).width > available;
        final Widget label = Text(
          text,
          style: resolved,
          textAlign: textAlign,
          // The three properties clause 13 names. `softWrap: false` is what
          // stops a narrow column breaking a label between its letters;
          // `maxLines: 1` alone still wraps.
          maxLines: 1,
          softWrap: false,
          overflow: TextOverflow.ellipsis,
          // Locked to the role's own line box, so the height a control
          // computed from `UiType.controlHeightFor` is the height the label
          // actually takes.
          strutStyle: UiType.strutOf(resolved),
          // The full text, only when the drawn text is not all of it. `Text`
          // publishes the string it was given either way; naming it here is
          // what makes the promise explicit rather than incidental.
          semanticsLabel: overflowing ? text : null,
        );
        if (!overflowing) return label;
        return tooltip?.call(context, text, label) ?? label;
      },
    );
  }
}
