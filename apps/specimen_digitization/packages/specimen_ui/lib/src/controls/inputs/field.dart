/// The text field (10 section 4.2, `UiField`).
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/announcer.dart';
import '../../primitives/field_core.dart';
import '../../primitives/focus_ring.dart';
import '../../primitives/pressable.dart';
import '../../primitives/squircle.dart';

/// The outline a field is drawn in.
///
/// An enum rather than a `bool`, because 09 section 5 gives the two shapes
/// different names and 10 section 11 asks for choices as enums.
enum UiFieldShape {
  /// `radius.field`. Text fields, text areas, selects.
  box,

  /// `radius.capsule`. Search fields.
  capsule,
}

/// The resolved paint of one field shaped control.
///
/// Every token a field draws with, resolved once from [UiThemeData] and read
/// by state (10 section 1.5). The states a field carries are `disabled`,
/// `focused` and `error`. [UiField], [UiTextArea], [UiSearchField] and the
/// trigger of [UiSelect] all resolve this one style, which is what keeps the
/// four the same object to the eye.
///
/// 10 section 11 would name this `UiFieldStyle`. `foundation/fields.dart`
/// already owns that name for the light fields of 09 section 3.2, which are a
/// gradient rather than a control, so this carries the family's name instead.
@immutable
class UiInputStyle {
  /// Binds every token a field draws with.
  const UiInputStyle({
    required this.fill,
    required this.side,
    required this.label,
    required this.text,
    required this.footer,
    required this.footerColor,
    required this.glyph,
    required this.padding,
    required this.minHeight,
    required this.radius,
    required this.capsule,
  });

  /// The fill behind the text. It does not change on focus (10 section 4.2).
  final WidgetStateProperty<Color> fill;

  /// The edge: `boundary`, `ink` at `stroke.emphasis` on focus,
  /// `status.blocked.content` on error.
  final WidgetStateProperty<BorderSide> side;

  /// The label above the field.
  final TextStyle label;

  /// The text being edited.
  final TextStyle text;

  /// Help text, error text and the counter.
  final TextStyle footer;

  /// The colour of the help or error line, by state.
  final WidgetStateProperty<Color> footerColor;

  /// The leading glyph's colour, by state.
  final WidgetStateProperty<Color> glyph;

  /// The padding inside the edge.
  final EdgeInsetsDirectional padding;

  /// The visual height of a single line field. The hit box is
  /// [UiDensity.hitBox] in both densities.
  final double minHeight;

  /// The corner radius, for the outline and the focus ring.
  final double radius;

  /// True when the outline is a capsule.
  final bool capsule;

  /// The style for [shape] in [ui].
  ///
  /// [hasTrailing] shortens the end padding, because a trailing action brings
  /// its own 48 dp hit box and that box becomes the end inset.
  static UiInputStyle resolve(
    UiThemeData ui,
    UiFieldShape shape, {
    bool hasTrailing = false,
  }) {
    final bool capsule = shape == UiFieldShape.capsule;

    Color fill(Set<WidgetState> states) => states.contains(WidgetState.disabled)
        ? ui.color.disabledFill
        : ui.color.paper;

    BorderSide side(Set<WidgetState> states) {
      final bool focused = states.contains(WidgetState.focused);
      final Color color;
      if (states.contains(WidgetState.disabled)) {
        color = ui.color.disabledOutline;
      } else if (states.contains(WidgetState.error)) {
        color = ui.color.status.blocked.content;
      } else if (focused) {
        color = ui.color.ink;
      } else {
        color = ui.color.boundary;
      }
      return BorderSide(
        color: color,
        width: focused ? ui.shape.stroke.emphasis : ui.shape.stroke.boundary,
      );
    }

    Color footerColor(Set<WidgetState> states) {
      if (states.contains(WidgetState.error)) {
        return ui.color.status.blocked.content;
      }
      return states.contains(WidgetState.disabled)
          ? ui.color.disabledContent
          : ui.color.inkSecondary;
    }

    Color glyph(Set<WidgetState> states) =>
        states.contains(WidgetState.disabled)
        ? ui.color.disabledContent
        : ui.color.inkSecondary;

    final double start = capsule ? ui.space.s5 : ui.space.s4;
    return UiInputStyle(
      fill: WidgetStateProperty.resolveWith(fill),
      side: WidgetStateProperty.resolveWith(side),
      label: ui.type.label.copyWith(color: ui.color.inkSecondary),
      text: ui.type.body,
      footer: ui.type.bodySmall,
      footerColor: WidgetStateProperty.resolveWith(footerColor),
      glyph: WidgetStateProperty.resolveWith(glyph),
      padding: EdgeInsetsDirectional.only(
        start: start,
        end: hasTrailing ? ui.space.s1 : start,
      ),
      minHeight: ui.density.controlHeight,
      radius: ui.shape.field,
      capsule: capsule,
    );
  }
}

