/// The status strip above the evidence segments (screen blueprints, 6.1).
///
/// The disposition, the run and version, the stage, what blocks clearance,
/// and what the reviewer has changed but not yet saved. The run internals
/// that used to fill the record status card live behind one closed
/// disclosure, because they are an operator's concern and not a reviewer's
/// (audit finding H8.2).
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../operational_panel.dart';
import '../../review_context.dart';
import '../../theme/motion.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'blockers.dart';
import 'pending_changes.dart';

/// The compact status header of the evidence pane.
class WorkbenchStatusStrip extends StatefulWidget {
  const WorkbenchStatusStrip({
    super.key,
    required this.specimen,
    required this.blockers,
    required this.pending,
    required this.canOperate,
    required this.busy,
    required this.onAction,
    required this.onGoToBlocker,
    required this.onReviewPending,
    this.conflictVersion,
    this.onRefresh,
    this.staleChanges = const <PendingFieldChange>[],
  });

  /// The record being reviewed.
  final Specimen specimen;

  /// Everything outstanding, already collected.
  final List<ClearanceBlocker> blockers;

  /// Corrections the reviewer has made but not sent.
  final List<PendingFieldChange> pending;

  /// Corrections dropped because the field moved under the reviewer.
  final List<PendingFieldChange> staleChanges;

  /// True when this session may act on the run.
  final bool canOperate;

  /// True while a save is in flight.
  final bool busy;

  /// Sends a run action.
  final Future<void> Function(Json) onAction;

  /// Moves to the control that resolves one blocker.
  final void Function(ClearanceBlocker) onGoToBlocker;

  /// Opens the pending changes for saving.
  final VoidCallback onReviewPending;

  /// The version another reviewer saved, when one arrived under this one.
  final int? conflictVersion;

  /// Reloads the record so the reviewer can compare.
  final VoidCallback? onRefresh;

  @override
  State<WorkbenchStatusStrip> createState() => _WorkbenchStatusStripState();
}

class _WorkbenchStatusStripState extends State<WorkbenchStatusStrip> {
  bool _blockersOpen = false;

  /// The disposition this strip last drew, so a change can be told from a
  /// first paint. A record opened at Cleared was not cleared just now.
  String? _lastDisposition;

  /// True once the disposition changed while this record was open, which is
  /// the only moment in the product where a human commits an attributable,
  /// versioned decision about a museum record (motion catalog, row 50).
  bool _settled = false;

  @override
  void initState() {
    super.initState();
    _lastDisposition = widget.specimen.disposition;
  }

