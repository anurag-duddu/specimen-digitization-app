/// The capsule button (10 section 4.1, `UiButton`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';

/// How much weight a button carries.
enum UiButtonVariant {
  /// The one high-contrast fill in the product: `ink` filled, `paper` text.
  primary,

  /// A `paper` fill with a `boundary` stroke and `ink` text.
  secondary,

  /// No fill, `ink` text, the state layer only.
  ghost,
}

/// The size a control is drawn at.
enum UiSize {
  /// 32 visual, 48 hit.
  sm,

  /// 40 or 48 by density.
  md,

  /// 56.
  lg,
}

/// The resolved paint of one button.
@immutable
class UiButtonStyle {
  /// Binds every token a button draws with.
  const UiButtonStyle({
    required this.background,
    required this.foreground,
    required this.side,
    required this.label,
    required this.padding,
    required this.minHeight,
  });

  /// The fill, by state.
  final WidgetStateProperty<Color> background;

  /// The text and glyph colour, by state.
  final WidgetStateProperty<Color> foreground;

  /// The edge, by state. Null for a variant with no edge.
  final WidgetStateProperty<BorderSide?> side;

  /// The label's type role.
  final TextStyle label;

  /// The padding inside the capsule.
  final EdgeInsetsGeometry padding;

  /// The visual height. The hit box is [UiDensity.hitBox] regardless.
  final double minHeight;

  /// The style for [variant] at [size] in [ui].
  static UiButtonStyle resolve(
    UiThemeData ui,
    UiButtonVariant variant,
    UiSize size,
  ) {
    Color fill(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) {
        return variant == UiButtonVariant.ghost
            ? ui.color.ground.withValues(alpha: 0)
            : ui.color.disabledFill;
      }
      return switch (variant) {
        UiButtonVariant.primary => ui.color.ink,
        UiButtonVariant.secondary => ui.color.paper,
        UiButtonVariant.ghost => ui.color.ground.withValues(alpha: 0),
      };
    }

    Color text(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) return ui.color.disabledContent;
      return variant == UiButtonVariant.primary
          ? ui.color.paper
          : ui.color.ink;
    }

    BorderSide? edge(Set<WidgetState> states) {
      if (variant != UiButtonVariant.secondary) return null;
      return BorderSide(
        color: states.contains(WidgetState.disabled)
            ? ui.color.disabledOutline
            : ui.color.boundary,
        width: ui.shape.stroke.boundary,
      );
    }

    return UiButtonStyle(
      background: WidgetStateProperty.resolveWith(fill),
      foreground: WidgetStateProperty.resolveWith(text),
      side: WidgetStateProperty.resolveWith(edge),
      label: size == UiSize.lg ? ui.type.title : ui.type.label,
      padding: EdgeInsetsDirectional.symmetric(
        horizontal: size == UiSize.sm ? ui.space.s3 : ui.space.s5,
      ),
      minHeight: switch (size) {
        UiSize.sm => 32,
        UiSize.md => ui.density.controlHeight,
        UiSize.lg => 56,
      },
    );
  }
}

/// A capsule button.
///
/// @experimental Wave 0 builds the three variants it needs to exercise
/// `Pressable` on the gallery: `primary`, `secondary` and `ghost` at size
/// `md`. Slot C1 completes the control per 10 section 4.1, which adds the
/// `danger` variant, the `sm` and `lg` sizes, the loading state and the
/// trailing glyph slot. Treat the API as unfinished until it does.
class UiButton extends StatelessWidget {
  /// A button labelled [label] that does [onPressed].
  const UiButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = UiButtonVariant.primary,
    this.size = UiSize.md,
    this.leading,
    this.disabledReason,
    this.semanticsLabel,
    this.autofocus = false,
  });

  /// The visible label. Verb first, two to four words (02 section 6 item 11).
  final String label;

  /// What the button does. Null disables it.
  final VoidCallback? onPressed;

  /// How much weight the button carries.
  final UiButtonVariant variant;

  /// The size the button is drawn at.
  final UiSize size;

  /// An optional leading glyph.
  final IconSpec? leading;

  /// Why the button is disabled, in the reviewer's words.
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// True to take focus when first built.
  final bool autofocus;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiButtonStyle style = UiButtonStyle.resolve(ui, variant, size);
    return Pressable(
      semanticsLabel: semanticsLabel ?? label,
      onPressed: onPressed,
      disabledReason: disabledReason,
      capsule: true,
      scaleOnPress: true,
      autofocus: autofocus,
      builder: (BuildContext context, Set<WidgetState> states) {
        final Color foreground = style.foreground.resolve(states);
        final BorderSide? side = style.side.resolve(states);
        return DecoratedBox(
          decoration: ShapeDecoration(
            shape: StadiumBorder(side: side ?? BorderSide.none),
            color: style.background.resolve(states),
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: style.minHeight),
            child: Padding(
              padding: style.padding,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  if (leading != null) ...<Widget>[
                    UiIcon(
                      leading!,
                      size: UiIconSize.inline,
                      color: foreground,
                    ),
                    SizedBox(width: ui.space.s2),
                  ],
                  Flexible(
                    child: Text(
                      label,
                      style: style.label.copyWith(color: foreground),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
