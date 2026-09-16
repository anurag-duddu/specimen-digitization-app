/// The select (10 section 4.2, `UiSelect`).
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/glass.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/field_core.dart';
import '../../primitives/popover.dart';
import '../../primitives/pressable.dart';
import 'field.dart';

/// One option a [UiSelect] offers.
@immutable
class UiSelectOption<T> {
  /// An option that selects [value] and reads [label].
  const UiSelectOption({
    required this.value,
    required this.label,
    this.leading,
  });

  /// What choosing this option selects.
  final T value;

  /// What the option reads, in the list and in the trigger. Sentence case.
  final String label;

  /// An optional glyph before the label.
  final IconSpec? leading;
}

/// The resolved paint of one select.
///
/// The trigger is a field, so it resolves the family's [UiInputStyle] rather
/// than a second set of edge and fill tokens; the rest is the list.
@immutable
class UiSelectStyle {
  /// Binds every token a select draws with.
  const UiSelectStyle({
    required this.input,
    required this.optionLabel,
    required this.optionFill,
    required this.value,
    required this.placeholder,
    required this.rowHeight,
    required this.menuMaxHeight,
    required this.filterThreshold,
  });

  /// The trigger's edge, fill, padding and height.
  final UiInputStyle input;

  /// One option's label, by state.
  final WidgetStateProperty<TextStyle> optionLabel;

  /// Behind the selected option.
  final WidgetStateProperty<Color> optionFill;

  /// The selected option's label, drawn in the trigger.
  final WidgetStateProperty<TextStyle> value;

  /// The placeholder, drawn in the trigger while nothing is selected.
  final TextStyle placeholder;

  /// One option row's height, from density.
  final double rowHeight;

  /// How tall the list grows before it scrolls.
  final double menuMaxHeight;

  /// Above this many options the list gets a filter field (10 section 4.2).
  final int filterThreshold;

  /// The style in [ui].
  static UiSelectStyle resolve(UiThemeData ui) {
    TextStyle optionLabel(Set<WidgetState> states) => ui.type.body.copyWith(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledContent
          : ui.color.ink,
    );

    Color optionFill(Set<WidgetState> states) =>
        states.contains(WidgetState.selected)
        ? ui.color.stateLayer(ui.color.hoverOpacity)
        : ui.color.paper.withValues(alpha: 0);

    TextStyle value(Set<WidgetState> states) => ui.type.body.copyWith(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledContent
          : ui.color.ink,
    );

    return UiSelectStyle(
      input: UiInputStyle.resolve(ui, UiFieldShape.box),
      optionLabel: WidgetStateProperty.resolveWith(optionLabel),
      optionFill: WidgetStateProperty.resolveWith(optionFill),
      value: WidgetStateProperty.resolveWith(value),
      placeholder: ui.type.body.copyWith(color: ui.color.inkTertiary),
      rowHeight: ui.density.rowHeight,
      // Seven rows and part of an eighth, so a list that scrolls says so by
      // showing a row cut off at the bottom rather than by ending flush.
      menuMaxHeight: ui.density.rowHeight * 7.5,
      filterThreshold: 8,
    );
  }
}

/// A single selection from a list of options.
///
/// The trigger is a field with the selected option's label and a caret. It
/// opens a popover list; above [UiSelectStyle.filterThreshold] options the
/// list gets a filter field. `Down` and `Up` move between options, `Enter`
/// picks, `Escape` closes and returns focus to the trigger.
///
/// Retires `DropdownMenu`, `DropdownButton` and `MenuAnchor` used as a select.
class UiSelect<T> extends StatefulWidget {
  /// A select named [label] offering [options], currently on [value].
  const UiSelect({
    super.key,
    required this.label,
    required this.options,
    required this.value,
    required this.placeholder,
    this.onChanged,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.semanticsLabel,
    this.showLabel = true,
    this.filterLabel = 'Filter the options',
    this.emptyLabel = 'Nothing matches that filter.',
  });

  /// What the select chooses. Sentence case, no terminal period.
  final String label;

  /// Every option, in the order the reviewer should read them.
  final List<UiSelectOption<T>> options;

  /// The option currently selected, or null when none is.
  final T? value;

  /// What the trigger reads while nothing is selected. Names the choice, so
  /// it still says what the control is for (02 section 4.11).
  final String placeholder;

  /// Called with the option the reviewer picked. Null disables the select.
  final ValueChanged<T>? onChanged;

  /// One line under the trigger saying what the choice does.
  final String? helpText;

  /// The rule the choice broke, stated positively (02 section 4.10).
  final String? errorText;

  /// Why the select is disabled, in the reviewer's words (03 section 3.6).
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// False where the surface around the select already names it.
  final bool showLabel;

