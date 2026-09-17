/// The chip (10 section 4.1, `UiChip`).
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../foundation/color.dart';
import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';
import 'button.dart';

/// What a chip is for.
enum UiChipVariant {
  /// Static. A `paper` fill with a `hairline` stroke, or a status triple's
  /// fill when the chip names a status. Nothing to press.
  tag,

  /// Toggleable. Fills `ink` at 8 percent when selected, with the `emphasis`
  /// stroke.
  filter,

  /// A value the reviewer entered, with a remove glyph at the end.
  input,
}

/// The resolved paint of one chip.
@immutable
class UiChipStyle {
  /// Binds every token a chip draws with.
  const UiChipStyle({
    required this.background,
    required this.foreground,
    required this.side,
    required this.label,
    required this.padding,
    required this.height,
    required this.gap,
    required this.removeTarget,
    required this.leadingSize,
  });

  /// The fill, by state.
  final WidgetStateProperty<Color> background;

  /// The text and glyph colour, by state.
  final WidgetStateProperty<Color> foreground;

  /// The edge, by state.
  final WidgetStateProperty<BorderSide> side;

  /// The label's type role.
  final TextStyle label;

  /// The padding inside the capsule, before the remove target is added.
  final EdgeInsetsGeometry padding;

  /// The visual height: the `sm` row of the size table, grown with the text
  /// (11 section 2.2), so 32 in both densities at scale 1.0.
  final double height;

  /// The space between a glyph and the label.
  final double gap;

  /// The remove glyph's hit box, which is larger than the chip it sits in.
  final double removeTarget;

  /// The leading widget slot's box: `inline`, so an avatar or a swatch is the
  /// size of the glyph it stands in for.
  final double leadingSize;

  /// The style for [variant] in [ui], tinted by [status] where the chip names
  /// one, at [textScaler].
  static UiChipStyle resolve(
    UiThemeData ui,
    UiChipVariant variant, {
    UiStatusTriple? status,
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    Color fill(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) return ui.color.disabledFill;
      if (variant == UiChipVariant.filter &&
          states.contains(WidgetState.selected)) {
        // 10 section 4.1 asks for `ink` at 8 percent. `hoverOpacity` is the
        // token carrying 8 percent in light and the dark column's
        // counterpart, so the selected fill tracks the mode the way every
        // other overlay in the system does instead of pinning a literal.
        return ui.color.stateLayer(ui.color.hoverOpacity);
      }
      return status?.fill ?? ui.color.paper;
    }

    Color text(Set<WidgetState> states) => states.contains(WidgetState.disabled)
        ? ui.color.disabledContent
        : status?.onFill ?? ui.color.ink;

    BorderSide edge(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) {
        return BorderSide(
          color: ui.color.disabledOutline,
          width: ui.shape.stroke.boundary,
        );
      }
      return switch (variant) {
        UiChipVariant.filter => BorderSide(
          color: states.contains(WidgetState.selected)
              ? ui.color.ink
              : ui.color.boundary,
          width: states.contains(WidgetState.selected)
              ? ui.shape.stroke.emphasis
              : ui.shape.stroke.boundary,
        ),
        UiChipVariant.tag || UiChipVariant.input => BorderSide(
          color: ui.color.hairline,
          width: ui.shape.stroke.hairline,
        ),
      };
    }

    return UiChipStyle(
      background: WidgetStateProperty.resolveWith(fill),
      foreground: WidgetStateProperty.resolveWith(text),
      side: WidgetStateProperty.resolveWith(edge),
      label: ui.type.label,
      padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s3),
      height: UiType.heightAroundAt(
        UiButtonStyle.smallHeight,
        ui.type.label,
        textScaler,
      ),
      gap: ui.space.s2,
      removeTarget: UiDensity.hitBox,
      leadingSize: ui.space.iconInline,
    );
  }
}

