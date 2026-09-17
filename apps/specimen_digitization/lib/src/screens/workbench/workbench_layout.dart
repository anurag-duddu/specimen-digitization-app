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

/// The share of the viewport the source header takes at rest
/// (13 sections 3.1 and 4.1; 07 section 6.1).
const double sourceHeaderMaxFraction = 0.55;

/// The share it holds once the reviewer has scrolled it to its floor.
///
/// The header is a `UiCollapsingHeader` between the two fractions, so the
/// arithmetic that used to compute a band out of the pane's leftovers is the
/// scroll position now: the reviewer's finger decides how much photograph is
/// on screen, between these two numbers, and nothing else does.
const double sourceHeaderMinFraction = 0.40;

/// The least height the photograph's own pixels are worth drawing at.
///
/// The floor under the fraction on a window short enough that 40 percent of
/// it is less than this, and the floor under the header's content where a
/// large text scale has grown the chrome row riding its edge.
const double sourceImageMinHeight = 120;

/// The body text size the layout measures a reviewer's text scale against.
///
/// A `TextScaler` is not a multiplier on every platform, so the only honest
/// way to ask "is the type large" is to scale a known size and compare.
const double layoutTextProbe = 14;

/// Above this multiple of [layoutTextProbe], a region stops pinning and
/// scrolls with the page instead.
///
/// Two regions read it. A source pane beside the evidence, where the pane's
/// own fixed rows are together taller than the pane at 200 percent and what
/// gives is the pinning rather than the content (finding V-1, pass criterion
/// 8.5). And the record's evidence segments, which stick under the header
/// while the chrome budget holds them and scroll away above it: 13 section
/// 2.3 says a screen over the budget gives a pinned region up rather than
/// shrinking one below its density height, and at 200 percent on a phone the
/// segments are the region the record can do without.
const double layoutTextScrollThreshold = 1.4;

/// The largest text the record's evidence segments still stick at.
///
/// 13 section 4.1 sticks them under the header, and 13 section 3.5 counts a
/// sticky bar against the chrome budget while it is stuck. On a 390 by 844
/// phone that budget is 236 dp, and at 130 percent text the frame has already
/// spent 177 of it on its top bar, the one line band and the action bar; the
/// segments are 61 more, which is 238. 13 section 2.3 says a screen over the
/// budget gives a pinned region up rather than shrinking one below its
/// density height, and the segments are the region this record can do
/// without: they scroll with the evidence there, one flick from the top of
/// it, and the tab strip still says which evidence is showing.
const double stickySegmentsMaxScale = 1.0;

/// True while the record's segments may stick under its header.
///
/// Two things spend the budget the bar needs: the reviewer's text size, above
/// [stickySegmentsMaxScale], and the window class. From `expanded` up 13
/// section 2.3 allows 20 percent, and the frame's own chrome takes it at
/// default type: at 1180 by 820 the top bar is 48, the one line band 52 and
/// the action bar 64, which is 164 of the 164 allowed, and at 1440 by 900 the
/// same 164 of 180. A 56 dp bar cannot stick in the 0 or the 16 that is left,
/// so from `expanded` up the segments scroll with the evidence at every text
/// size. This is the record beside a queue pane and a sidebar at 1440, which
/// leaves it 799 dp and the stacked regime, as much as the record on its own.
bool segmentsStick(TextScaler scaler, WindowClass window) =>
    window.index <= WindowClass.medium.index &&
    scaler.scale(layoutTextProbe) <= layoutTextProbe * stickySegmentsMaxScale;

/// True when the reviewer's text is large enough that a pane has to scroll.
bool paneScrollsAtThisTextScale(TextScaler scaler) =>
    scaler.scale(layoutTextProbe) > layoutTextProbe * layoutTextScrollThreshold;