  /// What the filter field reads, once the list is long enough to have one.
  final String filterLabel;

  /// What the list says when the filter matches nothing.
  final String emptyLabel;

  @override
  State<UiSelect<T>> createState() => _UiSelectState<T>();
}

class _UiSelectState<T> extends State<UiSelect<T>> {
  final PopoverController _popover = PopoverController();
  final TextEditingController _filter = TextEditingController();
  final FocusNode _filterFocus = FocusNode(debugLabel: 'UiSelect filter');
  double _triggerWidth = 0;

  @override
  void initState() {
    super.initState();
    _popover.addListener(_popoverChanged);
  }

  @override
  void dispose() {
    _popover
      ..removeListener(_popoverChanged)
      ..dispose();
    _filter.dispose();
    _filterFocus.dispose();
    super.dispose();
  }

  bool get _enabled => widget.onChanged != null && widget.options.isNotEmpty;

  bool get _hasFilter => widget.options.length > _threshold;

  int get _threshold => UiSelectStyle.resolve(context.ui).filterThreshold;

  UiSelectOption<T>? get _selected {
    for (final UiSelectOption<T> option in widget.options) {
      if (option.value == widget.value) return option;
    }
    return null;
  }

  List<UiSelectOption<T>> get _visible {
    final String query = _filter.text.trim().toLowerCase();
    if (query.isEmpty) return widget.options;
    return <UiSelectOption<T>>[
      for (final UiSelectOption<T> option in widget.options)
        if (option.label.toLowerCase().contains(query)) option,
    ];
  }

  void _popoverChanged() {
    if (!mounted) return;
    if (!_popover.isOpen && _filter.text.isNotEmpty) _filter.clear();
    setState(() {});
  }

  void _open() {
    if (!_enabled) return;
    final RenderObject? box = context.findRenderObject();
    if (box is RenderBox && box.hasSize) _triggerWidth = box.size.width;
    _popover.open();
  }

  void _toggle() => _popover.isOpen ? _popover.close() : _open();

  void _pick(UiSelectOption<T> option) {
    _popover.close();
    widget.onChanged?.call(option.value);
  }

  /// `Down` and `Up` move between the options, `Enter` picks.
  ///
  /// Movement is focus movement rather than a highlight of our own, so the
  /// option a screen reader announces and the option `Enter` picks are the
  /// same one by construction. `Pressable` already activates on `Enter`, so
  /// this only has to handle the key while the filter field holds focus.
  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final LogicalKeyboardKey key = event.logicalKey;
    if (key == LogicalKeyboardKey.arrowDown) {
      FocusManager.instance.primaryFocus?.nextFocus();
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowUp) {
      FocusManager.instance.primaryFocus?.previousFocus();
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.enter &&
        FocusManager.instance.primaryFocus == _filterFocus) {
      final List<UiSelectOption<T>> visible = _visible;
      if (visible.isEmpty) return KeyEventResult.handled;
      _pick(visible.first);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  Set<WidgetState> get _states => <WidgetState>{
    if (!_enabled) WidgetState.disabled,
    if (widget.errorText != null) WidgetState.error,
    if (_popover.isOpen) WidgetState.focused,
  };

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiSelectStyle style = UiSelectStyle.resolve(ui);
    final UiSelectOption<T>? selected = _selected;
    final String? message = widget.errorText ?? widget.helpText;

    return UiFieldFrame(
      style: style.input,
      states: _states,
      label: widget.showLabel ? widget.label : null,
      message: message,
      isError: widget.errorText != null,
      child: Popover(
        controller: _popover,
        placement: PopoverPlacement.auto,
        level: GlassLevel.floating,
        radius: ui.shape.tile,
        // Deliberately unlabelled. The trigger has just announced the label,
        // the selected option and that the list is expanded; a pane repeating
        // the label is a second thing to listen past on the way to the
        // options.
        overlayBuilder: (BuildContext context) => _buildMenu(ui, style),
        child: _buildTrigger(ui, style, selected, message),
      ),
    );
  }

