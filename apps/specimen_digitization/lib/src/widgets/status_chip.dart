/// The status chip (design system, section 7.2; UX writing, section 4.13).
///
/// Glyph plus word plus a 1dp `content` border over the `fill`, at
/// `radius.xs`. Color is never the only carrier, and the whole chip is one
/// merged semantics node, so a screen reader reads "Queue: cleared" instead of
/// "icon, text" as two nodes (accessibility, section 3.1).
library;

import 'package:flutter/material.dart';

import '../theme/icons.dart';
import 'specimen_status.dart';

/// A non-interactive chip stating one status.
class StatusChip extends StatelessWidget {
  /// A chip for one of the statuses this client knows.
  const StatusChip(
    SpecimenStatus status, {
    super.key,
    this.count,
    this.dense = false,
  }) : _status = status,
       _presentation = null;

  /// A chip for a presentation another enum produced, such as an upload
  /// state. There is no constructor anywhere that takes a bare color.
  const StatusChip.presented(
    StatusPresentation presentation, {
    super.key,
    this.count,
    this.dense = false,
  }) : _status = null,
       _presentation = presentation;

  final SpecimenStatus? _status;
  final StatusPresentation? _presentation;

  /// An optional trailing count, for a chip that summarizes a queue.
  final int? count;

  /// Drops the chip to the smaller label role, for a chip inside a dense row.
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final StatusPresentation style =
        _presentation ?? _status!.presentation(context);
    final ThemeData theme = Theme.of(context);
    final TextStyle? text = dense
        ? theme.textTheme.labelSmall
        : theme.textTheme.labelMedium;
    final double glyph = context.sizes.iconInline;
    final int? total = count;
    final String label = total == null ? style.label : '${style.label} $total';
    final String semantics = total == null
        ? style.semanticsLabel
        : '${style.semanticsLabel}, $total';

    return Semantics(
      container: true,
      label: semantics,
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: style.fill,
          borderRadius: BorderRadius.circular(context.shape.radiusXs),
          border: Border.all(
            color: style.content,
            width: context.shape.strokeBoundary,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.space2,
            vertical: context.space.space1,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              SizedBox.square(
                dimension: glyph,
                child: style.progress == null
                    ? Icon(
                        style.icon,
                        size: glyph,
                        fill: style.fill01,
                        color: style.onFill,
                      )
                    // A determinate ring reports a measured fraction, so it
                    // keeps its motion under reduced motion (motion, 2.5).
                    : CircularProgressIndicator(
                        value: style.progress,
                        strokeWidth: context.shape.strokeEmphasis,
                        color: style.onFill,
                      ),
              ),
              SizedBox(width: context.space.space1),
              Flexible(
                child: Text(
                  label,
                  style: text?.copyWith(color: style.onFill),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