/// A small capsule carrying one word or one entered value.
///
/// Retires `Chip`, `InputChip` and `ActionChip`.
///
/// Never glass: a chip is a repeated item and 09 section 11 rejects glass on
/// repeated items outright.
class UiChip extends StatelessWidget {
  /// A chip reading [label].
  const UiChip({
    super.key,
    required this.label,
    this.variant = UiChipVariant.tag,
    this.icon,
    this.leading,
    this.status,
    this.selected = false,
    this.onPressed,
    this.onRemove,
    this.semanticsLabel,
    this.removeSemanticsLabel,
    this.disabledReason,
  }) : assert(
         onPressed == null || variant == UiChipVariant.filter,
         'only a filter chip is pressed; a tag is static and an input chip is '
         'removed rather than activated',
       ),
       assert(
         onRemove == null || variant == UiChipVariant.input,
         'the remove glyph belongs to the input variant',
       ),
       assert(
         icon == null || leading == null,
         'a chip carries one thing before its label: a registry glyph or the '
         'widget that stands where one would',
       );

  /// The visible label. Sentence case, one to three words.
  final String label;

  /// What the chip is for.
  final UiChipVariant variant;

  /// An optional leading glyph, drawn at 16.
  final IconSpec? icon;

  /// An optional widget before the label, drawn in an `inline` box.
  ///
  /// An avatar, a colour swatch, or a determinate ring where the state the
  /// chip names is a measured fraction. The slot 10 section 5 needs for the
  /// `StatusChip` pattern, which drew its own capsule around a ring while the
  /// slot did not exist. Mutually exclusive with [icon]: one thing stands
  /// before the label, not two.
  final Widget? leading;

  /// The status triple this chip names, where it names one.
  ///
  /// The `StatusChip` pattern (10 section 5) is a `tag` with a triple and a
  /// registry glyph. Status is never colour alone, so a chip with a triple
  /// still carries its word and its glyph.
  final UiStatusTriple? status;

  /// True when a `filter` chip is on.
  final bool selected;

  /// What activation does on a `filter` chip. Null disables it.
  final VoidCallback? onPressed;

  /// What the remove glyph does on an `input` chip. Null draws no glyph.
  final VoidCallback? onRemove;

  /// Overrides the label a screen reader reads for the chip itself.
  final String? semanticsLabel;

  /// The label a screen reader reads for the remove glyph. Defaults to
  /// "Remove" followed by the chip's label, which stands alone out of
  /// context (02 section 4.16).
  final String? removeSemanticsLabel;

  /// Why a `filter` chip is disabled, in the reviewer's words.
  final String? disabledReason;