  Widget _buildTrigger(
    UiThemeData ui,
    UiSelectStyle style,
    UiSelectOption<T>? selected,
    String? message,
  ) {
    final Set<WidgetState> states = _states;
    return Semantics(
      container: true,
      button: true,
      // `Pressable` has no word for `expanded`, and a select that does not
      // say whether its list is open is a select a screen reader cannot
      // follow.
      expanded: _popover.isOpen,
      label: widget.semanticsLabel ?? widget.label,
      value: selected?.label ?? widget.placeholder,
      hint: _enabled ? message : widget.disabledReason,
      enabled: _enabled,
      onTap: _enabled ? _toggle : null,
      child: Pressable(
        excludeFromSemantics: true,
        semanticsLabel: widget.semanticsLabel ?? widget.label,
        onPressed: _enabled ? _toggle : null,
        disabledReason: widget.disabledReason,
        radius: style.input.radius,
        builder: (BuildContext context, Set<WidgetState> pressed) =>
            // The node above reads the label and the selected option; the
            // drawn text saying the same thing would be read after it.
            ExcludeSemantics(
              child: UiFieldBox(
                style: style.input,
                states: <WidgetState>{...states, ...pressed},
                leading: selected?.leading,
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        selected?.label ?? widget.placeholder,
                        style: selected == null
                            ? style.placeholder
                            : style.value.resolve(states),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    SizedBox(width: ui.space.s2),
                    UiIcon(
                      _popover.isOpen ? UiIcons.collapse : UiIcons.expand,
                      size: UiIconSize.inline,
                      color: style.input.glyph.resolve(states),
                    ),
                  ],
                ),
              ),
            ),
      ),
    );
  }

  Widget _buildMenu(UiThemeData ui, UiSelectStyle style) {
    final List<UiSelectOption<T>> visible = _visible;
    return Focus(
      canRequestFocus: false,
      skipTraversal: true,
      onKeyEvent: _onKey,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minWidth: _triggerWidth,
          maxWidth: _triggerWidth == 0 ? double.infinity : _triggerWidth,
          maxHeight: style.menuMaxHeight,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (_hasFilter) _buildFilter(ui, style),
            Flexible(
              child: visible.isEmpty
                  ? Padding(
                      padding: EdgeInsetsDirectional.all(ui.space.s3),
                      child: Text(
                        widget.emptyLabel,
                        style: ui.type.bodySmall.copyWith(
                          color: ui.color.inkSecondary,
                        ),
                      ),
                    )
                  : ListView.builder(
                      shrinkWrap: true,
                      padding: EdgeInsetsDirectional.symmetric(
                        vertical: ui.space.s1,
                      ),
                      itemCount: visible.length,
                      itemBuilder: (BuildContext context, int index) {
                        final UiSelectOption<T> option = visible[index];
                        return _OptionRow(
                          label: option.label,
                          leading: option.leading,
                          selected: option.value == widget.value,
                          style: style,
                          onPressed: () => _pick(option),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFilter(UiThemeData ui, UiSelectStyle style) => Padding(
    padding: EdgeInsetsDirectional.fromSTEB(
      ui.space.s3,
      ui.space.s3,
      ui.space.s3,
      ui.space.s2,
    ),
    child: ConstrainedBox(
      constraints: BoxConstraints(minHeight: ui.density.controlHeight),
      child: Row(
        children: <Widget>[
          UiIcon(
            UiIcons.search,
            size: UiIconSize.inline,
            color: ui.color.inkSecondary,
          ),
          SizedBox(width: ui.space.s2),
          Expanded(
            child: FieldCore(
              semanticsLabel: widget.filterLabel,
              controller: _filter,
              focusNode: _filterFocus,
              autofocus: true,
              autocorrect: false,
              showFocusRing: false,
              style: ui.type.body,
              onChanged: (String _) => setState(() {}),
            ),
          ),
        ],
      ),
    ),
  );
}

/// One row of the option list.
// TODO(fe/data): replace with UiListRow when it merges.
class _OptionRow extends StatelessWidget {
  const _OptionRow({
    required this.label,
    required this.leading,
    required this.selected,
    required this.style,
    required this.onPressed,
  });

  final String label;
  final IconSpec? leading;
  final bool selected;
  final UiSelectStyle style;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Pressable(
      semanticsLabel: label,
      selected: selected,
      onPressed: onPressed,
      radius: ui.shape.inner,
      minHitBox: 0,
      builder: (BuildContext context, Set<WidgetState> states) => DecoratedBox(
        decoration: BoxDecoration(color: style.optionFill.resolve(states)),
        child: ConstrainedBox(
          // A minimum rather than a height: at 200 percent text the label is
          // taller than the row and the row has to grow (10 section 2
          // clause 7).
          constraints: BoxConstraints(minHeight: style.rowHeight),
          child: Padding(
            padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s3),
            child: Row(
              children: <Widget>[
                if (leading != null) ...<Widget>[
                  UiIcon(
                    leading!,
                    size: UiIconSize.inline,
                    color: ui.color.inkSecondary,
                  ),
                  SizedBox(width: ui.space.s2),
                ],
                Expanded(
                  child: Text(
                    label,
                    style: style.optionLabel.resolve(states),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (selected) ...<Widget>[
                  SizedBox(width: ui.space.s2),
                  UiIcon(
                    UiIcons.check,
                    size: UiIconSize.small,
                    color: ui.color.ink,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
