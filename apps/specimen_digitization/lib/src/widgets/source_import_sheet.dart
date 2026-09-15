/// The confirmation before a selection is added, and the report of what it
/// did (screen blueprints, section 13).
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

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../sources.dart';
import '../theme/icons.dart';
import 'adaptive_form.dart';
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
    await showAdaptiveForm<bool>(
      context,
      width: DialogWidths.narrow,
      builder: (BuildContext formContext) => SourceImportConfirmation(
        count: count,
        alreadyInQueue: alreadyInQueue,
      ),
    ) ??
    false;

/// The body of [confirmSourceImport], exposed so it can be tested on its own.
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

  /// The title, which is where the exact count is stated.
  String get title => 'Add ${photographsLabel(count)} to the queue?';

  /// The primary button, which repeats the title's verb and the count
  /// (writing guidelines, rule 12).
  String get action => 'Add ${photographsLabel(count)}';

  /// What happens to the objects that are already records, or null when none
  /// of them are.
  String? get duplicates => alreadyInQueue == 0
      ? null
      : '${photographsLabel(alreadyInQueue)} of these are already in the queue. '
            'Those stay as they are.';

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? already = duplicates;
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.all(context.space.space6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(title, style: theme.textTheme.titleLarge),
            SizedBox(height: context.space.space3),
            Text(consequence, style: theme.textTheme.bodyMedium),
            SizedBox(height: context.space.space2),
            // Stated as its own line rather than folded into the consequence,
            // because it is the line that answers "what does this cost me",
            // and a reviewer skimming a confirmation should find it whole.
            Text(
              SourceImportConfirmation.spend,
              style: theme.textTheme.bodyMedium,
            ),
            if (already != null) ...<Widget>[
              SizedBox(height: context.space.space2),
              Text(
                already,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
            SizedBox(height: context.space.space6),
            OverflowBar(
              alignment: MainAxisAlignment.end,
              spacing: context.space.space2,
              overflowSpacing: context.space.space2,
              children: <Widget>[
                TextButton(
                  onPressed: () => Navigator.of(context).pop(false),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(context).pop(true),
                  child: Text(action),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// What an import actually did, object by object.
///
/// Only opened when something did not become a record. An import that landed
/// whole is a confirmation the reviewer already read, and repeating it in a
/// dialog they have to dismiss is the interface asking to be thanked. This
/// mirrors `showBulkOutcome` in `selection_bar.dart` on purpose: one report
/// shape, learned once.
Future<void> showSourceImportOutcome(
  BuildContext context, {
  required SourceImportProgress progress,
}) => showAdaptiveForm<void>(
  context,
  width: DialogWidths.standard,
  builder: (BuildContext formContext) =>
      SourceImportReport(progress: progress),
);

/// The body of [showSourceImportOutcome], exposed so it can be tested on its
/// own.
class SourceImportReport extends StatelessWidget {
  const SourceImportReport({super.key, required this.progress});

  final SourceImportProgress progress;

  /// Why an object in the selection never became a record.
  static String reasonFor(String state) => switch (state) {
    'unsupported_media_type' =>
      'Not added. This source does not admit this media type.',
    'not_in_source' =>
      'Not added. This object is not in the current snapshot.',
    'duplicate' => 'Already in the queue, unchanged.',
    _ => 'Not added.',
  };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<SourceImportOutcome> unchanged = progress.unchanged;
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.all(context.space.space6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              '${progress.imported} of ${photographsLabel(progress.requested)} added',
              style: theme.textTheme.titleLarge,
            ),
            SizedBox(height: context.space.space2),
            Text(
              progress.stoppedReason ??
                  'The rest are unchanged. Nothing was removed.',
              style: theme.textTheme.bodyMedium,
            ),
            if (unchanged.isNotEmpty) ...<Widget>[
              SizedBox(height: context.space.space4),
              Text('Not added', style: theme.textTheme.titleSmall),
              SizedBox(height: context.space.space1),
              for (final SourceImportOutcome row in unchanged)
                Padding(
                  padding: EdgeInsets.only(bottom: context.space.space2),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(row.objectName, style: context.mono.identifier),
                      Text(
                        SourceImportReport.reasonFor(row.state),
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
            SizedBox(height: context.space.space6),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: FilledButton.icon(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Symbols.inventory_2),
                label: const Text('Back to the source'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
