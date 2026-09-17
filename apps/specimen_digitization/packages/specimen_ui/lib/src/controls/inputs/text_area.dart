/// The multiple line text field (10 section 4.2, `UiTextArea`).
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import 'field.dart';

/// A [UiField] that holds a paragraph.
///
/// The same label, edge, help line and error line as a single line field; it
/// opens at [minLines] and grows with the text to [maxLines], then scrolls.
/// This is the control a reason takes (03 section 7.3), so it opens tall
/// enough that a reviewer can see the sentence they are writing.
///
/// Retires `TextField` and `TextFormField` with `maxLines` at call sites.
class UiTextArea extends StatelessWidget {
  /// A text area named [label].
  const UiTextArea({
    super.key,
    required this.label,
    this.controller,
    this.focusNode,
    this.hintText,
    this.helpText,
    this.errorText,
    this.onChanged,
    this.onSubmitted,
    this.enabled = true,
    this.readOnly = false,
    this.autofocus = false,
    this.autocorrect = true,
    this.showLabel = true,
    this.disabledReason,
    this.semanticsLabel,
    this.textCapitalization = TextCapitalization.sentences,
    this.inputFormatters,
    this.minLines = 3,
    this.maxLines = 6,
    this.maxLength,
  }) : assert(
         maxLines == null || maxLines >= minLines,
         'a text area cannot show fewer lines than it opens at',
       );

  /// What the text area is for. Sentence case, no terminal period.
  final String label;

  /// The text being edited. The control builds its own when this is null.
  final TextEditingController? controller;

  /// The node that owns focus for this text area.
  final FocusNode? focusNode;

  /// Placeholder text inside the box. Never a substitute for [label].
  final String? hintText;

  /// One line under the box saying what it does (02 section 4.11).
  final String? helpText;

  /// The rule the entry broke, stated positively (02 section 4.10).
  final String? errorText;

  /// Called on every edit.
  final ValueChanged<String>? onChanged;

  /// Called when the reviewer submits.
  final ValueChanged<String>? onSubmitted;

  /// False for a text area the reviewer cannot use.
  final bool enabled;

  /// True for text that can be read and copied but not edited.
  final bool readOnly;

  /// True to take focus when first built.
  final bool autofocus;

  /// False for verbatim transcription, where a correction would be a lie.
  final bool autocorrect;

  /// False where the purpose is visible without a label.
  final bool showLabel;

  /// Why the text area is disabled, in the reviewer's words.
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// How the platform capitalises. Sentences, because this is prose.
  final TextCapitalization textCapitalization;

  /// Formatters applied as the reviewer types.
  final List<TextInputFormatter>? inputFormatters;

  /// How many lines the box opens at.
  final int minLines;

  /// How many lines it grows to before it scrolls. Null grows without limit.
  final int? maxLines;

  /// The character limit. Not null draws the counter under the box.
  final int? maxLength;

  @override
  Widget build(BuildContext context) => UiField(
    label: label,
    controller: controller,
    focusNode: focusNode,
    hintText: hintText,
    helpText: helpText,
    errorText: errorText,
    onChanged: onChanged,
    onSubmitted: onSubmitted,
    enabled: enabled,
    readOnly: readOnly,
    autofocus: autofocus,
    autocorrect: autocorrect,
    showLabel: showLabel,
    disabledReason: disabledReason,
    semanticsLabel: semanticsLabel,
    textCapitalization: textCapitalization,
    inputFormatters: inputFormatters,
    keyboardType: TextInputType.multiline,
    minLines: minLines,
    maxLines: maxLines,
    maxLength: maxLength,
  );
}
