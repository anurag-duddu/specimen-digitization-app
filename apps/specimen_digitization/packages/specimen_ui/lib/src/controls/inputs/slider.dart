/// A controlled numeric input with pointer, keyboard and semantic actions.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../foundation/density.dart';
import '../../primitives/focus_ring.dart';
import 'field.dart';

/// Selects one value in an inclusive numeric range.
///
/// Arrow keys change one step, Page keys change ten steps, and Home/End select
/// the limits. Horizontal arrows follow reading direction. The caller owns
/// [value]; null [onChanged] disables every interaction. Replaces Material's
/// Slider without introducing Material paint or behaviour dependencies.
class UiSlider extends StatefulWidget {
  /// Builds a labelled range input. [divisions] divides the range evenly.
  const UiSlider({
    super.key,
    required this.label,
    required this.value,
    this.min = 0,
    this.max = 1,
    this.divisions,
    this.onChanged,
    this.onChangeEnd,
    this.valueLabel,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.focusNode,
    this.autofocus = false,
  }) : assert(min < max),
       assert(value >= min && value <= max),
       assert(divisions == null || divisions > 0);

  /// Visible and spoken name.
  final String label;

  /// Current value, between [min] and [max].
  final double value;

  /// Inclusive lower limit.
  final double min;

  /// Inclusive upper limit.
  final double max;

  /// Number of equal steps; null permits continuous pointer input.
  final int? divisions;

  /// Receives proposed values. The caller must rebuild with its accepted value.
  final ValueChanged<double>? onChanged;

  /// Receives the final proposed value after pointer or keyboard adjustment.
  final ValueChanged<double>? onChangeEnd;

  /// Formats the visible and spoken value, including units where needed.
  final String Function(double value)? valueLabel;

  /// Supporting instructions.
  final String? helpText;

  /// Validation message, taking precedence over [helpText].
  final String? errorText;

  /// Explains why the value cannot be changed.
  final String? disabledReason;

  /// Optional caller-owned focus node.
  final FocusNode? focusNode;

  /// Requests focus when mounted.
  final bool autofocus;

  @override
  State<UiSlider> createState() => _UiSliderState();
}

class _UiSliderState extends State<UiSlider> {
  final FocusNode _focus = FocusNode(debugLabel: 'UiSlider');
  bool _showFocus = false;
  double? _lastProposed;
  bool get _enabled => widget.onChanged != null;
  FocusNode get _node => widget.focusNode ?? _focus;
  double get _step => (widget.max - widget.min) / (widget.divisions ?? 100);
  String _label(double value) =>
      widget.valueLabel?.call(value) ??
      value.toStringAsFixed(2).replaceFirst(RegExp(r'\.?0+$'), '');

  double _normalize(double value) {
    final double bounded = value.clamp(widget.min, widget.max).toDouble();
    return widget.divisions == null
        ? bounded
        : (widget.min + ((bounded - widget.min) / _step).round() * _step)
              .clamp(widget.min, widget.max)
              .toDouble();
  }

  void _propose(double value, {bool finish = true}) {
    if (!_enabled) return;
    final double next = _normalize(value);
    _lastProposed = next;
    if (next != widget.value) widget.onChanged!(next);
    if (finish) widget.onChangeEnd?.call(next);
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (!_enabled || (event is! KeyDownEvent && event is! KeyRepeatEvent)) {
      return KeyEventResult.ignored;
    }
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    final double? next = switch (event.logicalKey) {
      LogicalKeyboardKey.arrowRight => widget.value + (rtl ? -_step : _step),
      LogicalKeyboardKey.arrowLeft => widget.value + (rtl ? _step : -_step),
      LogicalKeyboardKey.arrowUp => widget.value + _step,
      LogicalKeyboardKey.arrowDown => widget.value - _step,
      LogicalKeyboardKey.pageUp => widget.value + _step * 10,
      LogicalKeyboardKey.pageDown => widget.value - _step * 10,
      LogicalKeyboardKey.home => widget.min,
      LogicalKeyboardKey.end => widget.max,
      _ => null,
    };
    if (next == null) return KeyEventResult.ignored;
    _propose(next);
    return KeyEventResult.handled;
  }

