/// Processing and recovery (screen blueprints, section 8).
///
/// Closed, this says the stage and, if the run is blocked, the blocker in
/// plain words with the next retry time. Open, it lists the attempts, the
/// usage as labelled values with units, and only the run actions the server
/// permits. A measurement the server did not record is never rendered as
/// zero, and an action the server forbids is never rendered at all. From the
/// thread it names where the run came from: the run, its profile, the
/// policy, and the trace with "Open trace" (UI.md T2.5).
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:url_launcher/link.dart';

import 'administrator_contact.dart';
import 'models.dart';
import 'review_context.dart';
import 'screens/workbench/moments.dart';
import 'thread/thread.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// The run actions this client can ask for, and the verb it uses for each.
const Map<String, String> runActionLabels = <String, String>{
  'pause': 'Pause processing',
  'resume': 'Resume processing',
  'cancel': 'Cancel processing',
  'reprocess': 'Start new run',
};

/// How consequential each run action is, which is what picks its variant
/// (blueprint 8): pausing and resuming are reversible, cancelling ends work
/// that is running, and a new run is the one thing an operator comes here to
/// start.
const Map<String, UiButtonVariant> runActionVariants =
    <String, UiButtonVariant>{
      'pause': UiButtonVariant.secondary,
      'resume': UiButtonVariant.secondary,
      'cancel': UiButtonVariant.danger,
      'reprocess': UiButtonVariant.primary,
    };

/// The closed by default "Processing" disclosure in the status strip.
class ProcessingDisclosure extends StatelessWidget {
  const ProcessingDisclosure({
    super.key,
    required this.specimen,
    required this.canOperate,
    required this.busy,
    required this.onAction,
    this.thread,
  });

  final Specimen specimen;
  final bool canOperate;
  final bool busy;
  final Future<void> Function(Json) onAction;

  /// The run's thread, when it has loaded (UI.md T2.5).
  final SpecimenThread? thread;

  /// The disclosure's own title, fixed so the strip and its tests agree.
  static const String title = 'Processing';

  @override
  Widget build(BuildContext context) {
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
    // A record whose run has not reported a step renders "Step not recorded"
    // rather than the word "Step" with nothing after it. An absence is a
    // state with a name, never a sentence that stops halfway.
    final String step = stage.isEmpty || stage == 'Not recorded'
        ? 'Step not recorded'
        : 'Step $stage';
    final String summary = blocker.isEmpty || blocker == 'Not recorded'
        ? step
        : '$step. Blocked: ${vocabularyLabel(blocker)}.$retry';

    return UiDisclosure(
      title: title,
      summary: summary,
      child: ProcessingDetail(
        specimen: specimen,
        canOperate: canOperate,
        busy: busy,
        onAction: onAction,
        thread: thread,
      ),
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
    this.thread,
  });

  final Specimen specimen;
  final bool canOperate;
  final bool busy;
  final Future<void> Function(Json) onAction;

  /// The run's thread, which names where the run came from (UI.md T2.5).
  final SpecimenThread? thread;

  /// The labels of the run's provenance.
  static const String runLabel = 'Run';
  static const String profileLabel = 'Profile';
  static const String policyLabel = 'Policy';
  static const String traceLabel = 'Trace';

  /// The control that opens the run's trace in Logfire.
  static const String openTraceLabel = 'Open trace';

  /// What the control that copies the trace id is called.
  static const String copyTraceLabel = 'Copy the trace ID';

  /// What the toast says once the trace id is on the clipboard.
  static const String traceCopiedMessage = 'Trace ID copied';

  /// A run that recorded no trace.
  static const String noTrace = 'No trace recorded';

  /// The blocker of a run stopped by the program's spent allowance (G30).
  static const String allowanceBlocker = 'program_allowance_exhausted';

  /// That run's plain words: the allowance, with the amount the thread
  /// records, is spent, and processing resumes when the owner raises it
  /// (the coordinator's wording, 2026-09-23). Without an amount, none is
  /// named.
  static String allowanceSpent(int? micros) {
    final String allowance = micros == null
        ? 'The model allowance'
        : 'The USD ${(micros / 1000000).toStringAsFixed(2)} model allowance';
    return '$allowance for this program is spent. '
        'Processing resumes when the owner raises it.';
  }

  /// The blocker of a run the lane never starts, because the upload was
  /// declared Sensitive (UI.md T3.1; PLAN section 2.2).
  static const String sensitiveBlocker = 'sensitive_record_not_processed';

