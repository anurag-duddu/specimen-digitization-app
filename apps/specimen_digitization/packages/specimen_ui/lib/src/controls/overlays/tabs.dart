/// Text tabs with manual keyboard activation and in-place pane changes.
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/edge_fade.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';

/// One tab.
@immutable
class UiTab {
  /// A tab labelled [label].
  const UiTab({required this.label, this.semanticsLabel});

  /// The visible label. Keep it brief enough to scan beside the other tabs.
  final String label;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;
}

/// The text, underline and measured geometry of a tab strip.
///
/// Hosts use this same sizing API to reserve header height or choose an
/// overflow layout. Selection never changes font weight or slot geometry.
@immutable
class UiTabStyle {
  /// Binds the tab tokens. Prefer [resolve].
  const UiTabStyle({
    required this.labelStyle,
    required this.label,
    required this.selectedLabel,
    required this.underline,
    required this.underlineWidth,
    required this.slotPadding,
    required this.outerHeight,
  });

  /// The type role, identical for selected and unselected tabs.
  final TextStyle labelStyle;

  /// The label colour of an unselected tab.
  final Color label;

  /// The label colour of the selected tab.
  final Color selectedLabel;

  /// The selected tab's underline.
  final Color underline;

  /// The underline thickness.
  final double underlineWidth;

  /// Horizontal breathing room around a label.
  final EdgeInsetsGeometry slotPadding;

  /// The target height, including text scaling and the 48 dp minimum.
  final double outerHeight;

  /// Resolves the strip's paint and height at [textScaler].
  static UiTabStyle resolve(
    UiThemeData ui, {
    TextScaler textScaler = TextScaler.noScaling,
  }) => UiTabStyle(
    labelStyle: ui.type.label,
    label: ui.color.inkSecondary,
    selectedLabel: ui.color.ink,
    underline: ui.color.ink,
    underlineWidth: ui.shape.stroke.emphasis,
    slotPadding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s3),
    outerHeight: UiType.heightAroundAt(
      UiDensity.hitBox,
      ui.type.label,
      textScaler,
    ),
  );

  /// The equal width each tab needs to show its full label.
  double slotWidth(BuildContext context, Iterable<UiTab> tabs) {
    final double widest = tabs.fold<double>(
      0,
      (double width, UiTab tab) =>
          math.max(width, measureLabel(context, tab.label, labelStyle).width),
    );
    return math.max(
      UiDensity.hitBox,
      widest + slotPadding.resolve(Directionality.of(context)).horizontal,
    );
  }

  /// The width the complete strip needs before horizontal overflow.
  double intrinsicWidth(BuildContext context, Iterable<UiTab> tabs) =>
      tabs.length * slotWidth(context, tabs);
}

/// Text tabs over panes, marked by a stationary underline per slot.
///
/// Arrows move focus and Enter or Space chooses. Focusing another tab never
/// swaps the pane. Overflow keeps all labels and reveals both the selected
/// tab and the focused tab without moving the surrounding workspace.
class UiTabs extends StatefulWidget {
  /// A strip of [tabs] bound to the caller-owned [selected] index.
  const UiTabs({
    super.key,
    required this.tabs,
    required this.selected,
    required this.semanticsLabel,
    this.strip,
    this.onSelected,
  });

  /// The tabs, in reading order.
  final List<UiTab> tabs;

  /// The current index. The strip writes to it and rebuilds from it.
  final ValueNotifier<int> selected;

  /// What the strip is called, for a screen reader.
  final String semanticsLabel;

  /// A caller-provided strip for a specialized tab presentation.
  final Widget? strip;

  /// Reports every user activation, including the already selected tab.
  /// Programmatic notifier changes do not invoke this navigation callback.
  final ValueChanged<int>? onSelected;

  @override
  State<UiTabs> createState() => _UiTabsState();
}

class _UiTabsState extends State<UiTabs> {
  List<FocusNode> _nodes = <FocusNode>[];
  int _revealed = 0;
  int _tabStop = 0;

  int get _chosen => widget.tabs.isEmpty
      ? 0
      : widget.selected.value.clamp(0, widget.tabs.length - 1);

  @override
  void initState() {
    super.initState();
    _tabStop = _chosen;
    _syncNodes();
    widget.selected.addListener(_selectionChanged);
    _revealed = _chosen;
    _revealAfterLayout();
  }

