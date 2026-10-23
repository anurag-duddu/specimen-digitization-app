/// Hierarchical destinations, with complete labels at every text scale.
library;

import 'dart:math' as math;
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';

/// One ancestor or the current location.
@immutable
class UiBreadcrumb {
  /// A destination named [label]. The last item is always the current page.
  const UiBreadcrumb({required this.label, this.onSelected, this.icon});

  /// The complete destination name.
  final String label;

  /// Navigates to an ancestor. Ignored for the current page.
  final VoidCallback? onSelected;

  /// The optional Phosphor glyph preceding the label.
  final IconSpec? icon;
}

/// The available presentation choices for this component.
enum UiBreadcrumbStyle {
  /// Text links with hover emphasis.
  text,

  /// Text links with a persistent underline.
  underlined,

  /// Accessible Iris emphasis.
  brand,

  /// Neutral surface styling.
  neutral,

  /// A boundary around each destination.
  bordered,
}

/// The available presentation choices for this component.
enum UiBreadcrumbDivider {
  /// A directional chevron separator.
  chevron,

  /// A slash separator.
  slash,
}

/// A wrapping breadcrumb trail. Its last item is readable, not actionable.
class UiBreadcrumbs extends StatelessWidget {
  /// Shows [items] in reading order.
  const UiBreadcrumbs({
    super.key,
    required this.items,
    this.style = UiBreadcrumbStyle.text,
    this.divider = UiBreadcrumbDivider.chevron,
  });

  /// Root to current page. An empty trail occupies no space.
  final List<UiBreadcrumb> items;

  /// The visual treatment, independent of the content or controlled state.
  final UiBreadcrumbStyle style;

  /// The decorative separation between adjacent items.
  final UiBreadcrumbDivider divider;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final ui = context.ui;
    Widget content(UiBreadcrumb item, bool current, Set<WidgetState> states) =>
        Container(
          padding: EdgeInsets.symmetric(
            vertical: ui.space.s2,
            horizontal:
                style == UiBreadcrumbStyle.text ||
                    style == UiBreadcrumbStyle.underlined
                ? 0
                : ui.space.s3,
          ),
          decoration: BoxDecoration(
            color: style == UiBreadcrumbStyle.brand && current
                ? ui.brand.secondary.fill
                : style == UiBreadcrumbStyle.neutral && current
                ? ui.color.ground
                : null,
            border: style == UiBreadcrumbStyle.bordered
                ? Border.all(
                    color: ui.color.boundary,
                    width: ui.shape.stroke.boundary,
                  )
                : null,
            borderRadius: BorderRadius.circular(ui.shape.inner),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (item.icon != null) ...[
                UiIcon(
                  item.icon!,
                  size: UiIconSize.small,
                  color: ui.color.inkSecondary,
                ),
                SizedBox(width: ui.space.s2),
              ],
              Flexible(
                child: Text(
                  item.label,
                  style: (current ? ui.type.label : ui.type.bodySmall).copyWith(
                    color: style == UiBreadcrumbStyle.brand && current
                        ? ui.brand.secondary.onFill
                        : current
                        ? ui.color.ink
                        : ui.color.inkSecondary,
                    decoration:
                        states.contains(WidgetState.hovered) ||
                            style == UiBreadcrumbStyle.underlined
                        ? TextDecoration.underline
                        : null,
                  ),
                ),
              ),
            ],
          ),
        );
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.hasBoundedWidth
            ? constraints.maxWidth
            : ui.space.readingMax;
        final labelWidth = math.max(
          ui.space.s0,
          width - ui.space.iconSmall - ui.space.s2,
        );
        return Wrap(
          spacing: ui.space.s2,
          runSpacing: ui.space.s1,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            for (var i = 0; i < items.length; i++)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (i > 0) ...[
                    ExcludeSemantics(
                      child: divider == UiBreadcrumbDivider.slash
                          ? Text(
                              '/',
                              style: ui.type.bodySmall.copyWith(
                                color: ui.color.inkTertiary,
                              ),
                            )
                          : UiIcon(
                              Directionality.of(context) == TextDirection.ltr
                                  ? UiIcons.next
                                  : UiIcons.previous,
                              size: UiIconSize.small,
                              color: ui.color.inkTertiary,
                            ),
                    ),
                    SizedBox(width: ui.space.s2),
                  ],
                  ConstrainedBox(
                    constraints: BoxConstraints(maxWidth: labelWidth),
                    child: i == items.length - 1 || items[i].onSelected == null
                        ? Semantics(
                            value: i == items.length - 1
                                ? 'Current page'
                                : null,
                            child: content(items[i], i == items.length - 1, {}),
                          )
                        : Pressable(
                            role: PressableRole.link,
                            semanticsLabel: items[i].label,
                            onPressed: items[i].onSelected,
                            radius: ui.shape.inner,
                            builder: (context, states) =>
                                content(items[i], false, states),
                          ),
                  ),
                ],
              ),
          ],
        );
      },
    );
  }
}
