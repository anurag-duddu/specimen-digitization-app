/// The raw evidence escape hatch (design system, 7.3 `EvidenceDrawer`;
/// 10 section 5).
///
/// Raw JSON is never the primary rendering of anything, so it lives one
/// control away: a ghost trigger that opens a sheet where the window is
/// stacked and a dialog where it is docked, with the payload in `mono.code` and a copy control
/// beside its size. Closed, the payload is not in the tree at all, so a screen
/// reader user is never made to walk a thousand lines of JSON to reach the
/// next control. Open, a bounded preview keeps its own real semantics rather
/// than one synthetic label (accessibility, section 3.1); copying always takes
/// the complete payload.
library;

import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'adaptive_form.dart';
import 'selectable_evidence.dart';

/// A trigger over a raw payload, and the modal it opens.
class EvidenceDrawer extends StatelessWidget {
  const EvidenceDrawer({
    super.key,
    required this.payload,
    this.title = defaultTitle,
    this.emptyMessage = 'No raw payload for this phase',
    this.section,
  });

  /// The label on the trigger. Kept constant across the app so the control is
  /// learned once.
  static const String defaultTitle = 'Technical detail';

  /// The label on the control that takes the payload.
  static const String copyLabel = 'Copy the raw payload';

  /// What the toast says once it has.
  static const String copiedMessage = 'Copied to the clipboard';

  /// Anything `jsonEncode` can take: a map, a list, a string, a number, null.
  final Object? payload;

  /// The trigger's label.
  final String title;

  /// What the drawer says when the server returned nothing.
  final String emptyMessage;

  /// What this payload belongs to, for the trigger's spoken name.
  ///
  /// Every drawer in the app carries the same visible word, which is correct:
  /// the control is learned once. But a history panel with a drawer per
  /// revision then announces "Technical detail" a dozen times over, and a
  /// screen reader user cannot tell one from another. The section is added to
  /// the spoken label only, so the visible word stays constant.
  final String? section;

  /// Pretty prints the complete payload used by the drawer's copy control.
  ///
  /// A payload that is not JSON encodable is shown as its `toString`, because
  /// showing the reviewer something is better than showing an exception.
  static String pretty(Object? payload) {
    if (payload == null) return '';
    try {
      return const JsonEncoder.withIndent('  ').convert(payload);
    } on JsonUnsupportedObjectError {
      return payload.toString();
    }
  }

  String get _spoken => section == null ? title : '$title, $section';

  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: UiButton(
      label: title,
      semanticsLabel: _spoken,
      variant: UiButtonVariant.ghost,
      leading: UiIcons.show,
      onPressed: () => _open(context),
    ),
  );

  /// A sheet where the window is stacked and a dialog where it is docked
  /// (10 section 5), written out rather than through
  /// `UiDialog.showAdaptive` because the two forms scroll the payload
  /// differently: the sheet scrolls its own body, and the dialog hands its
  /// body the height it has and lets this one scroll inside it. Nesting one
  /// scroll view inside the other would hand the inner one an unbounded main
  /// axis.
  Future<void> _open(BuildContext context) async {
    final String text = pretty(payload);
    Widget body(BuildContext _, {required bool scrollable}) => _Payload(
      text: text,
      emptyMessage: emptyMessage,
      scrollable: scrollable,
      // The toast host is installed by the scaffold around the page body, and
      // this modal is a route above it, so the confirmation is raised from the
      // trigger's context rather than the pane's (the queue slot met the same
      // rule).
      onCopied: () => _copied(context),
    );

    UiButton close(BuildContext modalContext) => UiButton(
      label: 'Close',
      variant: UiButtonVariant.ghost,
      onPressed: () => Navigator.of(modalContext).pop(),
    );

    if (presentsAsSheet(context)) {
      await UiSheet.show<void>(
        context: context,
        title: title,
        semanticsLabel: _spoken,
        dismissLabel: modalDismissLabel,
        secondaryAction: close,
        body: (BuildContext modalContext) =>
            body(modalContext, scrollable: false),
      );
      return;
    }
    await UiDialog.show<void>(
      context: context,
      title: title,
      semanticsLabel: _spoken,
      dismissLabel: modalDismissLabel,
      secondaryAction: close,
      body: (BuildContext modalContext) => body(modalContext, scrollable: true),
    );
  }

  void _copied(BuildContext context) {
    if (!context.mounted) return;
    UiToasts.show(context, message: copiedMessage, icon: UiIcons.copy);
  }
}

