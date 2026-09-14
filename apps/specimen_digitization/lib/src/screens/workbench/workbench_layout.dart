/// The three pane regimes of the workbench
/// (screen blueprints, 6.1; responsive and platform adaptation, 3.5).
///
/// The regime is read from the width the workbench is given, never from the
/// platform and never from the window, because the workbench can be handed a
/// detail pane that is narrower than the window it sits in.
library;

import 'package:flutter/painting.dart';

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

/// The height the pinned photograph's own pixels are given on a stacked
/// layout.
///
/// [available] is the height the workbench itself was given, never the height
/// of the window: the blueprint's forty percent is measured against the pane
/// the reviewer is looking at. [free] is what is left of it once every fixed
/// row has had its height: the record header, the decision bar, and the
/// source pane's own chrome, meaning its title row, its caveat, its view
/// controls and its region chips.
///
/// Taking the pane's own chrome out before this is the fix for finding V-1.
/// The old floor was a single number, 160, that was smaller than the chrome
/// it was supposed to contain, so a pane drawn at the floor overflowed its
/// own column and the photograph got no height at all. The chrome is measured
/// now, at whatever text scale the reviewer is reading at, and this function
/// only ever decides how many pixels of photograph sit inside it.
///
/// The forty percent is a target. [evidencePaneMinHeight] is the floor, and
/// the floor wins: a window too short for both takes the difference out of
/// the photograph rather than out of the evidence.
///
/// Returns zero when the photograph cannot be given [sourceImageMinHeight]
/// without squeezing the evidence pane below the height it can still scroll
/// at. The workbench answers a zero by scrolling the whole record instead of
/// pinning the photograph, so the pixels are still on the screen.
double pinnedSourceHeight(double available, double free) {
  final double target = available * sourcePaneMinViewportFraction;
  final double ceiling = free - evidencePaneMinHeight;
  final double height = target < ceiling ? target : ceiling;
  if (height >= sourceImageMinHeight) return height;
  // Neither can have what it wants. The photograph takes the least height it
  // can be read at, as long as the evidence pane can still scroll at its hard
  // minimum. A pane with a small viewport still scrolls; a pane with none
  // does not.
  return free - evidencePaneHardMinHeight >= sourceImageMinHeight
      ? sourceImageMinHeight
      : 0;
}

/// The least height the photograph's own pixels are worth drawing at.
///
/// This is the image band alone. The pane's controls and its region list are
/// measured separately and are never taken out of it, which is what the old
/// `pinnedSourceMinHeight` got wrong.
const double sourceImageMinHeight = 120;

/// The least a scrolling evidence pane can be given and still move under a
/// finger.
///
/// Below [evidencePaneMinHeight] the pane is cramped; below this it is not a
/// scroll view any more. When even this cannot be met the workbench stops
/// pinning the photograph and scrolls the whole record.
const double evidencePaneHardMinHeight = 96;

/// The body text size the layout measures a reviewer's text scale against.
///
/// A `TextScaler` is not a multiplier on every platform, so the only honest
/// way to ask "is the type large" is to scale a known size and compare.
const double layoutTextProbe = 14;

/// Above this multiple of [layoutTextProbe], a pane stops pinning its parts
/// against each other and scrolls as one instead.
///
/// At normal type the photograph is pinned above the evidence and the
/// decision bar is pinned below it, which is what the blueprint asks for. At
/// 200 percent the pane's own fixed rows are taller than the pane, and
/// something has to give: what gives is the pinning, not the content
/// (finding V-1, pass criterion 8.5).
const double layoutTextScrollThreshold = 1.4;

/// True when the reviewer's text is large enough that a pane has to scroll.
bool paneScrollsAtThisTextScale(TextScaler scaler) =>
    scaler.scale(layoutTextProbe) > layoutTextProbe * layoutTextScrollThreshold;
