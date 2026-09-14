/// The three pane regimes of the workbench
/// (screen blueprints, 6.1; responsive and platform adaptation, 3.5).
///
/// The regime is read from the width the workbench is given, never from the
/// platform and never from the window, because the workbench can be handed a
/// detail pane that is narrower than the window it sits in.
library;

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

/// The floor the evidence pane keeps on a stacked layout.
///
/// Enough for the segment selector and two rows beneath it, which is what
/// makes a pane worth scrolling. A pane squeezed below this has nowhere to
/// scroll to, which on a device reads as "the screen is frozen" rather than
/// as "the photograph is large".
///
/// Deliberately smaller than the photograph's target share: on a phone in
/// portrait both cannot have what they would like, and the photograph is the
/// one the blueprint says may shrink.
const double evidencePaneMinHeight = 180;

/// The height the pinned source header asks for on a stacked layout.
///
/// [available] is the height the workbench itself was given, never the height
/// of the window: the blueprint's forty percent is measured against the pane
/// the reviewer is looking at. [free] is what is left of it once the fixed
/// chrome, meaning the record header, the photograph's title row and the
/// decision bar, has had its height.
///
/// Splitting those two apart is the fix for the record screen that would not
/// scroll on a phone. Taking the decision bar's height out of the evidence
/// pane's own share left the pane with a zero-height viewport, and a scroll
/// view with no viewport does not move under a finger.
///
/// The forty percent is a target. [evidencePaneMinHeight] is the floor, and
/// the floor wins: a window too short for both takes the difference out of
/// the photograph rather than out of the evidence.
double pinnedSourceHeight(double available, double free) {
  final double target = available * sourcePaneMinViewportFraction;
  final double ceiling = free - evidencePaneMinHeight;
  final double height = target < ceiling ? target : ceiling;
  if (height >= pinnedSourceMinHeight) return height;
  // Neither can have what it wants. The photograph keeps the least height it
  // can be read at, rather than being drawn smaller than its own controls and
  // region list, and the evidence pane takes whatever is left. A pane with a
  // small viewport still scrolls; a pane with none does not.
  return free - pinnedSourceMinHeight > 0 ? pinnedSourceMinHeight : 0;
}

/// The least height the pinned photograph is worth drawing at.
///
/// Its own zoom controls and its region list are fixed rows inside it, so a
/// box shorter than this has no room left for the photograph and overflows
/// its own column. Below this the header is dropped entirely and the
/// photograph is reached through the full screen control instead.
const double pinnedSourceMinHeight = 160;
