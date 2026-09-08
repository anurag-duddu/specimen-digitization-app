import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';

String riskComposite(Json risk) {
  final partial =
      risk['status'] == 'blocked' ||
      risk['status'] == 'unmeasured' ||
      risk['measurement_complete'] == false;
  return partial || risk['composite'] == null
      ? 'Unmeasured'
      : '${risk['composite']} / 100';
}

class ReviewRiskPanel extends StatelessWidget {
  const ReviewRiskPanel({
    super.key,
    required this.risk,
    this.policy = const {},
  });
  final Json risk, policy;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Review risk${risk['calibrated'] == true ? '' : ' (uncalibrated)'}',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const Text(
            'Prioritization only. Scores never override coverage, evidence or validation gates. A partial assessment has no composite score.',
          ),
          RiskAssessmentDetails(risk: risk),
          if (policy.isNotEmpty)
            EvidenceDetails(
              title: 'Published risk policy resolution and definition',
              value: policy,
            ),
          for (final scope in ['labels', 'fields'])
            if (objects(risk[scope]).isNotEmpty) ...[
              Text(
                scope == 'labels' ? 'Label assessments' : 'Field assessments',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              for (final item in objects(risk[scope]))
                ExpansionTile(
                  key: ValueKey(
                    '${item['scope']}:${item['target_id']}:${item['input_sha256']}',
                  ),
                  title: Text(
                    '${textOf(item['target_id'])} · ${riskComposite(item)}',
                  ),
                  subtitle: Text(
                    'Assessment ${labelOf(textOf(item['status']))}',
                  ),
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: RiskAssessmentDetails(risk: item),
                    ),
                  ],
                ),
            ],
        ],
      ),
    ),
  );
}

class RiskAssessmentDetails extends StatelessWidget {
  const RiskAssessmentDetails({super.key, required this.risk});
  final Json risk;
  @override
  Widget build(BuildContext context) {
    final reference = objectOf(risk['policy_reference']);
    final details = {...risk}
      ..remove('labels')
      ..remove('fields');
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '${labelOf(textOf(risk['scope'], 'specimen'))} · ${textOf(risk['target_id'])}',
          ),
          Text(
            riskComposite(risk),
            style: Theme.of(context).textTheme.titleLarge,
          ),
          if (risk['status'] != null)
            Text('Assessment status: ${labelOf(textOf(risk['status']))}'),
          Text(
            'Policy ${textOf(reference['id'], textOf(risk['policy_id']))} · Version ${textOf(reference['version'], textOf(risk['policy_version']))}',
          ),
          Text(
            'Policy digest: ${textOf(reference['digest'], textOf(risk['policy_digest']))}',
          ),
          if (risk['policy_resolution_status'] != null)
            Text(
              'Policy resolution: ${labelOf(textOf(risk['policy_resolution_status']))} · ${labelOf(textOf(risk['policy_resolution_reason']))}',
            ),
          Text(
            'Registry ${textOf(risk['registry_version'])} · Features ${textOf(risk['feature_version'])}',
          ),
          for (final component in objects(risk['components']))
            Builder(
              builder: (context) {
                final signal = objectOf(component['signal']);
                return Text(
                  '${labelOf(textOf(signal['code']))} · Count ${textOf(signal['count'], 'Unmeasured')} · Weight ${textOf(component['weight'], 'Unmeasured')} · Contribution ${textOf(component['contribution'], 'Unmeasured')}',
                );
              },
            ),
          for (final reason in risk['reasons'] as List? ?? [])
            Text('Reason: ${labelOf(reason.toString())}'),
          if (risk['unmeasured'] is List &&
              (risk['unmeasured'] as List).isNotEmpty)
            Text(
              'Unmeasured dimensions: ${(risk['unmeasured'] as List).map((s) => labelOf(s.toString())).join(', ')}',
            ),
          EvidenceDetails(
            title: 'Risk components, versions and calibration',
            value: details,
          ),
        ],
      ),
    );
  }
}

class ObservationExecutionDetails extends StatelessWidget {
  const ObservationExecutionDetails({super.key, required this.observation});
  final Json observation;
  @override
  Widget build(BuildContext context) {
    final latency = observation['latency_seconds'];
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Reported observation execution',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          Text(
            'Configured model: ${textOf(observation['model_id'])} · Provider: ${textOf(observation['provider'])}',
          ),
          Text(
            'Reported model: ${textOf(observation['provider_model_id'], 'Not reported')}',
          ),
          Text(
            latency == null
                ? 'Latency: Not measured'
                : 'Latency: $latency seconds',
          ),
          Text(
            'Timing basis: ${labelOf(textOf(observation['latency_basis'], 'Not reported'))}',
          ),
          Text(
            'Finish state: ${labelOf(textOf(observation['finish_state'], 'Not reported'))} · Completion state: ${labelOf(textOf(observation['completion_state'], 'Not reported'))}',
          ),
          const Text(
            'Completion describes processing, not verified transcription accuracy.',
          ),
          Text(
            'Input tokens: ${textOf(observation['input_tokens'], 'Not reported')} · Output tokens: ${textOf(observation['output_tokens'], 'Not reported')}',
          ),
          Text(
            'Input asset: ${textOf(observation['input_asset_id'], 'Not reported')}',
          ),
          Text(
            'Input crop reference: ${textOf(observation['input_crop_ref'], 'Not reported')}',
          ),
          if (observation['parameters'] == null)
            const Text('Model parameters: Not reported')
          else
            EvidenceDetails(
              title: 'Reported model parameters',
              value: observation['parameters'],
            ),
        ],
      ),
    );
  }
}

class TranscriptionComparisonSummary extends StatelessWidget {
  const TranscriptionComparisonSummary({
    super.key,
    required this.transcription,
  });
  final Json transcription;
  @override
  Widget build(BuildContext context) {
    final status = transcription['alignment_status'];
    final measured =
        ['agreement', 'disagreement'].contains(status) &&
        transcription['disagreement_ratio'] != null;
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Comparison: ${labelOf(textOf(status, 'Not reported'))} · Difference fraction: ${measured ? transcription['disagreement_ratio'] : 'Unmeasured'}',
          ),
          if (status == 'policy_blocked')
            const Text(
              'Comparison limits prevented measurement. This is not agreement.',
            ),
          const Text('Reading agreement does not establish correctness.'),
          for (final reason
              in transcription['alignment_reasons'] as List? ?? [])
            Text(labelOf(reason.toString())),
        ],
      ),
    );
  }
}
