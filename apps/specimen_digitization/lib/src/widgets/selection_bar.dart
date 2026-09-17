/// The selection affordance, shared by every list a reviewer picks from
/// (07 section 3, "Multi-select"; 10 section 5).
///
/// Three pieces, none of which knows what it is selecting: a row that carries
/// a checkbox, a bar that states the count and offers what can be done with
/// it, and a report that says what a bulk action actually did, record by
/// record. The queue uses all three. A browse screen over a data source uses
/// the same three, which is why none of them mentions a specimen.
///
/// **The row body always opens; only the checkbox selects.** The convention on
/// touch is that a live selection turns every row into a checkbox, but that
/// makes one gesture mean two things depending on a mode, and it makes a row
/// announce itself as a button that does not open anything. A 48 dp checkbox
/// beside the row costs one gesture and keeps both meanings true.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../models.dart';
import 'product_modal.dart';

/// The words for one bulk decision.
///
/// Kept beside the control that shows them rather than on the wire enum, and
/// kept in one place so the bar, the confirmation and its primary button
/// cannot word the same action three ways.
extension BulkDecisionCopy on BulkDecisionKind {
  /// The label on the bar. The count sits beside it, so it is not repeated.
  String get label => switch (this) {
    BulkDecisionKind.approve => 'Approve',
    BulkDecisionKind.confirmCoverage => 'Confirm coverage',
  };

  /// The registry entry this action draws, as the glyph a [SelectionAction]
  /// carries.
  IconData get icon => switch (this) {
    BulkDecisionKind.approve => UiIcons.cleared.defaultGlyph,
    BulkDecisionKind.confirmCoverage => UiIcons.checklist.defaultGlyph,
  };

  /// The confirmation's title, which is where the exact count is stated.
  String title(int count) => switch (this) {
    BulkDecisionKind.approve => 'Approve ${recordsLabel(count)}?',
    BulkDecisionKind.confirmCoverage =>
      'Confirm label coverage on ${recordsLabel(count)}?',
  };

  /// The confirmation's primary button, which repeats the title's verb.
  String action(int count) => switch (this) {
    BulkDecisionKind.approve => 'Approve ${recordsLabel(count)}',
    BulkDecisionKind.confirmCoverage => 'Confirm label coverage',
  };

  /// One neutral sentence saying what will change.
  String consequence(int count) => switch (this) {
    BulkDecisionKind.approve =>
      'Approval is recorded on ${recordsLabel(count)}, at the version loaded now.',
    BulkDecisionKind.confirmCoverage =>
      'Full label coverage is recorded on ${recordsLabel(count)}, at the version '
          'loaded now.',
  };

  /// What survives the action, in one sentence.
  String get retained =>
      'Nothing is removed. Every record keeps its history and its evidence.';

  /// What a reviewer is told after a batch that landed whole.
  String done(int count) => switch (this) {
    BulkDecisionKind.approve => '${recordsLabel(count)} approved.',
    BulkDecisionKind.confirmCoverage =>
      'Label coverage confirmed on ${recordsLabel(count)}.',
  };
}

/// "1 record" or "6 records". One place, because six call sites agreeing
/// on the plural by hand is six chances to disagree.
///
/// The default for [SelectionBar.countLabel], and the right words wherever the
/// rows are records. A list whose rows are not records yet, such as objects in
/// a storage inventory that nothing has imported, passes its own noun instead:
/// calling one of those a record would name the very thing the screen exists
/// to distinguish.
String recordsLabel(int count) => count == 1 ? '1 record' : '$count records';

/// One thing the bar offers to do with a selection.
///
/// The glyph stays an `IconData` rather than an `IconSpec`, so a caller that
/// already holds one keeps compiling; the bar wraps it for the button.
typedef SelectionAction = ({
  String label,
  IconData icon,
  VoidCallback? onPressed,
});

