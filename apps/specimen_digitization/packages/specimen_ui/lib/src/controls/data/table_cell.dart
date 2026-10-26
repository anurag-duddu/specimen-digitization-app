/// Composable data-cell anatomy and row commands.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import '../../foundation/icons.dart';
import '../../primitives/pressable.dart';
import '../../primitives/focus_ring.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart';
import '../actions/icon_button.dart';
import '../overlays/popover_menu.dart';

/// A rich cell without implicit navigation or a competing selection gesture.
/// [selection] accepts a controlled checkbox/radio/switch. [leading] accepts an
/// avatar, icon or payment mark, while [detail] carries badges, progress, ratings
/// or trends. Hosts retain those controls' callbacks and accessible labels.
class UiTableCell extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiTableCell({
    super.key,
    required this.label,
    this.supporting,
    this.selection,
    this.leading,
    this.detail,
    this.trailing,
    this.numeric = false,
    this.enabled = true,
  });

  /// The visible accessible name supplied by the host.
  final String label;

  /// The optional supporting description or content slot.
  final String? supporting;

  /// Controlled checkbox, radio or switch; the host owns its permission.
  final Widget? selection;

  /// Avatar, icon or provider mark preceding the text.
  final Widget? leading;

  /// Badge, trend, rating or progress beneath the value.
  final Widget? detail;

  /// Row commands or supplemental content at the trailing edge.
  final Widget? trailing;

  /// Whether text aligns to the trailing edge as a numerical value.
  final bool numeric;

  /// Whether primary/supporting text uses normal rather than disabled paint.
  /// Interactive slots retain their own explicit enabled state and callbacks.
  final bool enabled;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        if (selection != null) ...[selection!, SizedBox(width: ui.space.s2)],
        if (leading != null) ...[leading!, SizedBox(width: ui.space.s3)],
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: numeric
                ? CrossAxisAlignment.end
                : CrossAxisAlignment.start,
            children: [
              Text(
                label,
                textAlign: numeric ? TextAlign.end : TextAlign.start,
                style: (numeric ? ui.type.mono.identifier : ui.type.label)
                    .copyWith(
                      color: enabled ? ui.color.ink : ui.color.disabledContent,
                    ),
              ),
              if (supporting != null)
                Text(
                  supporting!,
                  textAlign: numeric ? TextAlign.end : TextAlign.start,
                  style: ui.type.bodySmall.copyWith(
                    color: enabled
                        ? ui.color.inkSecondary
                        : ui.color.disabledContent,
                  ),
                ),
              if (detail != null)
                Padding(
                  padding: EdgeInsets.only(top: ui.space.s2),
                  child: detail,
                ),
            ],
          ),
        ),
        if (trailing != null) ...[
          SizedBox(width: ui.space.s2),
          Flexible(child: trailing!),
        ],
      ],
    );
  }
}

/// One row action. Disabled actions stay visible and correctly noninteractive.
@immutable
class UiTableAction {
  /// Creates the component with explicit content and caller-owned state.
  const UiTableAction({
    required this.label,
    this.onPressed,
    this.destructive = false,
    this.icon,
  });

  /// The visible accessible name supplied by the host.
  final String label;

  /// The host action; null keeps the command disabled.
  final VoidCallback? onPressed;

  /// Whether the command uses the destructive action treatment.
  final bool destructive;

  /// Optional glyph used by the icon and menu presentations.
  final IconSpec? icon;
}

/// How a row's commands are presented.
enum UiTableActionsPresentation {
  /// Explicit text commands.
  buttons,

  /// Glyph commands with record-specific names and tooltips.
  icons,

  /// An overflow menu using the shared dismissal and focus contract.
  menu,
}

/// Wrapping row command group with explicit record-specific accessible names.
class UiTableActions extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiTableActions({
    super.key,
    required this.rowLabel,
    required this.actions,
    this.presentation = UiTableActionsPresentation.buttons,
  });

  /// The record identity included in every accessible command name.
  final String rowLabel;

  /// The caller-owned commands in reading order.
  final List<UiTableAction> actions;

  /// Presentation independently of each action's callback or permission.
  final UiTableActionsPresentation presentation;

  @override
  Widget build(BuildContext context) =>
      presentation == UiTableActionsPresentation.menu
      ? UiMenuTrigger(
          semanticsLabel: 'Actions for $rowLabel',
          menuLabel: 'Actions for $rowLabel',
          items: [
            for (final action in actions)
              UiMenuItem(
                label: action.label,
                onSelected: action.onPressed,
                icon: action.icon,
                destructive: action.destructive,
              ),
          ],
        )
      : Wrap(
          spacing: context.ui.space.s2,
          runSpacing: context.ui.space.s2,
          children: [
            for (final action in actions)
              if (presentation == UiTableActionsPresentation.icons &&
                  action.icon != null)
                UiIconButton(
                  icon: action.icon!,
                  semanticsLabel: '${action.label}, $rowLabel',
                  onPressed: action.onPressed,
                )
              else
                UiButton(
                  label: action.label,
                  semanticsLabel: '${action.label}, $rowLabel',
                  size: UiSize.sm,
                  variant: action.destructive
                      ? UiButtonVariant.danger
                      : UiButtonVariant.ghost,
                  onPressed: action.onPressed,
                ),
          ],
        );
}

