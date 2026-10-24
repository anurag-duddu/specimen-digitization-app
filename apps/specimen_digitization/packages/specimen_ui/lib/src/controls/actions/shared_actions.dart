/// General-purpose action and annotation variants for the component library.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import '../../foundation/color.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/pressable.dart';
import '../data/progress.dart';
import '../inputs/checkbox.dart';
import '../overlays/tooltip.dart';
import 'icon_button.dart';

/// Visual emphasis independent of command meaning.
enum UiActionHierarchy {
  /// A solid high-emphasis surface.
  filled,

  /// A boundary without a solid fill.
  outline,

  /// A low-emphasis tinted surface.
  subtle,

  /// An inline text link with an underline.
  link,
}

/// Semantic color roles available to commands.
enum UiActionTone {
  /// Obsidian and paper for ordinary actions.
  neutral,

  /// Iris for a brand-accented action.
  brand,

  /// The blocked/error role for a destructive action.
  destructive,
}

/// Visual command sizes that preserve a 48 dp target.
enum UiActionSize {
  /// Compact visual size.
  small,

  /// Default visual size.
  medium,

  /// Large visual size.
  large,

  /// Prominent visual size.
  extraLarge,

  /// Largest visual size for standalone actions.
  doubleExtraLarge,
}

/// An action with independent emphasis, tone, size and content anatomy.
///
/// Every visual size retains a 48 dp hit target. Busy suppresses duplicate
/// submissions. Icon-only actions require [label], which remains accessible.
class UiActionButton extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiActionButton({
    super.key,
    required this.label,
    this.onPressed,
    this.hierarchy = UiActionHierarchy.filled,
    this.tone = UiActionTone.neutral,
    this.size = UiActionSize.medium,
    this.leading,
    this.trailing,
    this.leadingDot = false,
    this.iconOnly = false,
    this.busy = false,
    this.disabledReason,
    this.focusNode,
    this.statesController,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The host action; `null` makes the command unavailable.
  final VoidCallback? onPressed;

  /// The visual emphasis of the command.
  final UiActionHierarchy hierarchy;

  /// The semantic color role, separate from emphasis.
  final UiActionTone tone;

  /// The visual size; interactive targets retain their accessible minimum.
  final UiActionSize size;

  /// The optional content before the main label.
  final IconSpec? leading;

  /// The optional content after the main label.
  final IconSpec? trailing;

  /// Whether a status dot replaces the leading icon.
  final bool leadingDot;

  /// Whether the visual label is omitted while its accessible name remains.
  final bool iconOnly;

  /// Whether work is underway and duplicate activation is suppressed.
  final bool busy;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  /// The optional host-managed keyboard focus node.
  final FocusNode? focusNode;

  /// The optional controller for pointer, keyboard and disabled states.
  final WidgetStatesController? statesController;

  @override
  Widget build(BuildContext context) {
    assert(!iconOnly || leading != null);
    final ui = context.ui;
    final triple = switch (tone) {
      UiActionTone.brand => ui.brand.secondary,
      UiActionTone.destructive => ui.color.status.blocked,
      UiActionTone.neutral => UiStatusTriple(
        content: ui.color.ink,
        fill: ui.color.matte,
        onFill: ui.color.ink,
      ),
    };
    final height = <double>[32, 40, 48, 56, 64][size.index];
    Widget control = Pressable(
      semanticsLabel: label,
      onPressed: busy ? null : onPressed,
      busy: busy,
      disabledReason: disabledReason,
      focusNode: focusNode,
      statesController: statesController,
      radius: ui.shape.inner,
      stateLayerColour: hierarchy == UiActionHierarchy.filled
          ? ui.color.paper
          : null,
      builder: (context, states) {
        final disabled = states.contains(WidgetState.disabled);
        final foreground = disabled
            ? ui.color.disabledContent
            : hierarchy == UiActionHierarchy.filled
            ? ui.color.paper
            : triple.content;
        final fill = disabled
            ? ui.color.disabledFill
            : hierarchy == UiActionHierarchy.filled
            ? triple.content
            : hierarchy == UiActionHierarchy.subtle
            ? triple.fill
            : ui.color.paper.withValues(alpha: 0);
        return Container(
          constraints: BoxConstraints(minHeight: height),
          padding: EdgeInsets.symmetric(vertical: ui.space.s2),
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(ui.shape.inner),
            border: hierarchy == UiActionHierarchy.outline
                ? Border.all(
                    color: disabled ? ui.color.disabledOutline : triple.content,
                  )
                : null,
          ),
          child: _content(context, foreground),
        );
      },
    );
    if (iconOnly) {
      control = MergeSemantics(
        child: UiTooltip(
          message: disabledReason ?? label,
          excludeSemantics: true,
          child: control,
        ),
      );
    }
    return control;
  }

  Widget _content(BuildContext context, Color foreground) {
    final ui = context.ui;
    final leadingWidth = busy
        ? UiProgressSize.small.diameter
        : leadingDot
        ? ui.space.s2
        : ui.space.iconInline;
    final minimumContent = iconOnly
        ? leadingWidth
        : measureLabel(context, '…', ui.type.label).width;
    return LayoutBuilder(
      builder: (context, constraints) {
        final requestedInset = iconOnly ? ui.space.s3 : ui.space.s4;
        final inset = constraints.hasBoundedWidth
            ? math.min(
                requestedInset,
                math.max(0.0, (constraints.maxWidth - minimumContent) / 2),
              )
            : requestedInset;
        final available = constraints.maxWidth - inset * 2;
        var showLeading = busy || leadingDot || leading != null;
        var showTrailing = !iconOnly && trailing != null;
        double requiredWidth() =>
            minimumContent +
            (showLeading ? leadingWidth + ui.space.s2 : 0) +
            (showTrailing ? ui.space.iconInline + ui.space.s2 : 0);
        // Preserve the readable action before decorative content in a narrow
        // host. Icon-only commands keep the icon that identifies the action.
        if (!iconOnly && requiredWidth() > available) showTrailing = false;
        if (!iconOnly && requiredWidth() > available) showLeading = false;
        final row = Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            if (showLeading)
              if (busy)
                UiProgress.ring(
                  semanticsLabel: '$label in progress',
                  size: UiProgressSize.small,
                  color: foreground,
                )
              else if (leadingDot)
                Container(
                  width: ui.space.s2,
                  height: ui.space.s2,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: foreground,
                  ),
                )
              else
                UiIcon(leading!, color: foreground, size: UiIconSize.inline),
            if (!iconOnly) ...[
              if (showLeading) SizedBox(width: ui.space.s2),
              Flexible(
                child: Text(
                  label,
                  textAlign: TextAlign.center,
                  style: ui.type.label.copyWith(
                    color: foreground,
                    decoration: hierarchy == UiActionHierarchy.link
                        ? TextDecoration.underline
                        : null,
                  ),
                ),
              ),
              if (showTrailing) ...[
                SizedBox(width: ui.space.s2),
                UiIcon(trailing!, color: foreground, size: UiIconSize.inline),
              ],
            ],
          ],
        );
        return Padding(
          padding: EdgeInsets.symmetric(horizontal: inset),
          child: busy && !showLeading
              ? Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    row,
                    SizedBox(height: ui.space.s1),
                    SizedBox(
                      width: available,
                      height: ui.space.s1,
                      child: UiProgress.bar(
                        semanticsLabel: '$label in progress',
                        color: foreground,
                      ),
                    ),
                  ],
                )
              : row,
        );
      },
    );
  }
}

