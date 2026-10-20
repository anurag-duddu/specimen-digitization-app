/// Setting, changing and removing a monthly limit.
///
/// One form for every limit, the organization's and each collection's. It
/// asks for dollars, checks the amount before it asks the server, and says
/// what it did.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../costs.dart';
import '../../models.dart';
import '../../money.dart';

/// How the form closed, when it closed after a change.
enum CostLimitResult {
  /// A limit was set or changed.
  saved,

  /// The limit was removed.
  removed,
}

/// The words of the limit form, in one place so a test names them rather than
/// repeating them.
abstract final class CostLimitCopy {
  /// The sheet's title.
  static const String title = 'Monthly limit';

  /// The amount field.
  static const String fieldLabel = 'Limit in US dollars';

  /// What the field shows while empty.
  static const String fieldHint = '25.00';

  /// What the limit is counted against, under the field.
  static const String fieldHelp = 'Counted each month, in UTC.';

  /// The primary action, and while it runs.
  static const String save = 'Save limit';
  static const String saving = 'Saving…';

  /// The action that removes a limit, and while it runs.
  static const String remove = 'Remove limit';
  static const String removing = 'Removing…';

  /// The way out.
  static const String cancel = 'Cancel';

  /// What the form says a collection has before it is changed.
  static const String noneNow = 'No monthly limit now.';

  /// The limit a collection has before it is changed.
  static String now(int micros) => 'Now ${formatMicros(micros)} a month.';

  /// What a refused save says, with the server's reason beneath it.
  static const String notSaved = 'The limit was not saved. Retry in a moment.';

  /// What a refused removal says.
  static const String notRemoved =
      'The limit was not removed. Retry in a moment.';

  /// The sentence under the field for an amount that cannot be used.
  ///
  /// Each states the rule positively and shows the shape that works.
  static String problem(LimitInputProblem problem) => switch (problem) {
    LimitInputProblem.empty =>
      'Enter a monthly limit in US dollars, like 25.00.',
    LimitInputProblem.notAnAmount => 'Enter dollars and cents, like 25.00.',
    LimitInputProblem.tooPrecise =>
      'Use at most two decimal places, like 25.00.',
    LimitInputProblem.notAboveZero => 'Enter an amount above \$0.00.',
    LimitInputProblem.tooLarge =>
      'Enter an amount up to ${formatMicros(maxLimitDollars * microsPerDollar)}.',
  };

  /// The announcement after a change.
  static String savedFor(String subject) => 'Monthly limit saved for $subject.';
  static String removedFor(String subject) =>
      'Monthly limit removed for $subject.';
}

/// The body of the limit sheet.
///
/// [apply] sends the change: an amount in micro-dollars, or null to remove the
/// limit. It throws an [ApiFailure] when the server refuses, and the form
/// stays open with the reason, so what was typed is not lost.
class CostLimitForm extends StatefulWidget {
  const CostLimitForm({
    super.key,
    required this.subject,
    required this.current,
    required this.apply,
  });

  /// Whose limit this is: the organization, or a collection's name.
  final String subject;

  /// The limit in force, or null for none.
  final CostLimit? current;

  /// Sends the change to the server.
  final Future<void> Function(int? micros) apply;

  @override
  State<CostLimitForm> createState() => _CostLimitFormState();
}

class _CostLimitFormState extends State<CostLimitForm> {
  late final TextEditingController _text = TextEditingController(
    text: widget.current == null
        ? ''
        : limitFieldText(widget.current!.monthlyMicros),
  );
  final FocusNode _focus = FocusNode(debugLabel: 'monthly limit');
  LimitInputProblem? _problem;
  ApiFailure? _failure;

  /// The change in flight, or null when nothing is.
  CostLimitResult? _busy;

  /// The change the server last refused, so the reason names the right one.
  CostLimitResult? _refused;

  @override
  void initState() {
    super.initState();
    _focus.addListener(_blurred);
  }

  @override
  void dispose() {
    _focus
      ..removeListener(_blurred)
      ..dispose();
    _text.dispose();
    super.dispose();
  }

