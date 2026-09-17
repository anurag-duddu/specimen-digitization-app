/// The status chip (10 section 5; 02 section 4.13).
///
/// `UiChip.tag` carrying a status triple and a registry glyph. Colour is never
/// the only carrier: the word and the glyph travel with it, and the whole chip
/// is one merged semantics node so a screen reader reads "Queue: cleared"
/// rather than "icon, text" as two nodes (06 section 3.1).
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'specimen_status.dart';
import 'term_text.dart';

/// A non-interactive chip stating one status.
class StatusChip extends StatelessWidget {
  /// A chip for one of the statuses this client knows.
  const StatusChip(
    SpecimenStatus status, {
    super.key,
    this.count,
    this.dense = false,
    this.decisive = false,
  }) : _status = status,
       _presentation = null;

  /// A chip for a presentation another enum produced, such as an upload
  /// state. There is no constructor anywhere that takes a bare color.
  const StatusChip.presented(
    StatusPresentation presentation, {
    super.key,
    this.count,
    this.dense = false,
    this.decisive = false,
  }) : _status = null,
       _presentation = presentation;

  final SpecimenStatus? _status;
  final StatusPresentation? _presentation;

  /// An optional trailing count, for a chip that summarizes a queue.
  final int? count;

  /// Carried for the call sites that pass it, and no longer read.
  ///
  /// A `UiChip` is one size, `sm`, in both densities (10 section 4.1), so a
  /// chip inside a dense row is already the chip a dense row wants. The
  /// parameter stays because the patterns keep their API through this
  /// refactor and its consumers are other agents' screens.
  final bool dense;

  /// Carried for the call sites that pass it, and no longer read.
  ///
  /// The v1 chip cross faded its own fill when a decision landed, over
  /// `standard` rather than `quick`. `UiChip` has no state transition of its
  /// own (10 section 4.1) and the status strip that passes this already
  /// carries the decisive moment on its saved check, so the chip states the
  /// new status rather than travelling to it.
  final bool decisive;

  @override
  Widget build(BuildContext context) {
    final StatusPresentation style =
        _presentation ?? _status!.presentation(context);
    final int? total = count;
    final String label = total == null ? style.label : '${style.label} $total';
    final String semantics = total == null
        ? style.semanticsLabel
        : '${style.semanticsLabel}, $total';
    final double? progress = style.progress;

    // The status word is a domain term, so the chip is its own definition
    // affordance (pass criterion 10.2). The spoken phrase keeps the
    // vocabulary prefix criterion 4.16 asks for, so gaining a definition
    // does not cost a screen reader the "Queue:" or "Field:" it had.
    return TermAffordance(
      term: style.label,
      spokenTerm: semantics,
      // An upload reports bytes, and a fraction the byte stream gave us is
      // drawn rather than described (02 section 4.8), so a determinate ring
      // stands in the chip's leading slot where the registry glyph would.
      // The ring keeps its motion under reduced motion because it is
      // information (04 section 1.5), and the chip publishes one node, so the
      // ring's own label is never read beside the chip's.
      child: progress == null
          ? UiChip(
              label: label,
              icon: style.glyph,
              status: style.triple,
              semanticsLabel: semantics,
            )
          : UiChip(
              label: label,
              status: style.triple,
              semanticsLabel: semantics,
              leading: UiProgress.ring(
                semanticsLabel: semantics,
                value: progress,
                size: UiProgressSize.small,
                color: style.triple.onFill,
              ),
            ),
    );
  }
}
