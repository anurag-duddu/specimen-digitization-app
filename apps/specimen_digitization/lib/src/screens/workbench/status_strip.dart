/// The status strip above the evidence segments (screen blueprints, 6.1).
///
/// The disposition, the run and version, the stage, what blocks clearance,
/// and what the reviewer has changed but not yet saved. The run internals
/// that used to fill the record status card live behind one closed
/// disclosure, because they are an operator's concern and not a reviewer's
/// (audit finding H8.2).
library;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../models.dart';
import '../../operational_panel.dart';
import '../../review_context.dart';
import '../../theme/icons.dart';
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
    final ThemeData theme = Theme.of(context);
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
                  padding: EdgeInsets.only(bottom: context.space.space2),
                  child: ConflictBanner(
                    version: widget.conflictVersion!,
                    onRefresh: widget.onRefresh,
                  ),
                ),
        ),
        Wrap(
          spacing: context.space.space2,
          runSpacing: context.space.space2,
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
            Text(
              'Version ${s.revision}',
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (s.data['active_run_id'] != null)
              Text(
                'Run ${textOf(s.data['active_run_id'])}',
                style: theme.textTheme.labelMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            if (stage.isNotEmpty && stage != 'Not recorded')
              Text(
                'Step $stage',
                style: theme.textTheme.labelMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
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
                  padding: EdgeInsets.only(top: context.space.space2),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      widget.staleChanges.length == 1
                          ? '1 correction was dropped because that field changed on the '
                                'server. Make it again against the new version.'
                          : '${widget.staleChanges.length} corrections were dropped '
                                'because those fields changed on the server. Make them '
                                'again against the new version.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: context.tokens.needsReviewContent,
                      ),
                    ),
                  ),
                ),
        ),
        SizedBox(height: context.space.space2),
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

  Widget _blockers(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<ClearanceBlocker> blockers = widget.blockers;
    final bool clear = blockers.isEmpty;
    final Widget list = _blockersOpen && !clear
        ? Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              for (final ClearanceBlocker blocker in blockers)
                _BlockerRow(
                  blocker: blocker,
                  onGoTo: () => widget.onGoToBlocker(blocker),
                ),
            ],
          )
        : const SizedBox(width: double.infinity);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        MergeSemantics(
          child: Semantics(
            expanded: clear ? null : _blockersOpen,
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton.icon(
                onPressed: clear
                    ? null
                    : () => setState(() => _blockersOpen = !_blockersOpen),
                icon: Icon(
                  clear ? Symbols.check_circle : Symbols.flag,
                  color: clear
                      ? context.tokens.clearedContent
                      : context.tokens.needsReviewContent,
                ),
                label: Text(
                  blockersSummary(blockers.length),
                  style: theme.textTheme.titleSmall,
                ),
              ),
            ),
          ),
        ),
        if (context.motion.reduced)
          list
        else
          AnimatedSize(
            duration: context.motion.standard,
            curve: MotionTokens.standardCurve,
            alignment: Alignment.topLeft,
            child: list,
          ),
      ],
    );
  }
}

class _BlockerRow extends StatelessWidget {
  const _BlockerRow({required this.blocker, required this.onGoTo});

  final ClearanceBlocker blocker;
  final VoidCallback onGoTo;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? detail = blocker.detail;
    return Padding(
      padding: EdgeInsets.only(bottom: context.space.space1),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: EdgeInsets.only(top: context.space.space1),
            child: Icon(
              Symbols.flag,
              size: context.sizes.iconInline,
              color: context.tokens.needsReviewContent,
            ),
          ),
          SizedBox(width: context.space.space2),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(blocker.message, style: theme.textTheme.bodyMedium),
                if (detail != null && detail.isNotEmpty)
                  Text(
                    detail,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
              ],
            ),
          ),
          SizedBox(width: context.space.space2),
          TextButton(onPressed: onGoTo, child: const Text('Go to')),
        ],
      ),
    );
  }
}

class _PendingChip extends StatelessWidget {
  const _PendingChip({required this.count, required this.onPressed});

  final int count;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => ActionChip(
    avatar: Icon(
      Symbols.edit_note,
      size: context.sizes.iconInline,
      color: context.tokens.needsReviewOnFill,
    ),
    backgroundColor: context.tokens.needsReviewFill,
    side: BorderSide(
      color: context.tokens.needsReviewContent,
      width: context.shape.strokeBoundary,
    ),
    labelStyle: Theme.of(
      context,
    ).textTheme.labelMedium?.copyWith(color: context.tokens.needsReviewOnFill),
    label: Text(pendingChangesLabel(count)),
    tooltip: 'Review and save these corrections',
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
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      liveRegion: true,
      container: true,
      child: Container(
        padding: EdgeInsets.all(context.space.space3),
        decoration: BoxDecoration(
          color: context.tokens.needsReviewFill,
          borderRadius: BorderRadius.circular(context.shape.radiusSm),
          border: Border.all(
            color: context.tokens.needsReviewContent,
            width: context.shape.strokeBoundary,
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(
              Symbols.sync_problem,
              size: context.sizes.iconInline,
              color: context.tokens.needsReviewOnFill,
            ),
            SizedBox(width: context.space.space2),
            Expanded(
              child: Text(
                copyFor(version),
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: context.tokens.needsReviewOnFill,
                ),
              ),
            ),
            if (onRefresh != null)
              TextButton(onPressed: onRefresh, child: const Text(action)),
          ],
        ),
      ),
    );
  }
}

/// Asks the reviewer to refresh after a save that was not recorded
/// (blueprint 6.7). Returns true when they chose to refresh.
Future<bool> showConflictDialog(
  BuildContext context, {
  required int version,
  required bool anotherReviewer,
  required int pendingCount,
}) async =>
    await showAdaptiveForm<bool>(
      context,
      width: DialogWidths.standard,
      builder: (BuildContext formContext) => Padding(
        padding: EdgeInsets.all(formContext.space.space6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              anotherReviewer
                  ? 'This save was not recorded'
                  : 'Save not confirmed',
              style: Theme.of(formContext).textTheme.titleLarge,
            ),
            SizedBox(height: formContext.space.space2),
            Text(
              anotherReviewer
                  ? ConflictBanner.copyFor(version)
                  : 'The server has not confirmed this decision. The displayed '
                        'record is version $version. Refresh and compare '
                        'before you try again.',
            ),
            SizedBox(height: formContext.space.space2),
            Text(
              pendingCount == 0
                  ? 'Nothing you typed was lost.'
                  : '${pendingChangesLabel(pendingCount)} are kept and will be '
                        're-applied where the field has not changed.',
              style: Theme.of(formContext).textTheme.bodySmall,
            ),
            SizedBox(height: formContext.space.space6),
            Wrap(
              alignment: WrapAlignment.end,
              spacing: formContext.space.space2,
              children: <Widget>[
                TextButton(
                  onPressed: () => Navigator.of(formContext).pop(false),
                  child: const Text('Keep working'),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(formContext).pop(true),
                  child: const Text(ConflictBanner.action),
                ),
              ],
            ),
          ],
        ),
      ),
    ) ??
    false;

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
    final MotionTokens motion = context.motion;
    if (!shown) return const SizedBox.shrink();
    return Padding(
      padding: EdgeInsetsDirectional.only(start: context.space.space1),
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
          child: Icon(
            Symbols.check_circle,
            size: context.sizes.iconInline,
            color: context.tokens.clearedContent,
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
