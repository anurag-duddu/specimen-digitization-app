/// The measured difference between a region's readings (UI.md T2.2).
///
/// A score is shown beside the components that produced it, and unmeasured
/// says unmeasured (north star, "The bar", honesty row): the ratio stands
/// with the edits and the characters it divides, and with the "Not
/// calibrated" chip, because it orders review and is not a probability. A
/// difference the server did not measure is words, never a number.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../thread/thread.dart';
import '../vocabulary.dart';
import 'caveat_text.dart';
import 'not_calibrated_chip.dart';

/// One comparison of two readings of one label region.
class ReadingComparisonView extends StatelessWidget {
  /// The view of [comparison].
  const ReadingComparisonView({super.key, required this.comparison});

  /// The comparison, as the thread carries it.
  final ThreadComparison comparison;

  /// What a difference the server did not measure says.
  static const String notMeasured = 'Difference not measured';

  /// The headline for a measured [ratio], at two decimals.
  static String headline(double ratio) =>
      'Difference ${ratio.toStringAsFixed(2)}';

  /// The components the ratio divides: edits over characters.
  static String components(int edits, int characters) {
    final String counted = switch (edits) {
      0 => 'No edits',
      1 => '1 edit',
      _ => '$edits edits',
    };
    return '$counted over $characters characters';
  }

  /// Why the difference was not measured, from the server's own codes.
  String get _why {
    final List<String> reasons = comparison.reasons.isNotEmpty
        ? comparison.reasons
        : <String>[?comparison.status];
    final String because = reasons.isEmpty
        ? 'The server gave no reason.'
        : 'The server recorded: ${reasons.map(vocabularyLabel).join(', ')}.';
    return '$because An unmeasured difference is not agreement.';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double? ratio = comparison.ratio;
    if (ratio == null) {
      return CaveatText(label: notMeasured, why: _why);
    }
    final int? edits = comparison.editDistance;
    final int? characters = comparison.lengthBasis;
    return Semantics(
      container: true,
      child: Wrap(
        spacing: ui.space.s2,
        runSpacing: ui.space.s1,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          Text(headline(ratio), style: ui.type.label),
          if (edits != null && characters != null)
            Text(
              components(edits, characters),
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          const NotCalibratedChip(),
        ],
      ),
    );
  }
}
