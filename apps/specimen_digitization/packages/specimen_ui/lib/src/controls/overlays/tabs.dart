/// Tabs and their panes (10 section 4.3, `UiTabs` and `UiTabView`).
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import '../../primitives/surface.dart';

/// One tab.
@immutable
class UiTab {
  /// A tab labelled [label].
  const UiTab({required this.label, this.icon, this.semanticsLabel});

  /// The visible label. 10 characters is the target, 18 the maximum, because
  /// three tabs have to fit side by side at 360 (02 section 7).
  final String label;

  /// An optional glyph before the label.
  final IconSpec? icon;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;
}

/// The resolved paint of one tab strip.
@immutable
class UiTabsStyle {
  /// Binds every token a strip draws with.
  const UiTabsStyle({
    required this.label,
    required this.selectedColor,
    required this.color,
    required this.selectedFill,
    required this.trackPadding,
    required this.tabPadding,
    required this.minHeight,
    required this.gap,
  });

  /// A tab label's type role.
  final TextStyle label;

  /// The current tab's label colour.
  final Color selectedColor;

  /// Every other tab's label colour.
  final Color color;

  /// The fill behind the current tab.
  final Color selectedFill;

  /// Padding inside the track, around the tabs.
  final EdgeInsetsGeometry trackPadding;

  /// Padding inside one tab.
  final EdgeInsetsGeometry tabPadding;

  /// A tab's visual height.
  final double minHeight;

  /// The gap between a glyph and its label.
  final double gap;

  /// The style a strip draws with in [ui].
  static UiTabsStyle resolve(UiThemeData ui) => UiTabsStyle(
    label: ui.type.title,
    selectedColor: ui.color.paper,
    color: ui.color.inkSecondary,
    selectedFill: ui.color.ink,
    trackPadding: EdgeInsetsDirectional.all(ui.space.s1),
    tabPadding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s5),
    // The `lg` size 10 section 4.3 binds the strip to.
    minHeight: largeControlHeight,
    gap: ui.space.s2,
  );

  /// The `lg` control height (10 section 4).
  static const double largeControlHeight = 56;
}

