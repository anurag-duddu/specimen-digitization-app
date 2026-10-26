/// Civil date ranges with optional transaction controls and named presets.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart';
import '../overlays/dialog.dart';
import 'date_picker.dart';
import 'field.dart';

DateTime _civil(DateTime value) =>
    DateTime.utc(value.year, value.month, value.day);

/// Inclusive civil dates. Values are normalized to UTC midnight, not converted
/// from a time-zone instant. A same-day range is valid.
@immutable
class UiDateRange {
  /// Creates the component with explicit caller-owned configuration.
  UiDateRange(DateTime start, DateTime end)
    : start = _civil(start),
      end = _civil(end),
      assert(!_civil(end).isBefore(_civil(start)));

  /// The inclusive lower bound.
  final DateTime start;

  /// The inclusive upper bound.
  final DateTime end;
  @override
  bool operator ==(Object other) =>
      other is UiDateRange && other.start == start && other.end == end;
  @override
  int get hashCode => Object.hash(start, end);
}

/// A named range offered as a quick selection.
@immutable
class UiDateRangePreset {
  /// Creates the component with explicit caller-owned configuration.
  const UiDateRangePreset({required this.label, required this.range});

  /// The visible and accessible name of the control.
  final String label;

  /// The complete range proposed by this preset.
  final UiDateRange range;
}

