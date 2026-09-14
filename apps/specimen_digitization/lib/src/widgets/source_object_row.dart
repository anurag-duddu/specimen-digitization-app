/// One object in a source listing (screen blueprints, section 14).
///
/// The same anatomy as `UploadItem` and `QueueRow`: a leading image, an
/// identifier, one line of measurements and a `StatusChip`. A reviewer who has
/// learned the intake list has already learned this row.
///
/// The image is a placeholder, and that is a decision rather than an omission.
/// An object that has not been imported has no asset, so `GET
/// /assets/{id}/content` does not address it, and sending originals to fill a
/// grid would be tens of megabytes for one screen of rows. Until a source
/// thumbnail endpoint exists the row draws the same placeholder the intake
/// list draws for a file it cannot preview.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../sources.dart';
import '../theme/icons.dart';
import 'specimen_status.dart';
import 'status_chip.dart';
import 'thumbnail.dart';
import 'upload_item.dart';

/// The chip presentation for one row state.
extension SourceObjectStatePresentation on SourceObjectState {
  /// The product token triple this state draws from.
  String get tokenKey => switch (this) {
    // Quiet: the ordinary state of most rows, carrying no outcome yet.
    SourceObjectState.available => 'disposition.deferred',
    // Settled: this object is already a record.
    SourceObjectState.imported => 'disposition.cleared',
    SourceObjectState.unsupportedMediaType => 'state.blocked',
  };

  /// The visible chip word.
  String get label => switch (this) {
    SourceObjectState.available => 'Available',
    SourceObjectState.imported => 'In the queue',
    SourceObjectState.unsupportedMediaType => 'Unsupported type',
  };

  IconData get icon => switch (this) {
    SourceObjectState.available => Symbols.schedule,
    SourceObjectState.imported => Symbols.check_circle,
    SourceObjectState.unsupportedMediaType => Symbols.block,
  };

  /// A complete phrase for assistive technology.
  String get semanticsLabel => 'Object: ${label.toLowerCase()}';

  /// True when adding this object to the queue can succeed.
  ///
  /// An already imported object can: the server answers the existing specimen
  /// without reading a byte, which is what makes a select all safe to run
  /// twice. A media type the source does not admit cannot, so the row is shown
  /// and not offered.
  bool get selectable => this != SourceObjectState.unsupportedMediaType;

  StatusPresentation presentation(BuildContext context) {
    final DispositionStyle style = context.dispositionStyle(tokenKey);
    return StatusPresentation(
      content: style.content,
      fill: style.fill,
      onFill: style.onFill,
      icon: icon,
      fill01: style.fill01,
      label: label,
      semanticsLabel: semanticsLabel,
    );
  }
}

/// The media type as a reviewer reads it: `image/jpeg` becomes `JPEG`.
///
/// Rule 17 of the writing guidelines: a server value never reaches a screen
/// raw. An unrecognised type keeps its wire form rather than being hidden,
/// because a reviewer looking at a row the source refused needs to see what it
/// actually is.
String sourceMediaLabel(String mediaType) => switch (mediaType) {
  'image/jpeg' => 'JPEG',
  'image/png' => 'PNG',
  'image/tiff' => 'TIFF',
  'image/heic' || 'image/heif' => 'HEIC',
  'image/dng' || 'image/x-adobe-dng' => 'DNG',
  '' => 'Type not recorded',
  _ => mediaType,
};

/// The measurements line for one object.
///
/// Absence renders as words (writing guidelines, rule 14), so an object the
/// server did not size says so rather than showing `0.0 MB`.
String sourceMeasurements({required String mediaType, int? sizeBytes}) {
  final String size = sizeBytes == null
      ? 'Size not recorded'
      : '${(sizeBytes / UploadItem.bytesPerMegabyte).toStringAsFixed(1)} MB';
  // The middle dot separates metadata values and never sits inside a
  // sentence (writing guidelines, rule 8).
  return '${sourceMediaLabel(mediaType)} · $size';
}

/// One row in a source listing.
class SourceObjectRow extends StatelessWidget {
  const SourceObjectRow({
    super.key,
    required this.object,
    this.selected = false,
    this.selecting = false,
    this.onToggle,
    this.onExtend,
  });

  /// The inventory row this draws.
  final SourceObject object;

  /// True when this object is in the selection.
  final bool selected;

  /// True once the reviewer has entered selection, which is when the checkbox
  /// column appears on a window too narrow to keep it always.
  final bool selecting;

  /// Adds or removes this object. Null when the row cannot be selected.
  final VoidCallback? onToggle;

  /// Extends the selection from the anchor to this row, for a shift click or
  /// a long press.
  final VoidCallback? onExtend;

  bool get _enabled => onToggle != null && object.state.selectable;

  String _semanticsLabel() {
    final StringBuffer buffer = StringBuffer()
      ..write(object.displayName)
      ..write(', ')
      ..write(object.state.semanticsLabel)
      ..write(', ')
      ..write(
        sourceMeasurements(
          mediaType: object.mediaType,
          sizeBytes: object.sizeBytes,
        ),
      );
    return buffer.toString();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    // One node per row. A reader paging a thousand objects should hear one
    // stop per object, not four.
    return MergeSemantics(
      child: Semantics(
        // A checkbox role, because the gesture adds and removes rather than
        // opening: there is nothing behind a source object to open.
        checked: selected,
        enabled: _enabled,
        label: _semanticsLabel(),
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTap: _enabled ? onToggle : null,
            onLongPress: _enabled ? onExtend : null,
            borderRadius: BorderRadius.circular(context.shape.radiusSm),
            focusColor: theme.colorScheme.primary.withValues(
              alpha: _focusFillOpacity,
            ),
            child: ExcludeSemantics(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: selected ? theme.colorScheme.primaryContainer : null,
                  borderRadius: BorderRadius.circular(context.shape.radiusSm),
                ),
                child: ConstrainedBox(
                  // Every row is at least one target tall, so a checkbox in a
                  // list of a thousand is never a 32dp gesture.
                  constraints: BoxConstraints(
                    minHeight: context.sizes.targetMin,
                  ),
                  child: Padding(
                    padding: EdgeInsets.all(context.space.space2),
                    child: Row(
                      children: <Widget>[
                        if (selecting)
                          Checkbox(
                            value: selected,
                            onChanged: _enabled
                                ? (bool? _) => onToggle!.call()
                                : null,
                          ),
                        SpecimenThumbnail(bytes: null),
                        SizedBox(width: context.space.space3),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Text(
                                object.displayName,
                                style: context.mono.identifier,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              SizedBox(height: context.space.space1),
                              Text(
                                sourceMeasurements(
                                  mediaType: object.mediaType,
                                  sizeBytes: object.sizeBytes,
                                ),
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                        SizedBox(width: context.space.space2),
                        StatusChip.presented(
                          object.state.presentation(context),
                          dense: true,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The focus wash, matching `QueueRow`.
const double _focusFillOpacity = 0.12;
