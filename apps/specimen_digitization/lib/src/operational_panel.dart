/// Processing and recovery (screen blueprints, section 8).
///
/// Closed, this says the stage and, if the run is blocked, the blocker in
/// plain words with the next retry time. Open, it lists the attempts, the
/// usage as labelled values with units, and only the run actions the server
/// permits. A measurement the server did not record is never rendered as
/// zero, and an action the server forbids is never rendered at all.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'models.dart';
import 'review_context.dart';
import 'screens/workbench/moments.dart';
import 'theme/icons.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// The run actions this client can ask for, and the verb it uses for each.
const Map<String, String> runActionLabels = <String, String>{
  'pause': 'Pause processing',
  'resume': 'Resume processing',
  'cancel': 'Cancel processing',
  'reprocess': 'Start new run',
};

/// The closed by default "Processing" disclosure in the status strip.
class ProcessingDisclosure extends StatelessWidget {
  const ProcessingDisclosure({
    super.key,
    required this.specimen,
    required this.canOperate,
    required this.busy,
    required this.onAction,
  });

  final Specimen specimen;
  final bool canOperate;
  final bool busy;
  final Future<void> Function(Json) onAction;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Json run = objectOf(specimen.data['run']);
    final String blocker = textOf(
      run['blocker'],
      textOf(specimen.data['blocker'], ''),
    );
    final String stage = vocabularyLabel(
      textOf(run['stage'], textOf(specimen.data['stage'], '')),
    );
    final String retry = run['next_retry_at'] == null
        ? ''
        : ' Next retry ${relativeInstant(run['next_retry_at'])}.';
    final String summary = blocker.isEmpty || blocker == 'Not recorded'
        ? 'Step $stage'
        : 'Step $stage. Blocked: ${vocabularyLabel(blocker)}.$retry';

    return ExpansionTile(
      title: const Text('Processing'),
      subtitle: Text(summary, style: theme.textTheme.bodySmall),
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.only(bottom: context.space.space2),
      children: <Widget>[
        ProcessingDetail(
          specimen: specimen,
          canOperate: canOperate,
          busy: busy,
          onAction: onAction,
        ),
      ],
    );
  }
}

/// The run detail: what happened, what it cost, and what may be done next.
class ProcessingDetail extends StatelessWidget {
  const ProcessingDetail({
    super.key,
    required this.specimen,
    required this.canOperate,
    required this.busy,
    required this.onAction,
  });

  final Specimen specimen;
  final bool canOperate;
  final bool busy;
  final Future<void> Function(Json) onAction;