/// Select a start, then an end. Reversed selection is normalized deliberately.
///
/// With [showActions], changes remain a draft until Apply. Cancel restores the
/// caller's range. Without actions the complete range is reported immediately.
/// Calendar navigation, dates and presets remain bounded by [firstDate]/[lastDate].
class UiDateRangePicker extends StatefulWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiDateRangePicker({
    super.key,
    required this.label,
    required this.value,
    required this.firstDate,
    required this.lastDate,
    this.onChanged,
    this.presets = const <UiDateRangePreset>[],
    this.showActions = false,
    this.onCancel,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.applyLabel = 'Apply dates',
    this.cancelLabel = 'Cancel',
    this.dateLabelBuilder,
    this.dualCalendar = true,
    this.currentDate,
    this.markedDates = const {},
    this.showDateInputs = true,
    this.startDateLabel = 'Start date',
    this.endDateLabel = 'End date',
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The current value accepted by the host.
  final UiDateRange? value;

  /// The earliest selectable calendar date, inclusive.
  final DateTime firstDate;

  /// The latest selectable calendar date, inclusive.
  final DateTime lastDate;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<UiDateRange>? onChanged;

  /// The optional named ranges; out-of-bounds presets stay unavailable.
  final List<UiDateRangePreset> presets;

  /// Whether edits remain a draft until the user chooses Apply.
  final bool showActions;

  /// The callback after restoring the accepted value and cancelling a draft.
  final VoidCallback? onCancel;

  /// The persistent supporting instruction beneath the control.
  final String? helpText;

  /// The validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  /// The label of the action committing the complete draft.
  final String applyLabel;

  /// The label of the action discarding the draft.
  final String cancelLabel;

  /// The optional localized description of a calendar date.
  final String Function(DateTime)? dateLabelBuilder;

  /// Whether adjacent calendars appear when the available width permits.
  final bool dualCalendar;

  /// The host-reported current day; `null` omits today decoration.
  final DateTime? currentDate;

  /// Dates with explicit host-reported activity.
  final Set<DateTime> markedDates;

  /// Whether editable YYYY-MM-DD endpoints accompany the calendars.
  final bool showDateInputs;

  /// The visible and accessible lower-endpoint editor label.
  final String startDateLabel;

  /// The visible and accessible upper-endpoint editor label.
  final String endDateLabel;
  @override
  State<UiDateRangePicker> createState() => _UiDateRangePickerState();
}

class _UiDateRangePickerState extends State<UiDateRangePicker> {
  DateTime? _anchor;
  UiDateRange? _draft;
  late DateTime _visibleMonth;
  final _startInput = TextEditingController();
  final _endInput = TextEditingController();
  String? _startError;
  String? _endError;
  bool _typing = false;
  bool _showInputErrors = false;

  DateTime _monthWithinBounds(DateTime date) {
    final first = DateTime.utc(widget.firstDate.year, widget.firstDate.month);
    final last = DateTime.utc(widget.lastDate.year, widget.lastDate.month);
    final month = DateTime.utc(date.year, date.month);
    return month.isBefore(first)
        ? first
        : month.isAfter(last)
        ? last
        : month;
  }

  void _revealRange(UiDateRange? range) {
    _visibleMonth = _monthWithinBounds(range?.start ?? widget.firstDate);
  }

  String _iso(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  void _syncInputs() {
    _typing = false;
    _showInputErrors = false;
    _startError = null;
    _endError = null;
    _startInput.text = _anchor != null
        ? _iso(_anchor!)
        : _draft == null
        ? ''
        : _iso(_draft!.start);
    _endInput.text = _draft == null ? '' : _iso(_draft!.end);
  }

  DateTime? _parseInput(String raw) {
    final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(raw.trim());
    if (match == null) return null;
    final year = int.parse(match[1]!);
    final month = int.parse(match[2]!);
    final day = int.parse(match[3]!);
    final date = DateTime.utc(year, month, day);
    return date.year == year && date.month == month && date.day == day
        ? date
        : null;
  }

  String? _dateError(String raw, DateTime? date) {
    if (raw.trim().isEmpty) return 'Enter a date in YYYY-MM-DD format.';
    if (date == null) return 'Enter a valid date in YYYY-MM-DD format.';
    if (date.isBefore(_civil(widget.firstDate)) ||
        date.isAfter(_civil(widget.lastDate))) {
      return 'Choose a date from ${_iso(widget.firstDate)} to ${_iso(widget.lastDate)}.';
    }
    return null;
  }

  void _typedChanged({bool showErrors = false}) {
    if (!mounted || widget.onChanged == null) return;
    final previousDraft = _draft;
    final start = _parseInput(_startInput.text);
    final end = _parseInput(_endInput.text);
    final startError = _dateError(_startInput.text, start);
    var endError = _dateError(_endInput.text, end);
    if (startError == null && endError == null && end!.isBefore(start!)) {
      endError = 'The end date must be on or after the start date.';
    }
    final next = startError == null && endError == null
        ? UiDateRange(start!, end!)
        : null;
    setState(() {
      _typing = true;
      _anchor = null;
      _draft = next;
      if (next != null) _revealRange(next);
      _showInputErrors = _showInputErrors || showErrors;
      _startError = _showInputErrors ? startError : null;
      _endError = _showInputErrors ? endError : null;
    });
    if (!widget.showActions &&
        next != null &&
        next != previousDraft &&
        next != widget.value) {
      widget.onChanged!(next);
    }
  }

  @override
  void dispose() {
    _startInput.dispose();
    _endInput.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _draft = widget.value;
    _revealRange(_draft);
    _syncInputs();
  }

  @override
  void didUpdateWidget(UiDateRangePicker oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.value != widget.value ||
        oldWidget.firstDate != widget.firstDate ||
        oldWidget.lastDate != widget.lastDate) {
      _draft = widget.value;
      _anchor = null;
      _revealRange(_draft);
      _syncInputs();
    }
  }

  bool _allowed(UiDateRange range) =>
      !range.start.isBefore(_civil(widget.firstDate)) &&
      !range.end.isAfter(_civil(widget.lastDate));
  void _pick(DateTime day) {
    if (widget.onChanged == null) return;
    if (_anchor == null) {
      setState(() {
        _anchor = day;
        _draft = null;
        _syncInputs();
      });
      return;
    }
    final start = _anchor!;
    final range = day.isBefore(start)
        ? UiDateRange(day, start)
        : UiDateRange(start, day);
    setState(() {
      _draft = range;
      _anchor = null;
      _syncInputs();
    });
    if (!widget.showActions) widget.onChanged!(range);
  }

  String _date(DateTime date) =>
      widget.dateLabelBuilder?.call(date) ??
      '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  @override
  Widget build(BuildContext context) {
    assert(!_civil(widget.lastDate).isBefore(_civil(widget.firstDate)));
    assert(widget.value == null || _allowed(widget.value!));
    final ui = context.ui;
    final start = _anchor ?? _draft?.start;
    final end = _draft?.end;
    final nextMonth = DateTime.utc(_visibleMonth.year, _visibleMonth.month + 1);
    Widget calendar(String label, DateTime month, {bool following = false}) =>
        UiDatePicker(
          label: label,
          value: null,
          firstDate: widget.firstDate,
          lastDate: widget.lastDate,
          displayedMonth: month,
          onDisplayedMonthChanged: (next) => setState(() {
            _visibleMonth = _monthWithinBounds(
              following ? DateTime.utc(next.year, next.month - 1) : next,
            );
          }),
          rangeStart: start,
          rangeEnd: end,
          currentDate: widget.currentDate,
          markedDates: widget.markedDates,
          dateLabelBuilder: widget.dateLabelBuilder,
          onChanged: widget.onChanged == null ? null : _pick,
          disabledReason: widget.disabledReason,
        );
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(widget.label, style: ui.type.label),
        SizedBox(height: ui.space.s2),
        if (widget.presets.isNotEmpty) ...<Widget>[
          Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s2,
            children: <Widget>[
              for (final preset in widget.presets)
                UiButton(
                  label: preset.label,
                  variant: UiButtonVariant.secondary,
                  onPressed: widget.onChanged == null || !_allowed(preset.range)
                      ? null
                      : () {
                          setState(() {
                            _anchor = null;
                            _draft = preset.range;
                            _revealRange(_draft);
                            _syncInputs();
                          });
                          if (!widget.showActions) {
                            widget.onChanged!(preset.range);
                          }
                        },
                  disabledReason: !_allowed(preset.range)
                      ? 'Outside the available date range.'
                      : widget.disabledReason,
                ),
            ],
          ),
          SizedBox(height: ui.space.s3),
        ],
        Semantics(
          liveRegion: true,
          child: Text(
            _anchor != null
                ? 'Start ${_date(_anchor!)}. Choose the end date.'
                : _draft == null
                ? 'Choose the start date.'
                : '${_date(_draft!.start)} to ${_date(_draft!.end)}',
            style: ui.type.bodySmall,
          ),
        ),
        SizedBox(height: ui.space.s3),
        LayoutBuilder(
          builder: (context, constraints) {
            final dual =
                widget.dualCalendar &&
                constraints.maxWidth >= 800 &&
                !nextMonth.isAfter(_civil(widget.lastDate));
            return dual
                ? Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Expanded(
                        child: calendar('Start or end date', _visibleMonth),
                      ),
                      SizedBox(width: ui.space.s4),
                      Expanded(
                        child: calendar(
                          'Following month',
                          nextMonth,
                          following: true,
                        ),
                      ),
                    ],
                  )
                : calendar('Start or end date', _visibleMonth);
          },
        ),
        if (widget.showDateInputs) ...[
          SizedBox(height: ui.space.s3),
          LayoutBuilder(
            builder: (context, constraints) {
              Widget input(bool start) => Focus(
                canRequestFocus: false,
                onFocusChange: (focused) {
                  if (!focused && _typing) _typedChanged(showErrors: true);
                },
                child: UiField(
                  label: start ? widget.startDateLabel : widget.endDateLabel,
                  controller: start ? _startInput : _endInput,
                  hintText: 'YYYY-MM-DD',
                  helpText: 'YYYY-MM-DD',
                  errorText: start ? _startError : _endError,
                  enabled: widget.onChanged != null,
                  disabledReason: widget.disabledReason,
                  keyboardType: TextInputType.datetime,
                  autocorrect: false,
                  textInputAction: start
                      ? TextInputAction.next
                      : TextInputAction.done,
                  onChanged: (_) => _typedChanged(),
                  onSubmitted: (_) => _typedChanged(showErrors: true),
                ),
              );
              if (constraints.maxWidth < 560 ||
                  MediaQuery.textScalerOf(context).scale(16) > 24) {
                return Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    input(true),
                    SizedBox(height: ui.space.s3),
                    input(false),
                  ],
                );
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: input(true)),
                  SizedBox(width: ui.space.s3),
                  Expanded(child: input(false)),
                ],
              );
            },
          ),
        ],
        if (widget.errorText ?? widget.disabledReason ?? widget.helpText
            case final message?) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Text(
            message,
            style: ui.type.bodySmall.copyWith(
              color: widget.errorText == null
                  ? ui.color.inkSecondary
                  : ui.color.status.blocked.content,
            ),
          ),
        ],
        if (widget.showActions) ...<Widget>[
          SizedBox(height: ui.space.s3),
          Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s2,
            children: <Widget>[
              UiButton(
                label: widget.cancelLabel,
                variant: UiButtonVariant.secondary,
                onPressed: () {
                  setState(() {
                    _draft = widget.value;
                    _anchor = null;
                    _revealRange(_draft);
                    _syncInputs();
                  });
                  widget.onCancel?.call();
                },
              ),
              UiButton(
                label: widget.applyLabel,
                onPressed:
                    widget.onChanged == null ||
                        _draft == null ||
                        _anchor != null ||
                        !_allowed(_draft!)
                    ? null
                    : () => widget.onChanged!(_draft!),
                disabledReason:
                    widget.disabledReason ?? 'Choose both dates first.',
              ),
            ],
          ),
        ],
      ],
    );
  }
}

