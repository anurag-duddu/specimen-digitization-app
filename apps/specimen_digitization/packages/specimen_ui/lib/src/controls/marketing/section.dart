/// Shared anatomy and responsive composition for public-facing pages.
library;

import 'dart:math' as math;
import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../primitives/brand_hero.dart';
import '../../primitives/surface.dart';
import '../actions/button.dart';

/// The relationship between text, supporting media and actions.
enum UiSectionLayout {
  /// A reading column aligned to the leading edge.
  start,

  /// A centered reading column with media underneath.
  centered,

  /// Text and media in columns, stacking in reading order on narrow screens.
  split,

  /// Media leads on wide screens and follows the heading on narrow screens.
  splitReversed,
}

/// The section's surface treatment. Text always has a solid background.
enum UiSectionTreatment {
  /// Unframed composition in its parent.
  plain,

  /// Bordered solid card.
  card,

  /// Separate hero gradient above a solid content region.
  brand,
}

/// A named action supplied by the host. Null callbacks are visibly disabled.
@immutable
class UiMarketingAction {
  /// Creates a reusable navigation or call-to-action item.
  const UiMarketingAction(this.label, {this.onPressed, this.primary = false});

  /// Visible and accessible text.
  final String label;

  /// Host navigation or command. The library does not invent a destination.
  final VoidCallback? onPressed;

  /// Whether this is the principal action in its group.
  final bool primary;
}

/// A responsive section, composing the common heading and media anatomy.
///
/// Pass actual content in [media], such as a screenshot, photograph or map.
/// The library does not substitute images for functioning application controls.
class UiMarketingSection extends StatelessWidget {
  /// Creates a section whose content grows with text scale.
  const UiMarketingSection({
    super.key,
    required this.title,
    this.leading,
    this.eyebrow,
    this.description,
    this.media,
    this.child,
    this.actions = const [],
    this.layout = UiSectionLayout.start,
    this.treatment = UiSectionTreatment.plain,
  });

  /// Section heading, exposed to assistive technology.
  final String title;

  /// Optional explanatory visual before the heading, such as a Phosphor icon.
  final Widget? leading;

  /// Optional contextual label.
  final String? eyebrow;

  /// Supporting copy.
  final String? description;

  /// Optional image, illustration, form, map or application preview.
  final Widget? media;

  /// Content after the heading/actions, before supporting media.
  final Widget? child;

  /// Commands in reading order.
  final List<UiMarketingAction> actions;

  /// Composition at sufficient available width.
  final UiSectionLayout layout;

  /// Surface and brand treatment.
  final UiSectionTreatment treatment;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final centered = layout == UiSectionLayout.centered;
    final heading = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: centered
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.start,
      children: [
        if (leading != null) ...[leading!, SizedBox(height: ui.space.s4)],
        if (eyebrow != null) ...[
          Text(
            eyebrow!,
            textAlign: centered ? TextAlign.center : TextAlign.start,
            style: ui.type.label.copyWith(color: ui.brand.secondary.content),
          ),
          SizedBox(height: ui.space.s2),
        ],
        Semantics(
          header: true,
          child: Text(
            title,
            textAlign: centered ? TextAlign.center : TextAlign.start,
            style: ui.type.headline.copyWith(color: ui.color.ink),
          ),
        ),
        if (description != null) ...[
          SizedBox(height: ui.space.s4),
          Text(
            description!,
            textAlign: centered ? TextAlign.center : TextAlign.start,
            style: ui.type.bodyLarge.copyWith(color: ui.color.inkSecondary),
          ),
        ],
        if (actions.isNotEmpty) ...[
          SizedBox(height: ui.space.s6),
          MarketingActions(actions: actions, centered: centered),
        ],
        if (child != null) ...[SizedBox(height: ui.space.s6), child!],
      ],
    );
    final content = LayoutBuilder(
      builder: (context, constraints) {
        final split =
            layout == UiSectionLayout.split ||
            layout == UiSectionLayout.splitReversed;
        final scale = MediaQuery.textScalerOf(context).scale(16) / 16;
        if (split &&
            media != null &&
            constraints.maxWidth >= ui.space.readingMax * scale) {
          final text = Expanded(child: heading);
          final visual = Expanded(child: media!);
          return Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              layout == UiSectionLayout.splitReversed ? visual : text,
              SizedBox(width: ui.space.s8),
              layout == UiSectionLayout.splitReversed ? text : visual,
            ],
          );
        }
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (centered)
              Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: ui.space.readingMax),
                  child: heading,
                ),
              )
            else
              heading,
            if (media != null) ...[SizedBox(height: ui.space.s8), media!],
          ],
        );
      },
    );
    if (treatment == UiSectionTreatment.plain) return content;
    return Surface(
      hairline: true,
      radius: ui.shape.tile,
      clip: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (treatment == UiSectionTreatment.brand) const UiBrandAccent(),
          Padding(padding: EdgeInsets.all(ui.space.s6), child: content),
        ],
      ),
    );
  }
}

