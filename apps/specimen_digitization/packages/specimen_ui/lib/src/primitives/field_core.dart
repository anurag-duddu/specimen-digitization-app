/// Text editing, and nothing else (10 section 3; 11 section 4).
///
/// This is the one file in `primitives/` allowed to import `material.dart`,
/// and it imports it for `TextField` alone: the selection toolbar, the
/// magnifier, autofill, spell check, the IME and the semantics of a text
/// field are thousands of lines that `EditableText` on its own does not give
/// (10 section 1.3).
///
/// The decoration is not stripped, it is absent: `decoration: null` builds no
/// `InputDecorator` at all, so the bridge `ThemeData`'s
/// `InputDecorationTheme` has nothing to paint through and a field renders
/// the same with the bridge theme above it and without. A collapsed
/// decoration was still a decorator, and its enabled and focused borders were
/// two of the three edges a focused field drew (11 section 0).
///
/// What is left is one object with one style: the typed text, the placeholder
/// drawn in the same style on the same baseline, the caret and the selection.
/// The edge, the label, the help line and the error all belong to `UiField`
/// in the inputs family, and the ring belongs to the box.
library;

// The one Material import in primitives, for TextField's editing behaviour.
import 'package:flutter/material.dart' show Material, MaterialType, TextField;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../foundation/theme.dart';

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
    this.excludeFromSemantics = false,
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

  /// True where an ancestor already publishes the semantics for this editor.
  ///
  /// `UiField` in the inputs family publishes one node for the whole control,
  /// covering the label, the value, the hint and the 48 dp hit box the editor
  /// alone does not fill. Without this the editor publishes a second node
  /// carrying the same label, which a screen reader reads twice.
  final bool excludeFromSemantics;

  @override
  State<FieldCore> createState() => _FieldCoreState();
}

class _FieldCoreState extends State<FieldCore> {
  TextEditingController? _internalController;
  bool _empty = true;

  TextEditingController get _controller =>
      widget.controller ?? (_internalController ??= TextEditingController());

  @override
  void initState() {
    super.initState();
    _controller.addListener(_contentChanged);
    _empty = _controller.text.isEmpty;
  }

  @override
  void didUpdateWidget(FieldCore oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller?.removeListener(_contentChanged);
      _internalController?.removeListener(_contentChanged);
      _controller.addListener(_contentChanged);
      _contentChanged();
    }
  }

  @override
  void dispose() {
    widget.controller?.removeListener(_contentChanged);
    _internalController
      ?..removeListener(_contentChanged)
      ..dispose();
    super.dispose();
  }

  /// The placeholder is drawn while the value is empty and taken away the
  /// moment it is not, which is a rebuild the editor does not ask for.
  void _contentChanged() {
    if (!mounted) return;
    final bool empty = _controller.text.isEmpty;
    if (empty == _empty) return;
    setState(() => _empty = empty);
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextStyle style = (widget.style ?? ui.type.body).copyWith(
      color: widget.enabled ? ui.color.ink : ui.color.disabledContent,
    );
    // The line box is locked from the role, so the placeholder, the typed
    // text and the caret share one box whatever the value is.
    final StrutStyle strut = StrutStyle.fromTextStyle(style);

    // `TextField` asserts on a `Material` ancestor, for the selection
    // handles and the magnifier it paints into. Transparent, so it draws
    // nothing: the chrome is ours, and the widget 10 section 1.3 retires is
    // `Material` at a call site, not the ancestor its own `TextField` needs.
    final Widget field = Material(
      type: MaterialType.transparency,
      child: TextField(
        controller: _controller,
        focusNode: widget.focusNode,
        style: style,
        strutStyle: strut,
        cursorColor: ui.color.ink,
        cursorWidth: ui.shape.stroke.emphasis,
        cursorRadius: Radius.circular(ui.shape.stroke.caretRadius),
        // No decorator at all. Not a collapsed one: a collapsed
        // `InputDecoration` still builds an `InputDecorator`, which reads the
        // bridge theme's `InputDecorationTheme` and paints its enabled and
        // focused borders under our edge (11 section 0).
        decoration: null,
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
      ),
    );

    // The caret and the selection come from here rather than from the Material
    // theme, so the package paints the same inside a bare `WidgetsApp` as it
    // does inside the application.
    Widget core = DefaultSelectionStyle(
      cursorColor: ui.color.ink,
      selectionColor: ui.color.selection,
      child: field,
    );

    final String? hint = widget.hintText;
    if (hint != null) {
      core = Stack(
        children: <Widget>[
          if (_empty)
            _Placeholder(
              text: hint,
              style: style,
              strut: strut,
              // Where the editor puts its own first line. A single line
              // editor centres its text in a box one caret taller than the
              // line; a paragraph starts at the top and grows down.
              alignment: widget.maxLines == 1 && !widget.expands
                  ? AlignmentDirectional.centerStart
                  : AlignmentDirectional.topStart,
              paragraph: widget.maxLines != 1,
            ),
          core,
        ],
      );
    }

    if (widget.excludeFromSemantics) return core;

    return Semantics(
      label: widget.semanticsLabel,
      textField: true,
      enabled: widget.enabled,
      readOnly: widget.readOnly,
      obscured: widget.obscureText,
      child: core,
    );
  }
}

/// The placeholder, drawn by us because there is no decorator to draw it.
///
/// The same style, the same strut and the same alignment as the first line of
/// the value, in `ink.tertiary`, so the text a reviewer types lands exactly
/// where the placeholder sat. It is excluded from semantics because the
/// control's own node already carries the hint, and it ignores the pointer so
/// a tap on the placeholder is a tap on the editor behind it.
class _Placeholder extends StatelessWidget {
  const _Placeholder({
    required this.text,
    required this.style,
    required this.strut,
    required this.alignment,
    required this.paragraph,
  });

  final String text;
  final TextStyle style;
  final StrutStyle strut;
  final AlignmentGeometry alignment;

  /// True where the editor holds a paragraph, so a long placeholder wraps the
  /// way the text it stands in for will.
  final bool paragraph;

  @override
  Widget build(BuildContext context) => Positioned.fill(
    child: IgnorePointer(
      child: ExcludeSemantics(
        child: Align(
          alignment: alignment,
          child: Text(
            text,
            style: style.copyWith(color: context.ui.color.inkTertiary),
            strutStyle: strut,
            maxLines: paragraph ? null : 1,
            softWrap: paragraph,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ),
    ),
  );
}
