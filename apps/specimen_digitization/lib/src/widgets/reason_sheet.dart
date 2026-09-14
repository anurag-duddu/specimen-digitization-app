/// The reason sheet (design system, 7.3 `ReasonSheet`; UX writing, 4.4, 4.5).
///
/// Every consequence is visible before the commit. The sheet states what the
/// action will do, what survives it, what is still outstanding, and it will
/// not commit without a reason. Typed text is never thrown away by an
/// accidental tap on the scrim.
library;

import 'package:flutter/material.dart';

import '../theme/icons.dart';
import 'adaptive_form.dart';

/// Collects a reason for one consequential action.
///
/// Returns the trimmed reason, or null when the reviewer backed out.
///
/// [title] names the action as a question or a phrase, [action] is the verb
/// phrase on the primary button, [consequence] is one neutral sentence saying
/// what will change, [retained] is one sentence saying what survives, and
/// [outstanding] lists the findings the action does not resolve.
/// [recentReasons] are offered as chips that fill the field.
///
/// [reversal] names the way back, where the server exposes one. The review
/// API exposes none: a decision is recorded against a version and superseded
/// by the next one rather than removed, so the sheet states that instead of
/// offering an Undo it could not honour (pass criterion 3.4).
Future<String?> showReasonSheet(
  BuildContext context, {
  required String title,
  required String action,
  required String consequence,
  String? retained,
  String? reversal,
  List<String> outstanding = const <String>[],
  List<String> recentReasons = const <String>[],
}) => showAdaptiveForm<String>(
  context,
  width: DialogWidths.standard,
  builder: (BuildContext formContext) => ReasonForm(
    title: title,
    action: action,
    consequence: consequence,
    retained: retained,
    reversal: reversal,
    outstanding: outstanding,
    recentReasons: recentReasons,
  ),
);

/// The body of [showReasonSheet]. Exposed so it can be tested and previewed
/// without driving a route.
class ReasonForm extends StatefulWidget {
  const ReasonForm({
    super.key,
    required this.title,
    required this.action,
    required this.consequence,
    this.retained,
    this.reversal,
    this.outstanding = const <String>[],
    this.recentReasons = const <String>[],
  });

  final String title;
  final String action;
  final String consequence;
  final String? retained;

  /// How the action is taken back, when the server exposes a way.
  ///
  /// Null means there is none, and the sheet says so with [finality]. One of
  /// the two is always on screen before the confirm button, which is what
  /// pass criterion 3.4 asks for.
  final String? reversal;

  final List<String> outstanding;
  final List<String> recentReasons;

  /// The sentence every decision without a reversal carries.
  ///
  /// Fixed here rather than written out at each call site, so no sheet can
  /// ship without it and no two sheets can word it differently.
  static const String finality =
      'This cannot be undone. The decision is recorded on this version and '
      'is superseded by a later one, never removed.';

  @override
  State<ReasonForm> createState() => _ReasonFormState();
}

class _ReasonFormState extends State<ReasonForm> {
  final TextEditingController _reason = TextEditingController();
  final FocusNode _field = FocusNode(debugLabel: 'reason');

  @override
  void dispose() {
    _reason.dispose();
    _field.dispose();
    super.dispose();
  }

  bool get _hasText => _reason.text.trim().isNotEmpty;

  Future<void> _handleDismissAttempt() async {
    final NavigatorState navigator = Navigator.of(context);
    final bool discard =
        await showDialog<bool>(
          context: context,
          builder: (BuildContext confirmContext) => AlertDialog(
            title: const Text('Discard this reason?'),
            content: const Text('The text you typed is not saved anywhere.'),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.of(confirmContext).pop(false),
                child: const Text('Keep editing'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(confirmContext).pop(true),
                child: const Text('Discard the reason'),
              ),
            ],
          ),
        ) ??
        false;
    if (discard && navigator.mounted) navigator.pop();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    return PopScope<String?>(
      // Once there is text, the scrim, the drag handle and the system back
      // gesture all route through the confirmation instead of discarding.
      canPop: !_hasText,
      onPopInvokedWithResult: (bool didPop, String? result) {
        if (didPop) return;
        _handleDismissAttempt();
      },
      child: SafeArea(
        child: SingleChildScrollView(
          padding: EdgeInsets.all(context.space.space6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(widget.title, style: theme.textTheme.titleLarge),
              SizedBox(height: context.space.space2),
              Text(widget.consequence, style: theme.textTheme.bodyMedium),
              SizedBox(height: context.space.space2),
              Text(
                widget.reversal ?? ReasonForm.finality,
                style: theme.textTheme.titleSmall,
              ),
              if (widget.retained != null) ...<Widget>[
                SizedBox(height: context.space.space2),
                Text(
                  widget.retained!,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
              if (widget.outstanding.isNotEmpty) ...<Widget>[
                SizedBox(height: context.space.space4),
                Text('Still outstanding', style: theme.textTheme.titleSmall),
                SizedBox(height: context.space.space1),
                for (final String finding in widget.outstanding)
                  Padding(
                    padding: EdgeInsets.only(bottom: context.space.space1),
                    child: Text(
                      finding,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
              ],
              if (widget.recentReasons.isNotEmpty) ...<Widget>[
                SizedBox(height: context.space.space4),
                Text('Recent reasons', style: theme.textTheme.titleSmall),
                SizedBox(height: context.space.space1),
                Wrap(
                  spacing: context.space.space2,
                  runSpacing: context.space.space2,
                  children: <Widget>[
                    for (final String recent in widget.recentReasons)
                      ActionChip(
                        label: Text(recent),
                        tooltip: 'Use this reason',
                        onPressed: () {
                          setState(() {
                            _reason.text = recent;
                            _reason.selection = TextSelection.collapsed(
                              offset: recent.length,
                            );
                          });
                          _field.requestFocus();
                        },
                      ),
                  ],
                ),
              ],
              SizedBox(height: context.space.space4),
              TextField(
                controller: _reason,
                focusNode: _field,
                autofocus: true,
                minLines: _reasonMinLines,
                maxLines: _reasonMaxLines,
                onChanged: (String _) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Reason',
                  helperText: 'Recorded on the decision. Required.',
                ),
              ),
              SizedBox(height: context.space.space6),
              Wrap(
                alignment: WrapAlignment.end,
                spacing: context.space.space2,
                runSpacing: context.space.space2,
                children: <Widget>[
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  Semantics(
                    hint: _hasText ? '' : 'Type a reason first',
                    child: FilledButton(
                      onPressed: _hasText
                          ? () => Navigator.of(context).pop(_reason.text.trim())
                          : null,
                      child: Text(widget.action),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  static const int _reasonMinLines = 2;
  static const int _reasonMaxLines = 5;
}