/// The label, the box and the footer that every field shaped control shares.
///
/// [UiField] and the trigger of [UiSelect] both build through this, so a
/// select and a text field are the same object to the eye: the same label
/// above, the same edge, the same help or error line below.
class UiFieldFrame extends StatelessWidget {
  /// Frames [child] with [label] above and [message] below.
  const UiFieldFrame({
    super.key,
    required this.style,
    required this.states,
    required this.child,
    this.label,
    this.message,
    this.isError = false,
    this.counter,
  });

  /// The resolved tokens, so the frame and the box cannot disagree.
  final UiInputStyle style;

  /// The control's current states.
  final Set<WidgetState> states;

  /// The control itself, already carrying its own semantics node.
  final Widget child;

  /// What the control is for. Null draws no label, which is the search field.
  final String? label;

  /// The help or error line under the control.
  final String? message;

  /// True when [message] is an error rather than help.
  final bool isError;

  /// The character counter, drawn at the end of the footer.
  final String? counter;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (label != null) ...<Widget>[
          // Excluded because the control's own node already reads these
          // words. A label read twice is a label the reviewer skips past.
          ExcludeSemantics(child: Text(label!, style: style.label)),
          SizedBox(height: ui.space.s2),
        ],
        child,
        if (message != null || counter != null) ...<Widget>[
          SizedBox(height: ui.space.s2),
          _Footer(
            message: message,
            isError: isError,
            counter: counter,
            style: style,
            states: states,
          ),
        ],
      ],
    );
  }
}

/// The outlined box a field shaped control draws.
///
/// The edge, the fill, the leading glyph, the 48 dp hit box and the room a
/// trailing action needs. [UiField] puts an editor inside it and [UiSelect]
/// puts the selected option's label and a caret, which is why the two read as
/// one control with two behaviours.
class UiFieldBox extends StatelessWidget {
  /// Draws [child] inside the box [style] describes in [states].
  const UiFieldBox({
    super.key,
    required this.style,
    required this.states,
    required this.child,
    this.leading,
    this.trailing,
    this.focusRing = false,
    this.multiline = false,
  });

  /// The resolved tokens.
  final UiInputStyle style;

  /// The control's current states.
  final Set<WidgetState> states;

  /// What sits between the leading glyph and the trailing action.
  final Widget child;

  /// A glyph at the start, drawn at 20.
  final IconSpec? leading;

  /// An action at the end. It is given its own 48 dp hit box.
  final Widget? trailing;

  /// True to draw the keyboard focus ring. A control whose own `Pressable`
  /// draws the ring leaves this false.
  final bool focusRing;

