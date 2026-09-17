/// Tabs and their panes (10 section 4.3, `UiTabs` and `UiTabView`).
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/edge_fade.dart';
import '../../primitives/fit.dart';
import '../actions/button.dart' show UiSize;
import '../actions/segmented.dart';

/// One tab.
@immutable
class UiTab {
  /// A tab labelled [label].
  const UiTab({required this.label, this.semanticsLabel});

  /// The visible label. 10 characters is the target, 18 the maximum, because
  /// three tabs have to fit side by side at 360 (02 section 7).
  final String label;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;
}

/// A strip of tabs over a set of panes.
///
/// Retires `TabBar`. Selection lives in a `ValueNotifier<int>` the caller
/// owns, not in a `TabController`: a tab index is state the screen already
/// has, and a second controller is a second thing to keep in step.
///
/// The strip is a `UiSegmented` at `lg`, which is what 10 section 4.3
/// specifies it as, so a tab strip and a segmented control are one control
/// with one set of tokens, one thumb and one keyboard pattern: arrows move
/// focus along the track and `Enter` chooses, so arrowing past a tab does not
/// swap the pane under the reviewer on the way through. A strip therefore
/// carries 2 to 5 tabs, which is `UiSegmented`'s own range.
///
/// A caller that needs something else, a strip of glyph tabs or a row that
/// scrolls, passes it through [strip] rather than growing this control.
class UiTabs extends StatelessWidget {
  /// A strip of [tabs] bound to [selected].
  const UiTabs({
    super.key,
    required this.tabs,
    required this.selected,
    required this.semanticsLabel,
    this.strip,
  });

  /// The tabs, in the order they are read.
  final List<UiTab> tabs;

  /// The current index. The strip writes to it and rebuilds from it.
  final ValueNotifier<int> selected;

  /// What the strip is called, for a screen reader.
  final String semanticsLabel;

  /// Replaces the default strip.
  ///
  /// The slot 10 section 5 needs: a screen that already has a segmented
  /// control passes it here rather than getting a second one.
  final Widget? strip;

  /// The width the strip needs to draw every label in full.
  ///
  /// The same arithmetic `UiSegmented` lays itself out with, asked of that
  /// control's own style rather than restated here: equal segments at the
  /// widest label, each floored at the hit box, inside the track's inset. A
  /// change to the segment padding therefore moves this with it.
  double _intrinsicWidth(BuildContext context, UiSegmentedStyle style) {
    if (tabs.isEmpty) return 0;
    double widest = 0;
    for (final UiTab tab in tabs) {
      final double width = measureLabel(
        context,
        tab.label,
        style.labelStyle,
      ).width;
      if (width > widest) widest = width;
    }
    final double padding = style.segmentPadding
        .resolve(Directionality.of(context))
        .horizontal;
    return tabs.length *
            math.max(style.minSegmentWidth, widest + padding) +
        2 * style.inset;
  }

  @override
  Widget build(BuildContext context) {
    final Widget? given = strip;
    if (given != null) return given;
    final UiSegmentedStyle style = UiSegmentedStyle.resolve(
      context.ui,
      UiSize.lg,
    );
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth: _intrinsicWidth(context, style),
          builder: (BuildContext context, bool _) => _track(),
        ),
        // 11 section 3.3 gives a tab row one compact variant: it scrolls, and
        // the edges fade so the reviewer can see that there is more. The
        // track inside is the same control at the same size, so there is one
        // thumb, one keyboard pattern and one set of tokens either way.
        FitVariant(
          intrinsicWidth: 0,
          builder: (BuildContext context, bool _) =>
              ValueListenableBuilder<int>(
                valueListenable: selected,
                builder: (BuildContext context, int index, Widget? _) =>
                    EdgeFadedRow(
                      index: index,
                      length: tabs.length,
                      fadeExtent: context.ui.space.s6,
                      child: _track(),
                    ),
              ),
        ),
      ],
    );
  }

  /// The strip itself, and the node a screen reader reads it as.
  ///
  /// The `tabBar` role sits directly over the segments, inside the scroller
  /// rather than around it: every child node of a tab bar has to carry the
  /// `tab` role, and a `Scrollable`'s own node between the two would fail
  /// that check rather than degrade.
  Widget _track() => Semantics(
    container: true,
    // The bar and its tabs, and nothing between them: a node of any other
    // role under `tabBar` fails the SDK's own check rather than degrading.
    explicitChildNodes: true,
    role: SemanticsRole.tabBar,
    label: semanticsLabel,
    child: ValueListenableBuilder<int>(
      valueListenable: selected,
      builder: (BuildContext context, int index, Widget? _) =>
          UiSegmented<int>(
            size: UiSize.lg,
            value: tabs.isEmpty ? 0 : index.clamp(0, tabs.length - 1),
            segments: <UiSegment<int>>[
              for (int i = 0; i < tabs.length; i++)
                UiSegment<int>(
                  value: i,
                  label: tabs[i].label,
                  semanticsLabel: tabs[i].semanticsLabel,
                ),
            ],
            onChanged: (int value) => selected.value = value,
          ),
    ),
  );
}

/// The pane under a [UiTabs].
///
/// Retires `TabBarView`. Panes cross fade; they do not slide. A shared axis is
/// declined per 04 section 3.3 until routes need one, and a large horizontal
/// slide beside a photograph produces induced motion: the photograph appears
/// to drift the other way (04 section 5.4).
class UiTabView extends StatelessWidget {
  /// Shows the pane [selected] names.
  const UiTabView({
    super.key,
    required this.selected,
    required this.children,
  });

  /// The current index, shared with the strip.
  final ValueNotifier<int> selected;

  /// One pane per tab, in the same order.
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return ValueListenableBuilder<int>(
      valueListenable: selected,
      builder: (BuildContext context, int index, Widget? _) {
        final int safe = children.isEmpty
            ? 0
            : index.clamp(0, children.length - 1);
        return Semantics(
          container: true,
          role: SemanticsRole.tabPanel,
          child: AnimatedSwitcher(
            duration: ui.motion.medium,
            switchInCurve: MotionTokens.standardCurve,
            switchOutCurve: MotionTokens.standardCurve,
            child: children.isEmpty
                ? const SizedBox.shrink()
                : KeyedSubtree(
                    key: ValueKey<int>(safe),
                    child: children[safe],
                  ),
          ),
        );
      },
    );
  }
}
