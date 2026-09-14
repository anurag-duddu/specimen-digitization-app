import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';
import 'vocabulary.dart';
import 'widgets/caveat_text.dart';

class OperationalPanel extends StatelessWidget {
  const OperationalPanel({
    super.key,
    required this.specimen,
    required this.canOperate,
    required this.busy,
    required this.onAction,
  });
  final Specimen specimen;
  final bool canOperate, busy;
  final Future<void> Function(Json) onAction;
  Future<void> _confirm(
    BuildContext context,
    String action,
    String label,
  ) async {
    final reason = TextEditingController();
    final form = GlobalKey<FormState>();
    final decision = await showDialog<Json>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(label),
        content: Form(
          key: form,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                action == 'reprocess'
                    ? 'A new run keeps the previous record and repeats the processing the server allows.'
                    : 'The server applies this action to the current run. Work already sent may still finish, and only current results are saved.',
              ),
              TextFormField(
                controller: reason,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Reason',
                  helperText: reasonHelperText,
                ),
                validator: (v) =>
                    v == null || v.trim().isEmpty ? reasonRequired : null,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (form.currentState!.validate()) {
                Navigator.pop(context, <String, dynamic>{
                  'kind': 'run_action',
                  'action': action,
                  'reason': reason.text.trim(),
                });
              }
            },
            child: Text(label),
          ),
        ],
      ),
    );
    // Retain controllers through the closing dialog animation.
    await Future<void>.delayed(const Duration(milliseconds: 250));
    reason.dispose();
    if (decision != null && context.mounted) await onAction(decision);
  }

  @override
  Widget build(BuildContext context) {
    final run = objectOf(specimen.data['run']);
    final usage = objectOf(run['usage']);
    final policy = objectOf(objectOf(run['profile'])['execution']);
    final blocker = textOf(
      run['blocker'],
      textOf(specimen.data['blocker'], ''),
    );
    final actions = (specimen.data['available_actions'] as List? ?? [])
        .cast<String>();
    final lease = DateTime.tryParse(textOf(run['lease_until'], ''));
    final activeLease = lease != null && lease.isAfter(DateTime.now());
    String amount(String key) =>
        usage[key] == null ? 'Not measured' : usage[key].toString();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Processing and recovery',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              'Step: ${vocabularyLabel(textOf(run['stage'], textOf(specimen.data['stage'])))}',
            ),
            if (blocker.isNotEmpty)
              Text('Blocked: ${vocabularyLabel(blocker)}'),
            if (blocker == 'pilot_evidence_review_required') ...[
              const Text(
                'Pilot evidence review needed. Check the saved label regions and '
                'the independent readings.',
              ),
              const CaveatText(
                label: 'Risk is not measured and clearance is blocked.',
                why: 'Only the corrections the server allows are available.',
              ),
            ],
            if (blocker.contains('external_outcome_unknown')) ...[
              const Text(
                'The last external request may have run. Its result is unknown.',
              ),
              const CaveatText(
                label:
                    'An authorized operator must reconcile it before anyone '
                    'retries.',
                why: 'This app never repeats the request automatically.',
              ),
            ],
            if (blocker.contains('budget') || blocker.contains('cost')) ...[
              const Text('Processing stopped at a cost limit.'),
              const CaveatText(
                label:
                    'An administrator must review the approved limit or the '
                    'provider configuration.',
                why: 'Where a cost is not recorded, it is unknown, not zero.',
              ),
            ],
            if (run['next_retry_at'] != null)
              Text('Next scheduled retry: ${run['next_retry_at']}'),
            if (run['dead_letter'] == true) ...[
              const Text('Automatic retries have stopped.'),
              Text(
                'Retrying now requires a reason.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (activeLease) ...[
              Text(
                'Reserved by the processing service until ${run['lease_until']}.',
              ),
              Text(
                'Retry, resume and new run are unavailable until then.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (usage.isNotEmpty) ...[
              Text(
                'Steps ${amount('steps')} of ${policy['max_steps'] ?? 'Not recorded'} · External requests ${amount('external_calls')} of ${policy['max_external_calls'] ?? 'Not recorded'}',
              ),
              Text(
                'Tokens ${amount('tokens')} · Reserved tokens ${amount('reserved_tokens')} · Limit ${policy['max_tokens'] ?? 'Not recorded'}',
              ),
              Text(
                'Active time ${amount('active_seconds')} seconds · Reserved time ${amount('reserved_active_seconds')} seconds',
              ),
              Text(
                'Actual cost: ${usage['actual_cost_micros'] == null ? 'Not measured' : '${usage['actual_cost_micros']} micro-units'} · Reserved cost ${amount('reserved_cost_micros')} micro-units',
              ),
              EvidenceDetails(
                title: 'Execution policy, usage and attempts',
                value: {
                  'policy': policy,
                  'usage': usage,
                  'attempts': run['attempts'],
                  'lease_until': run['lease_until'],
                },
              ),
            ],
            if (canOperate)
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final action in {
                    'pause': 'Pause processing',
                    'resume': 'Resume processing',
                    'cancel': 'Cancel processing',
                    'reprocess': 'Start new run',
                  }.entries)
                    if (actions.contains(action.key))
                      OutlinedButton(
                        onPressed:
                            busy ||
                                (activeLease &&
                                    [
                                      'resume',
                                      'reprocess',
                                    ].contains(action.key))
                            ? null
                            : () => _confirm(context, action.key, action.value),
                        child: Text(action.value),
                      ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