/// A wrapping grid that respects available width and enlarged text.
class UiSectionGrid extends StatelessWidget {
  /// Uses up to [columns], with a reading width for every item.
  const UiSectionGrid({
    super.key,
    required this.children,
    this.columns = 3,
    this.minimumItemWidth = 240,
  }) : assert(columns > 0),
       assert(minimumItemWidth > 0);

  /// Section items, in reading order.
  final List<Widget> children;

  /// Maximum columns at sufficient width.
  final int columns;

  /// Smallest useful item allocation at 100% text.
  final double minimumItemWidth;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final gap = context.ui.space.s6;
      final scale = MediaQuery.textScalerOf(context).scale(16) / 16;
      final width = constraints.hasBoundedWidth
          ? constraints.maxWidth
          : context.ui.space.readingMax;
      final count = math.max(
        1,
        math.min(
          columns,
          ((width + gap) / (minimumItemWidth * scale + gap)).floor(),
        ),
      );
      final itemWidth = math.max(0.0, (width - gap * (count - 1)) / count);
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final child in children)
            SizedBox(width: itemWidth, child: child),
        ],
      );
    },
  );
}

/// Internal consistent action group shared by section families.
class MarketingActions extends StatelessWidget {
  /// Creates buttons with inherited owned-control semantics.
  const MarketingActions({
    super.key,
    required this.actions,
    this.centered = false,
    this.expanded = false,
  });

  /// Action definitions.
  final List<UiMarketingAction> actions;

  /// Centers wrapped action rows.
  final bool centered;

  /// Stacks full-width actions, as used in plan cards.
  final bool expanded;
  @override
  Widget build(BuildContext context) => expanded
      ? MarketingStack(
          children: [
            for (final action in actions)
              UiButton(
                label: action.label,
                expand: true,
                variant: action.primary
                    ? UiButtonVariant.primary
                    : UiButtonVariant.secondary,
                onPressed: action.onPressed,
              ),
          ],
        )
      : Wrap(
          alignment: centered ? WrapAlignment.center : WrapAlignment.start,
          spacing: context.ui.space.s2,
          runSpacing: context.ui.space.s2,
          children: [
            for (final action in actions)
              UiButton(
                label: action.label,
                variant: action.primary
                    ? UiButtonVariant.primary
                    : UiButtonVariant.secondary,
                onPressed: action.onPressed,
              ),
          ],
        );
}

/// Internal vertical rhythm for content with an unconstrained height.
class MarketingStack extends StatelessWidget {
  /// A stack that never forces paragraph height.
  const MarketingStack({
    super.key,
    required this.children,
    this.centered = false,
  });

  /// Visible items.
  final List<Widget> children;

  /// Centers the cross axis.
  final bool centered;
  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: centered
        ? CrossAxisAlignment.center
        : CrossAxisAlignment.stretch,
    children: [
      for (var i = 0; i < children.length; i++) ...[
        if (i > 0) SizedBox(height: context.ui.space.s4),
        children[i],
      ],
    ],
  );
}