  @override
  void didUpdateWidget(covariant WorkbenchStatusStrip oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.specimen.id != widget.specimen.id) {
      _lastDisposition = widget.specimen.disposition;
      _settled = false;
      return;
    }
    final String? next = widget.specimen.disposition;
    if (next == _lastDisposition) return;
    _lastDisposition = next;
    if (next == null) return;
    setState(() => _settled = true);
    // Three channels, because motion is never the only one: the chip, this
    // announcement, and one medium impact on the two platforms that have
    // haptics. The reviewer is looking at the screen, so the haptic is
    // redundancy rather than the message.
    final String spoken =
        'Saved. ${SpecimenStatus.fromWire(next).semanticsLabel}';
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !MediaQuery.supportsAnnounceOf(context)) return;
      SemanticsService.sendAnnouncement(
        View.of(context),
        spoken,
        Directionality.of(context),
      );
    });
    SpecimenHaptics.decisionLanded();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Specimen s = widget.specimen;
    final Json run = objectOf(s.data['run']);
    final SpecimenStatus status = SpecimenStatus.fromWire(
      s.disposition ?? s.data['operational_state'] as String?,
    );
    final String stage = vocabularyLabel(
      textOf(run['stage'], textOf(s.data['stage'], '')),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        // Height and opacity, deliberately no shake and deliberately no
        // haptic: this is a paragraph the reviewer has to read and act on,
        // and a buzz adds urgency without adding information
        // (motion catalog, row 51).
        MotionReveal(
          visible: widget.conflictVersion != null,
          child: widget.conflictVersion == null
              ? const SizedBox(width: double.infinity)
              : Padding(
                  padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
                  child: ConflictBanner(
                    version: widget.conflictVersion!,
                    onRefresh: widget.onRefresh,
                  ),
                ),
        ),
        Wrap(
          spacing: ui.space.s2,
          runSpacing: ui.space.s2,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // Flexible, because a `Row` hands a non-flex child unbounded
                // main axis constraints and the chip's own label would then
                // never truncate.
                Flexible(child: StatusChip(status, decisive: true)),
                _SavedCheck(shown: _settled),
              ],
            ),
            // Version, Run and Step are the three words the strip uses
            // that a first-time reviewer has no way to guess, so each
            // carries its own definition (pass criterion 10.2). The values
            // beside them are identifiers, so they are set in
            // `mono.identifier` and the word beside them is not.
            _MetaPair(term: 'Version', value: '${s.revision}'),
            if (s.data['active_run_id'] != null)
              _MetaPair(term: 'Run', value: textOf(s.data['active_run_id'])),
            if (stage.isNotEmpty && stage != 'Not recorded')
              _MetaPair(term: 'Step', value: stage, identifier: false),
            if (widget.pending.isNotEmpty)
              _PendingChip(
                count: widget.pending.length,
                onPressed: widget.onReviewPending,
              ),
          ],
        ),
        MotionReveal(
          visible: widget.staleChanges.isNotEmpty,
          child: widget.staleChanges.isEmpty
              ? const SizedBox(width: double.infinity)
              : Padding(
                  padding: EdgeInsetsDirectional.only(top: ui.space.s2),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      widget.staleChanges.length == 1
                          ? '1 correction was dropped because that field '
                                'changed on the server. Make it again against '
                                'the new version.'
                          : '${widget.staleChanges.length} corrections were '
                                'dropped because those fields changed on the '
                                'server. Make them again against the new '
                                'version.',
                      style: ui.type.bodySmall.copyWith(
                        color: ui.color.status.needsReview.content,
                      ),
                    ),
                  ),
                ),
        ),
        SizedBox(height: ui.space.s2),
        _blockers(context),
        ProcessingDisclosure(
          specimen: s,
          canOperate: widget.canOperate,
          busy: widget.busy,
          onAction: widget.onAction,
        ),
      ],
    );
  }

  /// What blocks clearance: one line when nothing does, and a disclosure over
  /// the list when something does.
  ///
  /// `UiDisclosure` has no leading slot, so the amber flag that used to sit
  /// beside the summary now sits on every row inside it. The cleared form is
  /// a statement rather than a control, because a disclosure over an empty
  /// list is a control that does nothing (pass criterion 5.6).
  Widget _blockers(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<ClearanceBlocker> blockers = widget.blockers;
    final String summary = blockersSummary(blockers.length);
    if (blockers.isEmpty) {
      return Padding(
        padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s2),
        child: MergeSemantics(
          child: Row(
            children: <Widget>[
              UiIcon(
                UiIcons.cleared,
                size: UiIconSize.inline,
                color: ui.color.status.cleared.content,
              ),
              SizedBox(width: ui.space.s2),
              Flexible(child: Text(summary, style: ui.type.label)),
            ],
          ),
        ),
      );
    }
    return UiDisclosure(
      style: fullTargetDisclosure(ui),
      title: summary,
      onExpansionChanged: (bool open) => _blockersOpen = open,
      initiallyExpanded: _blockersOpen,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (final ClearanceBlocker blocker in blockers)
            _BlockerRow(
              blocker: blocker,
              onGoTo: () => widget.onGoToBlocker(blocker),
            ),
        ],
      ),
    );
  }
}

/// A word the product defines, and the value beside it.
///
/// The word carries its own definition; the value is an identifier and is set
/// in `mono.identifier` so two run ids can be told apart at a glance
/// (blueprint 6.1).
class _MetaPair extends StatelessWidget {
  const _MetaPair({
    required this.term,
    required this.value,
    this.identifier = true,
  });

  final String term;
  final String value;

  /// False where the value is a word rather than an identifier, such as the
  /// processing step.
  final bool identifier;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextStyle label = ui.type.label.copyWith(
      color: ui.color.inkSecondary,
    );
    return MergeSemantics(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          TermText(term, style: label, spokenTerm: '$term $value'),
          SizedBox(width: ui.space.s1),
          // The spoken term already carries the value, so the drawn one is
          // not a second stop that says the number twice.
          Flexible(
            child: ExcludeSemantics(
              child: Text(
                value,
                style: identifier
                    ? ui.type.mono.identifier.copyWith(
                        color: ui.color.inkSecondary,
                      )
                    : label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BlockerRow extends StatelessWidget {
  const _BlockerRow({required this.blocker, required this.onGoTo});

  final ClearanceBlocker blocker;
  final VoidCallback onGoTo;

  /// What the control that moves to the blocking field is called.
  static const String goToLabel = 'Go to';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String? detail = blocker.detail;
    return Padding(
      padding: EdgeInsetsDirectional.only(bottom: ui.space.s1),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: EdgeInsetsDirectional.only(top: ui.space.s1),
            child: UiIcon(
              UiIcons.needsReview,
              size: UiIconSize.inline,
              color: ui.color.status.needsReview.content,
            ),
          ),
          SizedBox(width: ui.space.s2),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(blocker.message, style: ui.type.body),
                if (detail != null && detail.isNotEmpty)
                  Text(
                    detail,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
              ],
            ),
          ),
          SizedBox(width: ui.space.s2),
          UiButton(
            label: goToLabel,
            variant: UiButtonVariant.ghost,
            semanticsLabel: '$goToLabel: ${blocker.message}',
            onPressed: onGoTo,
          ),
        ],
      ),
    );
  }
}

