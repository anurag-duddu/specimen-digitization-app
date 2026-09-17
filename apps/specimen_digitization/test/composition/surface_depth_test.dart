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
///
/// Empty, and it is a real zero. The one cell it held was the row of 13
/// section 0 that named this clause: the record on a phone put the photograph
/// on its matte and a floating glass capsule of view controls on top of the
/// matte, which is two surfaces where compact allows one. The controls ride
/// the collapsing header's lower edge now, beside the matte rather than over
/// it (13 sections 3.1 and 4.1), and the chain is one.
const Map<String, num> surfaceDepthBacklog = <String, num>{};

/// The panes each cell draws today, where it is over budget.
/// Two cells. The import sheet at compact draws its own pane over the
/// navigation pill the scaffold floats beneath the barrier: the pill is still
/// mounted and still blurs under a modal, and a phone's budget is one pane
/// (slot A3 owns the shell's half of 13 section 2.2). The record at medium
/// draws three where the class allows two: the scrolled top bar, the frame's
/// action bar and the collapsed header's own chrome all blur from medium up,
/// because the wave A amendment to 13 section 2.2 publishes `GlassQuality.off`
/// at compact only. One of the three has to draw solid at medium, and which
/// is a pattern decision for `fe/polish-3` rather than a screen's.
///
/// Five compact cells left this backlog when the instrument started counting
/// what the amendment counts: a `GlassSurface` published `GlassQuality.off`
/// draws solid and builds no filter, and the earlier count of every
/// `GlassSurface` put the frame's solid top bar, band and header chrome on
/// the same footing as the one pane that blurs.
///
/// Slot A3 closed the shell's half of it in the same wave: at compact the
/// shell draws the bar's fill solid on `ground` and passes
/// `scrolledUnder: false`, which is the wave A amendment to 13 section 2.2
/// read as the gate measures it, so `setup`, `queue`, `intake` and `source`
/// are down to the pill's one pane by either count.
const Map<String, num> glassCountBacklog = <String, num>{
  'import-sheet@compact-390x844': 2,
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
///
/// A `GlassSurface` published `GlassQuality.off` draws the same surface solid
/// (13 section 2.2, wave A amendment) and builds no `BackdropFilter`, so it is
/// not a pane this budget counts: the budget is the count of save layers, and
/// a solid fill is not one. A pane is frosted where its own build put a filter
/// under it, which is read here as a filter in its subtree above any pane it
/// holds, since `GlassSurface` is the one widget in the system that blurs.
List<Element> glassPanesNow() => compositionElements()
    .where(
      (Element element) => element.widget is GlassSurface && isFrosted(element),
    )
    .toList();

/// True where the pane at [pane] blurs what is behind it.
bool isFrosted(Element pane) {
  bool found = false;
  void visit(Element element) {
    if (found) return;
    if (element.widget is BackdropFilter) {
      found = true;
      return;
    }
    if (element != pane && element.widget is GlassSurface) return;
    element.visitChildren(visit);
  }

  visit(pane);
  return found;
}

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
