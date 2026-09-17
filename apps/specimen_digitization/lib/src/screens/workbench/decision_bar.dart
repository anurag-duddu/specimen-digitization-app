/// The decision bar (screen blueprints, 6.1; responsive 3.5).
///
/// The two actions the reviewer is here for never scroll away, and neither is
/// ever a silent no-op: when the server does not permit one, the button
/// carries the reason on its own semantics node rather than a bare disabled
/// state (accessibility, 2.2 finding 3; pass criterion 5.6).
///
/// The bar is `glass.floating` where it floats, which is above the navigation
/// on a stacked layout, and `paper` where it is in flow at the foot of the
/// evidence pane on a two or three pane layout (09 section 3.3; responsive
/// 3.5). It is the scaffold's action bar in everything but the slot: the
/// shell owns the `UiScaffold` and publishes no way for a routed screen to
/// fill `actionBar`, which is recorded in the slot closeout.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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
    this.nextBlockedReason,
    this.previousBlockedReason,
    this.positionLabel,
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

  /// Why there is no next specimen, when the host offers navigation but this
  /// record is the last one loaded.
  ///
  /// The control is drawn and disabled with this as its tooltip and its
  /// semantic hint, rather than moving nowhere or disappearing: a reviewer at
  /// the end of the queue has to be told they are at the end
  /// (pass criterion 5.6).
  final String? nextBlockedReason;

  /// Why there is no previous specimen, at the head of the queue.
  final String? previousBlockedReason;

  /// Where this record sits in the loaded queue, as "3 of 38", or null when
  /// the queue does not carry it (pass criterion 6.5).
  final String? positionLabel;

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

  /// The two queue steps, named once.
  static const String nextLabel = 'Next specimen';

  /// The step backwards.
  static const String previousLabel = 'Previous specimen';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiButtonRow actions = UiButtonRow(
      primary: UiButton(
        label: approveLabel,
        loading: busy,
        disabledReason: approveBlockedReason,
        onPressed: approveBlockedReason == null ? onApprove : null,
      ),
      secondary: UiButton(
        label: coverageLabel,
        variant: UiButtonVariant.secondary,
        loading: busy,
        disabledReason: coverageBlockedReason,
        onPressed: coverageBlockedReason == null ? onConfirmCoverage : null,
      ),
      tertiary: <UiButton>[
        if (pendingCount > 0)
          UiButton(
            label: 'Save ${pendingChangesLabel(pendingCount)}',
            variant: UiButtonVariant.ghost,
            leading: UiIcons.save,
            loading: busy,
            onPressed: onSavePending,
          ),
      ],
    );

    // The scaffold floats its own chrome over the body rather than reserving
    // room in it, so at compact the navigation pill sits exactly where this
    // bar does. `bottomInset` is the clearance it asks for, and it already
    // carries the display's own safe area; the `max` is for a host with no
    // scaffold, such as a component test.
    final double clearance = math.max(
      UiScaffold.of(context).bottomInset,
      MediaQuery.paddingOf(context).bottom,
    );

    final Widget bar = Padding(
      padding: EdgeInsetsDirectional.symmetric(
        horizontal: ui.space.s4,
        vertical: ui.space.s2,
      ),
      child: Row(
        children: <Widget>[
          if (onPrevious != null || previousBlockedReason != null)
            _Step(
              label: WorkbenchDecisionBar.previousLabel,
              reason: previousBlockedReason,
              onPressed: onPrevious,
              icon: UiIcons.previous,
            ),
          if (positionLabel != null)
            Padding(
              padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s1),
              child: Text(
                positionLabel!,
                style: ui.type.label.copyWith(color: ui.color.inkSecondary),
              ),
            ),
          Expanded(child: actions),
          if (onNext != null || nextBlockedReason != null)
            _Step(
              label: WorkbenchDecisionBar.nextLabel,
              reason: nextBlockedReason,
              onPressed: onNext,
              icon: UiIcons.next,
            ),
        ],
      ),
    );

    final Widget surface = compact
        ? GlassSurface(
            level: GlassLevel.floating,
            // A tile rather than a capsule, which is the shape the scaffold
            // gives its own action bar: the row stacks to three buttons on a
            // phone and a capsule around three lines reads as a pill that
            // grew (10 section 4.4).
            radius: ui.shape.tile,
            child: bar,
          )
        : Surface(radius: ui.shape.tile, hairline: true, child: bar);

    return clearance == 0
        ? surface
        : Padding(
            padding: EdgeInsets.only(bottom: clearance),
            child: surface,
          );
  }
}

/// One step along the queue, drawn even when it is unavailable.
///
/// `UiIconButton` takes the reason itself: it publishes it as the control's
/// semantic hint and draws it on hover and on long press through
/// `UiTooltip.reason`, which is what a dimmed control with nothing to say
/// would otherwise cost (pass criterion 5.6, finding V-2).
class _Step extends StatelessWidget {
  const _Step({
    required this.label,
    required this.reason,
    required this.onPressed,
    required this.icon,
  });

  final String label;
  final String? reason;
  final VoidCallback? onPressed;
  final IconSpec icon;

  @override
  Widget build(BuildContext context) => UiIconButton(
    icon: icon,
    semanticsLabel: label,
    tooltip: label,
    disabledReason: reason,
    onPressed: onPressed,
  );
}