/// A row that can be selected, with the selection affordance outside it.
///
/// [label] names the record for the checkbox, because a checkbox announced
/// without one is a control a screen reader cannot tell apart from the next.
class SelectableRow extends StatelessWidget {
  const SelectableRow({
    super.key,
    required this.selected,
    required this.label,
    required this.onToggle,
    required this.child,
    this.showCheckbox = true,
    this.enabled = true,
    this.onExtend,
    this.onLongPress,
    this.longPressHint = SelectableRow.recordLongPressHint,
  });

  /// True when this row is in the selection.
  final bool selected;

  /// What the checkbox is called: the record's own name.
  final String label;

  /// Adds or removes this row.
  final VoidCallback onToggle;

  /// Adds every row between the last one picked and this one.
  ///
  /// Offered on a shift click, which is the pointer gesture for picking
  /// several at once. Null where the list has no order to extend along.
  final VoidCallback? onExtend;

  /// Starts a selection on a long press, for a window too narrow to carry a
  /// checkbox column all the time.
  ///
  /// Null wherever the column is already open, so the row does not carry a
  /// gesture, or the extra screen reader stop that naming one costs, when
  /// there is a checkbox beside it doing the same job.
  final VoidCallback? onLongPress;

  /// What the long press does, for a reader that announces custom actions.
  ///
  /// Without one the gesture is an unnamed action on an unnamed node, which is
  /// a reviewer on a phone being told an action exists and not what it is.
  ///
  /// Defaults to [recordLongPressHint]. A list whose rows are not records
  /// passes its own noun, the same way the bar takes its own count label.
  final String longPressHint;

  /// The default [longPressHint], for a list whose rows are records.
  static const String recordLongPressHint = 'Select this record';

  /// False while the list is not in selection and the window is too narrow to
  /// keep the column open.
  ///
  /// This is about the list, not about the row. A row the list will not let
  /// the reviewer pick sets [enabled] instead.
  final bool showCheckbox;

  /// False for a row this list will not let the reviewer pick.
  ///
  /// The control is drawn and disabled rather than removed, for two reasons.
  /// Removing it takes the leading column with it, so an unselectable row
  /// slides out of the alignment a reviewer scans a long list down, and the
  /// list only has to contain one such row for every row below it to be read
  /// against a different left edge. And a reader told nothing at all cannot
  /// tell a row it may not pick from a row it missed, where a disabled control
  /// says which.
  ///
  /// A disabled row takes no long press either: a gesture that picks a record
  /// the server will refuse is worse than no gesture.
  final bool enabled;

  /// The row itself, which keeps its own tap, its own semantics and its own
  /// layout.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget row = Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        if (showCheckbox) ...<Widget>[
          UiCheckbox(
            label: label,
            showLabel: false,
            value: selected,
            onChanged: enabled
                ? (bool _) {
                    final bool extending =
                        onExtend != null &&
                        HardwareKeyboard.instance.logicalKeysPressed.any(
                          _shiftKeys.contains,
                        );
                    extending ? onExtend!() : onToggle();
                  }
                : null,
          ),
          SizedBox(width: ui.space.s1),
        ],
        Expanded(child: child),
      ],
    );
    if (onLongPress == null || !enabled) return row;
    // A long press anywhere on the row starts a selection and picks that row.
    // The gesture is on a bare detector rather than on the row's own press
    // target so the row's tap, focus and state layer keep working exactly as
    // they did, and its semantics are declared here instead, named, so the
    // only way into a selection on a narrow window is a way a screen reader
    // can also take.
    return Semantics(
      label: label,
      onLongPress: onLongPress,
      onLongPressHint: longPressHint,
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        excludeFromSemantics: true,
        onLongPress: onLongPress,
        child: row,
      ),
    );
  }

  static final Set<LogicalKeyboardKey> _shiftKeys = <LogicalKeyboardKey>{
    LogicalKeyboardKey.shift,
    LogicalKeyboardKey.shiftLeft,
    LogicalKeyboardKey.shiftRight,
  };
}

