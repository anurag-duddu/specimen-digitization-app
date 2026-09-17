/// The reason sheet (design system, 7.3 `ReasonSheet`; UX writing, 4.4, 4.5;
/// 10 section 5).
///
/// Every consequence is visible before the commit. The sheet states what the
/// action will do, what survives it, what is still outstanding, and it will
/// not commit without a reason. Typed text is never thrown away by an
/// accidental tap on the scrim.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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
/// [configuredReasons] are the collection's or the profile's own decision
/// reasons, offered first because a collection that publishes a vocabulary
/// means its reviewers to use it. [recordReasons] are the machine's reasons
/// this record is in the queue, offered under their own heading so nothing
/// implies a reviewer wrote them (pass criterion 7.6).
///
/// [reversal] names the way back, where the server exposes one. The review
/// API exposes none: a decision is recorded against a version and superseded
/// by the next one rather than removed, so the sheet states that instead of
/// offering an Undo it could not honour (pass criterion 3.4).
///
/// A sheet on a compact window and a dialog on a wider one, through
/// `showAdaptiveModal`: the form owns its own scroll view, because the dialog
/// form has none of its own and a sheet that also scrolled would nest one
/// inside the other.
Future<String?> showReasonSheet(
  BuildContext context, {
  required String title,
  required String action,
  required String consequence,
  String? retained,
  String? reversal,
  List<String> outstanding = const <String>[],
  List<String> configuredReasons = const <String>[],
  List<String> recordReasons = const <String>[],
  List<String> recentReasons = const <String>[],
}) {
  Widget body(BuildContext _) => ReasonForm(
    title: title,
    action: action,
    consequence: consequence,
    retained: retained,
    reversal: reversal,
    outstanding: outstanding,
    configuredReasons: configuredReasons,
    recordReasons: recordReasons,
    recentReasons: recentReasons,
    // The sheet and the dialog draw the title themselves, as a header node.
    showTitle: false,
  );

  return showAdaptiveModal<String>(context, title: title, body: body);
}

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
    this.configuredReasons = const <String>[],
    this.recordReasons = const <String>[],
    this.recentReasons = const <String>[],
    this.showTitle = true,
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

  /// Decision reasons the collection or the profile published.
  final List<String> configuredReasons;

  /// The machine's reasons this record is in the review queue.
  final List<String> recordReasons;

  /// Reasons this reviewer typed before, newest first.
  final List<String> recentReasons;

  /// False when a modal frame above this one already draws [title].
  final bool showTitle;

  /// The heading over each group of chips, fixed so the sheet and its tests
  /// cannot word them differently.
  static const String configuredHeading = 'Reasons for this collection';
  static const String recordHeading = 'Why this record is in review';
  static const String recentHeading = 'Recent reasons';

  /// The heading over the findings the action does not resolve.
  static const String outstandingHeading = 'Still outstanding';

  /// The field's own name and the sentence under it.
  static const String reasonLabel = 'Reason';
  static const String reasonHelp = 'Recorded on the decision. Required.';

  /// Why the primary action is unavailable before anything is typed.
  static const String reasonRequiredHint = 'Type a reason first';

  /// The way out of the sheet.
  static const String cancelLabel = 'Cancel';

  /// What a chip does when it is pressed.
  static const String useReasonLabel = 'Use this reason';

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
        await UiDialog.show<bool>(
          context: context,
          title: 'Discard this reason?',
          semanticsLabel: 'Discard this reason?',
          dismissLabel: modalDismissLabel,
          body: (BuildContext _) =>
              const Text('The text you typed is not saved anywhere.'),
          primaryAction: (BuildContext confirmContext) => UiButton(
            label: 'Discard the reason',
            onPressed: () => Navigator.of(confirmContext).pop(true),
          ),
          secondaryAction: (BuildContext confirmContext) => UiButton(
            label: 'Keep editing',
            variant: UiButtonVariant.ghost,
            onPressed: () => Navigator.of(confirmContext).pop(false),
          ),
        ) ??
        false;
    if (discard && navigator.mounted) navigator.pop();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;

    return PopScope<String?>(
      // Once there is text, the scrim, the drag handle and the system back
      // gesture all route through the confirmation instead of discarding.
      canPop: !_hasText,
      onPopInvokedWithResult: (bool didPop, String? result) {
        if (didPop) return;
        _handleDismissAttempt();
      },
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (widget.showTitle) ...<Widget>[
              Semantics(
                container: true,
                header: true,
                child: Text(widget.title, style: ui.type.titleLarge),
              ),
              SizedBox(height: ui.space.s2),
            ],
            Text(widget.consequence, style: ui.type.body),
            SizedBox(height: ui.space.s2),
            Text(widget.reversal ?? ReasonForm.finality, style: ui.type.label),
            if (widget.retained != null) ...<Widget>[
              SizedBox(height: ui.space.s2),
              Text(
                widget.retained!,
                style: ui.type.body.copyWith(color: ui.color.inkSecondary),
              ),
            ],
            if (widget.outstanding.isNotEmpty) ...<Widget>[
              SizedBox(height: ui.space.s4),
              Text(ReasonForm.outstandingHeading, style: ui.type.label),
              SizedBox(height: ui.space.s1),
              for (final String finding in widget.outstanding)
                Padding(
                  padding: EdgeInsetsDirectional.only(bottom: ui.space.s1),
                  child: Text(
                    finding,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ),
            ],
            ..._chipGroup(
              ui,
              ReasonForm.configuredHeading,
              widget.configuredReasons,
            ),
            ..._chipGroup(ui, ReasonForm.recordHeading, widget.recordReasons),
            ..._chipGroup(ui, ReasonForm.recentHeading, widget.recentReasons),
            SizedBox(height: ui.space.s4),
            UiTextArea(
              label: ReasonForm.reasonLabel,
              helpText: ReasonForm.reasonHelp,
              controller: _reason,
              focusNode: _field,
              autofocus: true,
              minLines: _reasonMinLines,
              maxLines: _reasonMaxLines,
              onChanged: (String _) => setState(() {}),
            ),
            SizedBox(height: ui.space.s6),
            UiButtonRow(
              primary: UiButton(
                label: widget.action,
                disabledReason: ReasonForm.reasonRequiredHint,
                onPressed: _hasText
                    ? () => Navigator.of(context).pop(_reason.text.trim())
                    : null,
              ),
              secondary: UiButton(
                label: ReasonForm.cancelLabel,
                variant: UiButtonVariant.ghost,
                onPressed: () => Navigator.of(context).pop(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// One headed row of chips, each of which fills the field.
  ///
  /// Empty for an empty list, so a collection that publishes no vocabulary
  /// gets no heading promising one.
  List<Widget> _chipGroup(
    UiThemeData ui,
    String heading,
    List<String> reasons,
  ) {
    if (reasons.isEmpty) return const <Widget>[];
    return <Widget>[
      SizedBox(height: ui.space.s4),
      Text(heading, style: ui.type.label),
      SizedBox(height: ui.space.s1),
      Wrap(
        spacing: ui.space.s2,
        runSpacing: ui.space.s2,
        children: <Widget>[
          for (final String reason in reasons)
            UiChip(
              label: reason,
              // The only chip in the system that can be pressed. It publishes
              // a toggle rather than a button, which is recorded in the slot
              // closeout as the action chip the actions family does not have.
              variant: UiChipVariant.filter,
              semanticsLabel: '${ReasonForm.useReasonLabel}: $reason',
              onPressed: () => _fill(reason),
            ),
        ],
      ),
    ];
  }

  void _fill(String reason) {
    setState(() {
      _reason.text = reason;
      _reason.selection = TextSelection.collapsed(offset: reason.length);
    });
    _field.requestFocus();
  }

  static const int _reasonMinLines = 2;
  static const int _reasonMaxLines = 5;
}
