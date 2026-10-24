/// A controlled, bounded calendar with an accessible narrow-layout alternative.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import '../actions/icon_button.dart';
import 'field.dart';

const List<String> _months = <String>[
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];
DateTime _day(DateTime date) => DateTime.utc(date.year, date.month, date.day);
String _dateLabel(DateTime date) =>
    '${date.day} ${_months[date.month - 1]} ${date.year}';

/// An inline single-date picker using civil dates, represented as UTC midnight.
///
/// Inputs retain their calendar year, month and day without converting an
/// instant between zones. Time-of-day is ignored. UTC storage makes calendar
/// arithmetic independent of host-zone daylight-saving transitions.
///
/// Arrow keys move the focused day, Home/End move within its week, Page Up/Down
/// change month, and Enter/Space select. Selection remains caller-owned. A
/// narrow layout uses a scrollable date list instead of shrinking hit targets.
/// Default labels are English; the host can supply all calendar labels.
class UiDatePicker extends StatefulWidget {
  /// Builds a picker bounded inclusively by [firstDate] and [lastDate].
  UiDatePicker({
    super.key,
    required this.label,
    required this.value,
    required this.firstDate,
    required this.lastDate,
    this.onChanged,
    this.initialMonth,
    this.displayedMonth,
    this.onDisplayedMonthChanged,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.firstDayOfWeek = DateTime.monday,
    this.weekdayLabels = const <String>[
      'Mon',
      'Tue',
      'Wed',
      'Thu',
      'Fri',
      'Sat',
      'Sun',
    ],
    this.monthLabelBuilder,
    this.dateLabelBuilder,
    this.previousMonthLabel = 'Previous month',
    this.nextMonthLabel = 'Next month',
    this.rangeStart,
    this.rangeEnd,
    this.currentDate,
    this.markedDates = const {},
  }) : assert(!_day(lastDate).isBefore(_day(firstDate))),
       assert(
         value == null ||
             (!_day(value).isBefore(_day(firstDate)) &&
                 !_day(value).isAfter(_day(lastDate))),
       ),
       assert(firstDayOfWeek >= 1 && firstDayOfWeek <= 7),
       assert(weekdayLabels.length == 7);

  /// Visible field name.
  final String label;

  /// Selected date; null represents no selection.
  final DateTime? value;

  /// Optional inclusive range decoration for a composed range picker.
  /// Endpoints and interior dates retain their individual keyboard targets.
  final DateTime? rangeStart;

  /// The inclusive end of the optional selected range.
  final DateTime? rangeEnd;

  /// The host-reported current day; `null` omits the today decoration.
  final DateTime? currentDate;

  /// Dates with host-reported activity, shown with a dot and accessible detail.
  final Set<DateTime> markedDates;

  /// Earliest selectable day.
  final DateTime firstDate;

  /// Latest selectable day.
  final DateTime lastDate;

  /// Receives the selected civil date as UTC midnight. Null disables the picker.
  ///
  /// This represents a calendar date, not the instant of midnight in the user's
  /// time zone. The host owns conversion if a backend needs a zoned instant.
  final ValueChanged<DateTime>? onChanged;

  /// Initially displayed month; otherwise uses [value] or today's UTC date.
  final DateTime? initialMonth;

  /// Optional host-controlled visible month, independent of selected dates.
  ///
  /// A composed range picker uses this to keep adjacent calendars coordinated.
  /// When omitted, changing [value] reveals its month as usual.
  final DateTime? displayedMonth;

  /// Proposes a visible month when navigating a controlled calendar.
  final ValueChanged<DateTime>? onDisplayedMonthChanged;

  /// Supporting instructions.
  final String? helpText;

  /// Validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// Explains disabled state.
  final String? disabledReason;

  /// First weekday, following DateTime's Monday=1 convention.
  final int firstDayOfWeek;

  /// Short weekday labels in Monday-to-Sunday order, independent of week start.
  final List<String> weekdayLabels;

  /// Localized month and year heading.
  final String Function(DateTime month)? monthLabelBuilder;

  /// Localized full date for semantics and the compact day list.
  final String Function(DateTime date)? dateLabelBuilder;

  /// Accessible name for backward month navigation.
  final String previousMonthLabel;

  /// Accessible name for forward month navigation.
  final String nextMonthLabel;

