/// One record in the queue (10 section 5, `QueueRow`).
///
/// Keyed by the record's own identifier, so a background poll that reorders
/// the list does not move focus or scroll position. Relative age is allowed
/// here and only here, and it is always paired with the absolute time in the
/// accessibility label (02 section 4.14).
library;

import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../wall_time.dart';
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

/// The citable form on the reviewer's wall clock, with its zone: `13 Sep
/// 2026, 14:32 CDT` (02 section 4.14). An instant parsed in UTC, as the
/// server sends one, reads on that clock too, so no reviewer converts zones
/// in their head (design/01 H1.9; coordinator ruling for S6, 2026-09-24).
String absoluteTime(DateTime instant) {
  final WallTime wall = wallTime(instant);
  return '${_date(wall)}, ${_two(wall.hour)}:${_two(wall.minute)} ${wall.zone}';
}

/// The day of [instant] on the reviewer's wall clock, the way the citable
/// form spells it: `13 Sep 2026`.
String absoluteDate(DateTime instant) => _date(wallTime(instant));

String _date(WallTime wall) =>
    '${wall.day} ${_months[wall.month - 1]} ${wall.year}';

/// A queue row: thumbnail, identifier, reason, status, risk and age.
///
/// Built on `UiListRow`, so the whole row is one press target, one merged
/// semantics node and one leading slot whose width never moves with its
/// content.
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
    this.focusNode,
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

  /// The node the list moves keyboard focus to when its cursor lands here.
  ///
  /// A row that holds focus is the row `Enter` opens, so the queue's cursor
  /// and the focus ring are the same thing rather than two claims about where
  /// the reviewer is.
  final FocusNode? focusNode;

  /// The row width at which the status, the risk and the age fit beside the
  /// identifier rather than under it.
  ///
  /// A within-row content decision, not a window size class: the same row is
  /// drawn across a 1440 dp window and inside a 360 dp list pane beside a
  /// record, and what decides the layout is how much width this row was
  /// given. 05 section 1 names this kind of number rather than folding it
  /// into the breakpoint scale, which is what the constant is for.
  static const double _metaBesideTextMin = 500;

  /// The share of a wide row the trailing column may take.
  ///
  /// The trailing slot of a `UiListRow` is laid out at its natural width, so
  /// at 200 percent text it would otherwise push the identifier out of the
  /// row. Half is wider than the status chip needs at ordinary text size, so
  /// the cap only bites where something has to give.
  static const double _metaWidthShare = 0.5;

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
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) =>
        _row(context, constraints.maxWidth),
  );

  Widget _row(BuildContext context, double available) {
    final UiThemeData ui = context.ui;
    final bool beside = !available.isFinite || available >= _metaBesideTextMin;

    // The label carries every fact the row draws, because the row is one
    // merged node: a reader is not walked through the identifier, the reason,
    // the chip and the age as four separate stops (02 section 4.16).
    final Widget row = UiListRow(
      title: title,
      subtitle: reason,
      semanticsLabel: _semanticsLabel(),
      selected: selected,
      onPressed: onOpen,
      focusNode: focusNode,
      leading: SpecimenThumbnail(bytes: thumbnail),
      trailing: beside
          ? ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: available.isFinite
                    ? available * _metaWidthShare
                    : double.infinity,
              ),
              child: _meta(ui, stacked: false),
            )
          : null,
    );
    if (beside) return row;

    // A narrow row keeps the identifier and the reason readable and moves the
    // status, the risk and the age to a line of their own. The detector
    // carries the tap to that line so the whole block opens the record; the
    // row above it keeps the focus, the state layer and the one semantics
    // node, and the line itself says nothing a reader has not already heard.
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      excludeFromSemantics: true,
      onTap: onOpen,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          row,
          ExcludeSemantics(
            child: Padding(
              padding: EdgeInsetsDirectional.only(
                start:
                    ui.shape.stroke.bar +
                    ui.space.s3 +
                    UiListRowStyle.leadingExtent +
                    ui.space.s3,
                end: ui.space.s3,
                bottom: ui.space.s2,
              ),
              child: _meta(ui, stacked: true),
            ),
          ),
        ],
      ),
    );
  }

  /// The status, the risk and the age, stacked beside the text or flowing
  /// under it.
  Widget _meta(UiThemeData ui, {required bool stacked}) {
    final DateTime? updated = updatedAt;
    final List<Widget> parts = <Widget>[
      StatusChip(status, dense: true),
      RiskMeter(
        composite: riskComposite,
        components: riskComponents,
        calibrated: riskCalibrated,
        compact: true,
      ),
      if (updated != null)
        Text(
          relativeAge(updated, now: now),
          style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
        ),
    ];
    if (stacked) {
      return Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: ui.space.s2,
        runSpacing: ui.space.s1,
        children: parts,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (int index = 0; index < parts.length; index++) ...<Widget>[
          if (index > 0) SizedBox(height: ui.space.s1),
          parts[index],
        ],
      ],
    );
  }
}
