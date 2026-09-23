/// The heading over one group within a segment: a label region in Readings,
/// a group of fields in Fields (UI.md T2.2 and T2.3).
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// A group's name, as a heading.
///
/// A label, not a title, set without the leading above and below its line.
/// On a phone the first reading has to stay on the first screen under the
/// photograph and the strip (13 sections 0 and 2.5), and a title-sized
/// heading pushed it off by 9 dp. Aligned rather than stretched, so the
/// heading's node is the size of its words: a node the width of the pane is
/// mostly background, which is what a contrast check samples and what a
/// focus highlight outlines.
class GroupHeading extends StatelessWidget {
  /// The heading that reads [text].
  const GroupHeading(this.text, {super.key});

  /// The group's name.
  final String text;

  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: Semantics(
      container: true,
      header: true,
      child: Text(
        text,
        style: context.ui.type.label,
        textHeightBehavior: const TextHeightBehavior(
          applyHeightToFirstAscent: false,
          applyHeightToLastDescent: false,
        ),
      ),
    ),
  );
}
