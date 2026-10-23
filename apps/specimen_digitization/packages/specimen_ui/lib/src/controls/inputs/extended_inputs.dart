/// Composition patterns for verification, tokens and rich-editor commands.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../actions/shared_actions.dart';
import 'field.dart';
import 'select.dart';

/// A numeric verification code with native text editing, paste and autofill.
///
/// Each digit has a named 48 dp input. A pasted code is distributed from the
/// focused digit; Backspace on an empty digit returns to the preceding digit.
/// Codes keep logical left-to-right order in RTL. Large text wraps the cells.
/// This component never sends or validates a code against a service.
class UiVerificationCode extends StatefulWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiVerificationCode({
    super.key,
    required this.label,
    required this.value,
    this.length = 6,
    this.onChanged,
    this.onCompleted,
    this.errorText,
    this.helpText,
    this.disabledReason,
    this.autofocus = false,
  }) : assert(length == 4 || length == 6),
       assert(value.length <= length);

  /// The visible and accessible name of the control.
  final String label;

  /// The current value accepted by the host.
  final String value;

  /// The number of verification digits, either four or six.
  final int length;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<String>? onChanged;

  /// The callback issued once for each newly complete code.
  final ValueChanged<String>? onCompleted;

  /// The validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// The persistent supporting instruction beneath the control.
  final String? helpText;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  /// Whether the first editor requests focus on insertion.
  final bool autofocus;
  @override
  State<UiVerificationCode> createState() => _UiVerificationCodeState();
}

class _UiVerificationCodeState extends State<UiVerificationCode> {
  final _controllers = <TextEditingController>[];
  final _nodes = <FocusNode>[];
  String? _completed;
  @override
  void initState() {
    super.initState();
    _reset();
  }

  void _reset() {
    for (final c in _controllers) {
      c.dispose();
    }
    for (final n in _nodes) {
      n.dispose();
    }
    _controllers.clear();
    _nodes.clear();
    for (int i = 0; i < widget.length; i++) {
      final c = TextEditingController(
        text: i < widget.value.length ? widget.value[i] : '',
      );
      final n = FocusNode(debugLabel: 'Code digit ${i + 1}');
      n.addListener(() {
        if (n.hasFocus) {
          c.selection = TextSelection(
            baseOffset: 0,
            extentOffset: c.text.length,
          );
        }
      });
      _controllers.add(c);
      _nodes.add(n);
    }
  }

  @override
  void didUpdateWidget(UiVerificationCode old) {
    super.didUpdateWidget(old);
    if (widget.value.length < widget.length ||
        (old.value != widget.value && widget.value != _completed)) {
      // An accepted echo keeps completion deduplicated. A genuinely different
      // host value starts a new edit, even when that value is already complete.
      _completed = null;
    }
    if (old.length != widget.length) {
      _reset();
      return;
    }
    if (old.value != widget.value &&
        _controllers.map((c) => c.text).join() != widget.value) {
      for (int i = 0; i < widget.length; i++) {
        _controllers[i].text = i < widget.value.length ? widget.value[i] : '';
      }
    }
  }

