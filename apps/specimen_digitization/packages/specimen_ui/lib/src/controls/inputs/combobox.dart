/// Searchable single and multiple selection with rich option anatomy.
library;

import 'dart:math' as math;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/popover.dart';
import '../../primitives/pressable.dart';
import '../actions/shared_actions.dart';
import '../data/progress.dart';
import 'field.dart';

/// One searchable choice with optional identity and supporting detail.
@immutable
class UiComboboxOption<T> {
  /// Creates the component with explicit caller-owned configuration.
  const UiComboboxOption({
    required this.value,
    required this.label,
    this.supporting,
    this.leading,
    this.group,
    this.keywords = const <String>[],
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

  /// The optional heading grouping adjacent options.
  final String? group;

  /// The additional search terms that match this option.
  final List<String> keywords;

  /// Whether interaction is available.
  final bool enabled;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;
}

/// A searchable controlled option list, with independent selected-value tags.
///
/// The caller owns options, loading and accepted selections. Filtering never
/// loses selected values. Arrow keys move real focus, Enter/Space selects,
/// Escape/outside click dismisses and restores trigger focus. Disabled options
/// remain discoverable but cannot be selected by pointer, keyboard or semantics.
class UiCombobox<T> extends StatefulWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiCombobox({
    super.key,
    required this.label,
    required this.options,
    required this.selected,
    this.onChanged,
    this.multiple = false,
    this.placeholder = 'Choose an option',
    this.searchLabel = 'Search options',
    this.emptyLabel = 'No matching options',
    this.loading = false,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.header,
    this.triggerLeading,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The ordered available choices, each with a unique value.
  final List<UiComboboxOption<T>> options;

  /// The current selection accepted by the host.
  final Set<T> selected;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<Set<T>>? onChanged;

  /// Whether several options may be selected simultaneously.
  final bool multiple;

  /// The prompt displayed when there is no selection.
  final String placeholder;

  /// The accessible name of the search input.
  final String searchLabel;

  /// The message announced when no options match.
  final String emptyLabel;

  /// Whether options are loading and selection is temporarily unavailable.
  final bool loading;

  /// The persistent supporting instruction beneath the control.
  final String? helpText;

  /// The validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  /// The optional noninteractive content above the options.
  final Widget? header;

  /// Optional identity in the trigger; otherwise the selected single option supplies it.
  final Widget? triggerLeading;
  @override
  State<UiCombobox<T>> createState() => _UiComboboxState<T>();
}

class _UiComboboxState<T> extends State<UiCombobox<T>> {
  final _popover = PopoverController();
  final _query = TextEditingController();
  final _searchFocus = FocusNode(debugLabel: 'Combobox search');
  final _triggerFocus = FocusNode(debugLabel: 'Combobox trigger');
  final Map<T, FocusNode> _nodes = <T, FocusNode>{};
  double _width = 320;
  bool get _enabled => widget.onChanged != null && !widget.loading;
  List<UiComboboxOption<T>> get _visible {
    final query = _query.text.trim().toLowerCase();
    return widget.options
        .where(
          (option) => [
            option.label,
            option.supporting ?? '',
            ...option.keywords,
          ].join(' ').toLowerCase().contains(query),
        )
        .toList();
  }

  @override
  void initState() {
    super.initState();
    _popover.addListener(_changed);
  }

  void _changed() {
    if (!mounted) return;
    setState(() {});
    if (!_popover.isOpen) {
      // Pointer opening need not focus the trigger, so Popover may have saved
      // an unrelated field. Return to this control after its menu scope leaves.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted &&
            !_popover.isOpen &&
            _enabled &&
            _triggerFocus.context != null &&
            _triggerFocus.canRequestFocus) {
          _triggerFocus.requestFocus();
        }
      });
    }
  }

