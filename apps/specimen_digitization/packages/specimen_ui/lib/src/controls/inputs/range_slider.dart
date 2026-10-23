/// A controlled pair of numeric bounds on one track.
library;

import 'dart:math' as math;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import '../../foundation/density.dart';
import '../../foundation/theme.dart';
import '../../primitives/focus_ring.dart';
import 'field.dart';

/// Placement of the two visible range values.
enum UiRangeLabelPosition {
  /// Fixed values above the track.
  above,

  /// Fixed values below the track.
  below,

  /// Values follow the thumbs above the track, merging when they overlap.
  floating,

  /// Values follow the thumbs below the track, merging when they overlap.
  floatingBelow,
}

/// An ordered pair of inclusive numeric bounds.
@immutable
class UiRangeValues {
  /// Creates the component with explicit caller-owned configuration.
  const UiRangeValues(this.start, this.end) : assert(start <= end);

  /// The inclusive lower bound.
  final double start;

  /// The inclusive upper bound.
  final double end;
  @override
  bool operator ==(Object other) =>
      other is UiRangeValues && other.start == start && other.end == end;
  @override
  int get hashCode => Object.hash(start, end);
}

/// Two independently focusable slider thumbs; neither can cross the other.
///
/// Pointer/touch chooses the nearest thumb. Arrows respect RTL, Home/End reach
/// the other thumb or outer bound, Page keys move ten steps. Each thumb exposes
/// its own screen-reader increase/decrease action and meaningful bound label.
class UiRangeSlider extends StatefulWidget {
  /// Creates the component with explicit caller-owned configuration.
  UiRangeSlider({
    super.key,
    required this.label,
    required this.values,
    this.min = 0,
    this.max = 1,
    this.divisions,
    this.onChanged,
    this.onChangeEnd,
    this.startLabel = 'Minimum',
    this.endLabel = 'Maximum',
    this.valueLabel,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.showValues = true,
    this.labelPosition = UiRangeLabelPosition.above,
  }) : assert(min < max),
       assert(values.start >= min && values.end <= max),
       assert(divisions == null || divisions > 0);

  /// The visible and accessible name of the control.
  final String label;

  /// The current collection of values accepted by the host.
  final UiRangeValues values;

  /// The lowest permitted numeric value.
  final double min;

  /// The highest permitted numeric value.
  final double max;

  /// The number of equal steps, or `null` for continuous pointer changes.
  final int? divisions;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<UiRangeValues>? onChanged;

  /// The callback after a completed gesture or keyboard adjustment.
  final ValueChanged<UiRangeValues>? onChangeEnd;

  /// The accessible name of the lower-bound thumb.
  final String startLabel;

  /// The accessible name of the upper-bound thumb.
  final String endLabel;

  /// The optional human-readable value or value formatter.
  final String Function(double)? valueLabel;

  /// The persistent supporting instruction beneath the control.
  final String? helpText;

  /// The validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  /// Whether numeric values are visible alongside the track.
  final bool showValues;

  /// Fixed or thumb-relative value placement.
  final UiRangeLabelPosition labelPosition;
  @override
  State<UiRangeSlider> createState() => _UiRangeSliderState();
}

class _UiRangeSliderState extends State<UiRangeSlider> {
  final _nodes = <FocusNode>[
    FocusNode(debugLabel: 'Range start'),
    FocusNode(debugLabel: 'Range end'),
  ];
  final _highlight = <bool>[false, false];
  int _active = 0;
  bool _awaitingDragDirection = false;
  UiRangeValues? _proposed;
  bool get _enabled => widget.onChanged != null;
  double get _step => (widget.max - widget.min) / (widget.divisions ?? 100);
  String _format(double v) =>
      widget.valueLabel?.call(v) ??
      v.toStringAsFixed(2).replaceFirst(RegExp(r'\.?0+$'), '');
  double _value(int index) =>
      index == 0 ? widget.values.start : widget.values.end;
  double _low(int index) => index == 0 ? widget.min : widget.values.start;
  double _high(int index) => index == 0 ? widget.values.end : widget.max;
  double _normalize(int index, double value) {
    if (widget.divisions != null) {
      value = widget.min + ((value - widget.min) / _step).round() * _step;
    }
    return value.clamp(_low(index), _high(index)).toDouble();
  }

  void _update(int index, double value, {bool finish = true}) {
    if (!_enabled) return;
    final next = _normalize(index, value);
    _proposed = index == 0
        ? UiRangeValues(next, widget.values.end)
        : UiRangeValues(widget.values.start, next);
    if (_proposed != widget.values) widget.onChanged!(_proposed!);
    if (finish) widget.onChangeEnd?.call(_proposed!);
  }