  void _change(int index, String text) {
    if (widget.onChanged == null) return;
    final digits = text.replaceAll(RegExp('[^0-9]'), '');
    if (digits.isEmpty) {
      _controllers[index].clear();
    } else {
      for (int i = 0; i < digits.length && index + i < widget.length; i++) {
        _controllers[index + i].text = digits[i];
      }
      _nodes[(index + digits.length).clamp(0, widget.length - 1)]
          .requestFocus();
    }
    final code = _controllers.map((c) => c.text).join();
    // A String value has no representation for holes. Keep the visible cells
    // in the same order as the controlled value after a middle-digit deletion.
    for (int i = 0; i < widget.length; i++) {
      final digit = i < code.length ? code[i] : '';
      if (_controllers[i].text != digit) _controllers[i].text = digit;
    }
    widget.onChanged!(code);
    if (code.length < widget.length) _completed = null;
    if (code.length == widget.length && code != _completed) {
      _completed = code;
      widget.onCompleted?.call(code);
    }
  }

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    for (final n in _nodes) {
      n.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final style = UiInputStyle.resolve(ui, UiFieldShape.box);
    return UiFieldFrame(
      label: widget.label,
      style: style,
      states: {
        if (widget.onChanged == null) WidgetState.disabled,
        if (widget.errorText != null) WidgetState.error,
      },
      isError: widget.errorText != null,
      message: widget.errorText ?? widget.disabledReason ?? widget.helpText,
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: Wrap(
          spacing: ui.space.s1,
          runSpacing: ui.space.s2,
          children: [
            for (int i = 0; i < widget.length; i++)
              SizedBox(
                width:
                    ui.space.targetMin +
                    (MediaQuery.textScalerOf(
                              context,
                            ).scale(style.text.fontSize!) -
                            style.text.fontSize!)
                        .clamp(0, ui.space.targetMin),
                child: Focus(
                  canRequestFocus: false,
                  onKeyEvent: (_, event) {
                    if (event is KeyDownEvent &&
                        event.logicalKey == LogicalKeyboardKey.backspace &&
                        _controllers[i].text.isEmpty &&
                        i > 0 &&
                        widget.onChanged != null) {
                      _nodes[i - 1].requestFocus();
                      return KeyEventResult.handled;
                    }
                    return KeyEventResult.ignored;
                  },
                  child: UiField(
                    label:
                        '${widget.label}, digit ${i + 1} of ${widget.length}',
                    showLabel: false,
                    controller: _controllers[i],
                    focusNode: _nodes[i],
                    autofocus: i == 0 && widget.autofocus,
                    enabled: widget.onChanged != null,
                    disabledReason: widget.disabledReason,
                    keyboardType: TextInputType.number,
                    autofillHints: i == 0
                        ? const [AutofillHints.oneTimeCode]
                        : const [],
                    autocorrect: false,
                    textInputAction: i == widget.length - 1
                        ? TextInputAction.done
                        : TextInputAction.next,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(widget.length),
                    ],
                    onChanged: (text) => _change(i, text),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// An editable list of textual tags with independent remove actions.
///
/// Enter adds a trimmed, nonempty, unique tag. Backspace in the empty editor
/// removes the last tag. The caller owns the accepted list and persistence.
class UiTagField extends StatefulWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiTagField({
    super.key,
    required this.label,
    required this.values,
    this.onChanged,
    this.hintText = 'Type a tag and press Enter',
    this.helpText,
    this.errorText,
    this.disabledReason,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The current collection of values accepted by the host.
  final List<String> values;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<List<String>>? onChanged;

  /// The prompt displayed in an empty editor.
  final String hintText;

  /// The persistent supporting instruction beneath the control.
  final String? helpText;

  /// The validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;
  @override
  State<UiTagField> createState() => _UiTagFieldState();
}

class _UiTagFieldState extends State<UiTagField> {
  final _controller = TextEditingController();
  void _remove(int index) => widget.onChanged?.call(
    List.unmodifiable(List<String>.of(widget.values)..removeAt(index)),
  );
  void _add(String value) {
    final tag = value.trim();
    if (widget.onChanged == null || tag.isEmpty) return;
    if (!widget.values.contains(tag)) {
      widget.onChanged!(List.unmodifiable([...widget.values, tag]));
    }
    _controller.clear();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (widget.values.isNotEmpty) ...[
        Wrap(
          spacing: context.ui.space.s2,
          runSpacing: context.ui.space.s2,
          children: [
            for (int i = 0; i < widget.values.length; i++)
              UiTag(
                label: widget.values[i],
                onRemove: widget.onChanged == null ? null : () => _remove(i),
              ),
          ],
        ),
        SizedBox(height: context.ui.space.s2),
      ],
      Focus(
        canRequestFocus: false,
        onKeyEvent: (_, event) {
          if (event is KeyDownEvent &&
              event.logicalKey == LogicalKeyboardKey.backspace &&
              _controller.text.isEmpty &&
              widget.values.isNotEmpty &&
              widget.onChanged != null) {
            _remove(widget.values.length - 1);
            return KeyEventResult.handled;
          }
          return KeyEventResult.ignored;
        },
        child: UiField(
          label: widget.label,
          controller: _controller,
          enabled: widget.onChanged != null,
          hintText: widget.hintText,
          helpText: widget.helpText,
          errorText: widget.errorText,
          disabledReason: widget.disabledReason,
          onSubmitted: _add,
          textInputAction: TextInputAction.done,
        ),
      ),
    ],
  );
}

/// A named input with independently focusable prefix/suffix controls.
///
/// Use [UiField.prefixText] for static affixes. This composition keeps actual
/// dropdowns or action buttons out of the editor's merged semantics. At small
/// widths or enlarged type the controls stack instead of clipping.
class UiInputGroup extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiInputGroup({
    super.key,
    required this.field,
    this.leading,
    this.trailing,
  });

  /// The central editable control.
  final Widget field;

  /// The optional content before the main label.
  final Widget? leading;

  /// The optional content after the main label.
  final Widget? trailing;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final children = <Widget>[?leading, field, ?trailing];
      final gap = context.ui.space.s2;
      if (constraints.maxWidth < 560 ||
          MediaQuery.textScalerOf(context).scale(16) > 24) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (int i = 0; i < children.length; i++) ...[
              if (i > 0) SizedBox(height: gap),
              children[i],
            ],
          ],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (leading != null) ...[
            Flexible(child: leading!),
            SizedBox(width: gap),
          ],
          Expanded(flex: 3, child: field),
          if (trailing != null) ...[
            SizedBox(width: gap),
            Flexible(child: trailing!),
          ],
        ],
      );
    },
  );
}

/// Caller-approved country choice for an international phone input.
@immutable
class UiPhoneCountry {
  /// Creates the component with explicit caller-owned configuration.
  const UiPhoneCountry({
    required this.code,
    required this.name,
    required this.dialingCode,
  });

