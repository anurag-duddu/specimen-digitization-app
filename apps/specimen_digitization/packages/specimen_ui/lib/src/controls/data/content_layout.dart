/// Responsive content structures, independent of any product workflow.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../primitives/surface.dart';
import 'hairline.dart';
import 'progress.dart';
import 'section_header.dart';

/// A page heading with optional banner, identity and navigation regions.
/// Banner copy lives on a solid surface below the visual so it remains legible.
class UiPageHeader extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiPageHeader({
    super.key,
    required this.title,
    this.supporting,
    this.banner,
    this.identity,
    this.breadcrumbs,
    this.tabs,
    this.meta,
    this.actions = const [],
    this.centered = false,
  });

  /// The content heading in reading order.
  final String title;

  /// The optional supporting description or content slot.
  final String? supporting;

  /// Decorative banner displayed above the solid text surface.
  final Widget? banner;

  /// Optional avatar, provider mark or other identity.
  final Widget? identity;

  /// Breadcrumb trail preceding the heading.
  final Widget? breadcrumbs;

  /// Controlled page-section navigation below the heading.
  final Widget? tabs;

  /// Count, status or other heading metadata.
  final Widget? meta;

  /// The caller-owned commands in reading order.
  final List<Widget> actions;

  /// Whether heading, identity and commands are centred.
  final bool centered;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Column(
      crossAxisAlignment: centered
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (banner != null)
          SizedBox(
            width: double.infinity,
            height: ui.space.targetMin * 3,
            child: ClipRect(child: banner!),
          ),
        if (breadcrumbs != null)
          Padding(
            padding: EdgeInsets.only(top: ui.space.s4),
            child: breadcrumbs,
          ),
        if (identity != null)
          Padding(
            padding: EdgeInsets.only(top: ui.space.s4),
            child: identity,
          ),
        SizedBox(height: ui.space.s4),
        if (centered) ...[
          Semantics(
            header: true,
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: ui.type.headline.copyWith(color: ui.color.ink),
            ),
          ),
          if (meta != null)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s2),
              child: meta,
            ),
          if (supporting != null)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s2),
              child: Text(
                supporting!,
                textAlign: TextAlign.center,
                style: ui.type.body.copyWith(color: ui.color.inkSecondary),
              ),
            ),
          if (actions.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s4),
              child: Wrap(
                alignment: WrapAlignment.center,
                spacing: ui.space.s2,
                runSpacing: ui.space.s2,
                children: actions,
              ),
            ),
        ] else
          UiSectionHeader(
            title: title,
            role: UiSectionHeaderRole.page,
            supporting: supporting,
            meta: meta,
            actions: actions,
          ),
        if (tabs != null)
          Padding(
            padding: EdgeInsets.only(top: ui.space.s4),
            child: tabs,
          ),
      ],
    );
  }
}

/// The scope whose commands the footer contains.
enum UiContentFooterRole {
  /// Commands scoped to a card.
  card,

  /// Commands scoped to a page section.
  section,
}

/// Footer supporting copy/leading commands and trailing primary actions.
class UiContentFooter extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiContentFooter({
    super.key,
    this.supporting,
    this.leading,
    this.actions = const [],
    this.role = UiContentFooterRole.section,
  });

  /// The optional supporting description or content slot.
  final String? supporting;

  /// The optional identity or icon preceding the main content.
  final Widget? leading;

  /// The caller-owned commands in reading order.
  final List<Widget> actions;

  /// The content scope whose commands are presented.
  final UiContentFooterRole role;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const UiHairline(),
        Padding(
          padding: EdgeInsets.all(
            role == UiContentFooterRole.card ? ui.space.s4 : ui.space.s2,
          ),
          child: Wrap(
            alignment: WrapAlignment.spaceBetween,
            spacing: ui.space.s4,
            runSpacing: ui.space.s3,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              if (supporting != null)
                Text(
                  supporting!,
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
              ?leading,
              Wrap(
                spacing: ui.space.s2,
                runSpacing: ui.space.s2,
                children: actions,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// An inline call to action, with media, form/details and real host commands.
/// Compose email, plan, payment and receipt variants through [content].
class UiInlineCta extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiInlineCta({
    super.key,
    required this.title,
    required this.supporting,
    this.media,
    this.content,
    this.actions = const [],
  });

  /// The content heading in reading order. The optional supporting description or content slot.
  final String title, supporting;

  /// The optional media. The optional content.
  final Widget? media, content;

  /// The caller-owned commands in reading order.
  final List<Widget> actions;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final body = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        UiSectionHeader(
          title: title,
          supporting: supporting,
          role: UiSectionHeaderRole.card,
        ),
        if (content != null)
          Padding(
            padding: EdgeInsets.only(top: ui.space.s4),
            child: content,
          ),
        if (actions.isNotEmpty)
          Padding(
            padding: EdgeInsets.only(top: ui.space.s4),
            child: Wrap(
              spacing: ui.space.s2,
              runSpacing: ui.space.s2,
              children: actions,
            ),
          ),
      ],
    );
    return Surface(
      hairline: true,
      radius: ui.shape.tile,
      padding: EdgeInsets.all(ui.space.s5),
      child: LayoutBuilder(
        builder: (context, c) {
          if (media == null) return body;
          if (c.maxWidth <
              ui.space.readingMax * MediaQuery.textScalerOf(context).scale(1)) {
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                media!,
                SizedBox(height: ui.space.s4),
                body,
              ],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Flexible(child: media!),
              SizedBox(width: ui.space.s5),
              Expanded(flex: 3, child: body),
            ],
          );
        },
      ),
    );
  }
}