/// A star rating with an exact text value and optional controlled editing.
///
/// Null means not rated, while zero is a measured zero. Display values may be
/// fractional; interactive steps use whole ratings. The host owns persistence.
/// Keyboard arrows follow reading direction; Home/End choose zero/maximum.
class UiRating extends StatefulWidget {
  /// Creates a display rating or, with [onChanged], an adjustable rating.
  const UiRating({
    super.key,
    required this.label,
    required this.value,
    this.maximum = 5,
    this.onChanged,
    this.enabled = true,
    this.allowClear = true,
    this.clearLabel = 'Clear rating',
    this.notRatedLabel = 'Not rated',
  }) : assert(maximum > 0),
       assert(value == null || (value >= 0 && value <= maximum));

  /// The object or criterion being rated, included in the accessible name.
  final String label;

  /// The exact rating, or null when nobody has rated the object.
  final double? value;

  /// The number of stars and highest valid rating.
  final int maximum;

  /// Requests a value; null makes this a read-only display.
  final ValueChanged<double?>? onChanged;

  /// Whether an editable rating accepts input.
  final bool enabled;

  /// Whether the clear command can restore the unrated state.
  final bool allowClear;

  /// The visible and spoken clear command.
  final String clearLabel;

  /// The visible and spoken absence description.
  final String notRatedLabel;

  @override
  State<UiRating> createState() => _UiRatingState();
}

class _UiRatingState extends State<UiRating> {
  final _focus = FocusNode();
  bool _focused = false;
  bool get _editable => widget.enabled && widget.onChanged != null;
  String get _valueLabel => widget.value == null
      ? widget.notRatedLabel
      : '${widget.value == widget.value!.roundToDouble() ? widget.value!.toInt() : widget.value} of ${widget.maximum}';

  @override
  void dispose() {
    _focus.dispose();
    super.dispose();
  }

  void _request(double? value) {
    if (_editable && value != widget.value) widget.onChanged!(value);
  }

  void _step(bool increase) {
    final value = widget.value ?? 0;
    _request(
      (increase ? value.floor() + 1 : value.ceil() - 1)
          .clamp(0, widget.maximum)
          .toDouble(),
    );
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (!_editable || event is! KeyDownEvent) return KeyEventResult.ignored;
    final key = event.logicalKey;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    if (key == LogicalKeyboardKey.arrowRight ||
        key == LogicalKeyboardKey.arrowLeft) {
      _step((key == LogicalKeyboardKey.arrowRight) != rtl);
    } else if (key == LogicalKeyboardKey.arrowUp ||
        key == LogicalKeyboardKey.arrowDown) {
      _step(key == LogicalKeyboardKey.arrowUp);
    } else if (key == LogicalKeyboardKey.home) {
      _request(0);
    } else if (key == LogicalKeyboardKey.end) {
      _request(widget.maximum.toDouble());
    } else if ((key == LogicalKeyboardKey.delete ||
            key == LogicalKeyboardKey.backspace) &&
        widget.allowClear) {
      _request(null);
    } else {
      return KeyEventResult.ignored;
    }
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final color = widget.enabled
        ? ui.brand.secondary.content
        : ui.color.disabledContent;
    Widget star(int index) => Stack(
      children: [
        UiIcon(UiIcons.rating, color: color, size: UiIconSize.inline),
        ClipRect(
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            widthFactor: ((widget.value ?? 0) - index).clamp(0, 1).toDouble(),
            child: UiIcon(
              UiIcons.rating,
              current: true,
              color: color,
              size: UiIconSize.inline,
            ),
          ),
        ),
      ],
    );
    final stars = Wrap(
      spacing: _editable ? 0 : ui.space.s1,
      children: [
        for (var index = 0; index < widget.maximum; index++)
          if (widget.onChanged == null)
            star(index)
          else
            Pressable(
              semanticsLabel:
                  '${widget.label}, ${index + 1} of ${widget.maximum}',
              excludeFromSemantics: true,
              onPressed: _editable
                  ? () {
                      _focus.requestFocus();
                      _request(index + 1.0);
                    }
                  : null,
              builder: (_, states) => Padding(
                padding: EdgeInsets.all(ui.space.s2),
                child: star(index),
              ),
            ),
      ],
    );
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          label: widget.label,
          value: _valueLabel,
          slider: widget.onChanged != null,
          enabled: widget.onChanged == null ? null : widget.enabled,
          focusable: _editable,
          focused: _editable && _focused,
          onIncrease: _editable && (widget.value ?? 0) < widget.maximum
              ? () => _step(true)
              : null,
          onDecrease: _editable && (widget.value ?? 0) > 0
              ? () => _step(false)
              : null,
          increasedValue: _editable && (widget.value ?? 0) < widget.maximum
              ? '${(widget.value ?? 0).floor() + 1} of ${widget.maximum}'
              : null,
          decreasedValue: _editable && (widget.value ?? 0) > 0
              ? '${widget.value!.ceil() - 1} of ${widget.maximum}'
              : null,
          excludeSemantics: true,
          child: Focus(
            focusNode: _focus,
            canRequestFocus: _editable,
            onFocusChange: (value) => setState(() => _focused = value),
            onKeyEvent: _onKey,
            child: FocusRing(
              visible: _focused,
              radius: ui.shape.inner,
              child: ExcludeFocus(child: stars),
            ),
          ),
        ),
        SizedBox(height: ui.space.s1),
        ExcludeSemantics(
          child: Text(
            _valueLabel,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ),
        if (widget.onChanged != null && widget.allowClear)
          UiButton(
            label: widget.clearLabel,
            variant: UiButtonVariant.ghost,
            size: UiSize.sm,
            onPressed: _editable && widget.value != null
                ? () => _request(null)
                : null,
          ),
      ],
    );
  }
}