/// A strip of tabs over a set of panes.
///
/// Retires `TabBar`. Selection lives in a `ValueNotifier<int>` the caller
/// owns, not in a `TabController`: a tab index is state the screen already
/// has, and a second controller is a second thing to keep in step.
///
/// 10 section 4.3 specifies the strip as a `UiSegmented` at `lg`, which the
/// actions family owns. Until that lands the strip is a minimal capsule track
/// built here, and any caller may pass its own through [strip].
class UiTabs extends StatelessWidget {
  /// A strip of [tabs] bound to [selected].
  const UiTabs({
    super.key,
    required this.tabs,
    required this.selected,
    required this.semanticsLabel,
    this.strip,
    this.style,
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

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiTabsStyle? style;

  @override
  Widget build(BuildContext context) {
    final Widget? given = strip;
    if (given != null) return given;
    // TODO(fe/actions): default the strip to UiSegmented at lg when it merges.
    return _CapsuleStrip(
      tabs: tabs,
      selected: selected,
      semanticsLabel: semanticsLabel,
      style: style ?? UiTabsStyle.resolve(context.ui),
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

/// The default strip: a capsule track with an ink capsule on the current tab.
class _CapsuleStrip extends StatefulWidget {
  const _CapsuleStrip({
    required this.tabs,
    required this.selected,
    required this.semanticsLabel,
    required this.style,
  });

  final List<UiTab> tabs;
  final ValueNotifier<int> selected;
  final String semanticsLabel;
  final UiTabsStyle style;

  @override
  State<_CapsuleStrip> createState() => _CapsuleStripState();
}

class _CapsuleStripState extends State<_CapsuleStrip> {
  List<FocusNode> _nodes = <FocusNode>[];

  @override
  void initState() {
    super.initState();
    _syncNodes();
  }

  @override
  void didUpdateWidget(_CapsuleStrip oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.tabs.length != widget.tabs.length) _syncNodes();
  }

  @override
  void dispose() {
    _disposeNodes();
    super.dispose();
  }

  void _disposeNodes() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
  }

  void _syncNodes() {
    _disposeNodes();
    _nodes = <FocusNode>[
      for (int i = 0; i < widget.tabs.length; i++)
        FocusNode(debugLabel: 'UiTab $i'),
    ];
  }

  void _select(int index) {
    if (index < 0 || index >= widget.tabs.length) return;
    widget.selected.value = index;
  }

  /// Moves by [step] in reading order, selecting as it goes.
  ///
  /// Automatic activation, which is the WAI-ARIA tab pattern: the pane under
  /// the tab the reviewer arrows onto is the pane they are reading. [step] is
  /// already mirrored for the reading direction by the caller.
  void _move(int step) {
    if (widget.tabs.isEmpty) return;
    final int from = _nodes.indexWhere((FocusNode node) => node.hasFocus);
    final int start = from < 0 ? widget.selected.value : from;
    int next = (start + step) % widget.tabs.length;
    if (next < 0) next += widget.tabs.length;
    _select(next);
    _nodes[next].requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiTabsStyle style = widget.style;
    // Mirrored rather than hard coded: forward is to the right in a left to
    // right window and to the left in a right to left one (04 section 5.3).
    final int forward =
        Directionality.of(context) == TextDirection.rtl ? -1 : 1;
    return Shortcuts(
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.arrowRight): _TabMoveIntent(1),
        SingleActivator(LogicalKeyboardKey.arrowLeft): _TabMoveIntent(-1),
      },
      child: Actions(
        actions: <Type, Action<Intent>>{
          _TabMoveIntent: CallbackAction<_TabMoveIntent>(
            onInvoke: (_TabMoveIntent intent) {
              _move(intent.step * forward);
              return null;
            },
          ),
        },
        child: Semantics(
          container: true,
          explicitChildNodes: true,
          role: SemanticsRole.tabBar,
          label: widget.semanticsLabel,
          child: Surface(
            capsule: true,
            hairline: true,
            padding: style.trackPadding,
            child: ValueListenableBuilder<int>(
              valueListenable: widget.selected,
              builder: (BuildContext context, int index, Widget? _) => Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  for (int i = 0; i < widget.tabs.length; i++)
                    _Tab(
                      tab: widget.tabs[i],
                      style: style,
                      selected: i == index,
                      focusNode: _nodes[i],
                      onPressed: () {
                        _select(i);
                        _nodes[i].requestFocus();
                      },
                      motion: ui.motion,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// One tab of the default strip.
class _Tab extends StatelessWidget {
  const _Tab({
    required this.tab,
    required this.style,
    required this.selected,
    required this.focusNode,
    required this.onPressed,
    required this.motion,
  });

  final UiTab tab;
  final UiTabsStyle style;
  final bool selected;
  final FocusNode focusNode;
  final VoidCallback onPressed;
  final MotionTokens motion;

  @override
  Widget build(BuildContext context) {
    final Color foreground = selected ? style.selectedColor : style.color;
    return Pressable(
      semanticsLabel: tab.semanticsLabel ?? tab.label,
      onPressed: onPressed,
      role: PressableRole.tab,
      selected: selected,
      capsule: true,
      focusNode: focusNode,
      builder: (BuildContext context, Set<WidgetState> states) =>
          AnimatedContainer(
            duration: motion.capsuleFill,
            curve: MotionTokens.standardCurve,
            constraints: BoxConstraints(minHeight: style.minHeight),
            decoration: ShapeDecoration(
              shape: const StadiumBorder(),
              color: selected
                  ? style.selectedFill
                  : style.selectedFill.withValues(alpha: 0),
            ),
            padding: style.tabPadding,
            alignment: Alignment.center,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (tab.icon != null) ...<Widget>[
                  UiIcon(
                    tab.icon!,
                    size: UiIconSize.inline,
                    color: foreground,
                    current: selected,
                  ),
                  SizedBox(width: style.gap),
                ],
                Flexible(
                  child: Text(
                    tab.label,
                    style: style.label.copyWith(color: foreground),
                  ),
                ),
              ],
            ),
          ),
    );
  }
}

/// Moving the reviewer along the strip.
@immutable
class _TabMoveIntent extends Intent {
  const _TabMoveIntent(this.step);

  /// Plus one forward in reading order, minus one back.
  final int step;
}
