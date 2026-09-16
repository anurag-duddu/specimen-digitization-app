/// The capsule button (10 section 4.1, `UiButton`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import '../data/progress.dart';

/// How much weight a button carries.
enum UiButtonVariant {
  /// The one high-contrast fill in the product: `ink` filled, `paper` text.
  ///
  /// The disc inverts with the mode, dark on a light ground and light on a
  /// dark one, because both tokens follow the mode. 09 section 3.7 sets a 3:1
  /// floor and a fill that stayed dark in dark mode measures 1.08:1.
  primary,

  /// A `glass.flat` toned fill on `paper` with a `boundary` stroke and `ink`
  /// text.
  secondary,

  /// No fill, `ink` text, the state layer only.
  ghost,

  /// A fill of `status.blocked.content` with `paper` text, for an action that
  /// supersedes results a reviewer cannot get back (02 section 4.4).
  danger,
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
    required this.overlay,
    required this.side,
    required this.label,
    required this.padding,
    required this.minHeight,
    required this.gap,
  });

  /// The fill, by state.
  final WidgetStateProperty<Color> background;

  /// The text and glyph colour, by state.
  final WidgetStateProperty<Color> foreground;

  /// What the state layer lifts this variant's fill toward.
  ///
  /// One colour rather than a `WidgetStateProperty`, because the part that
  /// varies by state is the opacity, and that lives in `StateLayer` where the
  /// contract's two numbers are written once. A variant filled with `ink`
  /// lifts toward `paper`; every other variant lifts toward `ink`.
  final Color overlay;

  /// The edge, by state. Null for a variant with no edge.
  final WidgetStateProperty<BorderSide?> side;

  /// The label's type role.
  final TextStyle label;

  /// The padding inside the capsule.
  final EdgeInsetsGeometry padding;

  /// The visual height. The hit box is [UiDensity.hitBox] regardless.
  final double minHeight;

  /// The space between a glyph and the label.
  final double gap;

  /// The visual height of [size] in [ui].
  ///
  /// Public because a control that sits beside a button in a row has to match
  /// its height without copying the numbers out of the size table.
  static double heightOf(UiThemeData ui, UiSize size) => switch (size) {
    UiSize.sm => smallHeight,
    UiSize.md => ui.density.controlHeight,
    UiSize.lg => largeHeight,
  };

  /// 32, the `sm` row of the size table in 10 section 4.
  static const double smallHeight = 32;

  /// 56, the `lg` row. `md` is whatever the density says a control is.
  static const double largeHeight = 56;

  /// The style for [variant] at [size] in [ui].
  ///
  /// [loading] keeps the enabled paint while the control refuses activation:
  /// a button that is working is busy, not forbidden, and draining its fill
  /// would read as the server having taken the action away.
  static UiButtonStyle resolve(
    UiThemeData ui,
    UiButtonVariant variant,
    UiSize size, {
    bool loading = false,
  }) {
    bool off(Set<WidgetState> states) =>
        states.contains(WidgetState.disabled) && !loading;

    Color fill(Set<WidgetState> states) {
      if (off(states)) {
        return variant == UiButtonVariant.ghost
            ? transparent(ui)
            : ui.color.disabledFill;
      }
      return switch (variant) {
        UiButtonVariant.primary => ui.color.ink,
        // A button is a repeated item, and 09 section 11 rejects glass on
        // repeated items outright. The recipe in 10 section 4.1 is the flat
        // level's tone, so the fill is that tone composited onto `paper`: one
        // opaque colour, no `BackdropFilter`, nothing drawn against the pane
        // budget. In light it lands on `paper`; in dark it lifts off it,
        // which is what separates the variant from the ground behind it.
        UiButtonVariant.secondary => Color.alphaBlend(
          ui.glass.flat.fill,
          ui.color.paper,
        ),
        UiButtonVariant.ghost => transparent(ui),
        UiButtonVariant.danger => ui.color.status.blocked.content,
      };
    }

    Color text(Set<WidgetState> states) {
      if (off(states)) return ui.color.disabledContent;
      return switch (variant) {
        UiButtonVariant.primary || UiButtonVariant.danger => ui.color.paper,
        UiButtonVariant.secondary || UiButtonVariant.ghost => ui.color.ink,
      };
    }

    BorderSide? edge(Set<WidgetState> states) {
      if (variant != UiButtonVariant.secondary) return null;
      return BorderSide(
        color: off(states) ? ui.color.disabledOutline : ui.color.boundary,
        width: ui.shape.stroke.boundary,
      );
    }

    return UiButtonStyle(
      background: WidgetStateProperty.resolveWith(fill),
      foreground: WidgetStateProperty.resolveWith(text),
      // The filled variants lift toward `paper`, the outlined and ghost ones
      // toward `ink`. Without this, `ink` at 12 percent over an `ink` fill is
      // the same colour and the primary button, the one a reviewer presses
      // most, has no visible press at all.
      overlay: switch (variant) {
        UiButtonVariant.primary ||
        UiButtonVariant.danger => ui.color.paper,
        UiButtonVariant.secondary || UiButtonVariant.ghost => ui.color.ink,
      },
      side: WidgetStateProperty.resolveWith(edge),
      label: size == UiSize.lg ? ui.type.title : ui.type.label,
      padding: EdgeInsetsDirectional.symmetric(
        horizontal: switch (size) {
          UiSize.sm => ui.space.s3,
          UiSize.md => ui.space.s5,
          UiSize.lg => ui.space.s6,
        },
      ),
      minHeight: heightOf(ui, size),
      gap: ui.space.s2,
    );
  }

  /// A fill that is not there.
  ///
  /// `ghost` has no fill and the state layer is the whole of its feedback, so
  /// the colour has to exist without being seen.
  static Color transparent(UiThemeData ui) =>
      ui.color.ground.withValues(alpha: 0);
}

