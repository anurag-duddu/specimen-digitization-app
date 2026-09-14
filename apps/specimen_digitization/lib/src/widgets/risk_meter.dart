/// The risk meter (design system, 1.4 and 7.3; UX writing, 4.14 and 4.15).
///
/// A score never travels alone. The meter refuses to render a number without
/// the components that produced it, it says "Not measured" rather than zero
/// when the assessment is partial, and it carries the "Not calibrated" caveat
/// whenever the policy has not been calibrated.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import 'caveat_text.dart';

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

  /// The contributing signals, named. Never empty when a score is shown.
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
      : 'Not measured';

  bool get _measured => isMeasured(
    composite: composite,
    status: status,
    measurementComplete: measurementComplete,
  );

  Color _band(BuildContext context, double fraction) {
    if (fraction < _lowCeiling) return context.tokens.riskLowContent;
    if (fraction < _mediumCeiling) return context.tokens.riskMediumContent;
    return context.tokens.riskHighContent;
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
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

    final Widget headlineRow = Wrap(
      spacing: context.space.space2,
      runSpacing: context.space.space1,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: <Widget>[
        if (!_measured)
          Padding(
            padding: EdgeInsetsDirectional.only(end: context.space.space1),
            child: Icon(
              Symbols.hide_source,
              size: context.sizes.iconInline,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        Text(
          text,
          style: compact
              ? theme.textTheme.labelMedium
              : theme.textTheme.titleMedium,
        ),
        if (!calibrated) const _NotCalibratedChip(),
      ],
    );

    return Semantics(
      container: true,
      label: spoken,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          ExcludeSemantics(child: headlineRow),
          // No bar without a number. A bar at zero would assert a measurement
          // the server never made.
          if (_measured) ...<Widget>[
            SizedBox(height: context.space.space1),
            ExcludeSemantics(
              child: SizedBox(
                width: compact ? context.sizes.rowCompact : null,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(context.shape.radiusXs),
                  child: LinearProgressIndicator(
                    value: fraction,
                    minHeight: context.shape.strokeStrong,
                    color: _band(context, fraction),
                    backgroundColor: theme.colorScheme.surfaceContainerHighest,
                  ),
                ),
              ),
            ),
          ],
          if (!compact) ...<Widget>[
            SizedBox(height: context.space.space1),
            if (components.isEmpty)
              Text(
                'No contributing signals were reported.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              )
            else
              for (final String component in components)
                Text(
                  component,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
            if (!calibrated) ...<Widget>[
              SizedBox(height: context.space.space1),
              const CaveatText(
                label: 'Not calibrated',
                body:
                    'A risk score orders the queue. It is not a probability '
                    'that the record is wrong. Scores never override '
                    'coverage, evidence or validation gates.',
              ),
            ],
          ],
        ],
      ),
    );
  }

  /// Below this fraction the band reads as low.
  static const double _lowCeiling = 0.34;

  /// Below this fraction the band reads as medium.
  static const double _mediumCeiling = 0.67;
}

/// The uncalibrated qualifier, outline only, no glyph (UX writing, 4.13).
class _NotCalibratedChip extends StatelessWidget {
  const _NotCalibratedChip();

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      container: true,
      label: 'Not calibrated',
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(context.shape.radiusXs),
          border: Border.all(
            color: theme.colorScheme.outline,
            width: context.shape.strokeBoundary,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.space2,
            vertical: context.space.space1,
          ),
          child: Text(
            'Not calibrated',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
      ),
    );
  }
}
