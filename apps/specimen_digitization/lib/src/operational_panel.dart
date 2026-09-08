import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';

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
                    ? 'A new run preserves the previous record and repeats eligible processing under the server policy.'
                    : 'The server will apply this action to the current run. In-flight external work may finish; only valid current results can be committed.',
              ),
              TextFormField(
                controller: reason,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Reason for run action',
                ),
                validator: (v) => v == null || v.trim().isEmpty
                    ? 'A reason is required.'
                    : null,
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
              'Stage: ${labelOf(textOf(run['stage'], textOf(specimen.data['stage'])))}',
            ),
            if (blocker.isNotEmpty) Text('Blocked: ${labelOf(blocker)}'),
            if (blocker == 'pilot_evidence_review_required')
              const Text(
                'Pilot evidence review needed. Inspect the retained regions and independent readings. Risk is unmeasured and clearance is blocked; only corrections permitted by the server are available.',
              ),
            if (blocker.contains('external_outcome_unknown'))
              const Text(
                'The last external request may have executed. Its outcome is unknown. An authorized operator must reconcile that request before deliberately retrying; the client never repeats it automatically.',
              ),
            if (blocker.contains('budget') || blocker.contains('cost'))
              const Text(
                'Processing stopped at a budget or cost-policy gate. An administrator must review the approved limit or provider configuration. Missing cost information is not zero cost.',
              ),
            if (run['next_retry_at'] != null)
              Text('Next scheduled retry: ${run['next_retry_at']}'),
            if (run['dead_letter'] == true)
              const Text(
                'Automatic attempts exhausted. Authorized recovery requires an explicit reason.',
              ),
            if (activeLease)
              Text(
                'External work is leased until ${run['lease_until']}. Retry, resume and new-run requests must wait for the lease to end.',
              ),
            if (usage.isNotEmpty) ...[
              Text(
                'Steps ${amount('steps')} / ${policy['max_steps'] ?? 'limit unavailable'} · External requests ${amount('external_calls')} / ${policy['max_external_calls'] ?? 'limit unavailable'}',
              ),
              Text(
                'Tokens ${amount('tokens')} · Reserved tokens ${amount('reserved_tokens')} · Limit ${policy['max_tokens'] ?? 'unavailable'}',
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
