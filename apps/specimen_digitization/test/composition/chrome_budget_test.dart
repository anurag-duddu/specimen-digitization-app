// The chrome budget (13 sections 2.3 and 5, `chrome_budget`).
//
// The second row of 13 section 0: "chrome takes about three quarters of the
// height ... nobody adds them up". This adds them up. Every pinned region's
// render box height over the viewport height, against 28 percent at compact,
// 24 at medium and 20 at expanded and above.
//
// What counts as pinned. 13 section 5 says the screens mark their pinned
// regions with a `PinnedChrome` marker the package provides, which slot A1
// lands. Until a screen carries one, the gate measures the widgets that draw
// the five regions 13 section 2.3 names: the top bar, the environment band,
// the decision bar and the navigation pill, plus any pinned header once one
// exists. The switch is automatic and per pump: the moment a marker is in the
// tree, only markers are counted, so a screen that has moved and a screen that
// has not are each measured by the right instrument and never by both.
//
// A rail and a sidebar are not counted. They are laid out beside the body
// rather than above it, so they spend width; the budget in 13 section 2.3 is a
// share of `MediaQuery.sizeOf(context).height`, and a full height column would
// read as a hundred percent of a budget it does not touch.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'composition_harness.dart';

// ---------------------------------------------------------------------------
// The budget.
// ---------------------------------------------------------------------------

/// The share of the viewport a window class lets the chrome have.
double chromeBudgetFor(String window) => switch (windowClassOf(window)) {
  'compact' => 0.28,
  'medium' => 0.24,
  _ => 0.20,
};

// ---------------------------------------------------------------------------
// The backlog. Shrink only.
// ---------------------------------------------------------------------------

/// The share of the viewport each cell's chrome takes today, over budget.
///
/// Measured on 2026-09-17 against `front-end-refactor` at f3b6363, at every
/// window, both modes and 1.0, 1.3 and 2.0; the number is the worst of the six.
///
/// **Empty, and it is a real zero (polish 3, 2026-09-17).** The last two
/// lines were the record at expanded and large, and they were one sentence
/// about the frame rather than about the screen: at 200 percent text the
/// frame's own top bar is 61.25 dp, the one line environment band 52 and the
/// action bar 71.6, which is 184.85 of the 164 an 820 dp window allows and of
/// the 180 a 900 dp window allows, so no arrangement that kept all three held
/// the budget. 13 section 2.3 says a screen over the budget gives a region up,
/// and the record gives up the action bar from `expanded` up: its decision
/// sits in the top bar beside the identifier (13 section 4.1, the expanded
/// and large table), and what remains pinned is the bar and the band, 100 dp
/// at default type and 113.25 at 200 percent, which is 0.138 of 820 and 0.126
/// of 900, and 0.173 of 900 with the segments stuck at default type in the
/// stacked regime the record takes beside the queue pane and the sidebar.
const Map<String, num> chromeBudgetBacklog = <String, num>{};

// ---------------------------------------------------------------------------
// The measurement.
// ---------------------------------------------------------------------------

/// The pinned regions in the tree right now, outermost only.
///
/// A region inside a region is counted once, at the outer one, so a marker
/// wrapped around a bar that is itself a pinned widget does not pay twice.
List<Element> pinnedRegionsIn(List<Element> elements) => <Element>[
  for (final Element element in elements)
    if (isPinnedRegion(element) && !isInPinnedRegion(element)) element,
];

/// What the chrome is on one screen: its share of the viewport, the regions
/// that make it up, and any region that could not be measured.
///
/// All three come out of one walk. Building the sentence a failure needs out
/// of a second walk costs more than the measurement, and it is built for every
/// cell whether or not the cell fails, because an `expect` reason is an
/// argument rather than a callback.
///
/// A region is measured the way `PinnedChrome.extentOf` measures it: the
/// extent a marker declares, so a sliver that declares the height it pins is
/// counted at that height rather than at the height it happens to be drawn at,
/// or else the height of the region's own box. A marked region and a region no
/// screen has marked yet are counted in the same walk, so a screen that has
/// moved some of its chrome to the marker still pays for the rest.
({double share, String parts, List<String> problems}) chromeNow(
  double viewport,
) {
  final List<Element> elements = compositionElements();
  double total = 0;
  final List<String> parts = <String>[];
  final List<String> problems = <String>[];
  for (final Element element in pinnedRegionsIn(elements)) {
    final double? height = pinnedExtent(element);
    final String name = pinnedRegionName(element);
    if (height == null) {
      problems.add(
        '$name has no box to measure and declares no extent, so the budget '
        'cannot be taken. Pass extent: to the marker.',
      );
      continue;
    }
    total += height;
    parts.add('$name ${height.round()}');
  }
  return (share: total / viewport, parts: parts.join(', '), problems: problems);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('the backlog names cells the matrix runs', () {
    expectBacklogCellsExist(chromeBudgetBacklog.keys, 'chromeBudgetBacklog');
  });

  group('the pinned regions fit the budget', () {
    for (final CompositionScreen screen in compositionScreens) {
      for (final MapEntry<String, Size> window in compositionWindows.entries) {
        testWidgets('${screen.name} at ${window.key}', (
          WidgetTester tester,
        ) async {
          double worst = 0;
          String parts = '';
          await overCell(
            tester,
            screen: screen,
            window: window.value,
            measure: (String where) async {
              final ({double share, String parts, List<String> problems})
              chrome = chromeNow(window.value.height);
              expect(
                chrome.problems,
                isEmpty,
                reason:
                    '${screen.name} at ${window.key} $where: '
                    '${chrome.problems.join(' ')}',
              );
              if (chrome.share > worst) {
                worst = chrome.share;
                parts = '$where: ${chrome.parts}';
              }
            },
          );
          expectCellWithin(
            cellOf(screen.name, window.key),
            worst: worst,
            budget: chromeBudgetFor(window.key),
            backlog: chromeBudgetBacklog,
            backlogName: 'chromeBudgetBacklog',
            failure:
                '${screen.name} at ${window.key} pins '
                '${(worst * 100).toStringAsFixed(1)} percent of the viewport '
                'and 13 section 2.3 allows '
                '${(chromeBudgetFor(window.key) * 100).round()}. A screen '
                'over the budget gives a region up rather than shrinking one '
                'below its density height. The regions are $parts.',
            // Half a percentage point. A backlog line states the debt to the
            // nearest half a point rather than to five decimal places, which
            // is a number a reader can hold and a number a fix moves by more
            // than.
            tolerance: 0.005,
          );
        });
      }
    }
  });
}
