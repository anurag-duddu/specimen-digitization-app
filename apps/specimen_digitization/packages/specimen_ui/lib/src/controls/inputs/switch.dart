/// The switch (10 section 4.2, `UiSwitch`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';

/// The resolved paint of one switch.
///
/// The three measurements are written here rather than taken from the grid
/// because 10 section 4.2 gives the switch its own geometry: a 44 by 26 track
/// with a 22 dp thumb. They are named so a call site never restates them.
@immutable
class UiSwitchStyle {
  /// Binds every token a switch draws with.
  const UiSwitchStyle({
    required this.track,
    required this.side,
    required this.thumb,
    required this.label,
    required this.trackWidth,
    required this.trackHeight,
    required this.thumbSize,
    required this.glide,
  });

  /// The track's fill: `paper` when off, `ink` when on.
  final WidgetStateProperty<Color> track;

  /// The track's edge.
  final WidgetStateProperty<BorderSide> side;

  /// The thumb's fill.
  final WidgetStateProperty<Color> thumb;

  /// The label beside the track.
  final WidgetStateProperty<TextStyle> label;

  /// 44.
  final double trackWidth;

  /// 26.
  final double trackHeight;

  /// 22.
  final double thumbSize;

  /// How long the thumb takes to travel. Zero under reduced motion, which is
  /// the jump 09 section 8 asks for.
  final Duration glide;

  /// The inset between the thumb and the track, per side.
  double get thumbInset => (trackHeight - thumbSize) / 2;

  /// The style in [ui].
  static UiSwitchStyle resolve(UiThemeData ui) {
    Color track(Set<WidgetState> states) {
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

    // On, the thumb sits on `ink` and has to read as the light thing in the
    // pair; off, it sits on `paper` and has to read as the dark one. A thumb
    // that is `ink` in both states says "on" while the switch is off.
    Color thumb(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) {
        return ui.color.disabledContent;
      }
      return states.contains(WidgetState.selected)
          ? ui.color.paper
          : ui.color.inkSecondary;
    }

    TextStyle label(Set<WidgetState> states) => ui.type.body.copyWith(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledContent
          : ui.color.ink,
    );

    return UiSwitchStyle(
      track: WidgetStateProperty.resolveWith(track),
      side: WidgetStateProperty.resolveWith(side),
      thumb: WidgetStateProperty.resolveWith(thumb),
      label: WidgetStateProperty.resolveWith(label),
      trackWidth: 44,
      trackHeight: 26,
      thumbSize: 22,
      glide: ui.motion.short,
    );
  }
}

/// An on or off control.
///
/// A capsule track with a thumb that glides between the ends, and an optional
/// label at the start. The whole row is the hit box, so a reviewer aiming at
/// the words gets the switch.
///
/// Retires `Switch` and `SwitchListTile`.
class UiSwitch extends StatelessWidget {
  /// A switch labelled [label] that is on when [value] is true.
  const UiSwitch({
    super.key,
    required this.label,
    required this.value,
    this.onChanged,
    this.disabledReason,
    this.semanticsLabel,
    this.showLabel = true,
    this.autofocus = false,
  });

  /// What the switch turns on. Sentence case, no terminal period.
  final String label;

  /// True when the switch is on.
  final bool value;

  /// Called with the new value. Null disables the switch.
  final ValueChanged<bool>? onChanged;

  /// Why the switch is disabled, in the reviewer's words (03 section 3.6).
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// False where the row around the switch already names it.
  final bool showLabel;

  /// True to take focus when first built.
  final bool autofocus;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiSwitchStyle style = UiSwitchStyle.resolve(ui);
    return Pressable(
      semanticsLabel: semanticsLabel ?? label,
      role: PressableRole.toggle,
      checked: value,
      selected: value,
      onPressed: onChanged == null ? null : () => onChanged!(!value),
      disabledReason: disabledReason,
      autofocus: autofocus,
      capsule: true,
      builder: (BuildContext context, Set<WidgetState> states) => Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (showLabel) ...<Widget>[
            Flexible(child: Text(label, style: style.label.resolve(states))),
            SizedBox(width: ui.space.s3),
          ],
          _Track(style: style, states: states),
        ],
      ),
    );
  }
}

/// The track and the thumb.
class _Track extends StatelessWidget {
  const _Track({required this.style, required this.states});

  final UiSwitchStyle style;
  final Set<WidgetState> states;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: style.trackWidth,
    height: style.trackHeight,
    child: DecoratedBox(
      decoration: ShapeDecoration(
        shape: StadiumBorder(side: style.side.resolve(states)),
        color: style.track.resolve(states),
      ),
      child: Padding(
        padding: EdgeInsets.all(style.thumbInset),
        child: AnimatedAlign(
          alignment: states.contains(WidgetState.selected)
              ? AlignmentDirectional.centerEnd
              : AlignmentDirectional.centerStart,
          duration: style.glide,
          curve: MotionTokens.standardCurve,
          child: SizedBox.square(
            dimension: style.thumbSize,
            child: DecoratedBox(
              decoration: ShapeDecoration(
                shape: const CircleBorder(),
                color: style.thumb.resolve(states),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
