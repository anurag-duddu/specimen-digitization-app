/// Review risk, execution facts and the comparison summary
/// (screen blueprints, 6.3 and 6.4; design system, 1.4).
///
/// A score is never shown without the components that produced it, a partial
/// assessment has no overall score, and every absence is a word rather than a
/// zero.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'review_context.dart';
import 'vocabulary.dart';
import 'widgets/caveat_text.dart';
import 'widgets/evidence_drawer.dart';
import 'widgets/risk_meter.dart';

/// The composite as a sentence, or the abstention where it is not measured.
String riskComposite(Json risk) {
  final partial =
      risk['status'] == 'blocked' ||
      risk['status'] == 'unmeasured' ||
      risk['measurement_complete'] == false;
  return partial || risk['composite'] == null
      ? RiskMeter.absence
      : '${risk['composite']} of ${RiskMeter.scale}';
}

/// True when [risk] carries a score that may be shown.
bool riskMeasured(Json risk) => RiskMeter.isMeasured(
  composite: risk['composite'] as num?,
  status: risk['status'] as String?,
  measurementComplete: risk['measurement_complete'] != false,
);

/// The contributing signals of [risk], one sentence each.
List<String> riskComponents(Json risk) => <String>[
  for (final component in objects(risk['components']))
    _componentLine(component),
];

String _componentLine(Json component) {
  final signal = objectOf(component['signal']);
  return '${vocabularyLabel(textOf(signal['code']))} · '
      'Count ${textOf(signal['count'], RiskMeter.absence)} · '
      'Weight ${textOf(component['weight'], RiskMeter.absence)} · '
      'Contribution ${textOf(component['contribution'], RiskMeter.absence)}';
}

/// The record's own risk, its policy and the assessments under it.
class ReviewRiskPanel extends StatelessWidget {
  const ReviewRiskPanel({
    super.key,
    required this.risk,
    this.policy = const {},
  });

  final Json risk, policy;

  /// The heading over the whole panel.
  static const String heading = 'Review risk';

  /// The one sentence that says what a score is for.
  static const String scope =
      'Scores order the queue only. A partial assessment has no overall '
      'score.';

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Surface(
      radius: ui.shape.tile,
      hairline: true,
      child: UiDisclosure(
        title: heading,
        summary: riskMeasured(risk)
            ? 'Queue priority available'
            : RiskMeter.absence,
        hideSummaryWhenExpanded: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(scope, style: ui.type.bodySmall),
            if (risk['calibrated'] != true)
              const CaveatText(
                label: 'Not calibrated',
                why:
                    'A risk score orders the queue. It is not a probability that '
                    'the record is wrong. Scores never override coverage, evidence '
                    'or validation checks.',
              ),
            SizedBox(height: ui.space.s2),
            RiskAssessmentDetails(risk: risk, meter: true),
            if (policy.isNotEmpty)
              EvidenceDrawer(
                title: 'Policy technical details',
                payload: policy,
              ),
            for (final scopeKey in ['labels', 'fields'])
              for (final (index, item) in objects(risk[scopeKey]).indexed)
                UiDisclosure(
                  key: ValueKey(
                    '${item['scope']}:${item['target_id']}:${item['input_sha256']}',
                  ),
                  title: scopeKey == 'labels'
                      ? 'Label ${index + 1}'
                      : _fieldAssessmentLabel(item, index),
                  summary: riskMeasured(item)
                      ? 'Queue priority available'
                      : RiskMeter.absence,
                  hideSummaryWhenExpanded: true,
                  child: RiskAssessmentDetails(risk: item),
                ),
          ],
        ),
      ),
    );
  }

  String _fieldAssessmentLabel(Json item, int index) {
    final target = textOf(item['target_id'], '');
    final label = vocabularyLabel(target);
    return RegExp(r'^[a-z][a-z_]*$').hasMatch(target)
        ? label
        : 'Field ${index + 1}';
  }
}

/// Scientific signals are readable; execution metadata stays in audit details.
class RiskAssessmentDetails extends StatelessWidget {
  const RiskAssessmentDetails({
    super.key,
    required this.risk,
    this.meter = false,
  });