  /// The host-defined stable country identifier.
  final String code;

  /// The complete human-readable identity.
  final String name;

  /// The displayed international dialing prefix.
  final String dialingCode;
}

/// Native telephone editing with an optional, explicit country selector.
///
/// Values stay verbatim. The host owns its country list, formatting, validation
/// and conversion to an international number; no country is inferred.
class UiPhoneField extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiPhoneField({
    super.key,
    required this.label,
    this.controller,
    this.countryCode,
    this.countries = const [],
    this.onCountryChanged,
    this.onChanged,
    this.enabled = true,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.countryLabel = 'Country or region',
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The optional host-managed text and selection controller.
  final TextEditingController? controller;

  /// The explicitly selected country identifier, or `null` when unknown.
  final String? countryCode;

  /// The countries allowed by the host; an empty list omits the selector.
  final List<UiPhoneCountry> countries;

  /// The callback proposing an explicit country selection.
  final ValueChanged<String>? onCountryChanged;

  /// The callback proposing the next value; `null` makes editing unavailable.
  final ValueChanged<String>? onChanged;

  /// Whether interaction is available.
  final bool enabled;

  /// The persistent supporting instruction beneath the control.
  final String? helpText;

  /// The validation message, taking precedence over supporting instructions.
  final String? errorText;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  /// The visible and accessible country-selector label.
  final String countryLabel;
  @override
  Widget build(BuildContext context) => UiInputGroup(
    leading: countries.isEmpty
        ? null
        : UiSelect<String>(
            label: countryLabel,
            value: countryCode,
            placeholder: 'Choose country',
            options: [
              for (final country in countries)
                UiSelectOption(
                  value: country.code,
                  label: '${country.name} (${country.dialingCode})',
                ),
            ],
            onChanged: !enabled ? null : onCountryChanged,
            disabledReason: disabledReason,
          ),
    field: UiField(
      label: label,
      controller: controller,
      onChanged: onChanged,
      enabled: enabled,
      keyboardType: TextInputType.phone,
      autofillHints: const [AutofillHints.telephoneNumber],
      autocorrect: false,
      helpText: helpText,
      errorText: errorText,
      disabledReason: disabledReason,
    ),
  );
}

/// Commands supported by a rich-text editing host.
enum UiTextFormat {
  /// Toggles bold emphasis.
  bold,

  /// Toggles italic emphasis.
  italic,

  /// Toggles underlining.
  underline,

  /// Toggles a heading block.
  heading,

  /// Toggles a second-level heading block.
  heading2,

  /// Toggles a quotation block.
  quote,

  /// Requests link editing.
  link,

  /// Requests image insertion.
  image,

  /// Toggles an unordered list.
  bulletList,

  /// Toggles an ordered list.
  numberedList,
}

/// A formatting toolbar with controlled active marks and real host callbacks.
///
/// The editor owns its document model, selection, undo and serialization.
/// Commands never silently mutate plain text into an incompatible markup format.
class UiTextToolbar extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiTextToolbar({
    super.key,
    required this.onCommand,
    this.active = const {},
    this.commands = UiTextFormat.values,
    this.labelBuilder,
  });

  /// The callback dispatching a formatting command to the editing host.
  final ValueChanged<UiTextFormat>? onCommand;

  /// The formatting marks currently active in the host selection.
  final Set<UiTextFormat> active;

  /// The ordered subset of commands the editor supports.
  final List<UiTextFormat> commands;

  /// The optional localized label for each command.
  final String Function(UiTextFormat)? labelBuilder;
  @override
  Widget build(BuildContext context) => Wrap(
    spacing: context.ui.space.s1,
    runSpacing: context.ui.space.s1,
    children: [
      for (final command in commands)
        Semantics(
          selected: active.contains(command),
          child: UiActionButton(
            label:
                labelBuilder?.call(command) ??
                switch (command) {
                  UiTextFormat.bold => 'Bold',
                  UiTextFormat.italic => 'Italic',
                  UiTextFormat.underline => 'Underline',
                  UiTextFormat.heading => 'Heading 1',
                  UiTextFormat.heading2 => 'Heading 2',
                  UiTextFormat.quote => 'Quote',
                  UiTextFormat.link => 'Link',
                  UiTextFormat.image => 'Image',
                  UiTextFormat.bulletList => 'Bullet list',
                  UiTextFormat.numberedList => 'Numbered list',
                },
            size: UiActionSize.small,
            hierarchy: active.contains(command)
                ? UiActionHierarchy.subtle
                : UiActionHierarchy.link,
            tone: active.contains(command)
                ? UiActionTone.brand
                : UiActionTone.neutral,
            onPressed: onCommand == null ? null : () => onCommand!(command),
          ),
        ),
    ],
  );
}
