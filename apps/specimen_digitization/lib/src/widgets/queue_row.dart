/// One record in the queue (design system, 7.3 `QueueRow`).
///
/// Keyed by the record's own identifier, so a background poll that reorders
/// the list does not move focus or scroll position. Relative age is allowed
/// here and only here, and it is always paired with the absolute time in the
/// accessibility label (UX writing, section 4.14).
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import 'risk_meter.dart';
import 'specimen_status.dart';
import 'status_chip.dart';
import 'thumbnail.dart';

/// A relative age, for the queue list only.
///
/// Deliberately coarse: a reviewer scanning a queue needs "3 days", not
/// "3 days, 4 hours". Anything under a minute reads as "just now".
String relativeAge(DateTime moment, {DateTime? now}) {
  final Duration age = (now ?? DateTime.now()).difference(moment);
  if (age.isNegative || age.inMinutes < 1) return 'just now';
  if (age.inHours < 1) return '${age.inMinutes} min';
  if (age.inDays < 1) return '${age.inHours} h';
  if (age.inDays < _daysInWeek) return '${age.inDays} d';
  return '${age.inDays ~/ _daysInWeek} w';
}

const int _daysInWeek = 7;

const List<String> _months = <String>[
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

String _two(int value) => value.toString().padLeft(2, '0');

/// The citable form: `13 Sep 2026, 14:32 CDT`.
String absoluteTime(DateTime moment) =>
    '${moment.day} ${_months[moment.month - 1]} ${moment.year}, '
    '${_two(moment.hour)}:${_two(moment.minute)} ${moment.timeZoneName}';

/// A queue row: thumbnail, identifier, reason, status, risk and age.
class QueueRow extends StatelessWidget {
  const QueueRow({
    super.key,
    required this.id,
    required this.title,
    required this.reason,
    required this.status,
    this.thumbnail,
    this.riskComposite,
    this.riskComponents = const <String>[],
    this.riskCalibrated = true,
    this.updatedAt,
    this.now,
    this.selected = false,
    this.onOpen,
  });

  /// The record's identifier. Also the row's identity for focus and scroll.
  final String id;

  /// The specimen identifier, as the record calls it.
  final String title;

  /// One line of plain language saying why the row is in this queue.
  final String reason;

  /// The record's disposition or operational state.
  final SpecimenStatus status;

  /// Encoded image bytes for the leading thumbnail. A placeholder is drawn
  /// when this is null or fails to decode.
  final Uint8List? thumbnail;

  /// The composite risk score, if the server produced one.
  final num? riskComposite;

  /// The signals behind the score. Required whenever a score is shown.
  final List<String> riskComponents;

  /// False when the risk policy has not been calibrated.
  final bool riskCalibrated;

  /// When the record last changed.
  final DateTime? updatedAt;

  /// Injected clock, so a test can assert an age without waiting.
  final DateTime? now;

  /// True when this row is the one open in the detail pane.
  final bool selected;

  /// Opens the record.
  final VoidCallback? onOpen;

  String _semanticsLabel() {
    final StringBuffer buffer = StringBuffer()
      ..write(title)
      ..write(', ')
      ..write(status.semanticsLabel)
      ..write(', ')
      ..write(reason);
    if (updatedAt != null) {
      buffer
        ..write(', updated ')
        ..write(absoluteTime(updatedAt!));
    }
    return buffer.toString();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final DateTime? updated = updatedAt;

    // One node for the row: the label and the tap action merged, with the
    // row's own text nodes dropped so the reader is not walked through the
    // identifier, the reason, the chip and the age as four separate stops.
    return MergeSemantics(
      child: Semantics(
        selected: selected,
        label: _semanticsLabel(),
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTap: onOpen,
            borderRadius: BorderRadius.circular(context.shape.radiusSm),
            focusColor: theme.colorScheme.primary.withValues(
              alpha: _focusFillOpacity,
            ),
            child: ExcludeSemantics(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: selected ? theme.colorScheme.primaryContainer : null,
                  borderRadius: BorderRadius.circular(context.shape.radiusSm),
                  // A 3dp leading bar marks the open record. When there is no
                  // bar the padding below makes up the width, so selecting a row
                  // never shifts its content sideways.
                  border: selected
                      ? BorderDirectional(
                          start: BorderSide(
                            color: theme.colorScheme.primary,
                            width: context.shape.strokeStrong,
                          ),
                        )
                      : null,
                ),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: context.sizes.targetMin,
                  ),
                  child: Padding(
                    padding: EdgeInsetsDirectional.fromSTEB(
                      selected
                          ? context.space.space2
                          : context.space.space2 + context.shape.strokeStrong,
                      context.space.space2,
                      context.space.space2,
                      context.space.space2,
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: <Widget>[
                        SpecimenThumbnail(bytes: thumbnail),
                        SizedBox(width: context.space.space3),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Text(
                                title,
                                style: context.mono.identifier,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              Text(
                                reason,
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                        SizedBox(width: context.space.space2),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            StatusChip(status, dense: true),
                            SizedBox(height: context.space.space1),
                            RiskMeter(
                              composite: riskComposite,
                              components: riskComponents,
                              calibrated: riskCalibrated,
                              compact: true,
                            ),
                          ],
                        ),
                        if (updated != null) ...<Widget>[
                          SizedBox(width: context.space.space2),
                          Text(
                            relativeAge(updated, now: now),
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                        Icon(
                          Symbols.chevron_right,
                          size: context.sizes.iconInline,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// The focus fill behind a keyboard focused row. Low enough to keep the
  /// text legible, high enough to find at a glance.
  static const double _focusFillOpacity = 0.12;
}
