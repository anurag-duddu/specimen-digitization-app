/// The risk meter (design system, 1.4 and 7.3; UX writing, 4.14 and 4.15;
/// 10 section 5).
///
/// A score never travels alone. The meter refuses to render a number without
/// the components that produced it, it says "Not measured" rather than zero
/// when the assessment is partial, and it carries the "Not calibrated" caveat
/// whenever the policy has not been calibrated.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'caveat_text.dart';
import 'not_calibrated_chip.dart';
import 'term_text.dart';

/// A prioritization score, with the reason it can be trusted only that far.
class RiskMeter extends StatelessWidget {
  RiskMeter({
    super.key,
    required this.composite,
    required this.components,
    this.calibrated = true,
    this.status,
    this.measurementComplete = true,
    this.compact = false,
  }) : assert(
         compact ||
             !isMeasured(
               composite: composite,
               status: status,
               measurementComplete: measurementComplete,
             ) ||
             components.isNotEmpty,
         'a risk score is never shown without the components that produced '
         'it (design system, principle 1.4)',
       );

  /// The composite score, out of [scale]. Null means the server did not
  /// produce one.
  final num? composite;

  /// The contributing signals, named. Never empty when the expanded form
  /// shows a score.
  ///
  /// The compact form never draws them, and the search endpoint answers a
  /// bare composite with the contributing signals left on the record, so a
  /// compact meter may honestly pass an empty list rather than invent a line
  /// of prose to satisfy an assert.
  final List<String> components;

  /// False when the policy behind the score has not been calibrated.
  final bool calibrated;

  /// The assessment status the server reported, such as `blocked` or
  /// `unmeasured`.
  final String? status;

  /// False when the server measured only part of the assessment.
  final bool measurementComplete;

  /// The one line form, for a queue row.
  final bool compact;

  /// Scores are stated out of one hundred, never as a percentage.
  static const int scale = 100;

  /// The tile's own name, fixed so the meter and its tests agree on it.
  static const String label = 'Risk';

  /// What the meter says where there is no score.
  static const String absence = 'Not measured';

  /// The sentence under the components when none were reported.
  static const String noComponents = 'No contributing signals were reported.';

  /// The statuses that make an assessment partial, whatever the composite
  /// says. This mirrors `riskComposite` in `risk_assessment.dart`.
  static const Set<String> partialStatuses = <String>{'blocked', 'unmeasured'};

  /// True only when there is a score that may be shown.
  static bool isMeasured({
    required num? composite,
    String? status,
    bool measurementComplete = true,
  }) {
    final bool partial =
        partialStatuses.contains(status) || !measurementComplete;
    return !partial && composite != null;
  }

  /// The headline, either the score or the abstention.
  static String headline({
    required num? composite,
    String? status,
    bool measurementComplete = true,
  }) =>
      isMeasured(
        composite: composite,
        status: status,
        measurementComplete: measurementComplete,
      )
      ? 'Risk $composite of $scale'
      : absence;

  bool get _measured => isMeasured(
    composite: composite,
    status: status,
    measurementComplete: measurementComplete,
  );

  Color _band(UiThemeData ui, double fraction) {
    if (fraction < _lowCeiling) return ui.color.status.riskLow;
    if (fraction < _mediumCeiling) return ui.color.status.riskMedium;
    return ui.color.status.riskHigh;
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String text = headline(
      composite: composite,
      status: status,
      measurementComplete: measurementComplete,
    );
    final double fraction = _measured
        ? (composite!.toDouble() / scale).clamp(0, 1).toDouble()
        : 0;
    final String spoken = _measured
        ? '$text${calibrated ? '' : ', not calibrated'}'
        : 'Risk not measured';

    return compact
        ? _compact(ui, text: text, fraction: fraction, spoken: spoken)
        : _tile(ui, fraction: fraction, spoken: spoken);
  }

  /// The queue row's one line: the word, the number and a short band.
  ///
  /// A data tile is a block, and a row that carries one has stopped being a
  /// row. The band keeps the risk colour, which is the one place the colour
  /// survives: `UiArcIndicator` draws its marker in the accent and takes no
  /// status colour (recorded in the slot closeout).
  Widget _compact(
    UiThemeData ui, {
    required String text,
    required double fraction,
    required String spoken,
  }) => Semantics(
    container: true,
    label: spoken,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        ExcludeSemantics(
          child: Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s1,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              if (!_measured)
                UiIcon(
                  UiIcons.unmeasured,
                  size: UiIconSize.inline,
                  color: ui.color.inkSecondary,
                ),
              // "Risk" and "Not measured" are both domain terms, and a score
              // without its meaning is the thing principle 1.4 forbids
              // (pass criterion 10.2).
              TermText(
                _measured ? label : text,
                trailing: _measured ? text.substring(label.length) : null,
                spokenTerm: spoken,
                style: ui.type.label,
              ),
              if (!calibrated) const NotCalibratedChip(showGlyph: false),
            ],
          ),
        ),
        // No bar without a number. A bar at zero would assert a measurement
        // the server never made.
        if (_measured) ...<Widget>[
          SizedBox(height: ui.space.s1),
          ExcludeSemantics(
            child: SizedBox(
              width: ui.space.rowCompact,
              child: UiProgress.bar(
                value: fraction,
                semanticsLabel: spoken,
                color: _band(ui, fraction),
              ),
            ),
          ),
        ],
      ],
    ),
  );

  /// The workbench's form: the total beside the components, on a data tile.
  Widget _tile(
    UiThemeData ui, {
    required double fraction,
    required String spoken,
  }) => UiDataTile(
    label: label,
    value: _measured ? '$composite' : absence,
    unit: _measured ? 'OF $scale' : null,
    semanticsLabel: spoken,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        UiArcIndicator(
          // Null is the absence the arc draws as "Unmeasured" with its own
          // glyph, which is the honest state and never a ring at zero.
          value: _measured ? fraction : null,
          semanticsLabel: label,
          valueLabel: _measured ? '$composite of $scale' : null,
        ),
        SizedBox(height: ui.space.s2),
        if (components.isEmpty)
          Text(
            noComponents,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          )
        else
          for (final String component in components)
            Text(
              component,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
        if (!calibrated) ...<Widget>[
          SizedBox(height: ui.space.s1),
          const NotCalibratedChip(showGlyph: false),
          SizedBox(height: ui.space.s1),
          const CaveatText(
            label: NotCalibratedChip.label,
            why:
                'A risk score orders the queue. It is not a probability '
                'that the record is wrong. Scores never override '
                'coverage, evidence or validation gates.',
          ),
        ],
      ],
    ),
  );

  /// Below this fraction the band reads as low.
  static const double _lowCeiling = 0.34;

  /// Below this fraction the band reads as medium.
  static const double _mediumCeiling = 0.67;
}
