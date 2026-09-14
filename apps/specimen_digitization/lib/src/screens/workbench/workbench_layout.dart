/// The three pane regimes of the workbench
/// (screen blueprints, 6.1; responsive and platform adaptation, 3.5).
///
/// The regime is read from the width the workbench is given, never from the
/// platform and never from the window, because the workbench can be handed a
/// detail pane that is narrower than the window it sits in.
library;

import 'package:flutter/widgets.dart';

import '../../layout/window_class.dart';

/// How the source pane, the evidence pane and the history pane are arranged.
enum WorkbenchRegime {
  /// Below 840. One column: the source pane pinned as a collapsible header
  /// with the evidence scrolling beneath it.
  stacked,

  /// 840 to 1199. Source pane and evidence pane side by side, and History as
  /// a third segment of the evidence selector.
  twoPane,

  /// 1200 and above. Source pane, evidence pane and a persistent history
  /// pane, so a reviewer never loses their place in the evidence to check
  /// whether a field was corrected before.
  threePane;

  /// The regime for a pane of this width.
  static WorkbenchRegime fromWidth(double width) {
    if (width < WindowClass.expandedMin) return WorkbenchRegime.stacked;
    if (width < WindowClass.largeMin) return WorkbenchRegime.twoPane;
    return WorkbenchRegime.threePane;
  }

  /// True when the source pane scrolls as a pinned header rather than
  /// standing beside the evidence.
  bool get isStacked => this == WorkbenchRegime.stacked;

  /// True when History is a segment of the evidence selector rather than a
  /// pane of its own.
  bool get historyIsSegment => this != WorkbenchRegime.threePane;

  /// The source pane's flex in a row layout (blueprint 3.5).
  int get sourceFlex => this == WorkbenchRegime.threePane ? 5 : 1;

  /// The evidence pane's flex in a row layout.
  int get evidenceFlex => this == WorkbenchRegime.threePane ? 4 : 1;
}

/// The fixed width of the persistent history pane (responsive 3.5).
const double historyPaneWidth = 320;

/// The share of the viewport the pinned source header keeps on a stacked
/// layout (blueprint 6.1, and audit pass criterion 8.4).
const double sourcePaneMinViewportFraction = 0.4;

/// The evidence segments, in the order they are shown.
enum WorkbenchSegment {
  /// The two independent model readings and their comparison.
  readings('Readings'),

  /// The record's fields, their layers, and the authority evidence.
  fields('Fields'),

  /// The decision timeline and the version browser.
  history('History');

  const WorkbenchSegment(this.label);

  /// The visible word on the selector.
  final String label;

  /// The segments shown for a regime. History leaves the selector once it has
  /// a pane of its own.
  static List<WorkbenchSegment> forRegime(WorkbenchRegime regime) =>
      regime.historyIsSegment
      ? WorkbenchSegment.values
      : <WorkbenchSegment>[WorkbenchSegment.readings, WorkbenchSegment.fields];
}

/// The height the pinned source header asks for on a stacked layout.
///
/// The blueprint asks for 40 percent of the viewport, which a tall window
/// gives outright. The workbench offers it through a loose `Flexible`, so a
/// window too short to give it that much takes the difference out of the
/// photograph rather than pushing the decision bar off the screen.
double pinnedSourceHeight(BuildContext context) =>
    MediaQuery.sizeOf(context).height * sourcePaneMinViewportFraction;