  /// That record's plain words: it is not processed, never "waiting", and
  /// how to have it processed, since sensitivity cannot be changed.
  static const String sensitiveNotProcessed =
      'This record was uploaded as sensitive, so it is not processed. To have '
      'it processed, upload the photograph again as not sensitive.';

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
    final UiThemeData ui = context.ui;
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
          Text('Blocked: ${vocabularyLabel(blocker)}', style: ui.type.label),
        if (blocker == 'pilot_evidence_review_required') ...<Widget>[
          Text(
            'Pilot evidence review needed. Check the saved label regions and '
            'the independent readings.',
            style: ui.type.body,
          ),
          const CaveatText(
            label: 'Risk is not measured and clearance is blocked.',
            why: 'Only the corrections the server allows are available.',
          ),
        ],
        if (blocker.contains('external_outcome_unknown')) ...<Widget>[
          Text(
            'The last external request may have run. Its result is unknown.',
            style: ui.type.body,
          ),
          const CaveatText(
            label:
                'An authorized operator must reconcile it before anyone '
                'retries.',
            why: 'This app never repeats the request automatically.',
          ),
        ],
        if (blocker.contains('budget') || blocker.contains('cost')) ...<Widget>[
          Text('Processing stopped at a cost limit.', style: ui.type.body),
          const CaveatText(
            label:
                'An administrator must review the approved limit or the '
                'provider configuration.',
            why: 'Where a cost is not recorded, it is unknown, not zero.',
          ),
          const AdministratorContactLine(),
        ],
        if (blocker == allowanceBlocker) ...<Widget>[
          Text(
            allowanceSpent(thread?.run.allowanceMicros),
            style: ui.type.body,
          ),
          const AdministratorContactLine(),
        ],
        if (blocker == sensitiveBlocker)
          Text(sensitiveNotProcessed, style: ui.type.body),
        if (run['next_retry_at'] != null)
          _Measurement(
            label: 'Next scheduled retry',
            value: relativeInstant(run['next_retry_at']),
          ),
        if (run['dead_letter'] == true) ...<Widget>[
          Text('Automatic retries have stopped.', style: ui.type.body),
          Text(
            'Retrying now requires a reason.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
        if (activeLease) ...<Widget>[
          _Measurement(
            label: 'Reserved by the processing service until',
            value: relativeInstant(run['lease_until']),
          ),
          Text(
            'Retry, resume and new run are unavailable until then.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
        if (thread case final SpecimenThread loaded) ..._provenance(ui, loaded),
        if (attempts.isNotEmpty) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Text('Attempts', style: ui.type.label),
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
          SizedBox(height: ui.space.s2),
          Text('Usage', style: ui.type.label),
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
          _runActions(context, actions, run, activeLease: activeLease),
      ],
    );
  }

  /// Where the run came from: the run, its profile and version, the policy
  /// the queue decided under, and its trace (UI.md T2.5). A part the thread
  /// does not carry is left out rather than drawn empty.
  static List<Widget> _provenance(UiThemeData ui, SpecimenThread thread) {
    final ThreadRun run = thread.run;
    final String? profile = switch (run.profileKey) {
      final String key => <String>[
        vocabularyLabel(key),
        ?run.profileVersion,
      ].join(' '),
      null => null,
    };
    return <Widget>[
      SizedBox(height: ui.space.s2),
      if (run.runId case final String id)
        _Measurement(label: runLabel, value: id),
      if (profile != null) _Measurement(label: profileLabel, value: profile),
      if (thread.decision?.policyVersion case final String policy)
        _Measurement(label: policyLabel, value: policy),
      _TraceLine(trace: thread.trace),
    ];
  }

  /// The permitted run actions, arranged by `UiButtonRow`.
  ///
  /// Only the actions the server permits are rendered at all. A permitted
  /// action that is blocked right now renders disabled with the reason on it
  /// (accessibility, 3.2; blueprint 8).
  Widget _runActions(
    BuildContext context,
    List<String> actions,
    Json run, {
    required bool activeLease,
  }) {
    final List<UiButton> permitted = <UiButton>[
      for (final MapEntry<String, String> action in runActionLabels.entries)
        if (actions.contains(action.key))
          UiButton(
            label: action.value,
            variant: runActionVariants[action.key] ?? UiButtonVariant.secondary,
            disabledReason: _blockedReason(
              action.key,
              busy: busy,
              activeLease: activeLease,
              leaseUntil: run['lease_until'],
            ),
            onPressed:
                _blockedReason(
                      action.key,
                      busy: busy,
                      activeLease: activeLease,
                      leaseUntil: run['lease_until'],
                    ) ==
                    null
                ? () => _confirm(context, action.key, action.value)
                : null,
          ),
    ];
    if (permitted.isEmpty) return const SizedBox.shrink();
    // The row draws its primary last, so the map's order survives left to
    // right and "Start new run" ends up where an operator looks for it.
    return Padding(
      padding: EdgeInsetsDirectional.only(top: context.ui.space.s2),
      child: UiButtonRow(
        primary: permitted.last,
        secondary: permitted.length >= 2
            ? permitted[permitted.length - 2]
            : null,
        tertiary: permitted.sublist(0, math.max(0, permitted.length - 2)),
      ),
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
    final UiThemeData ui = context.ui;
    return MergeSemantics(
      child: Padding(
        padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s1),
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
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                  if (detail != null)
                    Text(
                      detail!,
                      style: ui.type.mono.identifier.copyWith(
                        color: ui.color.inkSecondary,
                      ),
                    ),
                ],
              ),
            ),
            SizedBox(width: ui.space.s2),
            Text(value, style: ui.type.body),
          ],
        ),
      ),
    );
  }
}