  @override
  void didUpdateWidget(UiCombobox<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    final values = widget.options.map((o) => o.value).toSet();
    for (final value
        in _nodes.keys.where((v) => !values.contains(v)).toList()) {
      _nodes.remove(value)!.dispose();
    }
    if (!_enabled && _popover.isOpen) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !_enabled) _popover.close();
      });
    }
  }

  @override
  void dispose() {
    _popover
      ..removeListener(_changed)
      ..dispose();
    _query.dispose();
    _searchFocus.dispose();
    _triggerFocus.dispose();
    for (final node in _nodes.values) {
      node.dispose();
    }
    super.dispose();
  }

  void _toggle() {
    if (!_enabled) return;
    if (_popover.isOpen) {
      _popover.close();
      return;
    }
    _width = context.size?.width ?? 320;
    _query.clear();
    _popover.open();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _popover.isOpen) _searchFocus.requestFocus();
    });
  }

  void _pick(UiComboboxOption<T> option) {
    if (!_enabled || !option.enabled) return;
    final next = widget.multiple ? Set<T>.of(widget.selected) : <T>{};
    if (!next.add(option.value)) next.remove(option.value);
    widget.onChanged!(Set<T>.unmodifiable(next));
    if (!widget.multiple) _popover.close();
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final options = _visible.where((o) => o.enabled).toList();
    if (options.isEmpty) return KeyEventResult.ignored;
    final current = options.indexWhere(
      (o) => _nodes[o.value]?.hasFocus ?? false,
    );
    if (event.logicalKey == LogicalKeyboardKey.enter && _searchFocus.hasFocus) {
      _pick(options.first);
      return KeyEventResult.handled;
    }
    final delta = event.logicalKey == LogicalKeyboardKey.arrowDown
        ? 1
        : event.logicalKey == LogicalKeyboardKey.arrowUp
        ? -1
        : null;
    if (delta == null) return KeyEventResult.ignored;
    final next = current < 0
        ? (delta == 1 ? 0 : options.length - 1)
        : (current + delta) % options.length;
    final focus = _nodes[options[next].value];
    focus?.requestFocus();
    if (focus?.context case final context?) Scrollable.ensureVisible(context);
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    assert(widget.multiple || widget.selected.length <= 1);
    assert(
      widget.options.map((o) => o.value).toSet().length ==
          widget.options.length,
    );
    final ui = context.ui;
    final chosen = widget.options
        .where((o) => widget.selected.contains(o.value))
        .toList();
    final value = chosen.isEmpty
        ? widget.placeholder
        : widget.multiple
        ? '${chosen.length} selected'
        : chosen.first.label;
    final states = <WidgetState>{
      if (!_enabled) WidgetState.disabled,
      if (widget.errorText != null) WidgetState.error,
      if (_popover.isOpen) WidgetState.focused,
    };
    final style = UiInputStyle.resolve(
      ui,
      UiFieldShape.box,
      textScaler: MediaQuery.textScalerOf(context),
    );
    return UiFieldFrame(
      label: widget.label,
      style: style,
      states: states,
      message: widget.errorText ?? widget.disabledReason ?? widget.helpText,
      isError: widget.errorText != null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (widget.multiple && chosen.isNotEmpty) ...<Widget>[
            Wrap(
              spacing: ui.space.s2,
              runSpacing: ui.space.s2,
              children: <Widget>[
                for (final option in chosen)
                  UiTag(
                    label: option.label,
                    leading: option.leading,
                    onRemove: !_enabled
                        ? null
                        : () => widget.onChanged!(
                            Set<T>.unmodifiable(
                              Set<T>.of(widget.selected)..remove(option.value),
                            ),
                          ),
                  ),
              ],
            ),
            SizedBox(height: ui.space.s2),
          ],
          Popover(
            controller: _popover,
            surface: PopoverSurface.paper,
            overlayBuilder: (context) => _menu(),
            child: Semantics(
              container: true,
              button: true,
              expanded: _popover.isOpen,
              enabled: _enabled,
              label: widget.label,
              value: value,
              hint:
                  widget.errorText ?? widget.disabledReason ?? widget.helpText,
              onTap: _enabled ? _toggle : null,
              child: Pressable(
                semanticsLabel: widget.label,
                focusNode: _triggerFocus,
                excludeFromSemantics: true,
                onPressed: _enabled ? _toggle : null,
                focusRing: false,
                builder: (context, pressed) => ExcludeSemantics(
                  child: UiFieldBox(
                    style: style,
                    states: <WidgetState>{...states, ...pressed},
                    child: Row(
                      children: <Widget>[
                        if (widget.triggerLeading ??
                                (!widget.multiple && chosen.isNotEmpty
                                    ? chosen.first.leading
                                    : null)
                            case final leading?) ...[
                          leading,
                          SizedBox(width: ui.space.s2),
                        ],
                        Expanded(child: Text(value, style: ui.type.body)),
                        if (widget.loading)
                          UiProgress.ring(
                            semanticsLabel: 'Loading ${widget.label}',
                            size: UiProgressSize.small,
                          )
                        else
                          UiIcon(
                            _popover.isOpen ? UiIcons.collapse : UiIcons.expand,
                            size: UiIconSize.inline,
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _menu() {
    final ui = context.ui;
    final options = _visible;
    return Focus(
      canRequestFocus: false,
      onKeyEvent: _key,
      child: SizedBox(
        width: math.min(
          _width,
          MediaQuery.sizeOf(context).width - ui.space.s4 * 2,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(context).height * .6,
          ),
          child: Padding(
            padding: EdgeInsets.all(ui.space.s2),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                if (widget.header != null) widget.header!,
                UiField(
                  label: widget.searchLabel,
                  controller: _query,
                  focusNode: _searchFocus,
                  leading: UiIcons.search,
                  onChanged: (_) => setState(() {}),
                ),
                Flexible(
                  child: options.isEmpty
                      ? Padding(
                          padding: EdgeInsets.all(ui.space.s3),
                          child: Text(
                            widget.emptyLabel,
                            style: ui.type.bodySmall,
                          ),
                        )
                      : SingleChildScrollView(
                          // These named keyboard targets must remain mounted
                          // when they are outside the viewport. Lazy children
                          // have no context for focus or ensureVisible.
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: <Widget>[
                              for (
                                int i = 0;
                                i < options.length;
                                i++
                              ) ...<Widget>[
                                if (options[i].group != null &&
                                    (i == 0 ||
                                        options[i - 1].group !=
                                            options[i].group))
                                  Padding(
                                    padding: EdgeInsets.all(ui.space.s2),
                                    child: Text(
                                      options[i].group!,
                                      style: ui.type.labelSmall,
                                    ),
                                  ),
                                _option(options[i]),
                              ],
                            ],
                          ),
                        ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _option(UiComboboxOption<T> option) {
    final ui = context.ui;
    final selected = widget.selected.contains(option.value);
    return Pressable(
      semanticsLabel: [
        option.label,
        if (option.supporting != null) option.supporting!,
      ].join('. '),
      role: widget.multiple ? PressableRole.checkbox : PressableRole.button,
      checked: widget.multiple ? selected : null,
      selected: selected,
      disabledReason: option.disabledReason,
      focusNode: _nodes.putIfAbsent(
        option.value,
        () => FocusNode(debugLabel: option.label),
      ),
      onPressed: option.enabled ? () => _pick(option) : null,
      builder: (context, states) => Padding(
        padding: EdgeInsets.all(ui.space.s3),
        child: Row(
          children: <Widget>[
            if (option.leading != null) ...[
              option.leading!,
              SizedBox(width: ui.space.s3),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    option.label,
                    style: ui.type.body.copyWith(
                      color: option.enabled
                          ? ui.color.ink
                          : ui.color.disabledContent,
                    ),
                  ),
                  if (option.supporting != null)
                    Text(option.supporting!, style: ui.type.bodySmall),
                ],
              ),
            ),
            if (selected) const UiIcon(UiIcons.check, size: UiIconSize.inline),
          ],
        ),
      ),
    );
  }
}
