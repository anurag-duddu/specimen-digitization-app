/// Transient review feedback above the evidence segments.
///
/// Conflicts, pending corrections and save acknowledgments appear when
/// relevant. The strip does not repeat the record's status or provenance.
/// Status changes still receive one accessibility announcement; an autonomous
/// run change is distinct from the saved acknowledgment for a decision.
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../theme/motion.dart';
import '../../widgets/widgets.dart';
import 'blockers.dart';
import 'pending_changes.dart';

/// Corrections and save feedback for the current record.
class WorkbenchStatusStrip extends StatefulWidget {
  const WorkbenchStatusStrip({
    super.key,
    required this.specimen,
    required this.blockers,
    required this.pending,
    required this.onGoToBlocker,
    this.saved = false,
    this.conflictVersion,
    this.reconciliationMessage,
    this.reconciliationActionLabel,
    this.onRefresh,
    this.staleChanges = const <PendingFieldChange>[],
  });

  /// The record being reviewed.
  final Specimen specimen;

  /// This exact version was acknowledged after a local save.
  final bool saved;

  /// Everything outstanding, already collected.
  final List<ClearanceBlocker> blockers;

  /// Corrections the reviewer has made but not sent.
  final List<PendingFieldChange> pending;

  /// Corrections dropped because the field moved under the reviewer.
  final List<PendingFieldChange> staleChanges;

  /// Moves to the control that resolves one blocker.
  final void Function(ClearanceBlocker) onGoToBlocker;

  /// The version another reviewer saved, when one arrived under this one.
  final int? conflictVersion;

  /// A server acknowledgement whose current projection is not yet verified.
  final String? reconciliationMessage;

  /// The recovery action for this stage of reconciliation.
  final String? reconciliationActionLabel;

  /// Runs the labelled refresh or current-field comparison action.
  final VoidCallback? onRefresh;

  /// The glossary word the version fact is an instance of, so its definition
  /// is one tap from the line it is read on (13 section 3.2, polish 3; pass
  /// criterion 10.2). Drawn as the first word of the fact; the glossary reads
  /// it case insensitively.
  static const String versionTerm = 'Version';

  /// The run fact's word.
  static const String runTerm = 'Run';

  /// The step fact's word.
  static const String stepTerm = 'Step';

  @override
  State<WorkbenchStatusStrip> createState() => _WorkbenchStatusStripState();
}

class _WorkbenchStatusStripState extends State<WorkbenchStatusStrip> {
  /// Retains the last acknowledgement across drafts and recovery, so clearing
  /// those controls cannot repeat the announcement or haptic for an old save.
  (String, int, String)? _acknowledgedVersion;

  /// The last validated status, so a change the poll brings (processing to
  /// blocked, paused or cancelled) is heard once, like a decision is.
  ///
  /// Taken in `initState`, not by a lazy initialiser: the first read would
  /// otherwise happen in `didUpdateWidget`, after `widget` is already the
  /// new record, and no change would ever be seen.
  late SpecimenStatus _lastStatus;

  static SpecimenStatus _statusOf(Specimen record) => SpecimenStatus.ofRecord(
    disposition: record.disposition,
    state: record.state,
  );

  static (String, int, String) _versionOf(Specimen record) =>
      (record.id, record.revision, record.recordVersionId);

  static bool _showsSaved(WorkbenchStatusStrip strip) =>
      strip.saved &&
      strip.pending.isEmpty &&
      strip.staleChanges.isEmpty &&
      strip.reconciliationMessage == null;

  @override
  void initState() {
    super.initState();
    _lastStatus = _statusOf(widget.specimen);
    if (widget.saved) _acknowledgedVersion = _versionOf(widget.specimen);
  }

  @override
  void didUpdateWidget(covariant WorkbenchStatusStrip oldWidget) {
    super.didUpdateWidget(oldWidget);
    final SpecimenStatus status = _statusOf(widget.specimen);
    if (oldWidget.specimen.id != widget.specimen.id) {
      _lastStatus = status;
      _acknowledgedVersion = widget.saved ? _versionOf(widget.specimen) : null;
      return;
    }
    final bool statusChanged = status != _lastStatus;
    _lastStatus = status;
    final version = _versionOf(widget.specimen);
    final bool newAcknowledgement =
        widget.saved && _acknowledgedVersion != version;
    if (widget.saved) _acknowledgedVersion = version;
    if (newAcknowledgement && _showsSaved(widget)) {
      // Only the parent's acknowledged save can confirm a decision. Polling
      // a run into the queue is a status update, even when it is now cleared.
      _announce('Saved. ${status.semanticsLabel}');
      SpecimenHaptics.decisionLanded();
      return;
    }
    if (statusChanged) _announce(status.semanticsLabel);
  }

  void _announce(String spoken) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !MediaQuery.supportsAnnounceOf(context)) return;
      SemanticsService.sendAnnouncement(
        View.of(context),
        spoken,
        Directionality.of(context),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (widget.reconciliationMessage != null)
          Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
            child: Semantics(
              liveRegion: true,
              container: true,
              child: UiBanner(
                message: widget.reconciliationMessage!,
                tone: UiBannerTone.needsReview,
                icon: UiIcons.syncProblem,
                actionLabel: widget.onRefresh == null
                    ? null
                    : widget.reconciliationActionLabel ?? ConflictBanner.action,
                onAction: widget.onRefresh,
              ),
            ),
          ),
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
        MotionReveal(
          visible: widget.staleChanges.isNotEmpty,
          child: widget.staleChanges.isEmpty
              ? const SizedBox(width: double.infinity)
              : Padding(
                  padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
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
        // What the reviewer has changed and not sent. A statement of the
        // record's state and not a control: the decision bar carries the one
        // control that sends them, where a thumb can reach it from the field
        // that was just corrected (13 section 2.4).
        if (widget.pending.isNotEmpty)
          Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: _PendingChip(count: widget.pending.length),
            ),
          ),
        UiStatusStrip(
          disposition: _showsSaved(widget)
              ? Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    _SavedCheck(shown: true),
                    SizedBox(width: ui.space.s1),
                    ExcludeSemantics(
                      child: Text('Saved', style: ui.type.label),
                    ),
                  ],
                )
              : null,
          provenance: const <Widget>[],
          blockers: null,
        ),
      ],
    );
  }
}

/// The amber count of corrections the reviewer has made but not sent.
///
/// A state of the record, in the colour the state is drawn in (blueprint
/// 6.4), and nothing more: the control that sends them is the decision bar's
/// primary while there are any, which is where a reviewer's thumb already is
/// and one region per job (13 section 2.4).
class _PendingChip extends StatelessWidget {
  const _PendingChip({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) => UiChip(
    label: pendingChangesLabel(count),
    icon: UiIcons.editReason,
    status: context.ui.color.status.needsReview,
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
      'A newer version ($version) is available. Refresh and compare.';

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
