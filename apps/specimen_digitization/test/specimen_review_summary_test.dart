import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test('snapshot field counts remain independent, including known zero', () {
    final summary = const Specimen({
      'review_summary': {'review': 3, 'missing': 5},
    }).reviewSummary!;
    expect(summary.review, 3);
    expect(summary.missing, 5);
    final cleared = const Specimen({
      'review_summary': {'review': 0, 'missing': 0},
    }).reviewSummary!;
    expect(cleared.review, 0);
    expect(cleared.missing, 0);
  });

  test('absent or invalid counts never become zero or guessed values', () {
    for (final value in [
      null,
      {},
      {'review': 1},
      {'review': -1, 'missing': 2},
      {'review': 1, 'missing': '2'},
      {'review': 1.5, 'missing': 2},
    ]) {
      expect(Specimen({'review_summary': value}).reviewSummary, isNull);
    }
    expect(
      const Specimen({
        'reason_codes': ['mandatory_unresolved:city'],
        'validation_findings': [
          {'field_key': 'city'},
        ],
      }).reviewSummary,
      isNull,
    );
  });
}
