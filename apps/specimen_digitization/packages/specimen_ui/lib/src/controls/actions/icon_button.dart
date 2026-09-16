/// The icon button (10 section 4.1, `UiIconButton`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';
import 'button.dart';

/// How much weight an icon button carries.
///
/// There is no `primary` disc: an `ink` filled disc is the current navigation
/// destination (09 section 1), and a second meaning for the same shape is the
/// kind of collision one vocabulary exists to prevent.
enum UiIconButtonVariant {
  /// No fill, `ink` glyph, the state layer only.
  ghost,

  /// A `glass.flat` toned fill on `paper` with a `boundary` stroke.
  secondary,
}

/// The resolved paint of one icon button.
@immutable
class UiIconButtonStyle {
  /// Binds every token an icon button draws with.
  const UiIconButtonStyle({
    required this.background,
    required this.foreground,
    required this.side,
    required this.diameter,
  });

  /// The fill, by state.
  final WidgetStateProperty<Color> background;

  /// The glyph colour, by state.
  final WidgetStateProperty<Color> foreground;

  /// The edge, by state. Null for a variant with no edge.
  final WidgetStateProperty<BorderSide?> side;

  /// The visual diameter: 48 at touch, 40 at pointer. The hit box is
  /// [UiDensity.hitBox] in both.
  final double diameter;

  /// The style for [variant] in [ui].
  static UiIconButtonStyle resolve(
    UiThemeData ui,
    UiIconButtonVariant variant,
  ) {
    Color fill(Set<WidgetState> states) {
      // `ghost` has no fill in any state: a disabled ghost that grew one
      // would read as a different control rather than the same one turned
      // off. The state layer and the `disabled.content` glyph carry it.
      if (variant == UiIconButtonVariant.ghost) {
        return UiButtonStyle.transparent(ui);
      }
      return states.contains(WidgetState.disabled)
          ? ui.color.disabledFill
          : Color.alphaBlend(ui.glass.flat.fill, ui.color.paper);
    }

    Color glyph(Set<WidgetState> states) =>
        states.contains(WidgetState.disabled)
        ? ui.color.disabledContent
        : ui.color.ink;

    BorderSide? edge(Set<WidgetState> states) {
      if (variant != UiIconButtonVariant.secondary) return null;
      return BorderSide(
        color: states.contains(WidgetState.disabled)
            ? ui.color.disabledOutline
            : ui.color.boundary,
        width: ui.shape.stroke.boundary,
      );
    }

    return UiIconButtonStyle(
      background: WidgetStateProperty.resolveWith(fill),
      foreground: WidgetStateProperty.resolveWith(glyph),
      side: WidgetStateProperty.resolveWith(edge),
      diameter: ui.density.controlHeight,
    );
  }
}

/// A disc with one glyph in it.
///
/// Retires `IconButton`.
///
/// [semanticsLabel] is required because the control has no visible text
/// (10 section 11), and it doubles as the tooltip, so the two never disagree
/// (02 section 4.16). The tooltip is drawn by `UiTooltip` on hover and on
/// long press; a disabled button draws [disabledReason] there instead.
class UiIconButton extends StatelessWidget {
  /// A disc drawing [icon] that does [onPressed], announced as
  /// [semanticsLabel].
  const UiIconButton({
    super.key,
    required this.icon,
    required this.semanticsLabel,
    this.onPressed,
    this.variant = UiIconButtonVariant.ghost,
    this.tooltip,
    this.current = false,
    this.disabledReason,
    this.focusNode,
    this.autofocus = false,
  });

  /// Which meaning to draw, from the registry.
  final IconSpec icon;

  /// The label a screen reader reads. A complete phrase that stands alone:
  /// "Rotate the view", never "Rotate".
  final String semanticsLabel;

  /// What the button does. Null disables it.
  final VoidCallback? onPressed;

  /// How much weight the button carries.
  final UiIconButtonVariant variant;

  /// The hover and long-press tooltip. Defaults to [semanticsLabel].
  ///
  /// Overridden while the button is disabled with a [disabledReason], which
  /// is the one thing the reviewer needs more than the button's name.
  final String? tooltip;

  /// True to draw the glyph's fill form, where the registry entry has one.
  final bool current;

  /// Why the button is disabled, in the reviewer's words.
  final String? disabledReason;

  /// An external focus node, for a caller that moves focus itself.
  final FocusNode? focusNode;

  /// True to take focus when first built.
  final bool autofocus;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiIconButtonStyle style = UiIconButtonStyle.resolve(ui, variant);
    final String phrase = tooltip ?? semanticsLabel;
    // A button the server forbids owes the reviewer the reason rather than
    // its own label, so the reason form takes over: `Pressable` reports on
    // hover and on long press, and the tooltip draws whatever it reports
    // (03 section 3.6).
    final bool forbidden = onPressed == null && disabledReason != null;
    // `MergeSemantics` stays above the tooltip. Below it, the annotation and
    // the control sit inside an `OverlayPortal`, and a merged node whose
    // subtree is rebuilt that way trips
    // `SemanticsOwner.sendSemanticsUpdate`'s own assertion.
    return MergeSemantics(
      child: Semantics(
        tooltip: phrase,
        child: forbidden
            ? UiTooltip.reason(
                builder:
                    (BuildContext context, ValueChanged<String> report) =>
                        _disc(style, onDisabledReason: report),
              )
            : UiTooltip(message: phrase, child: _disc(style)),
      ),
    );
  }

  /// The disc itself.
  Widget _disc(
    UiIconButtonStyle style, {
    ValueChanged<String>? onDisabledReason,
  }) => Pressable(
    semanticsLabel: semanticsLabel,
    onPressed: onPressed,
    disabledReason: disabledReason,
    onDisabledReason: onDisabledReason,
    capsule: true,
    scaleOnPress: true,
    focusNode: focusNode,
    autofocus: autofocus,
    builder: (BuildContext context, Set<WidgetState> states) {
      final BorderSide? side = style.side.resolve(states);
      return SizedBox.square(
        dimension: style.diameter,
        child: DecoratedBox(
          decoration: ShapeDecoration(
            shape: CircleBorder(side: side ?? BorderSide.none),
            color: style.background.resolve(states),
          ),
          child: Center(
            child: UiIcon(
              icon,
              current: current,
              color: style.foreground.resolve(states),
            ),
          ),
        ),
      );
    },
  );
}