  @override
  void dispose() {
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double fraction =
        (widget.value - widget.min) / (widget.max - widget.min);
    final Set<WidgetState> states = <WidgetState>{
      if (!_enabled) WidgetState.disabled,
      if (widget.errorText != null) WidgetState.error,
    };
    return UiFieldFrame(
      style: UiInputStyle.resolve(ui, UiFieldShape.box),
      states: states,
      label: widget.label,
      message: widget.errorText ?? widget.disabledReason ?? widget.helpText,
      isError: widget.errorText != null,
      child: Semantics(
        label: widget.label,
        value: _label(widget.value),
        slider: true,
        enabled: _enabled,
        hint: widget.errorText ?? widget.disabledReason ?? widget.helpText,
        increasedValue: _enabled && widget.value < widget.max
            ? _label(_normalize(widget.value + _step))
            : null,
        decreasedValue: _enabled && widget.value > widget.min
            ? _label(_normalize(widget.value - _step))
            : null,
        onIncrease: _enabled && widget.value < widget.max
            ? () => _propose(widget.value + _step)
            : null,
        onDecrease: _enabled && widget.value > widget.min
            ? () => _propose(widget.value - _step)
            : null,
        excludeSemantics: true,
        child: Focus(
          canRequestFocus: false,
          onKeyEvent: _key,
          child: FocusableActionDetector(
            focusNode: _node,
            autofocus: widget.autofocus,
            enabled: _enabled,
            onShowFocusHighlight: (bool show) =>
                setState(() => _showFocus = show),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  _label(widget.value),
                  style: ui.type.label.copyWith(
                    color: _enabled ? ui.color.ink : ui.color.disabledContent,
                  ),
                ),
                FocusRing(
                  visible: _showFocus,
                  child: LayoutBuilder(
                    builder:
                        (BuildContext context, BoxConstraints constraints) {
                          final double inset = ui.space.s3;
                          final double width = constraints.maxWidth - inset * 2;
                          void update(double x, {bool finish = false}) {
                            if (width <= 0) return;
                            double t = ((x - inset) / width)
                                .clamp(0, 1)
                                .toDouble();
                            if (Directionality.of(context) ==
                                TextDirection.rtl) {
                              t = 1 - t;
                            }
                            _propose(
                              widget.min + t * (widget.max - widget.min),
                              finish: finish,
                            );
                          }

                          return MouseRegion(
                            cursor: _enabled
                                ? SystemMouseCursors.click
                                : SystemMouseCursors.basic,
                            child: GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTapUp: _enabled
                                  ? (TapUpDetails event) {
                                      _node.requestFocus();
                                      update(
                                        event.localPosition.dx,
                                        finish: true,
                                      );
                                    }
                                  : null,
                              onHorizontalDragStart: _enabled
                                  ? (DragStartDetails event) {
                                      _node.requestFocus();
                                      update(event.localPosition.dx);
                                    }
                                  : null,
                              onHorizontalDragUpdate: _enabled
                                  ? (DragUpdateDetails event) =>
                                        update(event.localPosition.dx)
                                  : null,
                              onHorizontalDragEnd: _enabled
                                  ? (_) => widget.onChangeEnd?.call(
                                      _lastProposed ?? widget.value,
                                    )
                                  : null,
                              child: SizedBox(
                                height: UiDensity.hitBox,
                                child: Padding(
                                  padding: EdgeInsets.symmetric(
                                    horizontal: inset,
                                  ),
                                  child: Stack(
                                    alignment: Alignment.center,
                                    clipBehavior: Clip.none,
                                    children: <Widget>[
                                      Container(
                                        height: ui.space.s1,
                                        decoration: BoxDecoration(
                                          color: _enabled
                                              ? ui.color.boundary
                                              : ui.color.disabledFill,
                                          borderRadius: BorderRadius.circular(
                                            ui.shape.inner,
                                          ),
                                        ),
                                      ),
                                      Align(
                                        alignment:
                                            AlignmentDirectional.centerStart,
                                        child: FractionallySizedBox(
                                          widthFactor: fraction,
                                          child: Container(
                                            height: ui.space.s1,
                                            decoration: BoxDecoration(
                                              color: _enabled
                                                  ? ui.color.accent
                                                  : ui.color.disabledContent,
                                              borderRadius:
                                                  BorderRadius.circular(
                                                    ui.shape.inner,
                                                  ),
                                            ),
                                          ),
                                        ),
                                      ),
                                      Align(
                                        alignment: AlignmentDirectional(
                                          fraction * 2 - 1,
                                          0,
                                        ),
                                        child: Transform.translate(
                                          offset: Offset(
                                            (fraction * 2 - 1) *
                                                inset *
                                                (Directionality.of(context) ==
                                                        TextDirection.rtl
                                                    ? -1
                                                    : 1),
                                            0,
                                          ),
                                          child: Container(
                                            width: inset * 2,
                                            height: inset * 2,
                                            decoration: BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: ui.color.paper,
                                              border: Border.all(
                                                color: _enabled
                                                    ? ui.color.accent
                                                    : ui.color.disabledContent,
                                                width: ui.shape.stroke.emphasis,
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
                          );
                        },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