  final Json risk;
  final bool meter;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final details = {...risk}
      ..remove('labels')
      ..remove('fields');
    final line = ui.type.bodySmall.copyWith(color: ui.color.inkSecondary);
    final components = riskComponents(risk);
    final unmeasured = risk['unmeasured'] as List? ?? const [];
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (meter)
            RiskMeter(
              composite: risk['composite'] as num?,
              components: components,
              calibrated: risk['calibrated'] == true,
              status: risk['status'] as String?,
              measurementComplete: risk['measurement_complete'] != false,
            )
          else ...[
            Text(riskComposite(risk), style: ui.type.title),
            for (final component in components) Text(component, style: line),
          ],
          if (!riskMeasured(risk))
            Text(
              'An overall priority score is unavailable until the assessment is complete.',
              style: line,
            ),
          if (unmeasured.isNotEmpty)
            Text(
              '${unmeasured.length} '
              '${unmeasured.length == 1 ? 'signal has' : 'signals have'} '
              'not been measured.',
              style: line,
            ),
          EvidenceDrawer(title: 'Technical details', payload: details),
        ],
      ),
    );
  }
}

/// What the provider reported about one reading's execution.
class ObservationExecutionDetails extends StatelessWidget {
  const ObservationExecutionDetails({super.key, required this.observation});

  final Json observation;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final latency = observation['latency_seconds'];
    final TextStyle line = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Configured model: ${textOf(observation['model_id'])} · Provider: ${textOf(observation['provider'])}',
            style: line,
          ),
          Text(
            'Reported model: ${textOf(observation['provider_model_id'], 'Not reported')}',
            style: line,
          ),
          Text(
            latency == null
                ? 'Latency: Not measured'
                : 'Latency: $latency seconds',
            style: line,
          ),
          Text(
            'Timing basis: ${vocabularyLabel(textOf(observation['latency_basis'], 'Not reported'))}',
            style: line,
          ),
          Text(
            'Finish state: ${vocabularyLabel(textOf(observation['finish_state'], 'Not reported'))} · Completion state: ${vocabularyLabel(textOf(observation['completion_state'], 'Not reported'))}',
            style: line,
          ),
          const CaveatText(
            label: 'Completion describes processing only.',
            why: 'It does not mean the transcription is correct.',
          ),
          Text(
            'Input tokens: ${textOf(observation['input_tokens'], 'Not reported')} · Output tokens: ${textOf(observation['output_tokens'], 'Not reported')}',
            style: line,
          ),
          Text(
            'Input asset: ${textOf(observation['input_asset_id'], 'Not reported')}',
            style: line,
          ),
          Text(
            'Input crop reference: ${textOf(observation['input_crop_ref'], 'Not reported')}',
            style: line,
          ),
          if (observation['parameters'] == null)
            Text('Model parameters: Not reported', style: line)
          else
            EvidenceDrawer(
              title: 'Reported model parameters',
              payload: observation['parameters'],
            ),
        ],
      ),
    );
  }
}

/// How far two retained readings agree, and what the measurement is worth.
class TranscriptionComparisonSummary extends StatelessWidget {
  const TranscriptionComparisonSummary({
    super.key,
    required this.transcription,
  });

  final Json transcription;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final status = transcription['alignment_status'];
    final measured =
        ['agreement', 'disagreement'].contains(status) &&
        transcription['disagreement_ratio'] != null;
    final TextStyle line = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Comparison: ${vocabularyLabel(textOf(status, 'Not reported'))} · Difference fraction: ${measured ? transcription['disagreement_ratio'] : 'Not measured'}',
            style: line,
          ),
          if (status == 'policy_blocked')
            Text(
              'Comparison limits prevented measurement. This is not agreement.',
              style: line,
            ),
          Text('Two readings agreeing does not make them right.', style: line),
          for (final reason
              in transcription['alignment_reasons'] as List? ?? [])
            Text(vocabularyLabel(reason.toString()), style: line),
        ],
      ),
    );
  }
}