  @override
  State<UiDatePicker> createState() => _UiDatePickerState();
}

class _UiDatePickerState extends State<UiDatePicker> {
  late DateTime _focused;
  late DateTime _month;
  DateTime? _revealedMonth;
  final Map<DateTime, FocusNode> _nodes = <DateTime, FocusNode>{};
  final Map<DateTime, GlobalKey> _keys = <DateTime, GlobalKey>{};
  bool get _enabled => widget.onChanged != null;
  DateTime get _first => _day(widget.firstDate);
  DateTime get _last => _day(widget.lastDate);
  DateTime _clamp(DateTime date) {
    final DateTime civil = _day(date);
    return civil.isBefore(_first)
        ? _first
        : civil.isAfter(_last)
        ? _last
        : civil;
  }

  String _label(DateTime date) =>
      widget.dateLabelBuilder?.call(date) ?? _dateLabel(date);
  bool _available(DateTime date) =>
      !date.isBefore(_first) && !date.isAfter(_last);

  @override
  void initState() {
    super.initState();
    _focused = _clamp(
      widget.value ??
          widget.displayedMonth ??
          widget.initialMonth ??
          DateTime.now().toUtc(),
    );
    final DateTime initial = _clamp(
      widget.displayedMonth ?? widget.initialMonth ?? _focused,
    );
    _month = DateTime.utc(initial.year, initial.month);
    if (_focused.year != _month.year || _focused.month != _month.month) {
      _focused = initial;
    }
  }