/// Boundary shapes for textual badges.
enum UiBadgeShape {
  /// A fully rounded capsule.
  pill,

  /// A small rounded rectangle.
  rounded,

  /// A rounded rectangle with a visible boundary.
  modern,

  /// A rectangular badge with square corners.
  square,
}

/// Contrast treatments for textual badges.
enum UiBadgeEmphasis {
  /// A semantic tint with readable text.
  soft,

  /// A semantic outline on the paper surface.
  outline,

  /// A semantic content-colored fill with paper text.
  solid,
}

/// The visual density of badges and tags; actions keep their minimum hit target.
enum UiAnnotationSize {
  /// Compact annotation text and padding.
  small,

  /// Default annotation text and padding.
  medium,

  /// Roomier annotation text and padding.
  large,
}

/// A labeled badge; its meaning is expressed in text, never color alone.
class UiStatusBadge extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiStatusBadge({
    super.key,
    required this.label,
    this.status,
    this.brand = false,
    this.shape = UiBadgeShape.pill,
    this.emphasis = UiBadgeEmphasis.soft,
    this.size = UiAnnotationSize.small,
    this.leading,
    this.trailing,
    this.onRemove,
    this.iconOnly = false,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The host-reported semantic state.
  final UiStatusTriple? status;

  /// Whether to use the secondary brand color instead of neutral paint.
  final bool brand;

  /// The shape of the annotation boundary.
  final UiBadgeShape shape;

  /// The fill and outline contrast treatment.
  final UiBadgeEmphasis emphasis;

  /// The visual size; interactive targets retain their accessible minimum.
  final UiAnnotationSize size;

  /// The optional content before the main label.
  final Widget? leading;

  /// The optional content after the main label.
  final Widget? trailing;

  /// The optional independently named remove action.
  final VoidCallback? onRemove;

  /// Whether to display only [leading], retaining [label] for accessibility.
  final bool iconOnly;

  @override
  Widget build(BuildContext context) {
    assert(!iconOnly || leading != null);
    final ui = context.ui;
    final triple =
        status ??
        (brand
            ? ui.brand.secondary
            : UiStatusTriple(
                content: ui.color.inkSecondary,
                fill: ui.color.matte,
                onFill: ui.color.ink,
              ));
    final foreground = emphasis == UiBadgeEmphasis.solid
        ? ui.color.paper
        : emphasis == UiBadgeEmphasis.soft
        ? triple.onFill
        : triple.content;
    return Semantics(
      label: onRemove == null || iconOnly ? label : null,
      container: onRemove != null,
      explicitChildNodes: onRemove != null,
      excludeSemantics: onRemove == null,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: size == UiAnnotationSize.large
              ? ui.space.s3
              : ui.space.s2,
          vertical: size == UiAnnotationSize.small ? ui.space.s1 : ui.space.s2,
        ),
        decoration: BoxDecoration(
          color: emphasis == UiBadgeEmphasis.solid
              ? triple.content
              : emphasis == UiBadgeEmphasis.soft
              ? triple.fill
              : ui.color.paper,
          border:
              emphasis == UiBadgeEmphasis.outline ||
                  shape == UiBadgeShape.modern
              ? Border.all(
                  color: emphasis == UiBadgeEmphasis.outline
                      ? triple.content
                      : ui.color.boundary,
                )
              : null,
          borderRadius: BorderRadius.circular(
            shape == UiBadgeShape.pill
                ? ui.space.readingMax
                : shape == UiBadgeShape.square
                ? 0
                : ui.shape.inner,
          ),
        ),
        child: IconTheme(
          data: IconThemeData(color: foreground),
          child: DefaultTextStyle(
            style:
                (size == UiAnnotationSize.small
                        ? ui.type.labelSmall
                        : ui.type.label)
                    .copyWith(color: foreground),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (leading != null) ...[
                  ExcludeSemantics(child: leading!),
                  if (!iconOnly) SizedBox(width: ui.space.s1),
                ],
                if (!iconOnly) Flexible(child: Text(label)),
                if (trailing != null) ...[
                  SizedBox(width: ui.space.s1),
                  ExcludeSemantics(child: trailing!),
                ],
                if (onRemove != null)
                  UiIconButton(
                    icon: UiIcons.close,
                    semanticsLabel: 'Remove $label',
                    onPressed: onRemove,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A badge and supporting announcement, optionally one navigable action.
class UiBadgeGroup extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiBadgeGroup({
    super.key,
    required this.badge,
    required this.label,
    this.badgeTrailing = false,
    this.onPressed,
  });

  /// The leading or trailing annotation.
  final UiStatusBadge badge;

  /// The visible and accessible name of the control.
  final String label;

  /// Whether the badge follows the supporting announcement.
  final bool badgeTrailing;

  /// The host action; `null` makes the command unavailable.
  final VoidCallback? onPressed;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final content = Padding(
      padding: EdgeInsets.all(ui.space.s2),
      child: Wrap(
        spacing: ui.space.s2,
        runSpacing: ui.space.s2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          if (!badgeTrailing) badge,
          Text(label, style: ui.type.bodySmall),
          if (badgeTrailing) badge,
          if (onPressed != null)
            const UiIcon(UiIcons.next, size: UiIconSize.inline),
        ],
      ),
    );
    return onPressed == null
        ? MergeSemantics(child: content)
        : Pressable(
            semanticsLabel: '${badge.label}. $label',
            onPressed: onPressed,
            radius: ui.shape.inner,
            builder: (context, states) => content,
          );
  }
}

/// A value tag with optional checkbox, count, leading identity and removal.
///
/// Selection and remove are separate native actions. Null [selected] makes
/// the tag informational; non-null adds a checkbox (null callback disables it).
class UiTag extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiTag({
    super.key,
    required this.label,
    this.leading,
    this.count,
    this.selected,
    this.onSelected,
    this.onRemove,
    this.disabledReason,
    this.size = UiAnnotationSize.medium,
    this.enabled = true,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The optional content before the main label.
  final Widget? leading;

  /// The optional item count announced with the tag.
  final int? count;

  /// The current selection accepted by the host.
  final bool? selected;

  /// The callback proposing the next checked state; `null` disables selection.
  final ValueChanged<bool>? onSelected;

  /// The optional independent remove action.
  final VoidCallback? onRemove;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;

  /// The visual size; interactive targets retain their accessible minimum.
  final UiAnnotationSize size;

  /// Whether selection and removal are available.
  final bool enabled;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Container(
      decoration: BoxDecoration(
        color: enabled ? ui.color.paper : ui.color.disabledFill,
        border: Border.all(color: ui.color.boundary),
        borderRadius: BorderRadius.circular(ui.shape.inner),
      ),
      padding: EdgeInsetsDirectional.only(
        start: ui.space.s2,
        end: onRemove == null ? ui.space.s2 : 0,
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          // A short count keeps its natural width. Only a long count is capped
          // so the flexible label still has room to wrap beside it.
          final countMaxWidth =
              (constraints.maxWidth -
                      (onRemove == null ? 0 : ui.space.targetMin) -
                      ui.space.s2)
                  .clamp(0.0, double.infinity) /
              2;
          return Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (leading != null) ...[
                ExcludeSemantics(child: leading!),
                SizedBox(width: ui.space.s2),
              ],
              Flexible(
                child: selected == null
                    ? Padding(
                        padding: EdgeInsets.symmetric(
                          vertical: size == UiAnnotationSize.small
                              ? ui.space.s1
                              : size == UiAnnotationSize.large
                              ? ui.space.s3
                              : ui.space.s2,
                        ),
                        child: Text(
                          label,
                          style: size == UiAnnotationSize.small
                              ? ui.type.labelSmall
                              : ui.type.label,
                        ),
                      )
                    : UiCheckbox(
                        label: label,
                        value: selected,
                        onChanged: enabled ? onSelected : null,
                        disabledReason: disabledReason,
                      ),
              ),
              if (count != null) ...[
                SizedBox(width: ui.space.s2),
                ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: countMaxWidth),
                  child: Semantics(
                    label: '$count items',
                    child: ExcludeSemantics(
                      child: Text('$count', style: ui.type.labelSmall),
                    ),
                  ),
                ),
              ],
              if (onRemove != null)
                UiIconButton(
                  icon: UiIcons.close,
                  semanticsLabel: 'Remove $label',
                  onPressed: enabled ? onRemove : null,
                  disabledReason: disabledReason,
                ),
            ],
          );
        },
      ),
    );
  }
}

