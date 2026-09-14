/// The decision bar (screen blueprints, 6.1; responsive 3.5).
///
/// The two actions the reviewer is here for never scroll away, and neither is
/// ever a silent no-op: when the server does not permit one, the button
/// carries the reason as a tooltip and as a semantic hint rather than a bare
/// disabled state (accessibility, 2.2 finding 3; pass criterion 5.6).
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../theme/icons.dart';
import '../../widgets/widgets.dart';
import 'pending_changes.dart';

/// The pinned bar at the foot of the evidence pane.
class WorkbenchDecisionBar extends StatelessWidget {
  const WorkbenchDecisionBar({
    super.key,
    required this.onConfirmCoverage,
    required this.onApprove,
    required this.coverageBlockedReason,
    required this.approveBlockedReason,
    required this.pendingCount,
    required this.onSavePending,
    this.onNext,
    this.onPrevious,
    this.compact = false,
    this.busy = false,
  });

  /// Opens the coverage reason sheet.
  final VoidCallback onConfirmCoverage;

  /// Opens the approval reason sheet.
  final VoidCallback onApprove;

  /// Why coverage cannot be confirmed, or null when it can.
  final String? coverageBlockedReason;

  /// Why the record cannot be approved, or null when it can.
  final String? approveBlockedReason;

  /// How many corrections are waiting to be sent.
  final int pendingCount;

  /// Saves them, with one reason.
  final VoidCallback onSavePending;

  /// The next specimen in the queue, when the host offers one.
  final VoidCallback? onNext;

  /// The previous specimen in the queue, when the host offers one.
  final VoidCallback? onPrevious;

  /// True on a stacked layout, where the bar is full width above the
  /// navigation bar rather than right aligned in a pane.
  final bool compact;

  /// True while a decision is in flight.
  ///
  /// The pressed button reports it inline and keeps its width; nothing is
  /// dimmed and nothing is covered, because the reviewer must still be able
  /// to read the evidence they just judged while the request is out
  /// (motion catalog, row 49).
  final bool busy;

  /// The two decision labels, fixed across the app.
  static const String coverageLabel = 'Confirm label coverage';

  /// The approval label.
  static const String approveLabel = 'Approve record';

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<Widget> actions = <Widget>[
      if (pendingCount > 0)
        FilledButton.icon(
          onPressed: busy ? null : onSavePending,
          icon: InFlightGlyph(busy: busy, resting: Symbols.save),
          label: Text('Save ${pendingChangesLabel(pendingCount)}'),
        ),
      _Decision(
        label: coverageLabel,
        reason: coverageBlockedReason,
        onPressed: onConfirmCoverage,
        filled: false,
        busy: busy,
      ),
      _Decision(
        label: approveLabel,
        reason: approveBlockedReason,
        onPressed: onApprove,
        filled: true,
        busy: busy,
      ),
    ];

    return Material(
      color: theme.colorScheme.surfaceContainer,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.space4,
            vertical: context.space.space2,
          ),
          child: Row(
            children: <Widget>[
              if (onPrevious != null)
                IconButton(
                  tooltip: 'Previous specimen',
                  onPressed: onPrevious,
                  icon: const Icon(Symbols.chevron_left),
                ),
              Expanded(
                child: Wrap(
                  alignment: compact ? WrapAlignment.center : WrapAlignment.end,
                  spacing: context.space.space2,
                  runSpacing: context.space.space2,
                  children: actions,
                ),
              ),
              if (onNext != null)
                IconButton(
                  tooltip: 'Next specimen',
                  onPressed: onNext,
                  icon: const Icon(Symbols.chevron_right),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Decision extends StatelessWidget {
  const _Decision({
    required this.label,
    required this.reason,
    required this.onPressed,
    required this.filled,
    required this.busy,
  });

  final String label;
  final String? reason;
  final VoidCallback onPressed;
  final bool filled;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final VoidCallback? action = reason == null && !busy ? onPressed : null;
    // The label stays; the indicator arrives beside it. Swapping the label
    // out would change the button's width, and a decision bar that resizes
    // while the request is out is a decision bar the reviewer has to find
    // again (motion catalog, row 49).
    final Widget content = Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        InFlightGlyph(busy: busy, resting: null),
        // Flexible, because a `Row` hands a non-flex child unbounded main
        // axis constraints, and a decision label is long.
        Flexible(child: Text(label)),
      ],
    );
    // `MergeSemantics` is what puts the reason on the button's own node.
    // Without it the hint sits on a parent node and the disabled button is a
    // separate child, so a screen reader focusing the control hears its name
    // and that it is dimmed, and never the sentence saying why
    // (accessibility, section 3.2 and the section 4.2 VoiceOver script,
    // step 4).
    return Tooltip(
      message: reason ?? label,
      child: MergeSemantics(
        child: Semantics(
          hint: reason ?? '',
          // Repeated here because a merge boundary keeps its own flags: a
          // node that does not say it is disabled is read as if it were live.
          enabled: action != null,
          child: filled
              ? FilledButton.tonal(onPressed: action, child: content)
              : OutlinedButton(onPressed: action, child: content),
        ),
      ),
    );
  }
}