// Bound both paragraph shaping and the selectable/semantic text. A line limit
// alone does not bound a large JSON string, and a character limit alone can
// still produce thousands of very short lines. Only inspect a bounded prefix;
// never split the entire payload just to decide what can be shown.
String _preview(String text) {
  const maxCharacters = 4096;
  const maxLines = 80;
  var end = text.length < maxCharacters ? text.length : maxCharacters;
  var lines = 1;
  for (var index = 0; index < end; index++) {
    if (text.codeUnitAt(index) == 0x0a && ++lines > maxLines) {
      end = index;
      break;
    }
  }
  if (end == text.length) return text;

  // Include one complete scalar beyond the cut, then discard its grapheme.
  // A dangling high surrogate would form a separate incomplete grapheme and
  // could leave part of the preceding emoji/flag visible. This inspects at
  // most two extra code units, even for an enormous combining sequence.
  var lookahead = end + 1;
  final last = text.codeUnitAt(lookahead - 1);
  if (last >= 0xd800 && last <= 0xdbff && lookahead < text.length) {
    final next = text.codeUnitAt(lookahead);
    if (next >= 0xdc00 && next <= 0xdfff) lookahead++;
  }
  return text.substring(0, lookahead).characters.skipLast(1).toString();
}

/// The payload, its size, and the control that takes it.
class _Payload extends StatelessWidget {
  const _Payload({
    required this.text,
    required this.emptyMessage,
    required this.scrollable,
    required this.onCopied,
  });

  final String text;
  final String emptyMessage;

  /// True in the dialog form, where this pane owns the scrolling.
  final bool scrollable;

  final VoidCallback onCopied;

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: text));
    onCopied();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool hasPayload = text.isNotEmpty;
    final String preview = _preview(text);
    final bool shortened = preview.length < text.length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                hasPayload ? '${text.length} characters' : emptyMessage,
                style: ui.type.label.copyWith(color: ui.color.inkSecondary),
              ),
            ),
            if (hasPayload && !shortened)
              UiIconButton(
                icon: UiIcons.copy,
                semanticsLabel: EvidenceDrawer.copyLabel,
                tooltip: EvidenceDrawer.copyLabel,
                onPressed: _copy,
              ),
          ],
        ),
        if (hasPayload) ...<Widget>[
          if (shortened) ...<Widget>[
            SizedBox(height: ui.space.s2),
            Text(
              'Preview shortened. Copy includes the full payload.',
              style: ui.type.body.copyWith(color: ui.color.inkSecondary),
            ),
            SizedBox(height: ui.space.s2),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: 'Copy full payload',
                leading: UiIcons.copy,
                variant: UiButtonVariant.secondary,
                onPressed: _copy,
              ),
            ),
          ],
          SizedBox(height: ui.space.s2),
          // Real text semantics, and a selection the reviewer can act on. No
          // synthetic label over the top.
          if (scrollable)
            Flexible(child: SingleChildScrollView(child: _code(ui, preview)))
          else
            _code(ui, preview),
        ],
      ],
    );
  }

  Widget _code(UiThemeData ui, String preview) => Surface(
    role: SurfaceRole.matte,
    radius: ui.shape.inner,
    padding: EdgeInsetsDirectional.all(ui.space.s3),
    child: SelectableEvidence(child: Text(preview, style: ui.type.mono.code)),
  );
}