/// Divider styling for headings or command groups.
enum UiContentDividerStyle {
  /// One rule above the content.
  single,

  /// Rules above and below the content.
  dual,

  /// A neutral filled divider region.
  filled,
}

/// Semantic content between decorative rules. Actions retain their hit targets.
class UiContentDivider extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiContentDivider({
    super.key,
    required this.child,
    this.style = UiContentDividerStyle.single,
  });

  /// The caller-supplied child.
  final Widget child;

  /// The visual treatment, independent of the content or controlled state.
  final UiContentDividerStyle style;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    if (style == UiContentDividerStyle.filled) {
      return Surface(
        role: SurfaceRole.ground,
        padding: EdgeInsets.all(ui.space.s3),
        child: child,
      );
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const UiHairline(),
        Padding(
          padding: EdgeInsets.symmetric(vertical: ui.space.s3),
          child: child,
        ),
        if (style == UiContentDividerStyle.dual) const UiHairline(),
      ],
    );
  }
}

/// Named pending state with optional measured fraction and cancellable action.
class UiLoadingState extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiLoadingState({
    super.key,
    required this.label,
    this.supporting,
    this.value,
    this.action,
    this.inline = false,
    this.indicatorStyle = UiLoadingIndicatorStyle.line,
  });

  /// The visible accessible name supplied by the host.
  final String label;

  /// The optional supporting description or content slot.
  final String? supporting;

  /// The caller-supplied formatted measurement or controlled value.
  final double? value;

  /// The caller-supplied action.
  final Widget? action;

  /// Whether the loading indicator shares a row with its description.
  final bool inline;

  /// The indicator mark style.
  final UiLoadingIndicatorStyle indicatorStyle;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final text = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: inline
          ? CrossAxisAlignment.start
          : CrossAxisAlignment.center,
      children: [
        Text(
          label,
          textAlign: inline ? TextAlign.start : TextAlign.center,
          style: ui.type.label.copyWith(color: ui.color.ink),
        ),
        if (supporting != null)
          Text(
            supporting!,
            textAlign: inline ? TextAlign.start : TextAlign.center,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
      ],
    );
    final progress = value == null
        ? UiLoadingIndicator(
            label: label,
            style: indicatorStyle,
            size: inline ? UiProgressSize.small : UiProgressSize.large,
          )
        : UiProgress.ring(
            semanticsLabel: label,
            value: value,
            size: inline ? UiProgressSize.small : UiProgressSize.large,
          );
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: EdgeInsets.all(inline ? ui.space.s2 : ui.space.s6),
        child: inline
            ? Row(
                children: [
                  progress,
                  SizedBox(width: ui.space.s3),
                  Expanded(child: text),
                  if (action != null) ...[
                    SizedBox(width: ui.space.s2),
                    Flexible(child: action!),
                  ],
                ],
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  progress,
                  SizedBox(height: ui.space.s4),
                  text,
                  if (action != null) ...[
                    SizedBox(height: ui.space.s4),
                    action!,
                  ],
                ],
              ),
      ),
    );
  }
}

/// Metric card with explicit formatted value, trend, icon and chart anatomy.
class UiMetricCard extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiMetricCard({
    super.key,
    required this.label,
    required this.value,
    this.supporting,
    this.leading,
    this.trend,
    this.chart,
    this.actions = const [],
  });

  /// Metric name, including units where needed.
  final String label;

  /// Formatted measurement; use explicit absence text when not measured.
  final String value;

  /// The optional supporting description or content slot.
  final String? supporting;

  /// Optional featured icon or identity.
  final Widget? leading;

  /// Caller-described change, including its direction and comparison interval.
  final Widget? trend;

  /// Optional miniature chart with a readable data equivalent.
  final Widget? chart;

  /// The caller-owned commands in reading order.
  final List<Widget> actions;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Surface(
      hairline: true,
      radius: ui.shape.tile,
      padding: EdgeInsets.all(ui.space.s5),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (leading != null)
            Align(alignment: AlignmentDirectional.centerStart, child: leading),
          UiSectionHeader(
            title: label,
            role: UiSectionHeaderRole.card,
            actions: actions,
          ),
          SizedBox(height: ui.space.s3),
          Text(
            value,
            style: ui.type.displayMedium.copyWith(color: ui.color.ink),
          ),
          if (supporting != null)
            Text(
              supporting!,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          if (trend != null)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s2),
              child: trend,
            ),
          if (chart != null)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s4),
              child: chart,
            ),
        ],
      ),
    );
  }
}
