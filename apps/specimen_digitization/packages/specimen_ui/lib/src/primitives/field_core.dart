/// Text editing with no Material chrome (10 section 3, `FieldCore`).
///
/// This is the one file in `primitives/` allowed to import `material.dart`,
/// and it imports it for `TextField` alone: the selection toolbar, the
/// magnifier, autofill, spell check, the IME and the semantics of a text field
/// are thousands of lines that `EditableText` on its own does not give
/// (10 section 1.3). Every piece of decoration is stripped with
/// `InputDecoration.collapsed`; the label, the edge, the help text and the
/// error all belong to `UiField` in the inputs family.
library;

// The one Material import in primitives, for TextField's editing behaviour.
import 'package:flutter/material.dart'
    show InputDecoration, Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../foundation/theme.dart';
import 'focus_ring.dart';

/// A text input with no chrome of its own.
class FieldCore extends StatefulWidget {
  /// Edits text with no decoration.
  const FieldCore({
    super.key,
    required this.semanticsLabel,
    this.controller,
    this.focusNode,
    this.style,
    this.hintText,
    this.inputFormatters,
    this.keyboardType,
    this.textInputAction,
    this.textCapitalization = TextCapitalization.none,
    this.onChanged,
    this.onSubmitted,
    this.onEditingComplete,
    this.readOnly = false,
    this.obscureText = false,
    this.enabled = true,
    this.autofocus = false,
    this.maxLines = 1,
    this.minLines,
    this.maxLength,
    this.expands = false,
    this.autocorrect = true,
    this.textAlignVertical,
    this.showFocusRing = true,
  });

  /// The label a screen reader reads. `UiField` passes its visible label
  /// through, so the node carries the same words the reviewer sees.
  final String semanticsLabel;

  /// The text being edited.
  final TextEditingController? controller;

  /// The node that owns focus for this field.
  final FocusNode? focusNode;

  /// The text style. Defaults to `body` in `ink`.
  final TextStyle? style;

  /// Placeholder text, in `ink.tertiary`. Never a substitute for a label.
  final String? hintText;

  /// Formatters applied as the reviewer types.
  final List<TextInputFormatter>? inputFormatters;

  /// Which keyboard to raise.
  final TextInputType? keyboardType;

  /// What the action key does.
  final TextInputAction? textInputAction;

  /// How the platform capitalises.
  final TextCapitalization textCapitalization;

  /// Called on every edit.
  final ValueChanged<String>? onChanged;

  /// Called when the reviewer submits.
  final ValueChanged<String>? onSubmitted;

  /// Called when editing finishes.
  final VoidCallback? onEditingComplete;

  /// True for a field that can be read and copied but not edited.
  final bool readOnly;

  /// True to hide the characters.
  final bool obscureText;

  /// False for a field the reviewer cannot use.
  final bool enabled;

  /// True to take focus when first built.
  final bool autofocus;

  /// How many lines the field shows. Null grows without limit.
  final int? maxLines;

  /// The fewest lines the field shows.
  final int? minLines;

  /// The character limit, where the field has one. The counter belongs to
  /// `UiField`, so no counter is drawn here.
  final int? maxLength;

  /// True for a field that fills its parent, which a text area does.
  final bool expands;

  /// False for a field holding an identifier or a verbatim transcription.
  final bool autocorrect;

  /// Where the text sits in a taller box.
  final TextAlignVertical? textAlignVertical;

  /// False where the wrapping control draws the focus state itself, such as a
  /// field whose edge thickens on focus.
  final bool showFocusRing;

  @override
  State<FieldCore> createState() => _FieldCoreState();
}

class _FieldCoreState extends State<FieldCore> {
  FocusNode? _internalNode;
  bool _focused = false;

  FocusNode get _node => widget.focusNode ?? (_internalNode ??= FocusNode());

  @override
  void initState() {
    super.initState();
    _node.addListener(_focusChanged);
  }

  @override
  void didUpdateWidget(FieldCore oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.focusNode != widget.focusNode) {
      oldWidget.focusNode?.removeListener(_focusChanged);
      _internalNode?.removeListener(_focusChanged);
      _node.addListener(_focusChanged);
    }
  }

  @override
  void dispose() {
    widget.focusNode?.removeListener(_focusChanged);
    _internalNode
      ?..removeListener(_focusChanged)
      ..dispose();
    super.dispose();
  }

  void _focusChanged() {
    if (!mounted || _focused == _node.hasFocus) return;
    setState(() => _focused = _node.hasFocus);
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextStyle style = (widget.style ?? ui.type.body).copyWith(
      color: widget.enabled ? ui.color.ink : ui.color.disabledContent,
    );
    // `TextField` asserts on a `Material` ancestor, for the selection
    // handles and the magnifier it paints into. Transparent, so it draws
    // nothing: the chrome is ours, and the widget 10 section 1.3 retires is
    // `Material` at a call site, not the ancestor its own `TextField` needs.
    final Widget field = TextField(
      controller: widget.controller,
      focusNode: _node,
      style: style,
      cursorColor: ui.color.ink,
      // Every piece of Material decoration removed: no border, no notch, no
      // floating label, no counter, no fill. The chrome is ours.
      decoration: InputDecoration.collapsed(
        hintText: widget.hintText,
        hintStyle: ui.type.body.copyWith(color: ui.color.inkTertiary),
      ),
      inputFormatters: widget.inputFormatters,
      keyboardType: widget.keyboardType,
      textInputAction: widget.textInputAction,
      textCapitalization: widget.textCapitalization,
      onChanged: widget.onChanged,
      onSubmitted: widget.onSubmitted,
      onEditingComplete: widget.onEditingComplete,
      readOnly: widget.readOnly,
      obscureText: widget.obscureText,
      enabled: widget.enabled,
      autofocus: widget.autofocus,
      maxLines: widget.maxLines,
      minLines: widget.minLines,
      maxLength: widget.maxLength,
      expands: widget.expands,
      autocorrect: widget.autocorrect,
      textAlignVertical: widget.textAlignVertical,
      // The counter is UiField's, below the box, beside the help text.
      buildCounter:
          (
            BuildContext context, {
            required int currentLength,
            required int? maxLength,
            required bool isFocused,
          }) => null,
    );

    return Semantics(
      label: widget.semanticsLabel,
      textField: true,
      enabled: widget.enabled,
      readOnly: widget.readOnly,
      obscured: widget.obscureText,
      child: FocusRing(
        visible: widget.showFocusRing && _focused,
        radius: ui.shape.field,
        child: Material(type: MaterialType.transparency, child: field),
      ),
    );
  }
}