  KeyEventResult _key(int index, KeyEvent event) {
    if (!_enabled || (event is! KeyDownEvent && event is! KeyRepeatEvent)) {
      return KeyEventResult.ignored;
    }
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final value = _value(index);
    final double? next = switch (event.logicalKey) {
      LogicalKeyboardKey.arrowRight => value + (rtl ? -_step : _step),
      LogicalKeyboardKey.arrowLeft => value + (rtl ? _step : -_step),
      LogicalKeyboardKey.arrowUp => value + _step,
      LogicalKeyboardKey.arrowDown => value - _step,
      LogicalKeyboardKey.pageUp => value + _step * 10,
      LogicalKeyboardKey.pageDown => value - _step * 10,
      LogicalKeyboardKey.home => _low(index),
      LogicalKeyboardKey.end => _high(index),
      _ => null,
    };
    if (next == null) return KeyEventResult.ignored;
    _update(index, next);
    return KeyEventResult.handled;
  }

  @override
  void dispose() {
    for (final node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return UiFieldFrame(
      label: widget.label,
      style: UiInputStyle.resolve(ui, UiFieldShape.box),
      states: <WidgetState>{
        if (!_enabled) WidgetState.disabled,
        if (widget.errorText != null) WidgetState.error,
      },
      message: widget.errorText ?? widget.disabledReason ?? widget.helpText,
      isError: widget.errorText != null,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (widget.showValues &&
              (widget.labelPosition == UiRangeLabelPosition.above ||
                  widget.labelPosition == UiRangeLabelPosition.floating))
            _labels(),
          LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth;
              final extent = math.max(1.0, width - UiDensity.hitBox);
              final rtl = Directionality.of(context) == TextDirection.rtl;
              double fraction(double v) =>
                  (v - widget.min) / (widget.max - widget.min);
              double fromX(double x) {
                var t = ((x - UiDensity.hitBox / 2) / extent).clamp(0.0, 1.0);
                if (rtl) t = 1 - t;
                return widget.min + t * (widget.max - widget.min);
              }

              void choose(double x, {bool dragging = false}) {
                final v = fromX(x);
                final startDistance = (v - widget.values.start).abs();
                final endDistance = (v - widget.values.end).abs();
                final bool collapsed = widget.values.start == widget.values.end;
                final sharedHitRadius =
                    UiDensity.hitBox / 2 / extent * (widget.max - widget.min);
                _awaitingDragDirection =
                    dragging &&
                    collapsed &&
                    (v - widget.values.start).abs() <= sharedHitRadius;
                _active = collapsed && v != widget.values.start
                    ? (v < widget.values.start ? 0 : 1)
                    : startDistance == endDistance
                    ? (_nodes[1].hasFocus ? 1 : 0)
                    : startDistance < endDistance
                    ? 0
                    : 1;
                if (!_awaitingDragDirection) _nodes[_active].requestFocus();
              }

              return GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTapUp: !_enabled
                    ? null
                    : (event) {
                        choose(event.localPosition.dx);
                        _update(_active, fromX(event.localPosition.dx));
                      },
                onHorizontalDragStart: !_enabled
                    ? null
                    : (event) {
                        _proposed = null;
                        choose(event.localPosition.dx, dragging: true);
                      },
                onHorizontalDragUpdate: !_enabled
                    ? null
                    : (event) {
                        if (_awaitingDragDirection) {
                          final delta = event.primaryDelta ?? 0;
                          if (delta == 0) return;
                          final logicalDelta = rtl ? -delta : delta;
                          _active = logicalDelta < 0 ? 0 : 1;
                          _awaitingDragDirection = false;
                          _nodes[_active].requestFocus();
                        }
                        // Once chosen, this thumb owns the entire gesture,
                        // even if the pointer reverses or reaches the other.
                        _update(
                          _active,
                          fromX(event.localPosition.dx),
                          finish: false,
                        );
                      },
                onHorizontalDragEnd: !_enabled
                    ? null
                    : (_) {
                        widget.onChangeEnd?.call(_proposed ?? widget.values);
                        _awaitingDragDirection = false;
                        _proposed = null;
                      },
                onHorizontalDragCancel: () {
                  _awaitingDragDirection = false;
                  _proposed = null;
                },
                child: SizedBox(
                  height: UiDensity.hitBox,
                  width: width,
                  child: Stack(
                    children: <Widget>[
                      PositionedDirectional(
                        start: UiDensity.hitBox / 2,
                        end: UiDensity.hitBox / 2,
                        top: (UiDensity.hitBox - ui.space.s1) / 2,
                        child: SizedBox(
                          height: ui.space.s1,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: ui.color.hairline,
                              borderRadius: BorderRadius.circular(
                                ui.shape.inner,
                              ),
                            ),
                          ),
                        ),
                      ),
                      PositionedDirectional(
                        start:
                            UiDensity.hitBox / 2 +
                            fraction(widget.values.start) * extent,
                        width:
                            (fraction(widget.values.end) -
                                fraction(widget.values.start)) *
                            extent,
                        top: (UiDensity.hitBox - ui.space.s1) / 2,
                        child: SizedBox(
                          height: ui.space.s1,
                          child: ColoredBox(
                            color: _enabled
                                ? ui.brand.secondary.content
                                : ui.color.disabledContent,
                          ),
                        ),
                      ),
                      for (int index = 0; index < 2; index++)
                        PositionedDirectional(
                          start: fraction(_value(index)) * extent,
                          child: _thumb(index),
                        ),
                    ],
                  ),
                ),
              );
            },
          ),
          if (widget.showValues &&
              (widget.labelPosition == UiRangeLabelPosition.below ||
                  widget.labelPosition == UiRangeLabelPosition.floatingBelow))
            _labels(),
        ],
      ),
    );
  }

  Widget _labels() {
    final ui = context.ui;
    final floating =
        widget.labelPosition == UiRangeLabelPosition.floating ||
        widget.labelPosition == UiRangeLabelPosition.floatingBelow;
    final start = '${widget.startLabel}: ${_format(widget.values.start)}';
    final end = '${widget.endLabel}: ${_format(widget.values.end)}';
    if (!floating) {
      return ExcludeSemantics(
        child: Row(
          children: [
            Expanded(child: Text(start, style: ui.type.label)),
            SizedBox(width: ui.space.s3),
            Expanded(
              child: Text(end, textAlign: TextAlign.end, style: ui.type.label),
            ),
          ],
        ),
      );
    }
    return ExcludeSemantics(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final texts = [
            _format(widget.values.start),
            _format(widget.values.end),
          ];
          final painters = [
            for (final text in texts)
              TextPainter(
                text: TextSpan(text: text, style: ui.type.label),
                textDirection: Directionality.of(context),
                textScaler: MediaQuery.textScalerOf(context),
              )..layout(),
          ];
          final widths = painters.map((p) => p.width + ui.space.s4).toList();
          final height =
              painters.map((p) => p.height).reduce(math.max) + ui.space.s2;
          for (final painter in painters) {
            painter.dispose();
          }
          final extent = math.max(0.0, constraints.maxWidth - UiDensity.hitBox);
          double position(double value, double width) =>
              (UiDensity.hitBox / 2 +
                      (value - widget.min) /
                          (widget.max - widget.min) *
                          extent -
                      width / 2)
                  .clamp(0.0, math.max(0.0, constraints.maxWidth - width));
          final startX = position(widget.values.start, widths[0]);
          final endX = position(widget.values.end, widths[1]);
          Widget bubble(String text) => Container(
            padding: EdgeInsets.symmetric(
              horizontal: ui.space.s2,
              vertical: ui.space.s1,
            ),
            decoration: BoxDecoration(
              color: ui.color.paper,
              border: Border.all(color: ui.color.boundary),
              borderRadius: BorderRadius.circular(ui.shape.inner),
            ),
            child: Text(text, style: ui.type.label),
          );
          if (startX + widths[0] + ui.space.s2 > endX) {
            return Align(
              alignment: AlignmentDirectional.center,
              child: bubble('${texts[0]} to ${texts[1]}'),
            );
          }
          return SizedBox(
            height: height,
            child: Stack(
              children: [
                PositionedDirectional(
                  start: startX,
                  width: widths[0],
                  child: bubble(texts[0]),
                ),
                PositionedDirectional(
                  start: endX,
                  width: widths[1],
                  child: bubble(texts[1]),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _thumb(int index) {
    final ui = context.ui;
    final v = _value(index);
    final name = index == 0 ? widget.startLabel : widget.endLabel;
    return Semantics(
      label: '${widget.label}, $name',
      value: _format(v),
      slider: true,
      enabled: _enabled,
      excludeSemantics: true,
      hint: widget.errorText ?? widget.disabledReason ?? widget.helpText,
      increasedValue: _enabled && v < _high(index)
          ? _format(_normalize(index, v + _step))
          : null,
      decreasedValue: _enabled && v > _low(index)
          ? _format(_normalize(index, v - _step))
          : null,
      onIncrease: _enabled && v < _high(index)
          ? () => _update(index, v + _step)
          : null,
      onDecrease: _enabled && v > _low(index)
          ? () => _update(index, v - _step)
          : null,
      child: Focus(
        onKeyEvent: (node, event) => _key(index, event),
        canRequestFocus: false,
        child: FocusableActionDetector(
          focusNode: _nodes[index],
          enabled: _enabled,
          onShowFocusHighlight: (show) =>
              setState(() => _highlight[index] = show),
          child: SizedBox.square(
            dimension: UiDensity.hitBox,
            child: Center(
              child: FocusRing(
                visible: _highlight[index],
                child: Container(
                  width: ui.space.s5,
                  height: ui.space.s5,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: ui.color.paper,
                    border: Border.all(
                      color: _enabled
                          ? ui.brand.secondary.content
                          : ui.color.disabledOutline,
                      width: ui.shape.stroke.emphasis,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