/// The bar that states how many records are selected and what can be done.
///
/// A `glass.floating` capsule anchored the way the toast layer is: the count
/// has to stay visible while the reviewer scrolls the thing they are counting,
/// and a band welded across the window would take a row's worth of the list
/// with it at every width.
class SelectionBar extends StatelessWidget {
  const SelectionBar({
    super.key,
    required this.count,
    required this.loadedCount,
    required this.moreToLoad,
    required this.allLoadedSelected,
    required this.onSelectAllLoaded,
    required this.onClear,
    required this.actions,
    this.busy = false,
    this.countLabel = recordsLabel,
    this.moreMatchLabel = SelectionBar.recordsMoreMatch,
  });

  /// How many records are selected.
  final int count;

  /// How many records are loaded, which is how far a select all reaches.
  final int loadedCount;

  /// True when the server said there is another page.
  final bool moreToLoad;

  /// True when every loaded record is already selected.
  final bool allLoadedSelected;

  final VoidCallback onSelectAllLoaded;
  final VoidCallback onClear;

  /// What the bar offers to do. Empty is legitimate: a list whose server
  /// permits nothing in bulk shows a count and no actions rather than
  /// controls that would be refused.
  final List<SelectionAction> actions;

  /// True while a bulk action is out. Every control is held rather than
  /// hidden, so the bar keeps its footprint and its count.
  final bool busy;

  /// What one of these rows is called, counted.
  ///
  /// Defaults to [recordsLabel]. A list of things that are not records yet
  /// passes its own noun, so the bar names what the reviewer is looking at
  /// rather than what this bar happened to be written for.
  final String Function(int count) countLabel;

  /// What the reviewer is told when a select all cannot reach the whole
  /// filter, which is whenever the server still has a page to give.
  ///
  /// Defaults to [recordsMoreMatch]. A caller that changed [countLabel] should
  /// change this too, so one bar does not use two nouns for one thing.
  final String moreMatchLabel;

  /// The two words the select all control uses, fixed so the label and the
  /// sentence under it cannot drift apart.
  static const String selectAllLabel = 'Select all loaded';

  /// The default [moreMatchLabel], for a list whose rows are records.
  static const String recordsMoreMatch =
      'More records match this filter. Load more to select them.';

