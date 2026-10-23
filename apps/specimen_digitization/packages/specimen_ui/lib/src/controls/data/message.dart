/// Message anatomy, independent of any messaging service.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../primitives/field_core.dart';
import '../../primitives/surface.dart';
import '../actions/button.dart';

/// The delivery information a host can show beside a message.
enum UiMessageState {
  /// The host acknowledged delivery.
  sent,

  /// Delivery is still in flight.
  pending,

  /// Delivery failed and may be retried.
  failed,

  /// The recipient has opened the message.
  read,
}

/// An attachment name/size and caller-owned open/download action.
@immutable
class UiMessageAttachment {
  /// Creates the component with explicit content and caller-owned state.
  const UiMessageAttachment({
    required this.name,
    required this.detail,
    this.preview,
    this.onOpen,
  });

  /// File name shown and spoken to the reader.
  final String name;

  /// File format, size or other factual supporting description.
  final String detail;

  /// The optional media preview supplied by the host.
  final Widget? preview;

  /// The host callback opening the attachment; no storage operation is implied.
  final VoidCallback? onOpen;
}

/// A controlled reaction. A zero count remains meaningful.
@immutable
class UiMessageReaction {
  /// Creates the component with explicit content and caller-owned state.
  const UiMessageReaction({
    required this.label,
    this.count,
    this.selected = false,
    this.onPressed,
  });

  /// The visible accessible name supplied by the host.
  final String label;

  /// The displayed count; null omits the count while zero remains explicit.
  final int? count;

  /// Whether this reaction is selected by the current reader.
  final bool selected;

  /// The host action; null keeps the command disabled.
  final VoidCallback? onPressed;
}

/// A message with explicit authorship, time and optional retry action.
class UiMessage extends StatelessWidget {
  /// Renders a caller-owned message.
  const UiMessage({
    super.key,
    required this.author,
    required this.body,
    required this.timeLabel,
    this.outgoing = false,
    this.state = UiMessageState.sent,
    this.onRetry,
    this.attachments = const [],
    this.reactions = const [],
    this.writing = false,
    this.avatar,
  });

  /// Who wrote it.
  final String author;

  /// Plain text, selectable and wrapped in full.
  final String body;

  /// Localized time supplied by the host.
  final String timeLabel;

  /// Aligns to the trailing edge for a message from the current person.
  final bool outgoing;

  /// Current delivery state.
  final UiMessageState state;

  /// Retries a failed message. Hidden in other states.
  final VoidCallback? onRetry;

  /// Files and controlled reactions; the host owns storage and delivery.
  final List<UiMessageAttachment> attachments;

  /// The caller-supplied reactions.
  final List<UiMessageReaction> reactions;

  /// Announces typing without fabricating a message or delivery receipt.
  final bool writing;

  /// Optional caller-supplied author portrait or initials.
  final Widget? avatar;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final delivery = switch (state) {
      UiMessageState.sent => 'Sent',
      UiMessageState.pending => 'Sending',
      UiMessageState.failed => 'Not sent',
      UiMessageState.read => 'Read',
    };
    return Align(
      alignment: outgoing
          ? AlignmentDirectional.centerEnd
          : AlignmentDirectional.centerStart,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: ui.space.readingMax),
        child: Surface(
          role: outgoing ? SurfaceRole.ground : SurfaceRole.paper,
          hairline: true,
          radius: ui.shape.tile,
          padding: EdgeInsets.all(ui.space.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (avatar != null) ...[
                    avatar!,
                    SizedBox(width: ui.space.s3),
                  ],
                  Flexible(
                    child: Text(
                      author,
                      style: ui.type.label.copyWith(color: ui.color.ink),
                    ),
                  ),
                ],
              ),
              SizedBox(height: ui.space.s2),
              if (writing)
                Semantics(
                  liveRegion: true,
                  child: Text(
                    '$author is writing…',
                    style: ui.type.body.copyWith(color: ui.color.inkSecondary),
                  ),
                )
              else if (body.isNotEmpty)
                UiSelectableText(
                  body,
                  style: ui.type.body.copyWith(color: ui.color.ink),
                ),
              for (final attachment in attachments)
                Padding(
                  padding: EdgeInsets.only(top: ui.space.s3),
                  child: Surface(
                    hairline: true,
                    radius: ui.shape.inner,
                    padding: EdgeInsets.all(ui.space.s3),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ?attachment.preview,
                        Text(
                          attachment.name,
                          style: ui.type.label.copyWith(color: ui.color.ink),
                        ),
                        Text(
                          attachment.detail,
                          style: ui.type.bodySmall.copyWith(
                            color: ui.color.inkSecondary,
                          ),
                        ),
                        if (attachment.onOpen != null)
                          UiButton(
                            label: 'Open ${attachment.name}',
                            variant: UiButtonVariant.ghost,
                            size: UiSize.sm,
                            onPressed: attachment.onOpen,
                          ),
                      ],
                    ),
                  ),
                ),
              SizedBox(height: ui.space.s2),
              Semantics(
                liveRegion: true,
                child: Text(
                  writing ? timeLabel : '$timeLabel · $delivery',
                  style: ui.type.bodySmall.copyWith(
                    color: state == UiMessageState.failed
                        ? ui.color.status.blocked.content
                        : ui.color.inkSecondary,
                  ),
                ),
              ),
              if (reactions.isNotEmpty)
                Padding(
                  padding: EdgeInsets.only(top: ui.space.s3),
                  child: Wrap(
                    spacing: ui.space.s2,
                    runSpacing: ui.space.s2,
                    children: [
                      for (final reaction in reactions)
                        Semantics(
                          selected: reaction.selected,
                          child: UiButton(
                            label: reaction.count == null
                                ? reaction.label
                                : '${reaction.label} ${reaction.count}',
                            semanticsLabel:
                                '${reaction.label}${reaction.count == null ? '' : ', ${reaction.count} reactions'}',
                            variant: reaction.selected
                                ? UiButtonVariant.secondary
                                : UiButtonVariant.ghost,
                            size: UiSize.sm,
                            onPressed: reaction.onPressed,
                          ),
                        ),
                    ],
                  ),
                ),
              if (state == UiMessageState.failed && onRetry != null) ...[
                SizedBox(height: ui.space.s2),
                UiButton(
                  label: 'Retry message',
                  variant: UiButtonVariant.secondary,
                  size: UiSize.sm,
                  onPressed: onRetry,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
