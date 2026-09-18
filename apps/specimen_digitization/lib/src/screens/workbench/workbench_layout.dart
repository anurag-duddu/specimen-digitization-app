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

/// True where the record's decision sits in the top bar rather than in the
/// frame's action bar (13 section 4.1, the expanded and large table).
///
/// From `expanded` up. 13 section 2.3 allows those classes 20 percent of the
/// viewport, and at 200 percent text the frame's own top bar is 61.25 dp, the
/// one line band 52 and the action bar 71.6: 184.85 of the 164 an 820 dp
/// window allows and of the 180 a 900 dp window allows, so no arrangement
/// that keeps all three holds the budget, and 2.3 says the screen gives a
/// region up rather than shrinking one. The region given up is the action
/// bar, whose job moves into the bar the record already publishes: a wide bar
/// has the width for the two decisions, the count and the two edge buttons
/// beside the identifier, and the bottom of the window is then the evidence
/// down to its last row. The band stays a region of its own, because it is the
/// one that says which data this is (07 section 1.3) and a strip the width of
/// the window is more visible than a chip in a bar. What remains pinned is
/// the bar and the band: 100 dp at default type and 113.25 at 200 percent,
/// which is 0.138 of 820 and 0.126 of 900.
///
/// Compact and medium keep the action bar: on a phone and a portrait tablet
/// the decision belongs under the thumb, and the 28 and 24 percent those
/// classes allow hold it (27.0 and 22.3 percent measured).
bool decisionInTopBar(WindowClass window) =>
    window.isAtLeast(WindowClass.expanded);

/// True while the record's segments may stick under its header.
///
/// Two things spend the budget the bar needs, and both are weighed: the
/// reviewer's text size, above [stickySegmentsMaxScale], and the window class.
/// At compact and medium the frame's bar, band and action bar leave room for
/// the segments at default type (27.0 and 22.3 percent measured with them
/// stuck). From `expanded` up the same three regions took the whole of the
/// 20 percent at default type, 164 of 164 at 1180 by 820, and the segments
/// could not stick at any size; with the decision in the top bar there
/// ([decisionInTopBar]) the frame pins 100 dp and a 48 dp bar at pointer
/// density brings the record at 1440 by 900, where it sits beside a queue
/// pane and a sidebar in the stacked regime, to 148 of the 180 allowed. The
/// clause is written against [decisionInTopBar] rather than as a constant so
/// that a frame that puts the action bar back at a class takes the sticky
/// segments away from it in the same change.
bool segmentsStick(TextScaler scaler, WindowClass window) =>
    scaler.scale(layoutTextProbe) <= layoutTextProbe * stickySegmentsMaxScale &&
    (window.index <= WindowClass.medium.index || decisionInTopBar(window));

/// True when the reviewer's text is large enough that a pane has to scroll.
bool paneScrollsAtThisTextScale(TextScaler scaler) =>
    scaler.scale(layoutTextProbe) > layoutTextProbe * layoutTextScrollThreshold;
