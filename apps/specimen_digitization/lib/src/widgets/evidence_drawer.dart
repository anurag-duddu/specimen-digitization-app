/// The raw evidence escape hatch (design system, 7.3 `EvidenceDrawer`).
///
/// Closed by default, labelled "Technical detail", and holding pretty printed
/// JSON in the `mono.code` role on `surfaceContainerHighest` with a copy
/// control. While it is closed the payload is not in the semantics tree at
/// all, so a screen reader user is not made to walk a thousand lines of JSON
/// to reach the next control. While it is open the text exposes its own real
/// semantics rather than one synthetic label (accessibility, section 3.1).
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import '../theme/motion.dart';

/// A closed by default disclosure over a raw payload.
class EvidenceDrawer extends StatefulWidget {
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

  @override
  State<EvidenceDrawer> createState() => _EvidenceDrawerState();
}

class _EvidenceDrawerState extends State<EvidenceDrawer> {
  bool _open = false;

  Future<void> _copy(String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(const SnackBar(content: Text('Copied to the clipboard')));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final MotionTokens motion = context.motion;
    final String text = EvidenceDrawer.pretty(widget.payload);
    final bool hasPayload = text.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        MergeSemantics(
          child: Semantics(
            expanded: _open,
            label: widget.section == null
                ? null
                : '${widget.title}, ${widget.section}',
            child: TextButton.icon(
              onPressed: () => setState(() => _open = !_open),
              icon: AnimatedRotation(
                turns: _open ? _halfTurn : 0,
                duration: motion.quick,
                curve: MotionTokens.standardCurve,
                child: Icon(
                  Symbols.expand_more,
                  size: context.sizes.iconInline,
                ),
              ),
              label: Text(widget.title),
            ),
          ),
        ),
        // `AnimatedSize` with a zero duration re-dirties itself during its
        // own layout, so under reduced motion the drawer opens directly.
        _maybeAnimated(
          motion,
          !_open
              // Closed: nothing of the payload reaches the tree, not even a
              // zero height subtree with semantics on it.
              ? const SizedBox(width: double.infinity)
              : Container(
                  width: double.infinity,
                  margin: EdgeInsets.only(bottom: context.space.space2),
                  padding: EdgeInsets.all(context.space.space3),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(context.shape.radiusSm),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: Text(
                              hasPayload
                                  ? '${text.length} characters'
                                  : widget.emptyMessage,
                              style: theme.textTheme.labelMedium?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                          if (hasPayload)
                            IconButton(
                              onPressed: () => _copy(text),
                              icon: const Icon(Symbols.content_copy),
                              iconSize: context.sizes.iconAction,
                              tooltip: 'Copy the raw payload',
                              // Never a tooltip as the only label.
                              constraints: BoxConstraints(
                                minWidth: context.sizes.targetMin,
                                minHeight: context.sizes.targetMin,
                              ),
                            ),
                        ],
                      ),
                      if (hasPayload) SizedBox(height: context.space.space2),
                      if (hasPayload)
                        // Real text semantics, and a selection the reviewer
                        // can act on. No synthetic label over the top.
                        SelectionArea(
                          child: Text(text, style: context.mono.code),
                        ),
                    ],
                  ),
                ),
        ),
      ],
    );
  }

  /// Wraps [child] in an `AnimatedSize`, unless motion is off.
  Widget _maybeAnimated(MotionTokens motion, Widget child) => motion.reduced
      ? child
      : AnimatedSize(
          duration: motion.standard,
          curve: MotionTokens.enterCurve,
          alignment: Alignment.topLeft,
          child: child,
        );

  static const double _halfTurn = 0.5;
}