/// A provider action using a caller-supplied, approved identity mark.
///
/// Use the actual provider asset in [mark], rather than approximating a logo
/// with a product icon. The host owns authentication and availability. Every
/// mode exposes [label] as one action and preserves the 48 dp minimum target.
class UiProviderButton extends StatelessWidget {
  /// Creates a provider action without initiating a connection itself.
  const UiProviderButton({
    super.key,
    required this.label,
    required this.mark,
    this.onPressed,
    this.supporting,
    this.supportingAbove = false,
    this.iconOnly = false,
    this.inverse = false,
    this.disabledReason,
  });

  /// The complete accessible action, such as “Continue with Google”.
  final String label;

  /// Provider-approved artwork; treated as decorative inside the action.
  final Widget mark;

  /// Invoked once when the host allows the action; null disables it.
  final VoidCallback? onPressed;

  /// Optional context beneath the main action.
  final String? supporting;

  /// Whether the supporting caption precedes the main label.
  final bool supportingAbove;

  /// Omits the visible text while retaining the full accessible label.
  final bool iconOnly;

  /// Draws an ink surface with paper text.
  final bool inverse;

  /// Why an unavailable provider cannot be activated.
  final String? disabledReason;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final control = Pressable(
      semanticsLabel: [label, ?supporting].join('. '),
      onPressed: onPressed,
      disabledReason: disabledReason,
      radius: ui.shape.inner,
      builder: (context, states) {
        final disabled = states.contains(WidgetState.disabled);
        final foreground = disabled
            ? ui.color.disabledContent
            : inverse
            ? ui.color.paper
            : ui.color.ink;
        return Container(
          constraints: BoxConstraints(minHeight: ui.space.targetMin),
          padding: EdgeInsets.all(ui.space.s3),
          decoration: BoxDecoration(
            color: disabled
                ? ui.color.disabledFill
                : inverse
                ? ui.color.ink
                : ui.color.paper,
            border: Border.all(
              color: disabled ? ui.color.disabledOutline : ui.color.boundary,
            ),
            borderRadius: BorderRadius.circular(ui.shape.inner),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ExcludeSemantics(
                child: SizedBox.square(
                  dimension: ui.space.s6,
                  child: FittedBox(child: mark),
                ),
              ),
              if (!iconOnly) ...[
                SizedBox(width: ui.space.s3),
                Flexible(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (supporting != null && supportingAbove)
                        Text(
                          supporting!,
                          style: ui.type.bodySmall.copyWith(color: foreground),
                        ),
                      Text(
                        label,
                        style: ui.type.label.copyWith(color: foreground),
                      ),
                      if (supporting != null && !supportingAbove)
                        Text(
                          supporting!,
                          style: ui.type.bodySmall.copyWith(color: foreground),
                        ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
    return iconOnly
        ? UiTooltip(message: label, excludeSemantics: true, child: control)
        : control;
  }
}

/// A store-download badge with approved artwork and accessible host action.
///
/// The same anatomy supports any store through explicit [storeName], [caption]
/// and [mark]; it never invents a store logo or opens an unprovided URL.
class UiStoreBadge extends StatelessWidget {
  /// Creates a store badge using the supplied store identity.
  const UiStoreBadge({
    super.key,
    required this.storeName,
    required this.caption,
    required this.mark,
    this.onPressed,
    this.inverse = true,
    this.disabledReason,
  });

  /// Display name of the store.
  final String storeName;

  /// Supporting caption, for example “Download on”.
  final String caption;

  /// Approved store artwork.
  final Widget mark;

  /// Host-owned store navigation; null disables the badge.
  final VoidCallback? onPressed;

  /// Draws the inverse badge treatment.
  final bool inverse;

  /// Why the store destination is currently unavailable.
  final String? disabledReason;
  @override
  Widget build(BuildContext context) => UiProviderButton(
    label: storeName,
    supporting: caption,
    supportingAbove: true,
    mark: mark,
    onPressed: onPressed,
    inverse: inverse,
    disabledReason: disabledReason,
  );
}
