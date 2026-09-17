/// The raw evidence escape hatch (design system, 7.3 `EvidenceDrawer`;
/// 10 section 5).
///
/// Raw JSON is never the primary rendering of anything, so it lives one
/// control away: a ghost trigger that opens a sheet on a compact window and a
/// dialog on a wider one, with the payload in `mono.code` and a copy control
/// beside its size. Closed, the payload is not in the tree at all, so a screen
/// reader user is never made to walk a thousand lines of JSON to reach the
/// next control. Open, the text keeps its own real semantics rather than one
/// synthetic label (accessibility, section 3.1).
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

  /// Pretty prints a payload the way the drawer renders it.
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

  /// A sheet on a compact window and a dialog on a wider one
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

    if (isCompactWindow(context)) {
      await UiSheet.show<void>(
        context: context,
        title: title,
        semanticsLabel: _spoken,
        dismissLabel: modalDismissLabel,
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
      body: (BuildContext modalContext) => body(modalContext, scrollable: true),
    );
  }

  void _copied(BuildContext context) {
    if (!context.mounted) return;
    UiToasts.show(context, message: copiedMessage, icon: UiIcons.copy);
  }
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
            if (hasPayload)
              UiIconButton(
                icon: UiIcons.copy,
                semanticsLabel: EvidenceDrawer.copyLabel,
                tooltip: EvidenceDrawer.copyLabel,
                onPressed: _copy,
              ),
          ],
        ),
        if (hasPayload) ...<Widget>[
          SizedBox(height: ui.space.s2),
          // Real text semantics, and a selection the reviewer can act on. No
          // synthetic label over the top.
          if (scrollable)
            Flexible(child: SingleChildScrollView(child: _code(ui)))
          else
            _code(ui),
        ],
      ],
    );
  }

  Widget _code(UiThemeData ui) => Surface(
    role: SurfaceRole.matte,
    radius: ui.shape.inner,
    padding: EdgeInsetsDirectional.all(ui.space.s3),
    child: SelectableEvidence(child: Text(text, style: ui.type.mono.code)),
  );
}
