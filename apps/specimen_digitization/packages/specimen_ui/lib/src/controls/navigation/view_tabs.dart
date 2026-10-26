/// Compact view navigation: the active view is named beside its icon.
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';

/// A named view with an icon that remains recognizable when inactive.
@immutable
class UiViewTab<T> {
  /// Describes a view without owning its selection or content.
  const UiViewTab({
    required this.value,
    required this.label,
    required this.icon,
  });

  /// Stable identity of the view.
  final T value;

  /// Visible when selected, and always the accessible name and tooltip.
  final String label;

  /// The view's Phosphor glyph.
  final IconSpec icon;
}

/// Tabs that reserve names for the current view and keep other views as icons.
///
/// The active name wraps at large text sizes. Every target remains at least
/// 48 dp, with horizontal scrolling only when even those targets cannot fit.
/// Arrow keys, Home and End select a view; left and right follow reading order.
class UiViewTabs<T> extends StatefulWidget {
  /// Builds the named views with [value] active.
  const UiViewTabs({
    super.key,
    required this.views,
    required this.value,
    required this.onChanged,
    required this.semanticsLabel,
  });

  /// Views in reading order. Values must be unique.
  final List<UiViewTab<T>> views;

  /// The active view, owned by the caller.
  final T value;

  /// Requests a view change without changing application data.
  final ValueChanged<T> onChanged;

  /// Accessible name of this set of views.
  final String semanticsLabel;

  @override
  State<UiViewTabs<T>> createState() => _UiViewTabsState<T>();
}

class _UiViewTabsState<T> extends State<UiViewTabs<T>> {
  final Map<T, FocusNode> _focusByValue = {};
  List<FocusNode> get _nodes => [
    for (final view in widget.views) _focusByValue[view.value]!,
  ];

  @override
  void initState() {
    super.initState();
    _resize();
    _reveal(widget.value);
  }

  @override
  void didUpdateWidget(UiViewTabs<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    _resize();
    if (oldWidget.value != widget.value) _reveal(widget.value);
  }

  void _resize() {
    final values = widget.views.map((view) => view.value).toSet();
    assert(values.length == widget.views.length, 'View values must be unique.');
    for (final value in _focusByValue.keys.toList()) {
      if (!values.contains(value)) _focusByValue.remove(value)!.dispose();
    }
    for (final view in widget.views) {
      _focusByValue.putIfAbsent(view.value, () => FocusNode()).debugLabel =
          view.label;
    }
  }

  @override
  void dispose() {
    for (final node in _focusByValue.values) {
      node.dispose();
    }
    super.dispose();
  }

  void _select(int index) {
    _nodes[index].requestFocus();
    widget.onChanged(widget.views[index].value);
    _reveal(widget.views[index].value);
  }