/// A date-range trigger presenting an accessible dialog or mobile sheet.
class UiDateRangeField extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiDateRangeField({
    super.key,
    required this.label,
    required this.value,
    required this.firstDate,
    required this.lastDate,
    this.onChanged,
    this.presets = const <UiDateRangePreset>[],
    this.disabledReason,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The current value accepted by the host.
  final UiDateRange? value;

  /// The earliest selectable calendar date, inclusive.
  final DateTime firstDate;

  /// The latest selectable calendar date, inclusive.
  final DateTime lastDate;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<UiDateRange>? onChanged;

  /// The optional named ranges; out-of-bounds presets stay unavailable.
  final List<UiDateRangePreset> presets;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;
  @override
  Widget build(BuildContext context) => UiButton(
    label: value == null
        ? label
        : '$label: ${value!.start.toIso8601String().substring(0, 10)} to ${value!.end.toIso8601String().substring(0, 10)}',
    variant: UiButtonVariant.secondary,
    disabledReason: disabledReason,
    onPressed: onChanged == null
        ? null
        : () async {
            final selected = await UiDialog.showAdaptive<UiDateRange>(
              context: context,
              title: label,
              body: (dialogContext) => UiDateRangePicker(
                label: label,
                value: value,
                firstDate: firstDate,
                lastDate: lastDate,
                presets: presets,
                showActions: true,
                onChanged: (range) => Navigator.of(dialogContext).pop(range),
                onCancel: () => Navigator.of(dialogContext).pop(),
              ),
            );
            if (selected != null) onChanged!(selected);
          },
  );
}
