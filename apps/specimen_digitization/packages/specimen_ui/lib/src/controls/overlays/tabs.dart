/// Tabs and their panes (10 section 4.3, `UiTabs` and `UiTabView`).
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
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
              _ScrollingTabs(selected: selected, count: tabs.length,
                  child: _track()),
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

/// A tab strip too wide for its column, scrolled with fading edges.
///
/// The fade is drawn only on a side there is something to scroll to, so an
/// edge that is the end of the row stays crisp and a faded edge always means
/// "there is more this way". It is a mask over the strip rather than a
/// gradient painted on top of it, because the strip is drawn over the sky and
/// a solid gradient would have to know which surface it is covering.
class _ScrollingTabs extends StatefulWidget {
  const _ScrollingTabs({
    required this.selected,
    required this.count,
    required this.child,
  });

  final ValueNotifier<int> selected;
  final int count;
  final Widget child;

  @override
  State<_ScrollingTabs> createState() => _ScrollingTabsState();
}

class _ScrollingTabsState extends State<_ScrollingTabs> {
  final ScrollController _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    widget.selected.addListener(_reveal);
    _controller.addListener(_edgesChanged);
  }

  @override
  void didUpdateWidget(_ScrollingTabs old) {
    super.didUpdateWidget(old);
    if (old.selected != widget.selected) {
      old.selected.removeListener(_reveal);
      widget.selected.addListener(_reveal);
    }
  }

  @override
  void dispose() {
    widget.selected.removeListener(_reveal);
    _controller
      ..removeListener(_edgesChanged)
      ..dispose();
    super.dispose();
  }

  void _edgesChanged() {
    if (mounted) setState(() {});
  }

  /// Brings the chosen tab into view.
  ///
  /// The offset is the reviewer's position along the row rather than the
  /// tab's own box: the boxes belong to `UiSegmented`, and a strip that
  /// reached inside it to measure one would be a second copy of that layout.
  /// With the 2 to 5 tabs a strip carries, the first tab lands at the start,
  /// the last at the end, and the ones between are in the middle, which is
  /// what "scrolled into view" asks for.
  void _reveal() {
    // After the frame the new selection produces, not during the
    // notification: the track's extent is read from a laid out viewport, and
    // a listener runs before the rebuild it caused.
    WidgetsBinding.instance.addPostFrameCallback((Duration _) => _scroll());
  }

  void _scroll() {
    if (!mounted || !_controller.hasClients || widget.count < 2) return;
    final ScrollPosition position = _controller.position;
    final double target =
        position.maxScrollExtent *
        (widget.selected.value.clamp(0, widget.count - 1) /
            (widget.count - 1));
    final MotionTokens motion = context.ui.motion;
    if (motion.reduced) {
      _controller.jumpTo(target);
      return;
    }
    _controller.animateTo(
      target,
      duration: motion.medium,
      curve: MotionTokens.standardCurve,
    );
  }

  bool get _fadeStart =>
      _controller.hasClients && _controller.position.extentBefore > 0;

  bool get _fadeEnd =>
      _controller.hasClients && _controller.position.extentAfter > 0;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextDirection direction = Directionality.of(context);
    final Widget scroller = SingleChildScrollView(
      controller: _controller,
      scrollDirection: Axis.horizontal,
      child: widget.child,
    );
    // The mask is always in the tree, opaque at both ends when there is
    // nothing to fade. Adding and removing it instead would change the
    // scroller's position in the tree, which re-inflates the `Scrollable`,
    // which throws away its `ScrollPosition` and with it the animation that
    // was bringing the chosen tab into view.
    return ShaderMask(
      blendMode: BlendMode.dstIn,
      shaderCallback: (Rect bounds) {
        final double fade = bounds.width == 0
            ? 0
            : (ui.space.s6 / bounds.width).clamp(0, 0.5);
        return LinearGradient(
          begin: AlignmentDirectional.centerStart,
          end: AlignmentDirectional.centerEnd,
          stops: <double>[0, fade, 1 - fade, 1],
          colors: <Color>[
            Color.fromRGBO(0, 0, 0, _fadeStart ? 0 : 1),
            const Color.fromRGBO(0, 0, 0, 1),
            const Color.fromRGBO(0, 0, 0, 1),
            Color.fromRGBO(0, 0, 0, _fadeEnd ? 0 : 1),
          ],
        ).createShader(bounds, textDirection: direction);
      },
      child: scroller,
    );
  }
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