  Future<void> _confirm(
    BuildContext context,
    String action,
    String label,
  ) async {
    final String? reason = await showReasonSheet(
      context,
      title: '$label?',
      action: label,
      consequence: action == 'reprocess'
          ? 'A new run keeps the previous record and repeats the processing '
                'the server allows.'
          : 'The server applies this action to the current run. Work already '
                'sent may still finish, and only current results are saved.',
      retained: 'Earlier evidence and decisions stay in history.',
    );
    if (reason == null || !context.mounted) return;
    await onAction(<String, dynamic>{
      'kind': 'run_action',
      'action': action,
      'reason': reason,
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Json run = objectOf(specimen.data['run']);
    final Json usage = objectOf(run['usage']);
    final Json policy = objectOf(objectOf(run['profile'])['execution']);
    final Json attempts = objectOf(run['attempts']);
    final String blocker = textOf(
      run['blocker'],
      textOf(specimen.data['blocker'], ''),
    );
    final List<String> actions =
        (specimen.data['available_actions'] as List? ?? <Object?>[])
            .map((Object? a) => a.toString())
            .toList();
    final DateTime? lease = DateTime.tryParse(textOf(run['lease_until'], ''));
    final bool activeLease = lease != null && lease.isAfter(DateTime.now());
    final String? currency = run['cost_currency'] as String?;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (blocker.isNotEmpty && blocker != 'Not recorded')
          Text(
            'Blocked: ${vocabularyLabel(blocker)}',
            style: theme.textTheme.titleSmall,
          ),
        if (blocker == 'pilot_evidence_review_required') ...<Widget>[
          const Text(
            'Pilot evidence review needed. Check the saved label regions and '
            'the independent readings.',
          ),
          const CaveatText(
            label: 'Risk is not measured and clearance is blocked.',
            why: 'Only the corrections the server allows are available.',
          ),
        ],
        if (blocker.contains('external_outcome_unknown')) ...<Widget>[
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
        if (blocker.contains('budget') || blocker.contains('cost')) ...<Widget>[
          const Text('Processing stopped at a cost limit.'),
          const CaveatText(
            label:
                'An administrator must review the approved limit or the '
                'provider configuration.',
            why: 'Where a cost is not recorded, it is unknown, not zero.',
          ),
        ],
        if (run['next_retry_at'] != null)
          _Measurement(
            label: 'Next scheduled retry',
            value: relativeInstant(run['next_retry_at']),
          ),
        if (run['dead_letter'] == true) ...<Widget>[
          const Text('Automatic retries have stopped.'),
          Text(
            'Retrying now requires a reason.',
            style: theme.textTheme.bodySmall,
          ),
        ],
        if (activeLease) ...<Widget>[
          _Measurement(
            label: 'Reserved by the processing service until',
            value: relativeInstant(run['lease_until']),
          ),
          Text(
            'Retry, resume and new run are unavailable until then.',
            style: theme.textTheme.bodySmall,
          ),
        ],
        if (attempts.isNotEmpty) ...<Widget>[
          SizedBox(height: context.space.space2),
          Text('Attempts', style: theme.textTheme.titleSmall),
          for (final MapEntry<String, dynamic> attempt in attempts.entries)
            _Measurement(
              label: vocabularyLabel(attempt.key.split(':').first),
              value: attempt.value == null
                  ? 'Not recorded'
                  : '${attempt.value} ${attempt.value == 1 ? 'attempt' : 'attempts'}',
              detail: attempt.key.contains(':') ? attempt.key : null,
            ),
        ],
        if (usage.isNotEmpty) ...<Widget>[
          SizedBox(height: context.space.space2),
          Text('Usage', style: theme.textTheme.titleSmall),
          _Measurement(
            label: 'Steps',
            value: _count(usage['steps'], policy['max_steps'], 'steps'),
          ),
          _Measurement(
            label: 'External requests',
            value: _count(
              usage['external_calls'],
              policy['max_external_calls'],
              'requests',
            ),
          ),
          _Measurement(
            label: 'Model units',
            value: _count(usage['tokens'], policy['max_tokens'], 'units'),
          ),
          _Measurement(
            label: 'Reserved model units',
            value: _plain(usage['reserved_tokens'], 'units'),
          ),
          _Measurement(
            label: 'Active time',
            value: _plain(usage['active_seconds'], 'seconds'),
          ),
          _Measurement(
            label: 'Reserved active time',
            value: _plain(usage['reserved_active_seconds'], 'seconds'),
          ),
          _Measurement(
            label: 'Actual cost',
            value: _cost(usage['actual_cost_micros'], currency),
          ),
          _Measurement(
            label: 'Reserved cost',
            value: _cost(usage['reserved_cost_micros'], currency),
          ),
          if (currency == null)
            const CaveatText(
              label: 'Cost is recorded in micro-units, not in a currency.',
              why:
                  'The server did not send a currency for this run, so the '
                  'client does not convert one. A cost the server did not '
                  'record is shown as not recorded, never as zero.',
            ),
          EvidenceDrawer(
            title: 'Execution policy, usage and attempts',
            payload: <String, dynamic>{
              'policy': policy,
              'usage': usage,
              'attempts': run['attempts'],
              'lease_until': run['lease_until'],
            },
          ),
        ],
        if (canOperate)
          Wrap(
            spacing: context.space.space2,
            runSpacing: context.space.space2,
            children: <Widget>[
              // Only the actions the server permits are rendered at all. A
              // permitted action that is blocked right now renders disabled
              // with the reason on it (accessibility, 3.2).
              for (final MapEntry<String, String> action
                  in runActionLabels.entries)
                if (actions.contains(action.key))
                  _RunAction(
                    label: action.value,
                    reason: _blockedReason(
                      action.key,
                      busy: busy,
                      activeLease: activeLease,
                      leaseUntil: run['lease_until'],
                    ),
                    onPressed: () =>
                        _confirm(context, action.key, action.value),
                  ),
            ],
          ),
      ],
    );
  }

  static String? _blockedReason(
    String action, {
    required bool busy,
    required bool activeLease,
    required Object? leaseUntil,
  }) {
    if (busy) return 'Wait for the save that is in flight to finish';
    if (activeLease && <String>['resume', 'reprocess'].contains(action)) {
      return 'The processing service holds this run until '
          '${relativeInstant(leaseUntil)}';
    }
    return null;
  }

  /// A measured count against its policy limit, where both are recorded.
  static String _count(Object? value, Object? limit, String unit) {
    if (value == null) return 'Not recorded';
    if (limit == null) return '$value $unit, no limit recorded';
    return '$value of $limit $unit';
  }

  static String _plain(Object? value, String unit) =>
      value == null ? 'Not recorded' : '$value $unit';

  /// Cost renders as currency when the server sends a unit, and never as zero
  /// when it sends nothing (blueprint 8).
  static String _cost(Object? micros, String? currency) {
    if (micros == null) return 'Not recorded';
    if (currency == null) return '$micros micro-units';
    final double amount = (micros as num) / 1000000;
    return '${amount.toStringAsFixed(2)} $currency';
  }
}

/// One labelled value with its unit, never a bare number.
class _Measurement extends StatelessWidget {
  const _Measurement({required this.label, required this.value, this.detail});

  final String label;
  final String value;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return MergeSemantics(
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: context.space.space1),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    label,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  if (detail != null)
                    Text(detail!, style: context.mono.identifier),
                ],
              ),
            ),
            SizedBox(width: context.space.space2),
            Text(value, style: theme.textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}

/// One run action, disabled with its reason rather than silently inert.
class _RunAction extends StatelessWidget {
  const _RunAction({
    required this.label,
    required this.reason,
    required this.onPressed,
  });

  final String label;
  final String? reason;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => Tooltip(
    message: reason ?? label,
    child: Semantics(
      hint: reason ?? '',
      child: OutlinedButton(
        onPressed: reason == null ? onPressed : null,
        child: Text(label),
      ),
    ),
  );
}

/// The processing card, as the large record fallback still shows it.
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

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: EdgeInsets.all(context.space.space4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Symbols.settings, size: context.sizes.iconInline),
              SizedBox(width: context.space.space2),
              Text(
                'Processing and recovery',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ],
          ),
          SizedBox(height: context.space.space2),
          ProcessingDetail(
            specimen: specimen,
            canOperate: canOperate,
            busy: busy,
            onAction: onAction,
          ),
        ],
      ),
    ),
  );
}