  /// True when the box holds a paragraph rather than a line.
  final bool multiline;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget box = SizedBox(width: double.infinity, child: _box(ui));
    // The trailing action is positioned rather than laid out in the row, so
    // it can be 48 dp tall inside a 40 dp field in pointer density: the 8 dp
    // the box pads its own hit box with is exactly the room it needs.
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: UiDensity.hitBox),
      child: trailing == null
          ? Align(heightFactor: 1, child: box)
          : Stack(
              alignment: AlignmentDirectional.center,
              children: <Widget>[
                box,
                Positioned.directional(
                  textDirection: Directionality.of(context),
                  end: ui.space.s1,
                  top: 0,
                  bottom: 0,
                  child: Center(child: trailing),
                ),
              ],
            ),
    );
  }

  Widget _box(UiThemeData ui) {
    final BorderSide side = style.side.resolve(states);
    final ShapeBorder shape = style.capsule
        ? StadiumBorder(side: side)
        : Squircle.border(style.radius, side: side);
    return FocusRing(
      visible: focusRing,
      radius: style.radius,
      capsule: style.capsule,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          shape: shape,
          color: style.fill.resolve(states),
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: style.minHeight),
          child: Padding(
            // A paragraph's glyphs sit on the first line rather than in the
            // middle of the text, so its row aligns to the top and the
            // padding puts that first line where a single line would be.
            padding: multiline
                ? style.padding.add(
                    EdgeInsetsDirectional.symmetric(vertical: ui.space.s3),
                  )
                : style.padding,
            child: Row(
              crossAxisAlignment: multiline
                  ? CrossAxisAlignment.start
                  : CrossAxisAlignment.center,
              children: <Widget>[
                if (leading != null) ...<Widget>[
                  UiIcon(
                    leading!,
                    size: UiIconSize.inline,
                    color: style.glyph.resolve(states),
                  ),
                  SizedBox(width: ui.space.s2),
                ],
                Expanded(child: child),
                if (trailing != null) const SizedBox(width: UiDensity.hitBox),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A text field.
///
/// The label sits above in `type.label`; the field is a `radius.field`
/// superellipse of `paper` with a `boundary` edge that becomes `ink` at
/// `stroke.emphasis` on focus and `status.blocked.content` on error; help or
/// error text sits below in `body.small`. There is no floating label, no
/// notch, and the fill does not change on focus.
///
/// Retires `TextField`, `TextFormField`, `InputDecoration` and
/// `OutlineInputBorder` at call sites.
class UiField extends StatefulWidget {
  /// A field named [label].
  ///
  /// [label] is both the visible label and, unless [semanticsLabel] overrides
  /// it, the label a screen reader reads, so the two cannot drift apart.
  const UiField({
    super.key,
    required this.label,
    this.controller,
    this.focusNode,
    this.hintText,
    this.helpText,
    this.errorText,
    this.leading,
    this.trailing,
    this.onClear,
    this.clearLabel,
    this.onChanged,
    this.onSubmitted,
    this.enabled = true,
    this.readOnly = false,
    this.obscureText = false,
    this.autofocus = false,
    this.autocorrect = true,
    this.showLabel = true,
    this.disabledReason,
    this.semanticsLabel,
    this.keyboardType,
    this.textInputAction,
    this.textCapitalization = TextCapitalization.none,
    this.inputFormatters,
    this.minLines,
    this.maxLines = 1,
    this.maxLength,
    this.shape = UiFieldShape.box,
  }) : assert(
         trailing == null || clearLabel == null,
         'a field has one trailing slot: a trailing action or the clear '
         'control, never both',
       ),
       assert(
         onClear == null || clearLabel != null,
         'onClear reports a clear that clearLabel is what draws',
       );

  /// What the field is for. Sentence case, no terminal period.
  final String label;

  /// The text being edited. The field builds its own when this is null.
  final TextEditingController? controller;

  /// The node that owns focus for this field.
  final FocusNode? focusNode;

  /// Placeholder text inside the field. Never a substitute for [label].
  final String? hintText;

  /// One line under the field saying what it does (02 section 4.11).
  final String? helpText;

  /// The rule the entry broke, stated positively (02 section 4.10).
  ///
  /// Not null puts the field in its error state, replaces [helpText] and is
  /// announced once.
  final String? errorText;

  /// A glyph at the start of the field, drawn at 20.
  final IconSpec? leading;

  /// An action at the end of the field. It brings its own 48 dp hit box.
  final Widget? trailing;

  /// Called after the clear control has emptied the field.
  ///
  /// The field does the emptying and reports it through [onChanged]; this is
  /// for a caller that has more to do, such as dropping a filter.
  final VoidCallback? onClear;

  /// What the clear control reads, as a phrase that stands alone.
  ///
  /// Not null draws the clear control while the field has content. A control
  /// the reviewer can press is a control a screen reader has to name
  /// (02 section 4.16).
  final String? clearLabel;

  /// Called on every edit.
  final ValueChanged<String>? onChanged;

  /// Called when the reviewer submits.
  final ValueChanged<String>? onSubmitted;

  /// False for a field the reviewer cannot use. Pair it with
  /// [disabledReason].
  final bool enabled;

  /// True for a field that can be read and copied but not edited.
  final bool readOnly;

  /// True to hide the characters.
  final bool obscureText;

  /// True to take focus when first built.
  final bool autofocus;

  /// False for a field holding an identifier or a verbatim transcription.
  final bool autocorrect;

  /// False where the field's purpose is visible without a label, which is the
  /// search field and nothing else.
  final bool showLabel;

  /// Why the field is disabled, in the reviewer's words (03 section 3.6).
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// Which keyboard to raise.
  final TextInputType? keyboardType;

  /// What the action key does.
  final TextInputAction? textInputAction;

  /// How the platform capitalises.
  final TextCapitalization textCapitalization;

  /// Formatters applied as the reviewer types.
  final List<TextInputFormatter>? inputFormatters;

  /// The fewest lines the field shows.
  final int? minLines;

  /// The most lines the field shows before it scrolls. Null grows without a
  /// limit.
  final int? maxLines;

  /// The character limit. Not null draws the counter under the field.
  final int? maxLength;

  /// Which outline the field is drawn in.
  final UiFieldShape shape;

  @override
  State<UiField> createState() => _UiFieldState();
}

class _UiFieldState extends State<UiField> {
  TextEditingController? _internalController;
  FocusNode? _internalNode;
  bool _focused = false;
  bool _keyboardFocus = false;

  TextEditingController get _controller =>
      widget.controller ?? (_internalController ??= TextEditingController());

  FocusNode get _node => widget.focusNode ?? (_internalNode ??= FocusNode());

  @override
  void initState() {
    super.initState();
    _controller.addListener(_contentChanged);
    _node.addListener(_focusChanged);
    FocusManager.instance.addHighlightModeListener(_highlightChanged);
    _focused = _node.hasFocus;
    _keyboardFocus = _focused && _traditional;
  }

  @override
  void didUpdateWidget(UiField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller?.removeListener(_contentChanged);
      _internalController?.removeListener(_contentChanged);
      _controller.addListener(_contentChanged);
    }
    if (oldWidget.focusNode != widget.focusNode) {
      oldWidget.focusNode?.removeListener(_focusChanged);
      _internalNode?.removeListener(_focusChanged);
      _node.addListener(_focusChanged);
      _focusChanged();
    }
  }

  @override
  void dispose() {
    FocusManager.instance.removeHighlightModeListener(_highlightChanged);
    widget.controller?.removeListener(_contentChanged);
    widget.focusNode?.removeListener(_focusChanged);
    _internalController
      ?..removeListener(_contentChanged)
      ..dispose();
    _internalNode
      ?..removeListener(_focusChanged)
      ..dispose();
    super.dispose();
  }

  /// True while the reviewer is driving from the keyboard.
  ///
  /// The edge thickens for any focus, because a reviewer who clicked into a
  /// field is owed the same "you are here" the keyboard gives. The ring is
  /// drawn only under `FocusHighlightMode.traditional`, which is clause 4 of
  /// the control contract.
  bool get _traditional =>
      FocusManager.instance.highlightMode == FocusHighlightMode.traditional;

  void _contentChanged() {
    if (mounted) setState(() {});
  }

  void _focusChanged() {
    if (!mounted) return;
    final bool focused = _node.hasFocus;
    final bool ring = focused && _traditional;
    if (focused == _focused && ring == _keyboardFocus) return;
    setState(() {
      _focused = focused;
      _keyboardFocus = ring;
    });
  }

  void _highlightChanged(FocusHighlightMode mode) => _focusChanged();

  void _clear() {
    _controller.clear();
    widget.onChanged?.call('');
    widget.onClear?.call();
  }

  Set<WidgetState> get _states => <WidgetState>{
    if (!widget.enabled) WidgetState.disabled,
    if (_focused) WidgetState.focused,
    if (widget.errorText != null) WidgetState.error,
  };

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget? trailing = _buildTrailing();
    final UiInputStyle style = UiInputStyle.resolve(
      ui,
      widget.shape,
      hasTrailing: trailing != null,
    );
    final Set<WidgetState> states = _states;
    final String? footer = widget.errorText ?? widget.helpText;

    return UiFieldFrame(
      style: style,
      states: states,
      label: widget.showLabel ? widget.label : null,
      message: footer,
      isError: widget.errorText != null,
      counter: widget.maxLength == null
          ? null
          : '${_controller.text.characters.length} / ${widget.maxLength}',
      child: Semantics(
        container: true,
        textField: true,
        label: widget.semanticsLabel ?? widget.label,
        value: _controller.text.isEmpty ? null : _controller.text,
        hint: widget.enabled
            ? (footer ?? widget.hintText)
            : widget.disabledReason,
        enabled: widget.enabled,
        readOnly: widget.readOnly,
        obscured: widget.obscureText,
        child: _buildHitArea(style, states, trailing),
      ),
    );
  }

  Widget _buildHitArea(
    UiInputStyle style,
    Set<WidgetState> states,
    Widget? trailing,
  ) => UiFieldBox(
    style: style,
    states: states,
    leading: widget.leading,
    trailing: trailing,
    focusRing: _keyboardFocus,
    multiline: widget.maxLines != 1,
    child: _buildCore(style),
  );

  Widget _buildCore(UiInputStyle style) => FieldCore(
    // The field publishes one node for the whole control, so the editor does
    // not publish a second one carrying the same words.
    semanticsLabel: widget.semanticsLabel ?? widget.label,
    excludeFromSemantics: true,
    controller: _controller,
    focusNode: _node,
    style: style.text,
    hintText: widget.hintText,
    inputFormatters: widget.inputFormatters,
    keyboardType: widget.keyboardType,
    textInputAction: widget.textInputAction,
    textCapitalization: widget.textCapitalization,
    onChanged: widget.onChanged,
    onSubmitted: widget.onSubmitted,
    readOnly: widget.readOnly,
    obscureText: widget.obscureText,
    enabled: widget.enabled,
    autofocus: widget.autofocus,
    autocorrect: widget.autocorrect,
    minLines: widget.minLines,
    maxLines: widget.maxLines,
    maxLength: widget.maxLength,
    // The field draws the focus state on its own edge and its own ring, and
    // the ring only for keyboard focus.
    showFocusRing: false,
  );

  Widget? _buildTrailing() {
    if (widget.trailing != null) return widget.trailing;
    if (widget.clearLabel == null || !widget.enabled) return null;
    if (_controller.text.isEmpty) return null;
    return _ClearAction(label: widget.clearLabel!, onPressed: _clear);
  }
}

/// The control that empties a field.
///
/// Its own 48 dp hit box and its own label, because a control the reviewer
/// can press is a control a screen reader has to name (10 section 4.2).
class _ClearAction extends StatelessWidget {
  const _ClearAction({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Pressable(
      semanticsLabel: label,
      onPressed: onPressed,
      capsule: true,
      builder: (BuildContext context, Set<WidgetState> states) => UiIcon(
        UiIcons.close,
        size: UiIconSize.inline,
        color: ui.color.inkSecondary,
      ),
    );
  }
}

/// The help, error and counter line under a field.
class _Footer extends StatelessWidget {
  const _Footer({
    required this.message,
    required this.isError,
    required this.counter,
    required this.style,
    required this.states,
  });

  final String? message;
  final bool isError;
  final String? counter;
  final UiInputStyle style;
  final Set<WidgetState> states;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Color color = style.footerColor.resolve(states);
    final TextStyle text = style.footer.copyWith(color: color);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        if (message != null) ...<Widget>[
          if (isError) ...<Widget>[
            UiIcon(UiIcons.error, size: UiIconSize.small, color: color),
            SizedBox(width: ui.space.s1),
          ],
          Expanded(
            child: _Message(message: message!, isError: isError, style: text),
          ),
        ] else
          const Spacer(),
        if (counter != null) ...<Widget>[
          SizedBox(width: ui.space.s2),
          // The count is on the field's own node already, through the
          // editor's maxValueLength, so the drawn counter is for the eye.
          ExcludeSemantics(
            child: Text(
              counter!,
              style: style.footer.copyWith(color: ui.color.inkTertiary),
            ),
          ),
        ],
      ],
    );
  }
}

/// The help or error line.
///
/// An error goes through [Announcer], so a screen reader reads it once when it
/// appears and never again (06 section 3). Help text does not: the field's
/// hint already carries it, and a second reading of the same sentence is
/// noise.
class _Message extends StatelessWidget {
  const _Message({
    required this.message,
    required this.isError,
    required this.style,
  });

  final String message;
  final bool isError;
  final TextStyle style;

  @override
  Widget build(BuildContext context) {
    final Widget text = Text(message, style: style);
    return isError ? Announcer(child: text) : ExcludeSemantics(child: text);
  }
}
