/// The status strip above the evidence segments (screen blueprints, 6.1).
///
/// The disposition, the run and version, the stage, what blocks clearance,
/// and what the reviewer has changed but not yet saved. The run internals
/// that used to fill the record status card live behind one closed
/// disclosure, because they are an operator's concern and not a reviewer's
/// (audit finding H8.2).
library;

import 'package:flutter/material.dart';
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
        if (widget.conflictVersion != null)
          Padding(
            padding: EdgeInsets.only(bottom: context.space.space2),
            child: ConflictBanner(
              version: widget.conflictVersion!,
              onRefresh: widget.onRefresh,
            ),
          ),
        Wrap(
          spacing: context.space.space2,
          runSpacing: context.space.space2,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            StatusChip(status),
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
        if (widget.staleChanges.isNotEmpty) ...<Widget>[
          SizedBox(height: context.space.space2),
          Semantics(
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
        ],
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