  /// Checks what was typed when the field loses focus, never on every
  /// keystroke (02 section 4.10). An empty field has not been answered yet,
  /// so leaving it is not an error.
  void _blurred() {
    if (_focus.hasFocus || _busy != null) return;
    if (_text.text.trim().isEmpty) return;
    setState(() => _problem = parseLimitInput(_text.text).problem);
  }

  Future<void> _save() async {
    if (_busy != null) return;
    final LimitInput input = parseLimitInput(_text.text);
    if (input.micros == null) {
      setState(() => _problem = input.problem);
      _focus.requestFocus();
      return;
    }
    await _run(input.micros, CostLimitResult.saved);
  }

  Future<void> _remove() => _run(null, CostLimitResult.removed);

  Future<void> _run(int? micros, CostLimitResult outcome) async {
    if (_busy != null) return;
    setState(() {
      _busy = outcome;
      _refused = null;
      _failure = null;
      _problem = null;
    });
    try {
      await widget.apply(micros);
      if (mounted) Navigator.of(context).pop(outcome);
    } on ApiFailure catch (failure) {
      if (mounted) {
        setState(() {
          _busy = null;
          _refused = outcome;
          _failure = failure;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final CostLimit? current = widget.current;
    final LimitInputProblem? problem = _problem;
    final ApiFailure? failure = _failure;
    final bool saving = _busy == CostLimitResult.saved;
    final bool removing = _busy == CostLimitResult.removed;
    return PopScope<CostLimitResult?>(
      // Nothing closes the sheet while a change is on its way: the answer
      // decides whether it was made.
      canPop: _busy == null,
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              widget.subject,
              style: ui.type.title.copyWith(color: ui.color.ink),
            ),
            SizedBox(height: ui.space.s1),
            Text(
              current == null
                  ? CostLimitCopy.noneNow
                  : CostLimitCopy.now(current.monthlyMicros),
              style: ui.type.body.copyWith(color: ui.color.inkSecondary),
            ),
            SizedBox(height: ui.space.s4),
            UiField(
              label: CostLimitCopy.fieldLabel,
              hintText: CostLimitCopy.fieldHint,
              helpText: CostLimitCopy.fieldHelp,
              errorText: problem == null
                  ? null
                  : CostLimitCopy.problem(problem),
              controller: _text,
              focusNode: _focus,
              autofocus: true,
              enabled: _busy == null,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              textInputAction: TextInputAction.done,
              inputFormatters: <TextInputFormatter>[
                FilteringTextInputFormatter.allow(RegExp(r'[0-9.,$\s]')),
              ],
              onChanged: (String _) {
                if (_problem != null || _failure != null) {
                  setState(() {
                    _problem = null;
                    _failure = null;
                  });
                }
              },
              onSubmitted: (String _) => _save(),
            ),
            if (failure != null) ...<Widget>[
              SizedBox(height: ui.space.s4),
              Announcer(
                child: UiBanner(
                  message: _refused == CostLimitResult.removed
                      ? CostLimitCopy.notRemoved
                      : CostLimitCopy.notSaved,
                  detail: failure.message,
                  tone: UiBannerTone.blocked,
                ),
              ),
            ],
            SizedBox(height: ui.space.s6),
            UiButtonRow(
              primary: UiButton(
                label: CostLimitCopy.save,
                // A glyph at rest, so the slot the busy mark takes is not an
                // empty gap beside the label.
                leading: UiIcons.check,
                busyLabel: CostLimitCopy.saving,
                loading: saving,
                onPressed: _busy == null ? _save : null,
              ),
              secondary: UiButton(
                label: CostLimitCopy.cancel,
                variant: UiButtonVariant.ghost,
                onPressed: _busy == null
                    ? () => Navigator.of(context).pop()
                    : null,
              ),
              tertiary: <UiButton>[
                if (current != null)
                  UiButton(
                    label: CostLimitCopy.remove,
                    leading: UiIcons.remove,
                    busyLabel: CostLimitCopy.removing,
                    variant: UiButtonVariant.ghost,
                    loading: removing,
                    onPressed: _busy == null ? _remove : null,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
