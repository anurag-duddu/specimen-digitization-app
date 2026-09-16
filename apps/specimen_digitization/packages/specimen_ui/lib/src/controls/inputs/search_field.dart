/// The search field (10 section 4.2, `UiSearchField`).
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import 'field.dart';

/// A capsule [UiField] that filters a list.
///
/// The search glyph leads, a clear control appears once there is something to
/// clear, `Escape` clears and then unfocuses, and `Enter` submits. The label
/// is carried in semantics rather than drawn, because a search field beside
/// the list it filters says what it is by where it sits.
///
/// Retires `TextField` with a search decoration at call sites.
class UiSearchField extends StatefulWidget {
  /// A search field labelled [label], whose clear control reads [clearLabel].
  const UiSearchField({
    super.key,
    required this.label,
    required this.clearLabel,
    this.controller,
    this.focusNode,
    this.hintText,
    this.helpText,
    this.onChanged,
    this.onSubmitted,
    this.enabled = true,
    this.autofocus = false,
    this.showLabel = false,
    this.disabledReason,
  });

  /// What the field searches. Read by a screen reader, and drawn only when
  /// [showLabel] is true.
  final String label;

  /// What the clear control reads, as a phrase that stands alone.
  final String clearLabel;

  /// The text being edited. The field builds its own when this is null.
  final TextEditingController? controller;

  /// The node that owns focus for this field.
  final FocusNode? focusNode;

  /// Placeholder text inside the capsule.
  final String? hintText;

  /// One line under the field saying what it searches.
  final String? helpText;

  /// Called on every edit, including when the clear control empties it.
  final ValueChanged<String>? onChanged;

  /// Called when the reviewer presses `Enter`.
  final ValueChanged<String>? onSubmitted;

  /// False for a field the reviewer cannot use.
  final bool enabled;

  /// True to take focus when first built.
  final bool autofocus;

  /// True to draw the label above the capsule as well as carry it in
  /// semantics.
  final bool showLabel;

  /// Why the field is disabled, in the reviewer's words.
  final String? disabledReason;

  @override
  State<UiSearchField> createState() => _UiSearchFieldState();
}

class _UiSearchFieldState extends State<UiSearchField> {
  TextEditingController? _internalController;
  FocusNode? _internalNode;

  TextEditingController get _controller =>
      widget.controller ?? (_internalController ??= TextEditingController());

  FocusNode get _node => widget.focusNode ?? (_internalNode ??= FocusNode());

  @override
  void dispose() {
    _internalController?.dispose();
    _internalNode?.dispose();
    super.dispose();
  }

  /// `Escape` clears, and then unfocuses.
  ///
  /// Two presses rather than one, because a reviewer who has typed a query
  /// wants it gone before they want the field gone, and losing both to one
  /// keystroke is the kind of thing that costs a retype. The key is consumed
  /// either way: while a search field holds focus, `Escape` is its key.
  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent ||
        event.logicalKey != LogicalKeyboardKey.escape) {
      return KeyEventResult.ignored;
    }
    if (_controller.text.isNotEmpty) {
      _controller.clear();
      widget.onChanged?.call('');
      return KeyEventResult.handled;
    }
    _node.unfocus();
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) => Focus(
    // A listener rather than a stop on the way round: it reads the key and
    // hands focus back untouched.
    canRequestFocus: false,
    skipTraversal: true,
    onKeyEvent: _onKey,
    child: UiField(
      label: widget.label,
      controller: _controller,
      focusNode: _node,
      shape: UiFieldShape.capsule,
      showLabel: widget.showLabel,
      leading: UiIcons.search,
      hintText: widget.hintText,
      helpText: widget.helpText,
      clearLabel: widget.clearLabel,
      onChanged: widget.onChanged,
      onSubmitted: widget.onSubmitted,
      enabled: widget.enabled,
      autofocus: widget.autofocus,
      autocorrect: false,
      disabledReason: widget.disabledReason,
      keyboardType: TextInputType.text,
      textInputAction: TextInputAction.search,
    ),
  );
}