/// A capsule button.
///
/// Retires `FilledButton`, `OutlinedButton`, `TextButton` and
/// `FilledButton.tonal`.
///
/// The label is a verb first, two to four words, with no trailing punctuation
/// (02 section 4.3). While [loading] the caller moves the label to the present
/// participle and the leading slot holds the ring, so a reviewer who looked
/// away still reads which action is in flight.
class UiButton extends StatelessWidget {
  /// A button labelled [label] that does [onPressed].
  const UiButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = UiButtonVariant.primary,
    this.size = UiSize.md,
    this.leading,
    this.trailing,
    this.loading = false,
    this.disabledReason,
    this.semanticsLabel,
    this.focusNode,
    this.autofocus = false,
    this.statesController,
  });

  /// The visible label. Verb first, two to four words (02 section 4.3).
  final String label;

  /// What the button does. Null disables it.
  final VoidCallback? onPressed;

  /// How much weight the button carries.
  final UiButtonVariant variant;

  /// The size the button is drawn at.
  final UiSize size;

  /// An optional leading glyph, drawn at 20. The ring takes its slot while
  /// [loading].
  final IconSpec? leading;

  /// An optional trailing glyph, drawn at 20.
  final IconSpec? trailing;

  /// True while the action is in flight.
  ///
  /// The leading slot holds a 16 dp `UiProgress.ring` and the button refuses
  /// activation, so a reviewer cannot send the same decision twice.
  final bool loading;

  /// What the ring would be called if anything read it.
  ///
  /// `UiProgress` requires a label because an indicator has no text of its
  /// own, and `Pressable` drops the semantics of its content so that the
  /// button publishes one node under its own label. The ring inside a button
  /// is therefore never read aloud; the label exists because the indicator's
  /// contract is not weakened for being nested, and it says what the ring
  /// would say if the button ever stopped merging its content.
  static const String _workingLabel = 'Working';

  /// Why the button is disabled, in the reviewer's words.
  final String? disabledReason;

  /// Overrides the label a screen reader reads. Defaults to [label].
  final String? semanticsLabel;

  /// An external focus node, for a caller that moves focus itself.
  final FocusNode? focusNode;

  /// True to take focus when first built.
  final bool autofocus;

  /// An external states controller.
  ///
  /// A caller that has to read the button's states from outside it passes one,
  /// which is also how the gallery holds a button in a state a gesture would
  /// otherwise be needed for.
  final WidgetStatesController? statesController;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiButtonStyle style = UiButtonStyle.resolve(
      ui,
      variant,
      size,
      loading: loading,
    );
    return Pressable(
      semanticsLabel: semanticsLabel ?? label,
      onPressed: loading ? null : onPressed,
      disabledReason: disabledReason,
      capsule: true,
      scaleOnPress: true,
      focusNode: focusNode,
      autofocus: autofocus,
      statesController: statesController,
      stateLayerColour: style.overlay,
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
                  if (loading || leading != null) ...<Widget>[
                    _LeadingSlot(
                      // The slot is the glyph's own box in both states, so a
                      // button that starts loading keeps the width it had
                      // (10 section 4.1).
                      size: ui.space.iconInline,
                      child: loading
                          ? UiProgress.ring(
                              // The button's own foreground, because `ink` is
                              // a colour chosen against `paper` and would
                              // disappear on a filled variant. Indeterminate,
                              // so the ring draws no track: a track is a
                              // scale, and a button waiting on the server has
                              // none.
                              semanticsLabel: _workingLabel,
                              size: UiProgressSize.small,
                              color: foreground,
                            )
                          : UiIcon(
                              leading!,
                              size: UiIconSize.inline,
                              color: foreground,
                            ),
                    ),
                    SizedBox(width: style.gap),
                  ],
                  Flexible(
                    child: Text(
                      label,
                      style: style.label.copyWith(color: foreground),
                      textAlign: TextAlign.center,
                    ),
                  ),
                  if (trailing != null) ...<Widget>[
                    SizedBox(width: style.gap),
                    UiIcon(
                      trailing!,
                      size: UiIconSize.inline,
                      color: foreground,
                    ),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

/// A fixed box for the leading glyph, so the ring and the glyph occupy the
/// same width.
class _LeadingSlot extends StatelessWidget {
  const _LeadingSlot({required this.size, required this.child});

  final double size;
  final Widget child;

  @override
  Widget build(BuildContext context) =>
      SizedBox(width: size, height: size, child: Center(child: child));
}
