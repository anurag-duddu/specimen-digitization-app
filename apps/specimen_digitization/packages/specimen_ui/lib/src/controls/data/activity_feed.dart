/// A readable sequence of events with caller-supplied timestamps.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import 'avatar.dart';
import 'hairline.dart';

/// One event. The host supplies localized dates and any business meaning.
@immutable
class UiActivityEntry {
  /// Describes an event in plain language.
  const UiActivityEntry({
    required this.title,
    required this.timeLabel,
    this.description,
    this.actor,
    this.supporting,
    this.actions = const [],
    this.unread = false,
  });

  /// The action or result, not just the actor's name.
  final String title;

  /// A visible, already formatted timestamp.
  final String timeLabel;

  /// Optional context. Wraps without truncation.
  final String? description;

  /// Optional actor, shown with the shared avatar fallback.
  final String? actor;

  /// Attachment, label group or quoted content associated with this event.
  final Widget? supporting;

  /// The caller-owned commands in reading order.
  final List<Widget> actions;

  /// Exposed textually so unread state is not conveyed by colour alone.
  final bool unread;
}

/// Separation between adjacent events.
enum UiActivityDivider {
  /// A continuous trace or separator.
  line,

  /// A continuous event timeline connector.
  connector,

  /// No decorative separation or key.
  none,
}

/// An activity feed with a single reading order and no nested scroll view.
class UiActivityFeed extends StatelessWidget {
  /// Renders [entries] in their supplied order.
  const UiActivityFeed({
    super.key,
    required this.entries,
    this.emptyLabel = 'No activity yet',
    this.divider = UiActivityDivider.line,
    this.compact = false,
  });

  /// Events in the order chosen by the host.
  final List<UiActivityEntry> entries;

  /// Text for an empty history.
  final String emptyLabel;

  /// The decorative separation between adjacent items.
  final UiActivityDivider divider;

  /// Whether compact token spacing is used.
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    if (entries.isEmpty) {
      return Text(
        emptyLabel,
        style: ui.type.body.copyWith(color: ui.color.inkSecondary),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < entries.length; i++) ...[
          if (i > 0 && divider == UiActivityDivider.line) const UiHairline(),
          Container(
            decoration:
                divider == UiActivityDivider.connector && i < entries.length - 1
                ? BoxDecoration(
                    border: BorderDirectional(
                      start: BorderSide(
                        color: ui.color.boundary,
                        width: ui.shape.stroke.hairline,
                      ),
                    ),
                  )
                : null,
            padding: EdgeInsetsDirectional.only(
              start: divider == UiActivityDivider.connector ? ui.space.s3 : 0,
              top: compact ? ui.space.s2 : ui.space.s4,
              bottom: compact ? ui.space.s2 : ui.space.s4,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (entries[i].actor != null) ...[
                  UiAvatar(name: entries[i].actor!),
                  SizedBox(width: ui.space.s3),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${entries[i].unread ? 'Unread · ' : ''}${entries[i].title}',
                        style: ui.type.label.copyWith(color: ui.color.ink),
                      ),
                      SizedBox(height: ui.space.s1),
                      Text(
                        entries[i].timeLabel,
                        style: ui.type.bodySmall.copyWith(
                          color: ui.color.inkSecondary,
                        ),
                      ),
                      if (entries[i].description != null) ...[
                        SizedBox(height: ui.space.s2),
                        Text(
                          entries[i].description!,
                          style: ui.type.body.copyWith(color: ui.color.ink),
                        ),
                      ],
                      if (entries[i].supporting != null)
                        Padding(
                          padding: EdgeInsets.only(top: ui.space.s3),
                          child: entries[i].supporting,
                        ),
                      if (entries[i].actions.isNotEmpty)
                        Padding(
                          padding: EdgeInsets.only(top: ui.space.s3),
                          child: Wrap(
                            spacing: ui.space.s2,
                            runSpacing: ui.space.s2,
                            children: entries[i].actions,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}
