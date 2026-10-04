// The review block of a research card, captured as a component
// (north star, "Adaptation"; responsive and platform adaptation, section 8).
//
// Why a sheet and not a screen golden. The block lives inside a collapsed
// "Research" disclosure on a field row, which the workbench screen goldens
// never open, and the states below need five different fields at once. The
// sheet draws every case the block has, from the thread the server's own
// reader produced (tests/research_harness/test_thread_review.py writes and
// checks the fixture), so a golden that changes because the wire changed is a
// real signal.
//
// What decides the layout is the width the block is handed, so that is the
// axis these goldens vary: 360, one column; 640, two columns of possibilities.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_review_block.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../research/research_fixture.dart';
import '../research/review_test_support.dart';
import 'golden_harness.dart';

/// One labelled block on the sheet.
typedef ReviewCase = ({String label, ResearchFieldThread field});

/// Every case the block has, on one sheet.
List<ReviewCase> reviewCases() => reviewCasesWithCrowded().sublist(0, 6);

/// The longest the block gets, alone on its own sheet: eight possibilities
/// with the longest text the server allows, so the sheet shows what wrapping
/// and the bound do. Taller than the other six together, so it cannot share.
List<ReviewCase> crowdedCases() => reviewCasesWithCrowded().sublist(6);

List<ReviewCase> reviewCasesWithCrowded() {
  final conflict = unresolvedJson();
  reviewOf(conflict, 'country')['question_reason'] = 'evidence_conflict';
  fixtureField(
    conflict,
    'country',
  )['checkpoint']['resolution']['question']['reason'] = 'evidence_conflict';

  final noSource = unresolvedJson();
  final habitat = fixtureField(noSource, 'habitat');
  habitat['value']['state'] = 'unresolved';
  habitat['checkpoint']['resolution']['value']['state'] = 'unresolved';

  final crowded = unresolvedJson();
  final review = reviewOf(crowded, 'country');
  final first = (review['candidates'] as List).first as Map<String, dynamic>;
  review['candidates'] = [
    for (var i = 0; i < 8; i++)
      {
        ...first,
        'label': 'Synthetic place name ${'long ' * 46}',
        'details': ['Synthetic unit ${'u' * 40}', 'Synthetic status'],
        'rank': i + 1,
      },
  ];
  review['candidates_not_shown'] = 3;

  return [
    (
      label: 'Several possibilities remain',
      field: unresolvedThread().field('country')!,
    ),
    (
      label: 'Readings or sources disagree',
      field: unresolvedThread(conflict).field('country')!,
    ),
    (
      label: 'Public sources could not settle it',
      field: unresolvedThread().field('province_state')!,
    ),
    (label: 'The label lacks it', field: unresolvedThread().field('habitat')!),
    (
      label: 'Waiting for a source',
      field: unresolvedThread(noSource).field('habitat')!,
    ),
    (
      label: 'Waiting for a rule',
      field: unresolvedThread().field('collection_method')!,
    ),
    (
      label: 'The longest text the server allows',
      field: unresolvedThread(crowded).field('country')!,
    ),
  ];
}

/// The measures a block is handed: one column, then two.
const Map<String, double> reviewMeasures = <String, double>{
  'measure-360': 360,
  'measure-640': 640,
};

class ReviewBlockSheet extends StatelessWidget {
  const ReviewBlockSheet({super.key, required this.cases});

  final List<ReviewCase> cases;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final item in cases) ...[
          Text(
            'Case: ${item.label}',
            style: ui.type.labelSmall.copyWith(color: ui.color.inkTertiary),
          ),
          SizedBox(height: ui.space.s2),
          ResearchReviewBlock(fieldLabel: 'Field', field: item.field),
          SizedBox(height: ui.space.s6),
        ],
      ],
    );
  }
}

void main() {
  // A guard on the coverage rather than on the component: the sheets are only
  // worth their bytes while they reach every case. It runs on every platform,
  // including the Linux CI where the pixel comparison is skipped.
  test('the sheets reach every review case and both layouts', () {
    expect({
      for (final item in reviewCases()) researchReviewCase(item.field),
    }, ResearchReviewCase.values.toSet());
    expect(
      crowdedCases().single.field.review!.candidates.length,
      8,
      reason: 'the bound is a second layout of the possibilities',
    );
    expect(
      reviewMeasures['measure-360']!,
      lessThan(ResearchReviewBlock.twoColumnMinWidth),
    );
    expect(
      reviewMeasures['measure-640']!,
      greaterThanOrEqualTo(ResearchReviewBlock.twoColumnMinWidth),
    );
  });

  final matrix = <(String, String, double, String, Brightness, double)>[
    for (final measure in reviewMeasures.entries)
      for (final theme in goldenThemes.entries)
        ('cases', measure.key, measure.value, theme.key, theme.value, 1.0),
    // At 200 percent the whole sheet is taller than the canvas, so the three
    // cases that carry possibilities and sources are drawn.
    ('large-text', 'measure-360', 360, 'light', Brightness.light, 2.0),
    for (final measure in reviewMeasures.entries)
      ('crowded', measure.key, measure.value, 'light', Brightness.light, 1.0),
  ];
  for (final (sheet, name, width, theme, brightness, scale) in matrix) {
    testWidgets('the review block $sheet at $name in $theme at ${scale}x text', (
      tester,
    ) async {
      final cases = switch (sheet) {
        'cases' => reviewCases(),
        'large-text' => reviewCases().sublist(0, 3),
        _ => crowdedCases(),
      };
      await pumpGoldenComponent(
        tester,
        brightness: brightness,
        measure: width,
        textScale: scale,
        child: ReviewBlockSheet(cases: cases),
      );
      expect(
        find.byType(ResearchReviewBlock),
        findsNWidgets(cases.length),
        reason: 'the golden is of a sheet that failed to build',
      );
      await expectGoldenComponent(
        tester,
        'research-review-${sheet}__${name}__${theme}__text${scale.toStringAsFixed(1)}',
      );
    });
  }
}
