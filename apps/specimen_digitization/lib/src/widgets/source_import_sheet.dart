/// The confirmation before a selection is added, and the report of what it
/// did (07 section 13).
///
/// A `UiSheet` on a compact window and a `UiDialog` above it, with one
/// `primary` action and one `ghost` way out, which is the modal every other
/// decision in this client is taken in.
///
/// **The confirmation is not a courtesy.** A gesture that picks a thousand
/// objects and a gesture that picks one look identical on screen, so the count
/// is stated once, in words, before anything is sent. That is true here even
/// though adding costs nothing: the number is the point, not the price.
///
/// **What it says about spending is what is true, and no more.** Importing
/// creates records and dispatches no processing, in any mode, so this
/// confirmation says no model runs rather than naming a cost. Running a
/// selection is a separate decision with a separate surface, and it does not
/// exist yet: the estimate-and-reserve endpoint it needs is workstream C of
/// `docs/execution/SOURCE_BROWSE_AND_RUN.md`, which is blocked on an ongoing
/// budget the owner has not set. Until that endpoint exists there is no
/// estimate to show and no allowance to count down, and a confirmation that
/// named either would be inventing both. The north star's rule for exactly
/// this case: where a design calls for data the API does not return yet, the
/// interface shows an honest absence rather than a placeholder.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../sources.dart';
import 'product_modal.dart';
import 'source_object_row.dart';

/// Asks whether to add [count] objects, of which [alreadyInQueue] are already
/// records.
///
/// Returns true when the reviewer commits.
Future<bool> confirmSourceImport(
  BuildContext context, {
  required int count,
  required int alreadyInQueue,
}) async =>
    await showProductModal<bool>(
      context: context,
      title: SourceImportConfirmation.titleFor(count),
      body: (BuildContext modal) => SourceImportConfirmation(
        count: count,
        alreadyInQueue: alreadyInQueue,
      ),
      // The primary repeats the title's verb and the count
      // (writing guidelines, rule 12).
      primaryAction: (BuildContext modal) => UiButton(
        label: SourceImportConfirmation.actionFor(count),
        onPressed: () => Navigator.of(modal).pop(true),
      ),
      secondaryAction: (BuildContext modal) => UiButton(
        label: SourceImportConfirmation.cancelLabel,
        variant: UiButtonVariant.ghost,
        onPressed: () => Navigator.of(modal).pop(false),
      ),
    ) ??
    false;

/// The body of [confirmSourceImport], exposed so it can be tested on its own.
///
/// The title and the two actions belong to the modal's own chrome, which is
/// what keeps every confirmation in this client the same shape.
class SourceImportConfirmation extends StatelessWidget {
  const SourceImportConfirmation({
    super.key,
    required this.count,
    required this.alreadyInQueue,
  });

  /// How many objects the reviewer picked.
  final int count;

  /// How many of those are already records.
  final int alreadyInQueue;

  /// What adding does, in one sentence.
  static const String consequence =
      'These become records in the queue, ready to review.';

  /// What adding does not do.
  ///
  /// The one sentence a reviewer needs before a gesture that could have picked
  /// a thousand objects: nothing is spent, because nothing is run. Reading is
  /// a separate decision on a separate surface.
  static const String spend = 'No model runs and no allowance is used.';

  /// The way out.
  static const String cancelLabel = 'Cancel';

  /// The modal's title, which is where the exact count is stated.
  static String titleFor(int count) =>
      'Add ${photographsLabel(count)} to the queue?';

  /// The primary button, which repeats the title's verb and the count.
  static String actionFor(int count) => 'Add ${photographsLabel(count)}';

  /// The title, which is where the exact count is stated.
  String get title => titleFor(count);

  /// The primary button, which repeats the title's verb and the count
  /// (writing guidelines, rule 12).
  String get action => actionFor(count);

  /// What happens to the objects that are already records, or null when none
  /// of them are.
  String? get duplicates => alreadyInQueue == 0
      ? null
      : '${photographsLabel(alreadyInQueue)} of these are already in the queue. '
            'Those stay as they are.';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String? already = duplicates;
    // A column, not a scroller. The modal frame bounds this body to what its
    // chrome leaves and scrolls it itself, so a body that scrolled as well
    // would be the second vertical scroll inside the first, which is what 13
    // section 2.1 gives a screen one of. `SearchFilters` reached the same
    // answer for the same reason.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(consequence, style: ui.type.body.copyWith(color: ui.color.ink)),
        SizedBox(height: ui.space.s2),
        // Stated as its own line rather than folded into the consequence,
        // because it is the line that answers "what does this cost me",
        // and a reviewer skimming a confirmation should find it whole.
        Text(spend, style: ui.type.body.copyWith(color: ui.color.ink)),
        if (already != null) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Text(
            already,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      ],
    );
  }
}

/// What an import actually did, object by object.
///
/// Only opened when something did not become a record. An import that landed
/// whole is a toast the reviewer already read, and repeating it in a dialog
/// they have to dismiss is the interface asking to be thanked. This mirrors
/// `showBulkOutcome` in `selection_bar.dart` on purpose: one report shape,
/// learned once.
Future<void> showSourceImportOutcome(
  BuildContext context, {
  required SourceImportProgress progress,
}) => showProductModal<void>(
  context: context,
  title: SourceImportReport.titleFor(progress),
  body: (BuildContext modal) => SourceImportReport(progress: progress),
  primaryAction: (BuildContext modal) => UiButton(
    label: SourceImportReport.dismissLabel,
    onPressed: () => Navigator.of(modal).pop(),
  ),
);

/// The body of [showSourceImportOutcome], exposed so it can be tested on its
/// own.
class SourceImportReport extends StatelessWidget {
  const SourceImportReport({super.key, required this.progress});

  final SourceImportProgress progress;

  /// The one way out of the report.
  static const String dismissLabel = 'Back to the source';

  /// What the report is called: how many of how many landed.
  static String titleFor(SourceImportProgress progress) =>
      '${progress.imported} of ${photographsLabel(progress.requested)} added';

  /// What the rest of the selection did, when the run reached the end.
  static const String restUnchanged =
      'The rest are unchanged. Nothing was removed.';

  /// Why an object in the selection never became a record.
  static String reasonFor(String state) => switch (state) {
    'unsupported_media_type' =>
      'Not added. This source does not admit this media type.',
    'not_in_source' => 'Not added. This object is not in the current snapshot.',
    'duplicate' => 'Already in the queue, unchanged.',
    _ => 'Not added.',
  };

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<SourceImportOutcome> unchanged = progress.unchanged;
    // The modal frame scrolls this body, as it does the confirmation's above.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          progress.stoppedReason ?? restUnchanged,
          style: ui.type.body.copyWith(color: ui.color.ink),
        ),
        if (unchanged.isNotEmpty) ...<Widget>[
          SizedBox(height: ui.space.s4),
          Text(
            'Not added',
            style: ui.type.label.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s1),
          for (final SourceImportOutcome row in unchanged)
            Padding(
              padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    row.objectName,
                    style: ui.type.mono.identifier.copyWith(
                      color: ui.color.ink,
                    ),
                  ),
                  Text(
                    reasonFor(row.state),
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ],
    );
  }
}
