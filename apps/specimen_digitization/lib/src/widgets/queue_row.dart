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
/// "3 days, 4 hours". Anything under a minute reads as "moments ago".
String relativeAge(DateTime moment, {DateTime? now}) {
  final Duration age = (now ?? DateTime.now()).difference(moment);
  if (age.isNegative || age.inMinutes < 1) return 'moments ago';
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
                    child: LayoutBuilder(
                      builder:
                          (BuildContext context, BoxConstraints constraints) {
                            final bool compact =
                                constraints.maxWidth < _compactBreakpoint;
                            return compact
                                ? _compactBody(context, theme, updated)
                                : _wideBody(context, theme, updated);
                          },
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

  /// Below this content width the status chip and risk meter drop to a
  /// second line, so they never compete with the title and reason for a
  /// narrow list-detail pane (design system, section 7.3, `QueueRow`).
  static const double _compactBreakpoint = 500;

  /// The identifier over the reason, both clipped so neither can push the
  /// row wider than the space it is given.
  Widget _titleAndReason(BuildContext context, ThemeData theme) {
    return Column(
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
    );
  }

  Widget _ageText(ThemeData theme) => Text(
    relativeAge(updatedAt!, now: now),
    style: theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    ),
  );

  Widget _chevron(BuildContext context, ThemeData theme) => Icon(
    Symbols.chevron_right,
    size: context.sizes.iconInline,
    color: theme.colorScheme.onSurfaceVariant,
  );

  Widget _riskMeter() => RiskMeter(
    composite: riskComposite,
    components: riskComponents,
    calibrated: riskCalibrated,
    compact: true,
  );

  /// 500dp and up: thumbnail, title and reason, then the chip, meter and
  /// age in one trailing column, all on a single line.
  Widget _wideBody(BuildContext context, ThemeData theme, DateTime? updated) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        SpecimenThumbnail(bytes: thumbnail),
        SizedBox(width: context.space.space3),
        Expanded(child: _titleAndReason(context, theme)),
        SizedBox(width: context.space.space2),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: _metaMaxWidth),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              StatusChip(status, dense: true),
              SizedBox(height: context.space.space1),
              _riskMeter(),
            ],
          ),
        ),
        if (updated != null) ...<Widget>[
          SizedBox(width: context.space.space2),
          _ageText(theme),
        ],
        _chevron(context, theme),
      ],
    );
  }

  /// Under 500dp: the thumbnail, title and reason keep the first line to
  /// themselves, with the chevron; the status chip, risk meter and age move
  /// to a second line that wraps rather than overflows, so a 320dp pane
  /// never clips.
  Widget _compactBody(
    BuildContext context,
    ThemeData theme,
    DateTime? updated,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            SpecimenThumbnail(bytes: thumbnail),
            SizedBox(width: context.space.space3),
            Expanded(child: _titleAndReason(context, theme)),
            SizedBox(width: context.space.space2),
            _chevron(context, theme),
          ],
        ),
        SizedBox(height: context.space.space1),
        Padding(
          padding: EdgeInsetsDirectional.only(
            start: context.sizes.iconDisplay + context.space.space3,
          ),
          child: Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: context.space.space2,
            runSpacing: context.space.space1,
            children: <Widget>[
              StatusChip(status, dense: true),
              _riskMeter(),
              if (updated != null) _ageText(theme),
            ],
          ),
        ),
      ],
    );
  }

  /// The trailing chip and meter column never grows past this, in either
  /// layout, so a long status label or an uncalibrated caveat wraps inside
  /// the meter instead of pushing the title out of the row.
  static const double _metaMaxWidth = 220;

  /// The focus fill behind a keyboard focused row. Low enough to keep the
  /// text legible, high enough to find at a glance.
  static const double _focusFillOpacity = 0.12;
}