/// The run's trace: its id, which can be copied, and "Open trace", a link to
/// it in Logfire (UI.md T2.5). The model keeps the address only when it is
/// an absolute https URL, so nothing else the payload carries becomes a
/// link. A trace id without an address is still named, and a run with
/// neither says so.
class _TraceLine extends StatelessWidget {
  const _TraceLine({required this.trace});

  final ThreadTrace trace;

  Future<void> _copy(BuildContext context, String id) async {
    await Clipboard.setData(ClipboardData(text: id));
    if (!context.mounted) return;
    UiToasts.show(
      context,
      message: ProcessingDetail.traceCopiedMessage,
      icon: UiIcons.copy,
    );
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String? id = trace.traceId;
    final Uri? url = trace.url;
    final TextStyle secondary = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );
    return Padding(
      padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s1),
      child: id == null && url == null
          ? Text(ProcessingDetail.noTrace, style: secondary)
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(ProcessingDetail.traceLabel, style: secondary),
                if (id != null)
                  Row(
                    children: <Widget>[
                      Expanded(child: Text(id, style: ui.type.mono.identifier)),
                      UiIconButton(
                        icon: UiIcons.copy,
                        semanticsLabel: ProcessingDetail.copyTraceLabel,
                        tooltip: ProcessingDetail.copyTraceLabel,
                        onPressed: () => unawaited(_copy(context, id)),
                      ),
                    ],
                  ),
                if (url != null)
                  // A real link on the web, opening in a new tab; the system
                  // browser elsewhere.
                  Link(
                    uri: url,
                    target: LinkTarget.blank,
                    builder: (BuildContext context, FollowLink? follow) =>
                        UiButton(
                          label: ProcessingDetail.openTraceLabel,
                          variant: UiButtonVariant.secondary,
                          onPressed: follow,
                        ),
                  ),
              ],
            ),
    );
  }
}

/// The processing card, as the large record fallback still shows it.
class OperationalPanel extends StatelessWidget {
  const OperationalPanel({
    super.key,
    required this.specimen,
    required this.canOperate,
    required this.busy,
    required this.onAction,
    this.thread,
  });

  final Specimen specimen;
  final bool canOperate, busy;
  final Future<void> Function(Json) onAction;

  /// The run's thread, when it has loaded (UI.md T2.5).
  final SpecimenThread? thread;

  /// The pane's own heading.
  static const String heading = 'Processing and recovery';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Surface(
      radius: ui.shape.tile,
      hairline: true,
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            children: <Widget>[
              const UiIcon(UiIcons.settings, size: UiIconSize.inline),
              SizedBox(width: ui.space.s2),
              Expanded(
                child: Semantics(
                  container: true,
                  header: true,
                  child: Text(heading, style: ui.type.title),
                ),
              ),
            ],
          ),
          SizedBox(height: ui.space.s2),
          ProcessingDetail(
            specimen: specimen,
            canOperate: canOperate,
            busy: busy,
            onAction: onAction,
            thread: thread,
          ),
        ],
      ),
    );
  }
}