  @override
  void didUpdateWidget(UiTabs oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selected != widget.selected) {
      oldWidget.selected.removeListener(_selectionChanged);
      widget.selected.addListener(_selectionChanged);
      _revealed = _chosen;
    }
    if (oldWidget.tabs.length != widget.tabs.length) _syncNodes();
    for (int i = 0; i < _nodes.length; i++) {
      _nodes[i].debugLabel = widget.tabs[i].label;
    }
    _revealAfterLayout();
  }

  @override
  void dispose() {
    widget.selected.removeListener(_selectionChanged);
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _syncNodes() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    _nodes = List<FocusNode>.generate(widget.tabs.length, (int index) {
      final FocusNode node = FocusNode(debugLabel: widget.tabs[index].label);
      node.addListener(() {
        if (node.hasFocus && mounted) {
          setState(() {
            _revealed = index;
            _tabStop = index;
          });
          _revealAfterLayout();
        }
      });
      return node;
    });
  }

  void _selectionChanged() {
    setState(() => _revealed = _chosen);
    _revealAfterLayout();
  }

  void _revealAfterLayout() {
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted || _nodes.isEmpty) return;
      final BuildContext? target =
          _nodes[_revealed.clamp(0, _nodes.length - 1)].context;
      if (target == null) return;
      // Only the horizontal tab viewport moves. A selection must not scroll
      // the page that happens to contain this strip.
      final ScrollableState? scroller = Scrollable.maybeOf(
        target,
        axis: Axis.horizontal,
      );
      final RenderObject? box = target.findRenderObject();
      if (scroller != null && box != null) {
        scroller.position.ensureVisible(
          box,
          alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
        );
      }
    });
  }

  void _move(int step) {
    if (_nodes.isEmpty) return;
    final int focused = _nodes.indexWhere((FocusNode node) => node.hasFocus);
    _nodes[((focused < 0 ? _chosen : focused) + step).clamp(
          0,
          _nodes.length - 1,
        )]
        .requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.strip case final Widget strip) return strip;
    if (widget.tabs.isEmpty) return const SizedBox.shrink();
    for (int i = 0; i < _nodes.length; i++) {
      _nodes[i].skipTraversal = i != _tabStop;
    }
    final UiThemeData ui = context.ui;
    final UiTabStyle style = UiTabStyle.resolve(
      ui,
      textScaler: MediaQuery.textScalerOf(context),
    );
    final double width = style.intrinsicWidth(context, widget.tabs);
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth: width,
          builder: (BuildContext context, bool _) => _track(style, width),
        ),
        FitVariant(
          intrinsicWidth: 0,
          builder: (BuildContext context, bool _) => EdgeFadedRow(
            index: _revealed,
            length: widget.tabs.length,
            fadeExtent: ui.space.s6,
            child: _track(style, width),
          ),
        ),
      ],
    );
  }

  Widget _track(UiTabStyle style, double width) {
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    return Semantics(
      container: true,
      explicitChildNodes: true,
      role: SemanticsRole.tabBar,
      label: widget.semanticsLabel,
      child: FocusTraversalGroup(
        policy: WidgetOrderTraversalPolicy(),
        child: Shortcuts(
          includeSemantics: false,
          shortcuts: const <ShortcutActivator, Intent>{
            SingleActivator(LogicalKeyboardKey.arrowRight): _MoveTabIntent(1),
            SingleActivator(LogicalKeyboardKey.arrowLeft): _MoveTabIntent(-1),
          },
          child: Actions(
            actions: <Type, Action<Intent>>{
              _MoveTabIntent: CallbackAction<_MoveTabIntent>(
                onInvoke: (_MoveTabIntent intent) {
                  _move(rtl ? -intent.step : intent.step);
                  return null;
                },
              ),
            },
            child: SizedBox(
              width: width,
              height: style.outerHeight,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  for (int i = 0; i < widget.tabs.length; i++)
                    Expanded(
                      child: Pressable(
                        semanticsLabel:
                            widget.tabs[i].semanticsLabel ??
                            widget.tabs[i].label,
                        role: PressableRole.tab,
                        selected: i == _chosen,
                        focusNode: _nodes[i],
                        shape: const RoundedRectangleBorder(),
                        radius: context.ui.shape.none,
                        insetFocusRing: true,
                        onPressed: () {
                          widget.selected.value = i;
                          widget.onSelected?.call(i);
                        },
                        builder:
                            (BuildContext context, Set<WidgetState> states) =>
                                DecoratedBox(
                                  decoration: BoxDecoration(
                                    border: Border(
                                      bottom: BorderSide(
                                        color: i == _chosen
                                            ? style.underline
                                            : style.underline.withValues(
                                                alpha: 0,
                                              ),
                                        width: style.underlineWidth,
                                      ),
                                    ),
                                  ),
                                  child: Padding(
                                    padding: style.slotPadding,
                                    child: Center(
                                      child: UiLabel(
                                        widget.tabs[i].label,
                                        style: style.labelStyle.copyWith(
                                          color: i == _chosen
                                              ? style.selectedLabel
                                              : style.label,
                                        ),
                                        textAlign: TextAlign.center,
                                      ),
                                    ),
                                  ),
                                ),
                      ),
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

class _MoveTabIntent extends Intent {
  const _MoveTabIntent(this.step);
  final int step;
}

/// The pane under a [UiTabs].
///
/// Retires `TabBarView`. Panes cross fade; they do not slide. A shared axis is
/// declined per 04 section 3.3 until routes need one, and a large horizontal
/// slide beside a photograph produces induced motion: the photograph appears
/// to drift the other way (04 section 5.4).
class UiTabView extends StatelessWidget {
  /// Shows the pane [selected] names.
  const UiTabView({super.key, required this.selected, required this.children});

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
            duration: ui.motion.quick,
            switchInCurve: MotionTokens.standardCurve,
            switchOutCurve: MotionTokens.standardCurve,
            layoutBuilder: (Widget? current, List<Widget> previous) => Stack(
              alignment: AlignmentDirectional.topStart,
              children: <Widget>[...previous, ?current],
            ),
            child: children.isEmpty
                ? const SizedBox.shrink()
                : KeyedSubtree(key: ValueKey<int>(safe), child: children[safe]),
          ),
        );
      },
    );
  }
}