  @override
  void didUpdateWidget(UiDatePicker oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.displayedMonth case final month?) {
      final visible = _clamp(month);
      final nextMonth = DateTime.utc(visible.year, visible.month);
      if (_month != nextMonth) {
        _month = nextMonth;
        if (_focused.year != _month.year || _focused.month != _month.month) {
          _focused = _clamp(
            DateTime.utc(
              _month.year,
              _month.month,
              math.min(
                _focused.day,
                DateTime.utc(_month.year, _month.month + 1, 0).day,
              ),
            ),
          );
        }
        _revealedMonth = null;
      }
      if (!_available(_focused)) _focused = _clamp(_focused);
    } else if (widget.value != oldWidget.value && widget.value != null) {
      _focused = _clamp(widget.value!);
      _month = DateTime.utc(_focused.year, _focused.month);
      _revealedMonth = null;
    } else if (!_available(_focused)) {
      _focused = _clamp(_focused);
      _month = DateTime.utc(_focused.year, _focused.month);
      _revealedMonth = null;
    }
  }

  @override
  void dispose() {
    for (final FocusNode node in _nodes.values) {
      node.dispose();
    }
    super.dispose();
  }

  FocusNode _node(DateTime date) => _nodes.putIfAbsent(date, () {
    final FocusNode node = FocusNode(debugLabel: _label(date));
    node.addListener(() {
      if (node.hasFocus && _focused != date) setState(() => _focused = date);
    });
    return node;
  });

  void _move(DateTime date, {bool focus = true}) {
    final DateTime target = _clamp(date);
    final DateTime month = DateTime.utc(target.year, target.month);
    setState(() {
      _focused = target;
      if (widget.displayedMonth == null) _month = month;
    });
    if (widget.displayedMonth != null && _month != month) {
      widget.onDisplayedMonthChanged?.call(month);
    }
    if (focus) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final node = _nodes[target];
        if (node?.context != null && node!.canRequestFocus) node.requestFocus();
        final BuildContext? dayContext = _keys[target]?.currentContext;
        if (dayContext != null) {
          final RenderObject? render = dayContext.findRenderObject();
          final ScrollableState? scroll = Scrollable.maybeOf(dayContext);
          if (render != null && scroll != null) {
            unawaited(scroll.position.ensureVisible(render, alignment: .5));
          }
        }
      });
    }
  }

  DateTime _shiftMonth(DateTime date, int offset) {
    final DateTime month = DateTime.utc(date.year, date.month + offset);
    return DateTime.utc(
      month.year,
      month.month,
      math.min(date.day, DateTime.utc(month.year, month.month + 1, 0).day),
    );
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (!_enabled ||
        (event is! KeyDownEvent && event is! KeyRepeatEvent) ||
        !_nodes.values.any((FocusNode node) => node.hasFocus)) {
      return KeyEventResult.ignored;
    }
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    final int weekday = (_focused.weekday - widget.firstDayOfWeek + 7) % 7;
    final DateTime? next = switch (event.logicalKey) {
      LogicalKeyboardKey.arrowRight => DateTime.utc(
        _focused.year,
        _focused.month,
        _focused.day + (rtl ? -1 : 1),
      ),
      LogicalKeyboardKey.arrowLeft => DateTime.utc(
        _focused.year,
        _focused.month,
        _focused.day + (rtl ? 1 : -1),
      ),
      LogicalKeyboardKey.arrowUp => DateTime.utc(
        _focused.year,
        _focused.month,
        _focused.day - 7,
      ),
      LogicalKeyboardKey.arrowDown => DateTime.utc(
        _focused.year,
        _focused.month,
        _focused.day + 7,
      ),
      LogicalKeyboardKey.home => DateTime.utc(
        _focused.year,
        _focused.month,
        _focused.day - weekday,
      ),
      LogicalKeyboardKey.end => DateTime.utc(
        _focused.year,
        _focused.month,
        _focused.day + 6 - weekday,
      ),
      LogicalKeyboardKey.pageUp => _shiftMonth(_focused, -1),
      LogicalKeyboardKey.pageDown => _shiftMonth(_focused, 1),
      _ => null,
    };
    if (next == null) return KeyEventResult.ignored;
    _move(next);
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final DateTime previous = DateTime.utc(_month.year, _month.month, 0);
    final DateTime next = DateTime.utc(_month.year, _month.month + 1);
    final int count = DateTime.utc(_month.year, _month.month + 1, 0).day;
    final int offset = (_month.weekday - widget.firstDayOfWeek + 7) % 7;
    final double cell = math.max(
      48,
      MediaQuery.textScalerOf(context).scale(ui.type.body.fontSize ?? 16) * 2 +
          ui.space.s3,
    );
    return UiFieldFrame(
      style: UiInputStyle.resolve(ui, UiFieldShape.box),
      states: <WidgetState>{
        if (!_enabled) WidgetState.disabled,
        if (widget.errorText != null) WidgetState.error,
      },
      label: widget.label,
      message: widget.errorText ?? widget.disabledReason ?? widget.helpText,
      isError: widget.errorText != null,
      child: Focus(
        canRequestFocus: false,
        onKeyEvent: _key,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: ui.color.paper,
            borderRadius: BorderRadius.circular(ui.shape.tile),
            border: Border.all(
              color: widget.errorText == null
                  ? ui.color.hairline
                  : ui.color.status.blocked.content,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.all(ui.space.s2),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Semantics(
                        header: true,
                        liveRegion: true,
                        child: Text(
                          widget.monthLabelBuilder?.call(_month) ??
                              '${_months[_month.month - 1]} ${_month.year}',
                          style: ui.type.label,
                        ),
                      ),
                    ),
                    UiIconButton(
                      icon: Directionality.of(context) == TextDirection.ltr
                          ? UiIcons.previous
                          : UiIcons.next,
                      semanticsLabel: widget.previousMonthLabel,
                      onPressed: _enabled && !previous.isBefore(_first)
                          ? () => _move(_shiftMonth(_focused, -1), focus: false)
                          : null,
                    ),
                    UiIconButton(
                      icon: Directionality.of(context) == TextDirection.ltr
                          ? UiIcons.next
                          : UiIcons.previous,
                      semanticsLabel: widget.nextMonthLabel,
                      onPressed: _enabled && !next.isAfter(_last)
                          ? () => _move(_shiftMonth(_focused, 1), focus: false)
                          : null,
                    ),
                  ],
                ),
                SizedBox(height: ui.space.s2),
                LayoutBuilder(
                  builder: (BuildContext context, BoxConstraints constraints) {
                    final bool compact = constraints.maxWidth < cell * 7;
                    if (compact) {
                      if (_revealedMonth != _month) {
                        _revealedMonth = _month;
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          if (!mounted) return;
                          final BuildContext? selectedContext =
                              _keys[_focused]?.currentContext;
                          final RenderObject? render = selectedContext
                              ?.findRenderObject();
                          final ScrollableState? scroll =
                              selectedContext == null
                              ? null
                              : Scrollable.maybeOf(selectedContext);
                          if (render != null && scroll != null) {
                            unawaited(
                              scroll.position.ensureVisible(
                                render,
                                alignment: .5,
                              ),
                            );
                          }
                        });
                      }
                      return SizedBox(
                        height: cell * 5,
                        child: SingleChildScrollView(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: <Widget>[
                              for (int i = 1; i <= count; i++)
                                _date(
                                  DateTime.utc(_month.year, _month.month, i),
                                  compact: true,
                                  cell: cell,
                                ),
                            ],
                          ),
                        ),
                      );
                    }
                    _revealedMonth = null;
                    return Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            for (int i = 0; i < 7; i++)
                              Expanded(
                                child: ExcludeSemantics(
                                  child: Center(
                                    child: Text(
                                      widget.weekdayLabels[(widget
                                                  .firstDayOfWeek -
                                              1 +
                                              i) %
                                          7],
                                      style: ui.type.labelSmall.copyWith(
                                        color: ui.color.inkSecondary,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                        SizedBox(height: ui.space.s2),
                        for (
                          int row = 0;
                          row < ((count + offset) / 7).ceil();
                          row++
                        )
                          Row(
                            children: <Widget>[
                              for (int column = 0; column < 7; column++)
                                Expanded(
                                  child:
                                      row * 7 + column < offset ||
                                          row * 7 + column >= offset + count
                                      ? SizedBox(height: cell)
                                      : _date(
                                          DateTime.utc(
                                            _month.year,
                                            _month.month,
                                            row * 7 + column - offset + 1,
                                          ),
                                          compact: false,
                                          cell: cell,
                                        ),
                                ),
                            ],
                          ),
                      ],
                    );
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _date(DateTime date, {required bool compact, required double cell}) {
    final UiThemeData ui = context.ui;
    final bool inRange =
        widget.rangeStart != null &&
        widget.rangeEnd != null &&
        !date.isBefore(_day(widget.rangeStart!)) &&
        !date.isAfter(_day(widget.rangeEnd!));
    final bool selected =
        (widget.value != null && _day(widget.value!) == date) ||
        (widget.rangeStart != null && _day(widget.rangeStart!) == date) ||
        (widget.rangeEnd != null && _day(widget.rangeEnd!) == date);
    final bool today =
        widget.currentDate != null && _day(widget.currentDate!) == date;
    final bool marked = widget.markedDates.any(
      (marked) => _day(marked) == date,
    );
    final bool enabled = _enabled && _available(date);
    final FocusNode node = _node(date)..skipTraversal = date != _focused;
    return Pressable(
      key: _keys.putIfAbsent(date, GlobalKey.new),
      focusNode: node,
      semanticsLabel:
          '${_label(date)}${inRange && !selected ? ', in selected range' : ''}${today ? ', today' : ''}${marked ? ', activity available' : ''}',
      selected: selected,
      onPressed: enabled
          ? () {
              _move(date);
              widget.onChanged!(date);
            }
          : null,
      disabledReason: _enabled ? null : widget.disabledReason,
      insetFocusRing: true,
      stateLayerColour: selected ? ui.brand.secondary.onFill : null,
      builder: (BuildContext context, Set<WidgetState> states) => Container(
        constraints: BoxConstraints(minHeight: cell),
        alignment: compact
            ? AlignmentDirectional.centerStart
            : Alignment.center,
        padding: EdgeInsets.symmetric(
          horizontal: ui.space.s2,
          vertical: ui.space.s1,
        ),
        decoration: BoxDecoration(
          color: selected || inRange ? ui.brand.secondary.fill : null,
          border: selected || today
              ? Border.all(
                  color: ui.brand.secondary.content,
                  width: selected
                      ? ui.shape.stroke.emphasis
                      : ui.shape.stroke.boundary,
                )
              : null,
          borderRadius: BorderRadius.circular(ui.shape.inner),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: compact
              ? CrossAxisAlignment.start
              : CrossAxisAlignment.center,
          children: [
            Text(
              compact ? _label(date) : '${date.day}',
              style: ui.type.body.copyWith(
                color: selected
                    ? ui.brand.secondary.onFill
                    : !enabled
                    ? ui.color.disabledContent
                    : ui.color.ink,
              ),
            ),
            if (marked) ...[
              SizedBox(height: ui.space.s1),
              Container(
                width: ui.space.s1,
                height: ui.space.s1,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: enabled
                      ? ui.brand.secondary.content
                      : ui.color.disabledContent,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
