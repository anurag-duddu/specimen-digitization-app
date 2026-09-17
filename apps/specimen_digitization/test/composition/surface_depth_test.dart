// Surface depth (13 sections 2.2 and 5, `surface_depth`).
//
// "Things inside things" is the third row of 13 section 0: a photograph in a
// matte in a pane in a padded page in a scaffold, a glass decision bar over a
// glass pill. Two numbers say it. The first is the deepest chain of `Surface`
// and `GlassSurface` ancestors anywhere on the screen, which is at most one at
// compact and two above it. The second is how many `GlassSurface` panes are on
// the window at once, against the per class budget 09 section 3.3 sets and 13
// section 2.2 restates: one at compact, two at medium, three at expanded, four
// at large, counted on the whole screen including the navigation.
//
// The pane count is the same rule `glass_budget` holds in the size class
// goldens, and deliberately not the same instrument. `glass_budget` counts
// `BackdropFilter` render objects, which is what a device pays for and is zero
// for a pane whose sigma the quality setting has turned off; this counts
// `GlassSurface`, which is what a reader sees as a pane whatever the sigma.
// A screen that passes one and fails the other is a screen whose glass is off
// rather than absent, and 13 section 2.2 is about depth rather than cost.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'composition_harness.dart';

// ---------------------------------------------------------------------------
// The budgets.
// ---------------------------------------------------------------------------

/// The deepest chain of surfaces a window class allows (13 section 2.2).
int depthBudgetFor(String window) => isCompact(window) ? 1 : 2;

/// The frosted panes a window class allows (09 section 3.3; 13 section 2.2).
int glassBudgetFor(String window) => switch (windowClassOf(window)) {
  'compact' => 1,
  'medium' => 2,
  'expanded' => 3,
  _ => 4,
};

// ---------------------------------------------------------------------------
// The backlogs. Shrink only.
// ---------------------------------------------------------------------------

/// The deepest surface chain each cell draws today, where it is over budget.
///
/// Measured on 2026-09-17 against `front-end-refactor` at f3b6363, at every
/// window, both modes and 1.0, 1.3 and 2.0.
/// One cell, and it is the row of 13 section 0 that named this clause. The
/// record screen on a phone puts the photograph on its matte inside the
/// source pane's own surface, which is two where compact allows one. Slot A2
/// owns 13 section 4.1, where the photograph sits on the matte and the matte
/// is the collapsing header's own content.
const Map<String, num> surfaceDepthBacklog = <String, num>{
  'record@compact-390x844': 2,
};

/// The panes each cell draws today, where it is over budget.
///
/// It held seven, and six of them were one sentence: the shell gave a phone
/// two panes rather than one, because `UiTopBar` filled with `glass.flat` the
/// moment the body scrolled under it and the pill was already a pane. The size
/// class goldens' own `glass_budget` never saw it, because it counts at rest
/// and the second pane arrived on the first scroll. Slot A3 closed that half:
/// at compact the shell draws the bar's fill solid on `ground` and passes
/// `scrolledUnder: false`, which is the wave A amendment to 13 section 2.2
/// read as the gate measures it, so `setup`, `queue`, `intake` and `source`
/// are down to the pill's one pane.
///
/// Three left. The record screen at compact is three: the pill, the source
/// pane's own pane and the decision bar's; at medium it is three against two,
/// which is the same decision bar over the same rail. Slot A2 owns those.
///
/// The import sheet at compact is two and cannot reach one from a screen. A
/// sheet is its own surface, which is the exemption 13 section 2.2 states in
/// prose and this gate does not implement: it counts every `GlassSurface` on
/// the window, and a sheet opened over a list screen is the modal's pane over
/// the navigation's. Neither is a screen's to spend differently, so the line
/// records what it measures and the clause and the instrument are for the
/// integrator to reconcile.
const Map<String, num> glassCountBacklog = <String, num>{
  'import-sheet@compact-390x844': 2,
  'record@compact-390x844': 3,
  'record@medium-768x1024': 3,
};

// ---------------------------------------------------------------------------
// The measurements.
// ---------------------------------------------------------------------------

/// True where [widget] is one of the two surfaces 13 section 2.2 counts.
bool isSurface(Widget widget) => widget is Surface || widget is GlassSurface;

/// The deepest chain of surfaces in the tree right now.
int surfaceDepthNow() {
  int deepest = 0;
  for (final Element element in compositionElements()) {
    if (!isSurface(element.widget)) continue;
    int above = 0;
    element.visitAncestorElements((Element parent) {
      if (isSurface(parent.widget)) above++;
      return true;
    });
    if (above + 1 > deepest) deepest = above + 1;
  }
  return deepest;
}

/// The frosted panes in the tree right now.
List<Element> glassPanesNow() => compositionElements()
    .where((Element element) => element.widget is GlassSurface)
    .toList();

/// How many frosted panes are in the tree right now.
int glassCountNow() => glassPanesNow().length;

/// What the panes sit in, for a failure to name them.
///
/// A `GlassSurface` is not a product name, so the nearest enclosing widget
/// whose name is one is what a reader can search for.
String glassPartsNow() => <String>[
  for (final Element pane in glassPanesNow()) _paneOwner(pane),
].join(', ');

/// The nearest ancestor of [pane] that a reader would recognise by name.
String _paneOwner(Element pane) {
  String owner = 'GlassSurface';
  pane.visitAncestorElements((Element parent) {
    final String name = '${parent.widget.runtimeType}';
    if (name.startsWith('Ui') || name.startsWith('Workbench')) {
      owner = name;
      return false;
    }
    return true;
  });
  return owner;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('the backlogs name cells the matrix runs', () {
    expectBacklogCellsExist(surfaceDepthBacklog.keys, 'surfaceDepthBacklog');
    expectBacklogCellsExist(glassCountBacklog.keys, 'glassCountBacklog');
  });

  group('surfaces do not sit inside surfaces', () {
    for (final CompositionScreen screen in compositionScreens) {
      for (final MapEntry<String, Size> window in compositionWindows.entries) {
        testWidgets('${screen.name} at ${window.key}', (
          WidgetTester tester,
        ) async {
          int depth = 0;
          int panes = 0;
          String parts = '';
          await overCell(
            tester,
            screen: screen,
            window: window.value,
            measure: (String where) async {
              await sweepScrolls(tester, () async {
                final int chain = surfaceDepthNow();
                if (chain > depth) depth = chain;
                final int now = glassCountNow();
                if (now > panes) {
                  panes = now;
                  parts = '$where: ${glassPartsNow()}';
                }
              });
            },
          );
          final String cell = cellOf(screen.name, window.key);
          expectCellWithin(
            cell,
            worst: depth,
            budget: depthBudgetFor(window.key),
            backlog: surfaceDepthBacklog,
            backlogName: 'surfaceDepthBacklog',
            failure:
                '${screen.name} at ${window.key} stacks $depth surfaces and '
                '13 section 2.2 allows ${depthBudgetFor(window.key)}. A '
                'photograph sits on its matte and the matte sits on the page; '
                'a row sits on the page, not on a card on the page.',
          );
          expectCellWithin(
            cell,
            worst: panes,
            budget: glassBudgetFor(window.key),
            backlog: glassCountBacklog,
            backlogName: 'glassCountBacklog',
            failure:
                '${screen.name} at ${window.key} draws $panes frosted panes '
                'and the budget for this class is '
                '${glassBudgetFor(window.key)} (09 section 3.3). Every pane '
                'is a save layer. The panes are $parts.',
          );
        });
      }
    }
  });
}