  /// What the select all box reads as.
  ///
  /// Checked once everything loaded is picked, mixed while some of it is, and
  /// unchecked when the reviewer picked by hand and then cleared. Mixed is a
  /// fact about the group rather than a state a reviewer asks for, which is
  /// exactly what `UiCheckbox` means by it.
  bool? get _selectAllValue {
    if (loadedCount == 0) return false;
    if (allLoadedSelected) return true;
    return count == 0 ? false : null;
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SafeArea(
      top: false,
      child: Padding(
        padding: EdgeInsetsDirectional.fromSTEB(
          ui.space.s4,
          ui.space.s2,
          ui.space.s4,
          ui.space.s4,
        ),
        child: Align(
          alignment: AlignmentDirectional.centerStart,
          child: GlassSurface(
            level: GlassLevel.floating,
            // `radius.tile` rather than the capsule 10 section 5 names. A
            // stadium's radius is half its height, and this bar wraps to
            // three lines in a 360 dp list pane, which puts the first and
            // last control outside the curve. 09 section 5 picks the shape
            // from the geometry rather than by hand, and a three line pane is
            // not a capsule.
            radius: ui.shape.tile,
            padding: EdgeInsetsDirectional.symmetric(
              horizontal: ui.space.s4,
              vertical: ui.space.s2,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // The count and the controls are one flow rather than a row
                // with a breakpoint in it: they sit on one line wherever they
                // fit, and wrap wherever they do not, at any width and any
                // text scale. A breakpoint here would be a number tuned to
                // today's labels, and the first longer label would push a
                // control off the edge.
                Wrap(
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: ui.space.s4,
                  runSpacing: ui.space.s2,
                  children: <Widget>[_summary(ui), ..._controls(ui)],
                ),
                // Only once a select all has been taken at face value is the
                // reviewer told how far it reached. Said earlier it is noise;
                // said later it is too late.
                if (allLoadedSelected && moreToLoad)
                  Padding(
                    padding: EdgeInsetsDirectional.only(top: ui.space.s2),
                    child: Text(
                      moreMatchLabel,
                      style: ui.type.bodySmall.copyWith(
                        color: ui.color.inkSecondary,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// The count, announced once when it changes.
  Widget _summary(UiThemeData ui) => Announcer(
    child: Text(
      '${countLabel(count)} selected',
      style: ui.type.label.copyWith(color: ui.color.ink),
    ),
  );

  List<Widget> _controls(UiThemeData ui) => <Widget>[
    UiCheckbox(
      label: selectAllLabel,
      value: _selectAllValue,
      // Unchecking is the way out of a select all, and the ghost button
      // beside it is the way out of any selection. Both reach `onClear`,
      // because leaving every record picked and leaving the selection are
      // the same thing.
      onChanged: busy
          ? null
          : (bool next) => next ? onSelectAllLoaded() : onClear(),
      disabledReason: busy ? _busyReason : null,
    ),
    UiButton(
      label: 'Clear selection',
      variant: UiButtonVariant.ghost,
      onPressed: busy ? null : onClear,
      disabledReason: busy ? _busyReason : null,
    ),
    for (final SelectionAction action in actions)
      UiButton(
        label: action.label,
        leading: IconSpec(action.icon),
        onPressed: busy ? null : action.onPressed,
        disabledReason: busy ? _busyReason : null,
      ),
  ];

  /// Why every control is held while a bulk call is out.
  static const String _busyReason =
      'A decision on this selection is in flight.';
}

/// Tells the reviewer what a bulk action did, record by record.
///
/// Only opened when something did not change. A batch that landed whole is a
/// confirmation the reviewer already read, and repeating it in a dialog they
/// have to dismiss is the interface asking to be thanked.
///
/// [nameOf] turns an identifier into whatever the list calls that record, so
/// nobody reads a bare identifier back.
Future<void> showBulkOutcome(
  BuildContext context, {
  required BulkDecisionReport report,
  required String Function(String id) nameOf,
}) => showProductModal<void>(
  context: context,
  title: '${report.applied} of ${recordsLabel(report.requested)} changed',
  body: (BuildContext dialogContext) =>
      BulkOutcomeReport(report: report, nameOf: nameOf),
  primaryAction: (BuildContext dialogContext) => UiButton(
    label: BulkOutcomeReport.dismissLabel,
    onPressed: () => Navigator.of(dialogContext).pop(),
  ),
);

/// The body of [showBulkOutcome], exposed so it can be tested on its own.
class BulkOutcomeReport extends StatelessWidget {
  const BulkOutcomeReport({
    super.key,
    required this.report,
    required this.nameOf,
  });

  final BulkDecisionReport report;
  final String Function(String id) nameOf;

  /// Why a record in the batch was never sent.
  ///
  /// Refused and never attempted are different things, and a reviewer
  /// deciding what to do next is owed the difference.
  static const String skippedReason =
      'Not sent. An earlier decision on this record was refused.';

  /// The one way out of the report.
  static const String dismissLabel = 'Back to the queue';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<BulkDecisionResult> unchanged = report.unchanged;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            'The rest are unchanged and still in the queue. Nothing was '
            'removed.',
            style: ui.type.body.copyWith(color: ui.color.ink),
          ),
          SizedBox(height: ui.space.s4),
          Text(
            'Not changed',
            style: ui.type.label.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s1),
          for (final BulkDecisionResult row in unchanged)
            Padding(
              padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    nameOf(row.specimenId),
                    style: ui.type.mono.identifier.copyWith(
                      color: ui.color.ink,
                    ),
                  ),
                  Text(
                    row.outcome == BulkOutcome.skipped
                        ? BulkOutcomeReport.skippedReason
                        : row.message,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