  void _reveal(T value) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final target = _focusByValue[value]?.context;
      if (target == null) return;
      final scroller = Scrollable.maybeOf(target, axis: Axis.horizontal);
      final box = target.findRenderObject();
      if (scroller != null && box != null) {
        // Reveal only this tab strip, never scroll the surrounding page.
        scroller.position.ensureVisible(
          box,
          alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
        );
      }
    });
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent || _nodes.isEmpty) {
      return KeyEventResult.ignored;
    }
    final focused = _nodes.indexWhere((node) => node.hasFocus);
    final selected = widget.views.indexWhere(
      (view) => view.value == widget.value,
    );
    final index = focused < 0 ? math.max(0, selected) : focused;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final next = switch (event.logicalKey) {
      LogicalKeyboardKey.home => 0,
      LogicalKeyboardKey.end => _nodes.length - 1,
      LogicalKeyboardKey.arrowRight => (index + (rtl ? -1 : 1)) % _nodes.length,
      LogicalKeyboardKey.arrowLeft => (index + (rtl ? 1 : -1)) % _nodes.length,
      _ => null,
    };
    if (next == null) return KeyEventResult.ignored;
    _select(next);
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    if (widget.views.isEmpty) return const SizedBox.shrink();
    final ui = context.ui;
    final selected = widget.views.indexWhere(
      (view) => view.value == widget.value,
    );
    assert(selected >= 0, 'The current view must appear in views.');
    final chosen = math.max(selected, 0);
    for (var i = 0; i < _nodes.length; i++) {
      _nodes[i].skipTraversal = i != chosen;
    }
    final scale = MediaQuery.textScalerOf(context);
    final iconWidth =
        ui.space.iconInline *
        scale.scale(ui.type.label.fontSize!) /
        ui.type.label.fontSize!;
    final activeWidth = math.max(
      UiDensity.hitBox,
      measureLabel(context, widget.views[chosen].label, ui.type.label).width +
          iconWidth +
          ui.space.s2 +
          ui.space.s4,
    );
    final gap = ui.space.s2;
    final targetWidth = math.max(UiDensity.hitBox, iconWidth + ui.space.s4);
    // Keep at least one complete word beside the glyph. Below that measure,
    // scrolling is clearer than a tall column of individual characters.
    final wordWidth = widget.views[chosen].label
        .split(RegExp(r'\s+'))
        .fold<double>(
          0,
          (width, word) =>
              math.max(width, measureLabel(context, word, ui.type.label).width),
        );
    final minimum =
        math.max(
          targetWidth,
          wordWidth + iconWidth + ui.space.s2 + ui.space.s4,
        ) +
        targetWidth * (widget.views.length - 1) +
        gap * (widget.views.length - 1);
    final natural =
        activeWidth +
        targetWidth * (widget.views.length - 1) +
        gap * (widget.views.length - 1);

    return LayoutBuilder(
      builder: (context, constraints) {
        final available = constraints.hasBoundedWidth
            ? constraints.maxWidth
            : natural;
        final width = available < minimum
            ? natural
            : math.min(natural, available);
        final row = SizedBox(
          width: width,
          child: Row(
            children: [
              for (var i = 0; i < widget.views.length; i++) ...[
                if (i > 0) SizedBox(width: gap),
                if (i == chosen)
                  Expanded(child: _tab(i, true))
                else
                  SizedBox(width: targetWidth, child: _tab(i, false)),
              ],
            ],
          ),
        );
        final tabList = Semantics(
          container: true,
          explicitChildNodes: true,
          role: SemanticsRole.tabBar,
          label: widget.semanticsLabel,
          child: row,
        );
        return Focus(
          canRequestFocus: false,
          includeSemantics: false,
          onKeyEvent: _key,
          child: available < minimum
              ? SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: tabList,
                )
              : tabList,
        );
      },
    );
  }

  Widget _tab(int index, bool selected) {
    final ui = context.ui;
    final view = widget.views[index];
    final ink = selected ? ui.color.ink : ui.color.inkSecondary;
    final tab = Pressable(
      semanticsLabel: view.label,
      role: PressableRole.tab,
      selected: selected,
      focusNode: _nodes[index],
      radius: ui.shape.inner,
      onPressed: () => _select(index),
      builder: (context, states) => DecoratedBox(
        decoration: BoxDecoration(
          color: selected ? ui.color.stateLayer(.06) : null,
          borderRadius: BorderRadius.circular(ui.shape.inner),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: UiDensity.hitBox),
          child: Padding(
            padding: EdgeInsets.all(ui.space.s2),
            child: Row(
              mainAxisAlignment: selected
                  ? MainAxisAlignment.start
                  : MainAxisAlignment.center,
              children: [
                UiIcon(
                  // A view is navigation, even when its glyph also denotes
                  // a filled status elsewhere. Only the active view is filled.
                  IconSpec(view.icon.glyph, filled: view.icon.filled),
                  current: selected,
                  size: UiIconSize.inline,
                  textStyle: ui.type.label,
                  color: ink,
                ),
                if (selected) ...[
                  SizedBox(width: ui.space.s2),
                  Expanded(
                    child: Text(
                      view.label,
                      style: ui.type.label.copyWith(color: ink),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
    return selected
        ? tab
        : MergeSemantics(
            child: UiTooltip(
              message: view.label,
              excludeSemantics: true,
              child: tab,
            ),
          );
  }
}
