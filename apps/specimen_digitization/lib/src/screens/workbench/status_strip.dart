/// The status strip above the evidence segments (13 sections 3.2 and 4.1).
///
/// One line at the top of the evidence: where the record stands, what made
/// the reading, and what is holding a decision up. `UiStatusStrip` is the
/// pattern; this is the record's binding of it. The blockers used to be a
/// disclosure that grew the strip to five rows on a phone and are now a
/// summary that opens `UiBlockersSheet`, one row per blocker with the control
/// that clears it (13 section 3.2).
///
/// The strip scrolls with the evidence, so it costs the chrome budget
/// nothing. Two things are drawn above it and only when they exist, because
/// each is a statement about this record rather than a part of the line: the
/// conflict banner, which says the record moved under the reviewer, and the
/// corrections the reviewer has made and not yet sent.
///
/// The run internals that used to fill the record status card are an
/// operator's concern and not a reviewer's (audit finding H8.2). They are one
/// closed disclosure in the Fields segment, beside the review context, which
/// is where the blocker that names them sends the reviewer.
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../review_context.dart';
import '../../theme/motion.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'blockers.dart';
import 'pending_changes.dart';

/// Where the record stands, in one line.
class WorkbenchStatusStrip extends StatefulWidget {
  const WorkbenchStatusStrip({
    super.key,
    required this.specimen,
    required this.blockers,
    required this.pending,
    required this.onGoToBlocker,
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

  /// Moves to the control that resolves one blocker.
  final void Function(ClearanceBlocker) onGoToBlocker;

  /// The version another reviewer saved, when one arrived under this one.
  final int? conflictVersion;

  /// Reloads the record so the reviewer can compare.
  final VoidCallback? onRefresh;

  @override
  State<WorkbenchStatusStrip> createState() => _WorkbenchStatusStripState();
}

class _WorkbenchStatusStripState extends State<WorkbenchStatusStrip> {
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
    final Specimen record = widget.specimen;
    final Json run = objectOf(record.data['run']);
    final SpecimenStatus status = SpecimenStatus.fromWire(
      record.disposition ?? record.data['operational_state'] as String?,
    );
    final String stage = vocabularyLabel(
      textOf(run['stage'], textOf(record.data['stage'], '')),
    );
    final List<ClearanceBlocker> blockers = widget.blockers;

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
          disposition: _Disposition(status: status, settled: _settled),
          // The provenance, on every window with a line long enough to hold
          // it beside the two things that outrank it. A phone has 358 dp for
          // a 130 dp chip, 160 of run and version and a 180 dp summary, and
          // 11 section 3.3 rule 3 is that a control below its threshold drops
          // a variant rather than ellipsising a word to a letter. What blocks
          // clearance is stated in words at every width, because the north
          // star says a count is never a colour or a glyph alone; the run and
          // the version are what a reviewer reads at leisure, and they are in
          // the Fields segment's processing disclosure either way.
          facts: WindowClass.of(context).isCompact
              ? const <String>[]
              : <String>[
                  'Version ${record.revision}',
                  if (record.data['active_run_id'] != null)
                    'Run ${textOf(record.data['active_run_id'])}',
                  if (stage.isNotEmpty && stage != 'Not recorded')
                    'Step $stage',
                ],
          blockers: blockers.isEmpty
              ? null
              : UiBlockers(
                  summary: blockersSummary(blockers.length),
                  sheetTitle: blockersSheetTitle,
                  items: <UiBlocker>[
                    for (final ClearanceBlocker blocker in blockers)
                      UiBlocker(
                        label: blocker.message,
                        detail: blocker.detail,
                        actionLabel: goToBlockerLabel,
                        onAction: () => widget.onGoToBlocker(blocker),
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}

/// Where the record stands, and the check that marks a decision just made.
///
/// The strip's disposition slot. A `Row` that is handed a bounded width by
/// the strip, so both children are flexible: an inflexible child of a `Row`
/// is given an unbounded main axis and a chip at 200 percent text then lays
/// out at its intrinsic width and pushes the line over (11 section 3.3).
class _Disposition extends StatelessWidget {
  const _Disposition({required this.status, required this.settled});

  final SpecimenStatus status;

  /// True once the disposition changed while this record was open.
  final bool settled;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      Flexible(child: StatusChip(status, decisive: true)),
      _SavedCheck(shown: settled),
    ],
  );
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
