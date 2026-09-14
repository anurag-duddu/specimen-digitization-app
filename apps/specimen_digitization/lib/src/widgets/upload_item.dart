/// One file in the intake list (design system, 7.3 `UploadItem`).
///
/// The state chip is the same component the queue uses, so a state is learned
/// once. A failed transfer is operational, not evidentiary, so it stays in the
/// list with a reason and a way out rather than vanishing.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import 'specimen_status.dart';
import 'status_chip.dart';
import 'thumbnail.dart';

/// The states one file passes through on its way into a collection.
enum UploadState {
  /// Chosen, not yet examined.
  ready('disposition.deferred', 'Ready'),

  /// Local quality checks are running.
  checking('state.processing', 'Checking'),

  /// Bytes are moving. Carries a determinate fraction.
  uploading('state.processing', 'Uploading'),

  /// The server took it.
  accepted('disposition.cleared', 'Accepted'),

  /// The collection already holds these pixels.
  duplicate('disposition.deferred', 'Already in collection'),

  /// The transfer stopped part way and can be resumed.
  interrupted('disposition.needsReview', 'Interrupted'),

  /// The reviewer took it out of this batch.
  skipped('disposition.deferred', 'Skipped'),

  /// The server refused it.
  failed('state.blocked', 'Failed');

  const UploadState(this.tokenKey, this.label);

  /// The product token triple this state draws from.
  final String tokenKey;

  /// The visible chip word.
  final String label;

  /// The glyph.
  IconData get icon => switch (this) {
    UploadState.ready => Symbols.schedule,
    UploadState.checking => Symbols.autorenew,
    UploadState.uploading => Symbols.autorenew,
    UploadState.accepted => Symbols.check_circle,
    UploadState.duplicate => Symbols.content_copy,
    UploadState.interrupted => Symbols.pause_circle,
    UploadState.skipped => Symbols.hide_source,
    UploadState.failed => Symbols.block,
  };

  /// A complete phrase for assistive technology.
  String get semanticsLabel => 'Upload: ${label.toLowerCase()}';

  /// Resolves the color triple and pairs it with the glyph and the word.
  ///
  /// [progress] is drawn as a determinate ring in place of the glyph. It is a
  /// measurement, so it keeps its motion under reduced motion.
  StatusPresentation presentation(BuildContext context, {double? progress}) {
    final DispositionStyle style = context.dispositionStyle(tokenKey);
    return StatusPresentation(
      content: style.content,
      fill: style.fill,
      onFill: style.onFill,
      icon: icon,
      fill01: style.fill01,
      label: label,
      semanticsLabel: semanticsLabel,
      progress: this == UploadState.uploading ? progress : null,
    );
  }
}

/// A file waiting to become a record.
class UploadItem extends StatelessWidget {
  const UploadItem({
    super.key,
    required this.name,
    required this.state,
    this.thumbnail,
    this.sizeBytes,
    this.pixelWidth,
    this.pixelHeight,
    this.progress,
    this.reason,
    this.onRemove,
  });

  /// The file name, as the operator's machine spells it.
  final String name;

  /// Where the file has got to.
  final UploadState state;

  /// Encoded image bytes for the leading thumbnail.
  final Uint8List? thumbnail;

  /// File size in bytes. Rendered to one decimal in megabytes.
  final int? sizeBytes;

  /// Measured pixel width, if the file has been examined.
  final int? pixelWidth;

  /// Measured pixel height, if the file has been examined.
  final int? pixelHeight;

  /// Determinate transfer fraction, 0 to 1, while [state] is uploading.
  final double? progress;

  /// One plain sentence saying why the state is what it is.
  final String? reason;

  /// Takes the file out of the batch. Disabled once the transfer commits.
  final VoidCallback? onRemove;

  /// Bytes per megabyte, decimal, matching how operating systems report a
  /// camera card.
  static const int bytesPerMegabyte = 1000000;

  /// The size and dimensions line, with abstentions for what was not
  /// measured (UX writing, section 4.14).
  static String measurements({int? sizeBytes, int? width, int? height}) {
    final String size = sizeBytes == null
        ? 'Size not measured'
        : '${(sizeBytes / bytesPerMegabyte).toStringAsFixed(1)} MB';
    final String pixels = width == null || height == null
        ? 'Dimensions not measured'
        : '$width by $height pixels';
    return '$size, $pixels';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String line = measurements(
      sizeBytes: sizeBytes,
      width: pixelWidth,
      height: pixelHeight,
    );

    return Semantics(
      container: true,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: context.space.space2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            SpecimenThumbnail(bytes: thumbnail),
            SizedBox(width: context.space.space3),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    name,
                    style: context.mono.identifier,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: context.space.space1),
                  Text(
                    line,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  SizedBox(height: context.space.space1),
                  StatusChip.presented(
                    state.presentation(context, progress: progress),
                    dense: true,
                  ),
                  if (reason != null) ...<Widget>[
                    SizedBox(height: context.space.space1),
                    Text(
                      reason!,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            IconButton(
              onPressed: onRemove,
              icon: const Icon(Symbols.close),
              iconSize: context.sizes.iconAction,
              tooltip: 'Remove from this batch',
              constraints: BoxConstraints(
                minWidth: context.sizes.targetMin,
                minHeight: context.sizes.targetMin,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
