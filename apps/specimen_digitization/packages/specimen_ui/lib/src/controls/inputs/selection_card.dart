/// Rich checkbox and radio choices with a complete, accessible hit target.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import 'field.dart';

/// Whether cards select one value or several independent values.
enum UiSelectionMode {
  /// One radio-style selection.
  single,

  /// Several independent checkbox selections.
  multiple,
}

/// A rich option: leading may contain an avatar, icon, payment mark or image.
@immutable
class UiSelectionCardOption<T> {
  /// Creates the component with explicit caller-owned configuration.
  const UiSelectionCardOption({
    required this.value,
    required this.label,
    this.supporting,
    this.leading,
    this.trailing,
    this.enabled = true,
    this.disabledReason,
  });

  /// The current value accepted by the host.
  final T value;

  /// The visible and accessible name of the control.
  final String label;

  /// The optional explanatory text accompanying the primary label.
  final String? supporting;

  /// The optional content before the main label.
  final Widget? leading;

  /// The optional content after the main label.
  final Widget? trailing;

  /// Whether interaction is available.
  final bool enabled;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;
}

/// A controlled group of selection cards.
///
/// The whole card activates one checkbox/radio node. Supporting text is part
/// of that node's name; leading/trailing slots are decorative and must not
/// contain actions. Single mode uses arrow keys to focus and select an enabled
/// option. Multiple mode uses arrows to focus and Space to toggle.
class UiSelectionCards<T> extends StatefulWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiSelectionCards({
    super.key,
    required this.label,
    required this.options,
    required this.selected,
    this.onChanged,
    this.mode = UiSelectionMode.multiple,
    this.helpText,
    this.errorText,
    this.disabledReason,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The ordered available choices, each with a unique value.
  final List<UiSelectionCardOption<T>> options;

  /// The current selection accepted by the host.
  final Set<T> selected;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<Set<T>>? onChanged;

  /// The single- or multiple-selection interaction model.
  final UiSelectionMode mode;

  /// The persistent supporting instruction beneath the control.
  final String? helpText;

  /// The validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  @override
  State<UiSelectionCards<T>> createState() => _UiSelectionCardsState<T>();
}

class _UiSelectionCardsState<T> extends State<UiSelectionCards<T>> {
  final Map<T, FocusNode> _nodes = <T, FocusNode>{};

  @override
  void dispose() {
    for (final node in _nodes.values) {
      node.dispose();
    }
    super.dispose();
  }

  @override
  void didUpdateWidget(UiSelectionCards<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    final values = widget.options.map((o) => o.value).toSet();
    for (final value
        in _nodes.keys.where((v) => !values.contains(v)).toList()) {
      _nodes.remove(value)!.dispose();
    }
  }

  void _select(T value) {
    if (widget.onChanged == null) return;
    final Set<T> next = widget.mode == UiSelectionMode.single
        ? <T>{value}
        : Set<T>.of(widget.selected);
    if (widget.mode == UiSelectionMode.multiple && !next.add(value)) {
      next.remove(value);
    }
    widget.onChanged!(Set<T>.unmodifiable(next));
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (widget.onChanged == null || event is! KeyDownEvent) {
      return KeyEventResult.ignored;
    }
    final enabled = widget.options.where((o) => o.enabled).toList();
    final index = enabled.indexWhere((o) => _nodes[o.value]?.hasFocus ?? false);
    if (index < 0 || enabled.isEmpty) return KeyEventResult.ignored;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final int? delta = switch (event.logicalKey) {
      LogicalKeyboardKey.arrowDown => 1,
      LogicalKeyboardKey.arrowUp => -1,
      LogicalKeyboardKey.arrowRight => rtl ? -1 : 1,
      LogicalKeyboardKey.arrowLeft => rtl ? 1 : -1,
      _ => null,
    };
    if (delta == null) return KeyEventResult.ignored;
    final next = enabled[(index + delta) % enabled.length];
    _nodes[next.value]?.requestFocus();
    if (widget.mode == UiSelectionMode.single) _select(next.value);
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    assert(
      widget.mode != UiSelectionMode.single || widget.selected.length <= 1,
    );
    assert(
      widget.options.map((o) => o.value).toSet().length ==
          widget.options.length,
    );
    final ui = context.ui;
    final states = <WidgetState>{
      if (widget.onChanged == null) WidgetState.disabled,
      if (widget.errorText != null) WidgetState.error,
    };
    return UiFieldFrame(
      label: widget.label,
      style: UiInputStyle.resolve(ui, UiFieldShape.box),
      states: states,
      message: widget.errorText ?? widget.disabledReason ?? widget.helpText,
      isError: widget.errorText != null,
      child: Semantics(
        container: true,
        explicitChildNodes: true,
        label: widget.label,
        child: Focus(
          canRequestFocus: false,
          onKeyEvent: _key,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              for (int i = 0; i < widget.options.length; i++) ...<Widget>[
                if (i > 0) SizedBox(height: ui.space.s3),
                _card(widget.options[i]),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _card(UiSelectionCardOption<T> option) {
    final ui = context.ui;
    final selected = widget.selected.contains(option.value);
    final enabled = option.enabled && widget.onChanged != null;
    return Pressable(
      semanticsLabel: [
        option.label,
        if (option.supporting != null) option.supporting!,
      ].join('. '),
      role: widget.mode == UiSelectionMode.single
          ? PressableRole.radio
          : PressableRole.checkbox,
      checked: selected,
      selected: selected,
      focusNode: _nodes.putIfAbsent(
        option.value,
        () => FocusNode(debugLabel: option.label),
      ),
      onPressed: enabled ? () => _select(option.value) : null,
      disabledReason: option.disabledReason ?? widget.disabledReason,
      radius: ui.shape.inner,
      builder: (context, states) => DecoratedBox(
        decoration: BoxDecoration(
          color: enabled
              ? (selected ? ui.brand.secondary.fill : ui.color.paper)
              : ui.color.disabledFill,
          borderRadius: BorderRadius.circular(ui.shape.inner),
          border: Border.all(
            color: !enabled
                ? ui.color.disabledOutline
                : widget.errorText != null
                ? ui.color.status.blocked.content
                : selected
                ? ui.brand.secondary.content
                : ui.color.boundary,
            width: selected
                ? ui.shape.stroke.emphasis
                : ui.shape.stroke.boundary,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.all(ui.space.s4),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              if (option.leading != null)
                option.leading!
              else
                UiIcon(
                  selected ? UiIcons.check : UiIcons.unselected,
                  size: UiIconSize.action,
                  color: enabled
                      ? ui.brand.secondary.content
                      : ui.color.disabledContent,
                ),
              SizedBox(width: ui.space.s3),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      option.label,
                      style: ui.type.label.copyWith(
                        color: enabled
                            ? ui.color.ink
                            : ui.color.disabledContent,
                      ),
                    ),
                    if (option.supporting != null) ...[
                      SizedBox(height: ui.space.s1),
                      Text(
                        option.supporting!,
                        style: ui.type.bodySmall.copyWith(
                          color: enabled
                              ? ui.color.inkSecondary
                              : ui.color.disabledContent,
                        ),
                      ),
                    ],
                    if (option.trailing != null) ...[
                      SizedBox(height: ui.space.s2),
                      option.trailing!,
                    ],
                  ],
                ),
              ),
              if (option.leading != null) ...[
                SizedBox(width: ui.space.s3),
                UiIcon(
                  selected ? UiIcons.check : UiIcons.unselected,
                  size: UiIconSize.action,
                  color: enabled
                      ? ui.brand.secondary.content
                      : ui.color.disabledContent,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
