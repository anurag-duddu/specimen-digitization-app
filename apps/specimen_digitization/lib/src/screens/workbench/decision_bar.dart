/// The decision bar (13 sections 2.3, 3.3 and 4.1).
///
/// The two decisions the reviewer came to make, in the frame's own action bar
/// slot. `UiDecisionBar` is the pattern: one row of `density.controlHeight`,
/// the primary, the secondary beside it or in the bar's own overflow when the
/// line does not hold both, the count of where the reviewer is, and previous
/// and next as edge buttons from `medium` up. At compact those two are the
/// swipe `UiDecisionSwipe` puts over the evidence.
///
/// Neither decision is ever a silent no-op: where the server does not permit
/// one, the button carries the reason on its own semantics node rather than a
/// bare disabled state (06 section 3.2; pass criterion 5.6). The two queue
/// steps are the same: a step at the end of the queue says why there is
/// nowhere to go, in the same sentence the `J` and `K` keys say, rather than
/// being drawn as a control that does nothing.
///
/// This widget is the record's own binding of the pattern. It carries no
/// surface of its own: the scaffold's action bar is the pane, the padding and
/// the one frosted surface a compact window may spend (13 section 2.2), and a
/// pane inside that pane is the "glass decision bar over a glass pill" 13
/// section 0 reads as a defect.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'pending_changes.dart';

/// The record's two decisions, in the scaffold's action bar.
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
    this.positionLabel,
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

  /// How many corrections the reviewer has made and not sent.
  final int pendingCount;

  /// Sends them, as one reviewer action under one reason.
  final VoidCallback onSavePending;

  /// Moves to the next specimen, or says why there is none.
  ///
  /// Never null where the host offers queue navigation at all: the control at
  /// the end of the queue announces the reason rather than being drawn
  /// disabled with nothing to say, which is the same answer the `J` key
  /// already gives (finding V-2).
  final VoidCallback? onNext;

  /// Moves to the previous specimen, or says why there is none.
  final VoidCallback? onPrevious;

  /// Where this record sits in the loaded queue, as "3 of 38", or null when
  /// the queue does not carry it (pass criterion 6.5).
  final String? positionLabel;

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

  /// The word on the control that sends a set of corrections.
  static String saveLabel(int count) => 'Save ${pendingChangesLabel(count)}';

  @override
  Widget build(BuildContext context) {
    // The bar holds two, and the record has three. Which two depends on what
    // the reviewer has in front of them: corrections they have made and not
    // sent are what stands between them and any decision at all, and a
    // decision taken over them would record a version without them. So while
    // there are corrections the primary is the save and the approval is the
    // second; with none, the two are the two decisions 13 section 3.3
    // describes.
    //
    // fe/polish-3: `UiDecisionBar` should take the tertiary actions
    // `UiButtonRow` does, so a screen whose decision has a prerequisite can
    // offer all three from the bar rather than choosing two.
    final bool pending = pendingCount > 0;
    final UiButton approve = UiButton(
      label: approveLabel,
      variant: pending ? UiButtonVariant.secondary : UiButtonVariant.primary,
      loading: busy,
      disabledReason: approveBlockedReason,
      onPressed: approveBlockedReason == null ? onApprove : null,
    );
    return UiDecisionBar(
      primary: pending
          ? UiButton(
              label: saveLabel(pendingCount),
              leading: UiIcons.save,
              loading: busy,
              onPressed: onSavePending,
            )
          : approve,
      secondary: pending
          ? approve
          : UiButton(
              label: coverageLabel,
              variant: UiButtonVariant.secondary,
              loading: busy,
              disabledReason: coverageBlockedReason,
              onPressed: coverageBlockedReason == null
                  ? onConfirmCoverage
                  : null,
            ),
      count: positionLabel,
      onPrevious: onPrevious,
      onNext: onNext,
      previousLabel: previousLabel,
      nextLabel: nextLabel,
    );
  }
}
