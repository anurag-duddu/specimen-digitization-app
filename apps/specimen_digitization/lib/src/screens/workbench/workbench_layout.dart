/// Constraint-based composition for the review workspace.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart' show UiLayoutMetrics;

import '../../layout/window_class.dart';

/// One scroll on narrow panes; a dominant canvas and one inspector on wide panes.
enum WorkbenchRegime {
  stacked,
  twoPane;

  static WorkbenchRegime fromWidth(double width) =>
      fromConstraints(BoxConstraints(maxWidth: width));

  /// Side-by-side work needs readable columns and a useful vertical viewport.
  static WorkbenchRegime fromConstraints(
    BoxConstraints constraints, {
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    final metrics = UiLayoutMetrics.fromConstraints(
      constraints,
      textScaler: textScaler,
    );
    final scale = (textScaler.scale(16) / 16).clamp(1.0, double.infinity);
    final short =
        constraints.hasBoundedHeight && constraints.maxHeight < 400 * scale;
    final hasColumns =
        metrics.columns(
          // Landscape review can use the shared readable minimum instead of
          // spending its limited height on a photograph above the readings.
          minWidth: short
              ? metrics.minColumnWidth
              : reviewColumnMinWidth * scale,
          maxColumns: 2,
        ) ==
        2;
    final hasHeight =
        !constraints.hasBoundedHeight ||
        constraints.maxHeight >= reviewMinimumPaneHeight * scale;
    return hasColumns && hasHeight ? twoPane : stacked;
  }

  bool get isStacked => this == stacked;
}

/// Bounds the reading measure while leaving the photograph room to breathe.
const double reviewInspectorMaxWidth = 650;

/// Minimum readable column for a photograph beside label comparison.
/// This local content policy is scaled with text before choosing two panes.
const double reviewColumnMinWidth = 360;

/// Below this available height, one page scroll gives controls room to appear.
const double reviewMinimumPaneHeight = 240;

/// Evidence views share one location, including on the widest windows.
enum WorkbenchSegment {
  readings('Label review'),
  fields('Specimen data'),
  history('Review history');

  const WorkbenchSegment(this.label);
  final String label;

  static List<WorkbenchSegment> forRegime(WorkbenchRegime regime) => values;
}

/// The general source header's expanded share, retained by the region editor.
const double sourceHeaderMaxFraction = 0.55;

/// The general source header's collapsed share, retained by the region editor.
const double sourceHeaderMinFraction = 0.40;

/// The review header leaves the first literal reading visible at rest.
/// The image remains the largest single region, with controls in its band.
const double reviewSourceHeaderMaxFraction = 0.43;

/// The review header's collapsed share. The review and region editor have
/// different reading flows, so changing this does not resize the editor.
const double reviewSourceHeaderMinFraction = 0.28;

/// The least height the photograph's own pixels are worth drawing at.
///
/// The floor under the fraction on a window short enough that the collapsed share of
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

/// Tabs stick only at default text size, when the compact chrome budget holds.
bool segmentsStick(TextScaler scaler, WindowClass window) =>
    scaler.scale(layoutTextProbe) <= layoutTextProbe * stickySegmentsMaxScale;

/// True when the reviewer's text is large enough that a pane has to scroll.
bool paneScrollsAtThisTextScale(TextScaler scaler) =>
    scaler.scale(layoutTextProbe) > layoutTextProbe * layoutTextScrollThreshold;
