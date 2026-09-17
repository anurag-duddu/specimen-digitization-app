/// The radio and its group (10 section 4.2, `UiRadio`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/theme.dart';
import '../../primitives/focus_ring.dart';
import '../../primitives/state_layer.dart';
import '../../primitives/squircle.dart';

/// The resolved paint of one radio.
///
/// The disc is 20 dp, which 10 section 4.2 states and the grid does not, so
/// it is named here and nowhere else.
@immutable
class UiRadioStyle {
  /// Binds every token a radio draws with.
  const UiRadioStyle({
    required this.side,
    required this.dot,
    required this.label,
    required this.discSize,
    required this.dotSize,
    required this.rowRadius,
  });

  /// The ring around the disc.
  final WidgetStateProperty<BorderSide> side;

  /// The dot inside a selected disc.
  final WidgetStateProperty<Color> dot;

  /// The label at the end of the row.
  final WidgetStateProperty<TextStyle> label;

  /// 20.
  final double discSize;

  /// The selected dot's diameter.
  final double dotSize;

  /// The corner the state layer takes over the row.
  final double rowRadius;

  /// The style in [ui].
  static UiRadioStyle resolve(UiThemeData ui) {
    BorderSide side(Set<WidgetState> states) => BorderSide(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledOutline
          : states.contains(WidgetState.selected)
          ? ui.color.ink
          : ui.color.boundary,
      width: states.contains(WidgetState.selected)
          ? ui.shape.stroke.emphasis
          : ui.shape.stroke.boundary,
    );

    Color dot(Set<WidgetState> states) => states.contains(WidgetState.disabled)
        ? ui.color.disabledContent
        : ui.color.ink;

    TextStyle label(Set<WidgetState> states) => ui.type.body.copyWith(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledContent
          : ui.color.ink,
    );

    return UiRadioStyle(
      side: WidgetStateProperty.resolveWith(side),
      dot: WidgetStateProperty.resolveWith(dot),
      label: WidgetStateProperty.resolveWith(label),
      discSize: 20,
      dotSize: ui.space.s2 + ui.space.s1 / 2,
      rowRadius: ui.shape.inner,
    );
  }
}

/// One option of a mutually exclusive group.
///
/// Built on `RawRadio`, so the group value, the arrow keys and the exclusive
/// semantics come from the SDK rather than from a second implementation of
/// them. It has to sit inside a [UiRadioGroup] of the same type.
///
/// Retires `Radio` and `RadioListTile`.
class UiRadio<T> extends StatefulWidget {
  /// A radio labelled [label] that selects [value].
  const UiRadio({
    super.key,
    required this.label,
    required this.value,
    this.focusNode,
    this.autofocus = false,
    this.enabled = true,
    this.disabledReason,
    this.semanticsLabel,
    this.showLabel = true,
  });

  /// What this option means. Sentence case, no terminal period.
  final String label;

  /// The value this option selects in its group.
  final T value;

  /// The node that owns focus for this option.
  final FocusNode? focusNode;

  /// True to take focus when first built.
  final bool autofocus;

  /// False for an option the reviewer cannot choose.
  final bool enabled;

  /// Why the option cannot be chosen, in the reviewer's words.
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// False where the row around the option already names it.
  final bool showLabel;

  @override
  State<UiRadio<T>> createState() => _UiRadioState<T>();
}

class _UiRadioState<T> extends State<UiRadio<T>> {
  FocusNode? _internalNode;

  FocusNode get _node => widget.focusNode ?? (_internalNode ??= FocusNode());

  @override
  void dispose() {
    _internalNode?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiRadioStyle style = UiRadioStyle.resolve(ui);
    final RadioGroupRegistry<T>? registry = RadioGroup.maybeOf<T>(context);
    final bool enabled = widget.enabled && registry != null;
    return Semantics(
      container: true,
      // `RawRadio` publishes the exclusive group and the checked state; this
      // adds the words, which it has no way to know.
      label: widget.semanticsLabel ?? widget.label,
      hint: enabled ? null : widget.disabledReason,
      // `enabled` is deliberately not set here. `RawRadio` states it, and two
      // statements of one flag are incompatible configurations, which splits
      // the control into two nodes: ours with the words and theirs with the
      // exclusive group. One node is the whole point.
      child: RawRadio<T>(
        value: widget.value,
        focusNode: _node,
        autofocus: widget.autofocus,
        toggleable: false,
        enabled: enabled,
        groupRegistry: registry,
        mouseCursor: const WidgetStatePropertyAll<MouseCursor>(
          SystemMouseCursors.click,
        ),
        builder: (BuildContext context, ToggleableStateMixin state) => _Option(
          style: style,
          states: state.states,
          label: widget.label,
          showLabel: widget.showLabel,
        ),
      ),
    );
  }
}

