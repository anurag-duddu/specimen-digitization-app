/// Wrapping, mutually exclusive value choices with an explicit reset.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../../primitives/squircle.dart';
import '../overlays/tooltip.dart';
import 'button.dart';

/// One value in a [UiChoiceGroup].
@immutable
class UiChoice<T> {
  /// Binds a value to its visible label.
  const UiChoice({
    required this.value,
    required this.label,
    this.semanticsLabel,
  });

  /// The value reported on selection.
  final T value;

  /// The visible label.
  final String label;

  /// A standalone spoken label, when the visible label needs context.
  final String? semanticsLabel;
}

/// A value filter, distinct from destination tabs.
///
/// Choices wrap without hiding values in a scrolling strip. A check and a
/// boundary persist on the selected value, including during hover. Arrows move
/// the single focus stop; Enter or Space selects. Pressing the current choice
/// keeps it selected; the separate reset command reports null.
class UiChoiceGroup<T> extends StatefulWidget {
  /// Presents [choices] under the accessible [label].
  const UiChoiceGroup({
    super.key,
    required this.label,
    required this.choices,
    required this.value,
    required this.onChanged,
    this.onSelected,
    this.resetLabel = 'Reset view',
    this.disabledReason,
  });

  /// What the values control, for assistive technology.
  final String label;

  /// Choices in reading order.
  final List<UiChoice<T>> choices;

  /// The selected value; null means no filter.
  final T? value;

  /// Reports a changed value or an explicit reset. Null disables the group.
  final ValueChanged<T?>? onChanged;

  /// Reports every user activation, including the current value and reset.
  final ValueChanged<T?>? onSelected;

  /// The visible reset command. It appears while a value is selected.
  final String resetLabel;

  /// Why the values cannot be changed.
  final String? disabledReason;

  @override
  State<UiChoiceGroup<T>> createState() => _UiChoiceGroupState<T>();
}

class _UiChoiceGroupState<T> extends State<UiChoiceGroup<T>> {
  final List<FocusNode> _nodes = <FocusNode>[];
  int _tabStop = 0;

  @override
  void initState() {
    super.initState();
    _tabStop = _selectedIndex;
    _syncNodes();
  }

  int get _selectedIndex {
    final index = widget.choices.indexWhere(
      (choice) => choice.value == widget.value,
    );
    return index < 0 ? 0 : index;
  }

  void _syncNodes() {
    for (final node in _nodes) {
      node.dispose();
    }
    _nodes.clear();
    for (int i = 0; i < widget.choices.length; i++) {
      final node = FocusNode(debugLabel: widget.choices[i].label);
      node.addListener(() {
        if (node.hasFocus && mounted && _tabStop != i) {
          setState(() => _tabStop = i);
        }
      });
      _nodes.add(node);
    }
    _tabStop = _tabStop.clamp(0, _nodes.isEmpty ? 0 : _nodes.length - 1);
  }

  @override
  void didUpdateWidget(UiChoiceGroup<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.choices.length != widget.choices.length) _syncNodes();
    if (!_nodes.any((node) => node.hasFocus)) _tabStop = _selectedIndex;
    for (int i = 0; i < _nodes.length; i++) {
      _nodes[i].debugLabel = widget.choices[i].label;
    }
  }

  @override
  void dispose() {
    for (final node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _select(T? value) {
    if (widget.onChanged == null) return;
    if (value != widget.value) widget.onChanged!(value);
    widget.onSelected?.call(value);
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final focused = _nodes.indexWhere((node) => node.hasFocus);
    if (focused < 0) return KeyEventResult.ignored;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final key = event.logicalKey;
    final int next;
    if (key == LogicalKeyboardKey.home) {
      next = 0;
    } else if (key == LogicalKeyboardKey.end) {
      next = _nodes.length - 1;
    } else if (key == LogicalKeyboardKey.arrowRight ||
        key == LogicalKeyboardKey.arrowLeft) {
      final step =
          (key == LogicalKeyboardKey.arrowRight ? 1 : -1) * (rtl ? -1 : 1);
      next = (focused + step).clamp(0, _nodes.length - 1);
    } else if (key == LogicalKeyboardKey.arrowDown ||
        key == LogicalKeyboardKey.arrowUp) {
      next = (focused + (key == LogicalKeyboardKey.arrowDown ? 1 : -1)).clamp(
        0,
        _nodes.length - 1,
      );
    } else {
      return KeyEventResult.ignored;
    }
    _nodes[next].requestFocus();
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    for (int i = 0; i < _nodes.length; i++) {
      _nodes[i].skipTraversal = i != _tabStop;
    }
    return Semantics(
      container: true,
      explicitChildNodes: true,
      label: widget.label,
      child: Focus(
        canRequestFocus: false,
        includeSemantics: false,
        onKeyEvent: _key,
        child: Wrap(
          spacing: ui.space.s2,
          runSpacing: ui.space.s2,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            for (int i = 0; i < widget.choices.length; i++) _choice(i),
            if (widget.value != null)
              UiButton(
                label: widget.resetLabel,
                variant: UiButtonVariant.ghost,
                size: UiSize.sm,
                onPressed: widget.onChanged == null
                    ? null
                    : () => _select(null),
                disabledReason: widget.disabledReason,
              ),
          ],
        ),
      ),
    );
  }

  Widget _choice(int index) {
    final ui = context.ui;
    final choice = widget.choices[index];
    final selected = choice.value == widget.value;
    Widget target(ValueChanged<String>? report) => Pressable(
      semanticsLabel: choice.semanticsLabel ?? choice.label,
      role: PressableRole.radio,
      selected: selected,
      focusNode: _nodes[index],
      disabledReason: widget.disabledReason,
      onDisabledReason: report,
      onPressed: widget.onChanged == null ? null : () => _select(choice.value),
      builder: (context, states) {
        final disabled = states.contains(WidgetState.disabled);
        final ink = disabled ? ui.color.disabledContent : ui.color.ink;
        return DecoratedBox(
          decoration: ShapeDecoration(
            shape: Squircle.border(
              ui.shape.inner,
              side: BorderSide(
                color: selected ? ink : ui.color.paper.withValues(alpha: 0),
                width: ui.shape.stroke.boundary,
              ),
            ),
            color: selected
                ? ui.color.paper
                : ui.color.paper.withValues(alpha: 0),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: UiDensity.hitBox),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: ui.space.s2,
                vertical: ui.space.s2,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: ui.space.iconInline,
                    height: ui.space.iconInline,
                    child: selected
                        ? UiIcon(
                            UiIcons.check,
                            size: UiIconSize.inline,
                            color: ink,
                          )
                        : null,
                  ),
                  SizedBox(width: ui.space.s1),
                  Flexible(
                    child: UiLabel(
                      choice.label,
                      style: ui.type.label.copyWith(color: ink),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
    return widget.onChanged == null && widget.disabledReason != null
        ? UiTooltip.reason(
            reason: widget.disabledReason,
            builder: (context, report) => target(report),
          )
        : UiTooltip(message: choice.label, child: target(null));
  }
}