/// The amber count of corrections the reviewer has made but not sent.
///
/// A chip rather than a button, because it is a state of the record that
/// happens to be pressable, and the amber is the state (blueprint 6.4). A
/// filter chip is the only pressable chip the system has; it publishes a
/// toggle, which is recorded in the slot closeout.
class _PendingChip extends StatelessWidget {
  const _PendingChip({required this.count, required this.onPressed});

  final int count;
  final VoidCallback onPressed;

  /// What pressing it does.
  static const String action = 'Review and save these corrections';

  @override
  Widget build(BuildContext context) => UiChip(
    label: pendingChangesLabel(count),
    variant: UiChipVariant.filter,
    icon: UiIcons.editReason,
    status: context.ui.color.status.needsReview,
    semanticsLabel: '${pendingChangesLabel(count)}. $action',
    onPressed: onPressed,
  );
}

/// The banner that says the record moved under the reviewer (blueprint 6.7).
class ConflictBanner extends StatelessWidget {
  const ConflictBanner({super.key, required this.version, this.onRefresh});

  /// The version that arrived from the server.
  final int version;

  /// Reloads the record.
  final VoidCallback? onRefresh;

  /// The one sentence both the banner and the dialog use.
  static String copyFor(int version) =>
      'Version $version was saved by another reviewer. Refresh and compare.';

  /// The label on the recovery action, in both surfaces.
  static const String action = 'Refresh and compare';

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    container: true,
    child: UiBanner(
      message: copyFor(version),
      tone: UiBannerTone.needsReview,
      icon: UiIcons.syncProblem,
      actionLabel: onRefresh == null ? null : action,
      onAction: onRefresh,
    ),
  );
}

/// Asks the reviewer to refresh after a save that was not recorded
/// (blueprint 6.7). Returns true when they chose to refresh.
Future<bool> showConflictDialog(
  BuildContext context, {
  required int version,
  required bool anotherReviewer,
  required int pendingCount,
}) async =>
    await showAdaptiveModal<bool>(
      context,
      title: anotherReviewer
          ? 'This save was not recorded'
          : 'Save not confirmed',
      body: (BuildContext formContext) => _ConflictBody(
        version: version,
        anotherReviewer: anotherReviewer,
        pendingCount: pendingCount,
      ),
      primaryAction: (BuildContext formContext) => UiButton(
        label: ConflictBanner.action,
        onPressed: () => Navigator.of(formContext).pop(true),
      ),
      secondaryAction: (BuildContext formContext) => UiButton(
        label: 'Keep working',
        variant: UiButtonVariant.ghost,
        onPressed: () => Navigator.of(formContext).pop(false),
      ),
    ) ??
    false;

/// What the conflict dialog says, above its two actions.
class _ConflictBody extends StatelessWidget {
  const _ConflictBody({
    required this.version,
    required this.anotherReviewer,
    required this.pendingCount,
  });

  final int version;
  final bool anotherReviewer;
  final int pendingCount;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            anotherReviewer
                ? ConflictBanner.copyFor(version)
                : 'The server has not confirmed this decision. The displayed '
                      'record is version $version. Refresh and compare '
                      'before you try again.',
            style: ui.type.body,
          ),
          SizedBox(height: ui.space.s2),
          Text(
            pendingCount == 0
                ? 'Nothing you typed was lost.'
                : '${pendingChangesLabel(pendingCount)} are kept and will be '
                      're-applied where the field has not changed.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      ),
    );
  }
}

/// The check that marks a decision this reviewer committed
/// (motion catalog, row 50, delight moment 1).
///
/// It scales from 0.6 and fades from 0, which is the one place in the app a
/// scale is sanctioned: it is drawn once per decision, and the decision is
/// the point of the product. Under reduced motion it appears at full size.
/// It is never the only signal; the chip beside it carries the word and the
/// strip announces the new disposition.
class _SavedCheck extends StatelessWidget {
  const _SavedCheck({required this.shown});

  final bool shown;

  /// Where the scale starts. Named so the one scale in the app is one number.
  static const double from = 0.6;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final MotionTokens motion = ui.motion;
    if (!shown) return const SizedBox.shrink();
    return Padding(
      padding: EdgeInsetsDirectional.only(start: ui.space.s1),
      child: Semantics(
        label: 'Saved',
        child: TweenAnimationBuilder<double>(
          tween: Tween<double>(begin: motion.reduced ? 1 : from, end: 1),
          duration: motion.emphasized,
          curve: MotionTokens.emphasizedEnterCurve,
          builder: (BuildContext context, double value, Widget? child) =>
              Transform.scale(
                scale: value,
                child: Opacity(
                  opacity: motion.reduced ? 1 : _fade(value),
                  child: child,
                ),
              ),
          child: UiIcon(
            UiIcons.cleared,
            size: UiIconSize.inline,
            color: ui.color.status.cleared.content,
          ),
        ),
      ),
    );
  }

  /// Maps the scale value onto the opacity, so one tween drives both and the
  /// two can never desynchronise.
  static double _fade(double scale) =>
      ((scale - from) / (1 - from)).clamp(0, 1).toDouble();
}
