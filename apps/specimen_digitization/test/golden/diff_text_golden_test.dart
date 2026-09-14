// The reading comparison, captured as a component
// (design system, 3.4 and 7.2; screen blueprints, 6.3).
//
// Why this is not a screen golden. `size_classes_golden_test.dart` returns
// every scroll view to offset 0 before it captures, because a capture of a
// scrolled pane is not a capture of the screen. At offset 0 the readings pane
// shows the first reading card of a region, and the first reading is the
// reference: `readings_panel.dart` passes a null reference for it, so it has
// no comparison to draw. The card that does draw one sits below the fold at
// every window and both text scales, measured on the `goldenSpecimen()`
// fixture after the golden's own scroll to top:
//
//   compact-390x844   @1.0  top=1488   window=844
//   medium-768x1024   @1.0  top=1305   window=1024
//   expanded-1180x820 @1.0  top=798    window=820, and the pane clips it
//   large-1440x900    @1.0  top=1180   window=900
//   (1562 to 2908 at 200 percent text)
//
// The consequence was measurable: appending 30 characters to
// `DiffText.summaryFor`, and restyling a changed run to a green double
// underline on the added fill, each moved 0 of the 97 screen goldens.
//
// Scrolling the pane to bring the second card into frame would close half the
// gap and buy a worse golden: eight hand tuned offsets, one per window and
// scale, each of which has to be re-derived whenever the readings panel's
// layout changes. The framing would then depend on layout the golden is
// supposed to hold still.
//
// It would also still be half the gap. The fixture compares 'Chicago 1912'
// with 'Chicago 1917': two literals of equal length, so it produces changed
// runs and nothing else. `DiffRunKind.added`, a reference longer than the
// literal, the identical summary and the dense field row role have no fixture
// that reaches them at any scroll offset. This sheet draws all of them.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/icons.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';

import 'golden_harness.dart';

/// One labelled comparison on the sheet.
typedef DiffCase = ({
  String label,
  String text,
  String? reference,
  bool dense,
});

/// Every state the comparison has, on one sheet.
///
/// The readings are the fixture's, so a reviewer holding this PNG beside a
/// workbench golden is looking at the same beetle. What varies is the
/// relationship between the two literals, because that is what decides which
/// runs are built and how each one is marked.
const List<DiffCase> diffCases = <DiffCase>[
  (
    label: 'Differs in the middle',
    text: 'Chicago 1917',
    reference: 'Chicago 1912',
    dense: false,
  ),
  (
    label: 'Longer than the reference',
    text: 'Chicago 1912 IL',
    reference: 'Chicago 1912',
    dense: false,
  ),
  (
    // Adjacent runs of two kinds, which is where a regression in the grouping
    // shows: one changed run and one added run, not eight spans.
    label: 'Changed and added together',
    text: 'Chixxxo 1917 IL',
    reference: 'Chicago 1912',
    dense: false,
  ),
  (
    // The positions the literal never reaches have no run to carry them. They
    // are counted in the summary and nowhere else, so the summary is the only
    // thing on screen that can be wrong.
    label: 'Shorter than the reference',
    text: 'Chi',
    reference: 'Chicago 1912',
    dense: false,
  ),
  (
    label: 'Matches the reference',
    text: 'Chicago 1912',
    reference: 'Chicago 1912',
    dense: false,
  ),
  (
    label: 'The first reading of a region',
    text: 'Chicago 1912',
    reference: null,
    dense: false,
  ),
  (
    label: 'The dense field row role',
    text: 'Chicago 1917',
    reference: 'Chicago 1912',
    dense: true,
  ),
];

/// The measures a reading card actually hands its literal.
///
/// A component has no window class of its own, so the axis these goldens vary
/// is the measure. Both numbers are measured from the readings pane rather
/// than chosen: 192 is what a card gives at text scale 1.0, at all four
/// windows, and 366 is the widest it ever gives, on an expanded window at 200
/// percent text. The narrow one is the one that wraps a marked run.
const Map<String, double> diffMeasures = <String, double>{
  'measure-192': 192,
  'measure-366': 366,
};

/// The sheet, drawn top to bottom in the measure it was given.
class DiffTextSheet extends StatelessWidget {
  const DiffTextSheet({super.key, required this.cases});

  final List<DiffCase> cases;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (final DiffCase c in cases) ...<Widget>[
          Text(
            c.label,
            style: theme.textTheme.titleSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          SizedBox(height: context.space.space1),
          DiffText(text: c.text, reference: c.reference, dense: c.dense),
          SizedBox(height: context.space.space4),
        ],
      ],
    );
  }
}

void main() {
  // A guard on the coverage rather than on the component. The sheet is only
  // worth its bytes while it still reaches every kind of run, and an edit to
  // `diffCases` that quietly drops one would otherwise leave a golden that
  // passes and covers less. This assertion runs on every platform, including
  // the Linux CI where the pixel comparison is skipped.
  test('the sheet reaches every run kind and both summaries', () {
    final Set<DiffRunKind> kinds = <DiffRunKind>{
      for (final DiffCase c in diffCases)
        ...DiffText.compare(c.text, c.reference).runs.map(
          (DiffRun run) => run.kind,
        ),
    };
    expect(
      kinds,
      DiffRunKind.values.toSet(),
      reason: 'every run kind must be drawn somewhere on the sheet',
    );

    final List<DiffOutcome> outcomes = <DiffOutcome>[
      for (final DiffCase c in diffCases) DiffText.compare(c.text, c.reference),
    ];
    expect(
      outcomes.where((DiffOutcome o) => o.identical && o.summary.isNotEmpty),
      isNotEmpty,
      reason: 'the matching summary is a different colour and must be drawn',
    );
    expect(
      outcomes.where((DiffOutcome o) => o.summary.isEmpty),
      isNotEmpty,
      reason: 'a first reading has no summary and must be drawn',
    );
    expect(
      diffCases.where((DiffCase c) => c.dense),
      isNotEmpty,
      reason: 'the dense literal role is a second type ramp',
    );
  });

  for (final double scale in <double>[1.0, 2.0]) {
    diffMeasures.forEach((String measure, double width) {
      goldenThemes.forEach((String theme, Brightness brightness) {
        testWidgets(
          'the reading comparison at $measure in $theme at ${scale}x text',
          (WidgetTester tester) async {
            await pumpGoldenComponent(
              tester,
              brightness: brightness,
              measure: width,
              textScale: scale,
              child: const DiffTextSheet(cases: diffCases),
            );
            expect(
              find.byType(DiffText),
              findsNWidgets(diffCases.length),
              reason: 'the golden is of a sheet that failed to build',
            );
            await expectGoldenComponent(
              tester,
              'diff-text__${measure}__${theme}__text${scale.toStringAsFixed(1)}',
            );
          },
        );
      });
    });
  }
}
