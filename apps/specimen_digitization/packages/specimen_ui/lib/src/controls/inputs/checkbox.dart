/// The checkbox (10 section 4.2, `UiCheckbox`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import '../../primitives/squircle.dart';

/// The resolved paint of one checkbox.
///
/// The box is 20 dp, which 10 section 4.2 states and the grid does not, so it
/// is named here and nowhere else.
@immutable
class UiCheckboxStyle {
  /// Binds every token a checkbox draws with.
  const UiCheckboxStyle({
    required this.fill,
    required this.side,
    required this.mark,
    required this.label,
    required this.boxSize,
    required this.radius,
    required this.barWidth,
    required this.barHeight,
  });

  /// Behind the mark: `ink` when checked or mixed, `paper` otherwise.
  final WidgetStateProperty<Color> fill;

  /// The box's edge.
  final WidgetStateProperty<BorderSide> side;

  /// The check and the indeterminate bar.
  final WidgetStateProperty<Color> mark;

  /// The label at the end of the row.
  final WidgetStateProperty<TextStyle> label;

  /// 20.
  final double boxSize;

  /// `radius.inner`.
  final double radius;

  /// The indeterminate bar's width.
  final double barWidth;

  /// The indeterminate bar's height, which is `stroke.bar`.
  final double barHeight;

  /// The style in [ui].
  static UiCheckboxStyle resolve(UiThemeData ui) {
    Color fill(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) return ui.color.disabledFill;
      return states.contains(WidgetState.selected)
          ? ui.color.ink
          : ui.color.paper;
    }

    BorderSide side(Set<WidgetState> states) => BorderSide(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledOutline
          : states.contains(WidgetState.selected)
          ? ui.color.ink
          : ui.color.boundary,
      width: ui.shape.stroke.boundary,
    );

    Color mark(Set<WidgetState> states) => states.contains(WidgetState.disabled)
        ? ui.color.disabledContent
        : ui.color.paper;

    TextStyle label(Set<WidgetState> states) => ui.type.body.copyWith(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledContent
          : ui.color.ink,
    );

    return UiCheckboxStyle(
      fill: WidgetStateProperty.resolveWith(fill),
      side: WidgetStateProperty.resolveWith(side),
      mark: WidgetStateProperty.resolveWith(mark),
      label: WidgetStateProperty.resolveWith(label),
      boxSize: 20,
      radius: ui.shape.inner,
      barWidth: ui.space.s3,
      barHeight: ui.shape.stroke.bar,
    );
  }
}

/// A box that is checked, unchecked or neither.
///
/// [value] null is the indeterminate state, which this product uses for a
/// selection that covers some of a group: it draws a bar rather than a check
/// and reads as mixed. The label sits at the end and the whole row is the hit
/// box.
///
/// Retires `Checkbox` and `CheckboxListTile`.
class UiCheckbox extends StatelessWidget {
  /// A checkbox labelled [label] whose state is [value].
  const UiCheckbox({
    super.key,
    required this.label,
    required this.value,
    this.onChanged,
    this.disabledReason,
    this.semanticsLabel,
    this.showLabel = true,
    this.autofocus = false,
  });

  /// What the box selects. Sentence case, no terminal period.
  final String label;

  /// True checked, false unchecked, null indeterminate.
  final bool? value;

  /// Called with the next value. Null disables the box.
  ///
  /// An indeterminate box moves to checked, which is what a reviewer means
  /// when they press a partly selected group.
  final ValueChanged<bool>? onChanged;

  /// Why the box is disabled, in the reviewer's words (03 section 3.6).
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// False where the row around the box already names it.
  final bool showLabel;

  /// True to take focus when first built.
  final bool autofocus;

  /// The state the box moves to when it is pressed.
  bool get _next => value != true;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiCheckboxStyle style = UiCheckboxStyle.resolve(ui);
    final bool enabled = onChanged != null;
    return Semantics(
      container: true,
      // `checked` and `mixed` together are how a tristate box reads: mixed
      // says "some of this group", which is a different fact from unchecked.
      checked: value ?? false,
      mixed: value == null,
      label: semanticsLabel ?? label,
      hint: enabled ? null : disabledReason,
      enabled: enabled,
      onTap: enabled ? () => onChanged!(_next) : null,
      child: Pressable(
        // The row publishes the node above, because `mixed` is a state
        // `Pressable` has no word for and an indeterminate box needs it.
        excludeFromSemantics: true,
        semanticsLabel: semanticsLabel ?? label,
        selected: value != false,
        onPressed: enabled ? () => onChanged!(_next) : null,
        disabledReason: disabledReason,
        autofocus: autofocus,
        radius: style.radius,
        builder: (BuildContext context, Set<WidgetState> states) =>
            // The row's own words are already the node's label above; read
            // twice they become "Coverage confirmed Coverage confirmed".
            ExcludeSemantics(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  _Box(style: style, states: states, value: value),
                  if (showLabel) ...<Widget>[
                    SizedBox(width: ui.space.s3),
                    Flexible(
                      child: Text(label, style: style.label.resolve(states)),
                    ),
                  ],
                ],
              ),
            ),
      ),
    );
  }
}

/// The box, and the mark inside it.
class _Box extends StatelessWidget {
  const _Box({required this.style, required this.states, required this.value});

  final UiCheckboxStyle style;
  final Set<WidgetState> states;
  final bool? value;

  @override
  Widget build(BuildContext context) {
    final Color mark = style.mark.resolve(states);
    return SizedBox.square(
      dimension: style.boxSize,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          shape: Squircle.border(
            style.radius,
            side: style.side.resolve(states),
          ),
          color: style.fill.resolve(states),
        ),
        child: Center(
          child: switch (value) {
            true => UiIcon(UiIcons.check, size: UiIconSize.small, color: mark),
            null => SizedBox(
              width: style.barWidth,
              height: style.barHeight,
              child: DecoratedBox(
                decoration: ShapeDecoration(
                  shape: const StadiumBorder(),
                  color: mark,
                ),
              ),
            ),
            false => const SizedBox.shrink(),
          },
        ),
      ),
    );
  }
}