/// The disc, the label, the state layer and the focus ring.
class _Option extends StatelessWidget {
  const _Option({
    required this.style,
    required this.states,
    required this.label,
    required this.showLabel,
  });

  final UiRadioStyle style;
  final Set<WidgetState> states;
  final String label;
  final bool showLabel;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final ShapeBorder shape = Squircle.border(style.rowRadius);
    final Widget row = ConstrainedBox(
      constraints: const BoxConstraints(
        minWidth: UiDensity.hitBox,
        minHeight: UiDensity.hitBox,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          FocusRing(
            // `ToggleableStateMixin` sets `focused` from
            // `onShowFocusHighlight`, which is true only under
            // `FocusHighlightMode.traditional`. That is clause 4 of the
            // control contract, already computed for us.
            visible: states.contains(WidgetState.focused),
            // A disc is ringed by a circle. The ring used to take the row's
            // corner, which put a rounded rectangle around a circle and 20 dp
            // of empty label beside it (09 section 3.6, fit amendment).
            shape: FocusRingShape.circle,
            child: _Disc(style: style, states: states),
          ),
          if (showLabel) ...<Widget>[
            SizedBox(width: ui.space.s3),
            // The node above already reads these words.
            Flexible(
              child: ExcludeSemantics(
                child: Text(label, style: style.label.resolve(states)),
              ),
            ),
          ],
        ],
      ),
    );
    return Stack(
      alignment: Alignment.center,
      children: <Widget>[
        row,
        // The state layer lives outside `Pressable` here because `RawRadio`
        // owns the focus node and the gestures for a radio, and a second
        // `Pressable` around it would put two stops in the Tab order.
        Positioned.fill(
          child: IgnorePointer(
            child: StateLayer(states: states, shape: shape),
          ),
        ),
      ],
    );
  }
}

/// The 20 dp disc.
class _Disc extends StatelessWidget {
  const _Disc({required this.style, required this.states});

  final UiRadioStyle style;
  final Set<WidgetState> states;

  @override
  Widget build(BuildContext context) => SizedBox.square(
    dimension: style.discSize,
    child: DecoratedBox(
      decoration: ShapeDecoration(
        shape: CircleBorder(side: style.side.resolve(states)),
      ),
      child: Center(
        child: states.contains(WidgetState.selected)
            ? SizedBox.square(
                dimension: style.dotSize,
                child: DecoratedBox(
                  decoration: ShapeDecoration(
                    shape: const CircleBorder(),
                    color: style.dot.resolve(states),
                  ),
                ),
              )
            : const SizedBox.shrink(),
      ),
    ),
  );
}

/// The options that make up one choice.
///
/// `RadioGroup` carries the group role, the single selection and the arrow
/// keys that move within a group (WAI-ARIA's radio group pattern); this adds
/// the group's own label above the options and the rhythm between them.
class UiRadioGroup<T> extends StatelessWidget {
  /// A group named [label] whose current choice is [value].
  const UiRadioGroup({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
    required this.children,
    this.helpText,
    this.showLabel = true,
  });

  /// What the group chooses between. Sentence case, no terminal period.
  final String label;

  /// The option currently chosen, or null when none is.
  final T? value;

  /// Called with the option the reviewer chose.
  final ValueChanged<T?> onChanged;

  /// The options, normally [UiRadio] of the same type.
  final List<Widget> children;

  /// One line under the options saying what the choice does.
  final String? helpText;

  /// False where the surface around the group already names it.
  final bool showLabel;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        if (showLabel) ...<Widget>[
          // Read rather than excluded: it is the group's legend, and a
          // reviewer arriving at the first option needs to know what the
          // choice is about.
          Text(
            label,
            style: ui.type.label.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s2),
        ],
        RadioGroup<T>(
          groupValue: value,
          onChanged: onChanged,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: children,
          ),
        ),
        if (helpText != null) ...<Widget>[
          SizedBox(height: ui.space.s2),
          Text(
            helpText!,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      ],
    );
  }
}
