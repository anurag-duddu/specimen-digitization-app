/// Persistent alert and notification anatomy, independent of delivery services.
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../actions/icon_button.dart';
import 'banner.dart';

/// A persistent alert card, notification or full-width announcement.
///
/// The host owns dismissal and action results. Time, avatar, image, progress and
/// supporting content are slots; this widget never creates notification data.
class UiNotice extends StatelessWidget {
  /// Creates a named alert with optional supporting detail and actions.
  const UiNotice({
    super.key,
    required this.title,
    this.description,
    this.tone = UiBannerTone.info,
    this.leading,
    this.showIcon = true,
    this.actions = const [],
    this.timestamp,
    this.child,
    this.onDismiss,
    this.dismissLabel = 'Dismiss notification',
    this.floating = true,
    this.announce = false,
  });

  /// Main notification text.
  final String title;

  /// Optional explanatory text, which wraps without truncation.
  final String? description;

  /// Functional status rather than decorative hue.
  final UiBannerTone tone;

  /// Avatar, image, progress or custom icon replacing the default status icon.
  final Widget? leading;

  /// Whether to include the default status icon when [leading] is absent.
  final bool showIcon;

  /// Named commands. They wrap beneath the message at narrow widths.
  final List<Widget> actions;

  /// Caller-formatted relative or absolute time.
  final String? timestamp;

  /// Optional details, attachment or progress content.
  final Widget? child;

  /// Requests dismissal; null leaves this notice persistent.
  final VoidCallback? onDismiss;

  /// Accessible close-button label.
  final String dismissLabel;

  /// Rounded card when true; an edge-to-edge band otherwise.
  final bool floating;

  /// Announces newly inserted feedback without automatically taking focus.
  final bool announce;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final style = UiBannerStyle.resolve(ui, tone);
    return Semantics(
      container: true,
      liveRegion: announce,
      child: Container(
        decoration: BoxDecoration(
          color: ui.color.paper,
          border: Border.all(
            color: ui.color.hairline,
            width: ui.shape.stroke.hairline,
          ),
          borderRadius: BorderRadius.circular(
            floating ? ui.shape.tile : ui.shape.none,
          ),
        ),
        padding: EdgeInsets.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (leading != null || showIcon) ...[
                  ConstrainedBox(
                    constraints: BoxConstraints(
                      maxWidth: ui.space.identityLeadingMax,
                    ),
                    child:
                        leading ??
                        Container(
                          padding: EdgeInsets.all(ui.space.s2),
                          decoration: BoxDecoration(
                            color: style.fill,
                            borderRadius: BorderRadius.circular(ui.shape.inner),
                          ),
                          child: UiIcon(style.icon, color: style.foreground),
                        ),
                  ),
                  SizedBox(width: ui.space.s3),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        style: ui.type.label.copyWith(color: ui.color.ink),
                      ),
                      if (description != null) ...[
                        SizedBox(height: ui.space.s1),
                        Text(
                          description!,
                          style: ui.type.bodySmall.copyWith(
                            color: ui.color.inkSecondary,
                          ),
                        ),
                      ],
                      if (timestamp != null) ...[
                        SizedBox(height: ui.space.s2),
                        Text(
                          timestamp!,
                          style: ui.type.labelSmall.copyWith(
                            color: ui.color.inkSecondary,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (onDismiss != null)
                  UiIconButton(
                    icon: UiIcons.close,
                    semanticsLabel: dismissLabel,
                    onPressed: onDismiss,
                  ),
              ],
            ),
            if (child != null) ...[SizedBox(height: ui.space.s3), child!],
            if (actions.isNotEmpty) ...[
              SizedBox(height: ui.space.s3),
              Wrap(
                spacing: ui.space.s2,
                runSpacing: ui.space.s2,
                children: actions,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