  /// The narrowest width this chip draws the whole of its label at
  /// (11 section 3.3).
  double _intrinsicWidth(
    BuildContext context,
    UiThemeData ui,
    UiChipStyle style,
  ) {
    final double before = switch ((icon, leading)) {
      (final IconSpec _, _) => ui.space.iconSmall + style.gap,
      (_, final Widget _) => style.leadingSize + style.gap,
      _ => 0.0,
    };
    final double body =
        before + measureLabel(context, label, style.label).width;
    return switch (variant) {
      UiChipVariant.filter => math.max(
        UiDensity.hitBox,
        body + style.padding.horizontal,
      ),
      // The capsule's start padding, the content, and the remove target,
      // which keeps its own 48 dp box inside a 32 dp capsule.
      UiChipVariant.input when onRemove != null =>
        ui.space.s3 + body + style.removeTarget,
      UiChipVariant.tag ||
      UiChipVariant.input => body + style.padding.horizontal,
    };
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiChipStyle style = UiChipStyle.resolve(
      ui,
      variant,
      status: status,
      textScaler: MediaQuery.textScalerOf(context),
    );
    // 11 section 3.3 gives a chip no compact variant: one declared
    // arrangement, and an ellipsis with the whole label on a tooltip when the
    // row it sits in has run out of room for it.
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth: _intrinsicWidth(context, ui, style),
          builder: (BuildContext context, bool lastResort) {
            final Widget capsule = switch (variant) {
              UiChipVariant.filter => _buildFilter(style),
              UiChipVariant.input when onRemove != null => _buildInput(
                context,
                style,
              ),
              UiChipVariant.tag || UiChipVariant.input => _buildStatic(style),
            };
            return lastResort
                ? UiTooltip(message: label, child: capsule)
                : capsule;
          },
        ),
      ],
    );
  }

  /// The capsule and its contents, painted from [states].
  Widget _body(UiChipStyle style, Set<WidgetState> states) => DecoratedBox(
    decoration: ShapeDecoration(
      shape: StadiumBorder(side: style.side.resolve(states)),
      color: style.background.resolve(states),
    ),
    child: ConstrainedBox(
      constraints: BoxConstraints(minHeight: style.height),
      child: Padding(
        padding: style.padding,
        child: _content(style, style.foreground.resolve(states)),
      ),
    ),
  );

  /// What stands before the label, and the label, in reading order.
  Widget _content(UiChipStyle style, Color foreground) => Row(
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      if (icon != null) ...<Widget>[
        UiIcon(icon!, size: UiIconSize.small, color: foreground),
        SizedBox(width: style.gap),
      ] else if (leading != null) ...<Widget>[
        SizedBox.square(
          dimension: style.leadingSize,
          child: Center(child: leading),
        ),
        SizedBox(width: style.gap),
      ],
      Flexible(
        child: UiLabel(label, style: style.label.copyWith(color: foreground)),
      ),
    ],
  );

  /// A chip with nothing to press. One merged semantics node, so a glyph and
  /// a word are read as one thing.
  Widget _buildStatic(UiChipStyle style) {
    final Widget body = _body(style, const <WidgetState>{});
    return MergeSemantics(
      child: semanticsLabel == null
          ? body
          : Semantics(
              label: semanticsLabel,
              excludeSemantics: true,
              child: body,
            ),
    );
  }

  /// A chip that toggles.
  Widget _buildFilter(UiChipStyle style) => Pressable(
    semanticsLabel: semanticsLabel ?? label,
    onPressed: onPressed,
    disabledReason: disabledReason,
    role: PressableRole.toggle,
    checked: selected,
    selected: selected,
    capsule: true,
    scaleOnPress: true,
    builder: (BuildContext context, Set<WidgetState> states) =>
        _body(style, states),
  );

  /// A chip carrying an entered value, with its own remove target.
  ///
  /// The capsule stays at the `sm` height while the remove glyph keeps the
  /// 48 dp target the contract sets, so the row is as tall as that target and
  /// the capsule is drawn centred inside it. That is the transparent slop
  /// density already uses, spent on one child rather than on the whole
  /// control. Nesting the remove glyph inside a pressable chip would have
  /// been the other way to reach it, and `Pressable` drops the semantics of
  /// its own content, so the remove glyph would have lost its label.
  Widget _buildInput(BuildContext context, UiChipStyle style) {
    final UiThemeData ui = context.ui;
    const Set<WidgetState> rest = <WidgetState>{};
    return Stack(
      alignment: Alignment.center,
      children: <Widget>[
        Positioned.fill(
          child: Center(
            child: SizedBox(
              width: double.infinity,
              height: style.height,
              child: DecoratedBox(
                decoration: ShapeDecoration(
                  shape: StadiumBorder(side: style.side.resolve(rest)),
                  color: style.background.resolve(rest),
                ),
              ),
            ),
          ),
        ),
        Padding(
          padding: EdgeInsetsDirectional.only(start: ui.space.s3),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Flexible(
                child: MergeSemantics(
                  child: Semantics(
                    label: semanticsLabel ?? label,
                    excludeSemantics: true,
                    child: _content(style, style.foreground.resolve(rest)),
                  ),
                ),
              ),
              Pressable(
                semanticsLabel: removeSemanticsLabel ?? 'Remove $label',
                onPressed: onRemove,
                capsule: true,
                minHitBox: style.removeTarget,
                builder: (BuildContext context, Set<WidgetState> states) =>
                    UiIcon(
                      UiIcons.close,
                      size: UiIconSize.small,
                      color: style.foreground.resolve(states),
                    ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
