/// One photograph in a source listing (screen blueprints, section 13).
///
/// The same anatomy as `UploadItem` and `QueueRow`: a leading image, an
/// identifier, one line of measurements and a `StatusChip`. A reviewer who has
/// learned the intake list has already learned this row.
///
/// Selection lives outside the row, in `SelectableRow`, exactly as it does in
/// the queue. The body opens only where there is something to open, which is
/// an object that has already become a specimen. An object that has not been
/// imported has nothing behind it, so its body carries no tap and announces no
/// button.
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
    SourceObjectState.unsupportedMediaType => 'Unsupported format',
  };

  IconData get icon => switch (this) {
    SourceObjectState.available => Symbols.schedule,
    SourceObjectState.imported => Symbols.check_circle,
    SourceObjectState.unsupportedMediaType => Symbols.block,
  };

  /// A complete phrase for assistive technology.
  String get semanticsLabel => 'Photograph: ${label.toLowerCase()}';

  /// True when adding this object to the queue can succeed.
  ///
  /// An already imported object can: the server answers the existing specimen
  /// without reading a byte, which is what makes a select all safe to run
  /// twice. A media type the source does not admit cannot, so the row is shown
  /// and not offered.
  bool get selectable => this != SourceObjectState.unsupportedMediaType;
}

/// "1 photograph" or "6 photographs".
///
/// A source listing counts photographs, not records. The distinction is the
/// whole point of this screen: a photograph in storage becomes a record when
/// it is added, and until then the queue has never heard of it.
///
/// "Photograph" rather than "object" because the reviewer is looking at
/// pictures of specimens, and every media type a source admits is an image.
/// "Object" is the storage model's word, and the vocabulary table has no row
/// for it (UX writing, rule 7).
String photographsLabel(int count) =>
    count == 1 ? '1 photograph' : '${groupedCount(count)} photographs';

/// A count with thousands separators (UX writing, section 4.14).
///
/// This screen is the first in the client to render a number over 999: a
/// source holds a thousand slides, and the guideline asks for a separator on
/// every count past that. No localization package is in the dependency set,
/// and the separator here is the one the guideline itself writes.
String groupedCount(int count) {
  final String digits = count.abs().toString();
  final StringBuffer out = StringBuffer(count < 0 ? '-' : '');
  for (int index = 0; index < digits.length; index++) {
    if (index > 0 && (digits.length - index) % 3 == 0) out.write(',');
    out.write(digits[index]);
  }
  return out.toString();
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
  const SourceObjectRow({super.key, required this.object, this.onOpen});

  /// The inventory row this draws.
  final SourceObject object;

  /// Opens the specimen this object became. Null for an object that is not in
  /// the queue, because there is nothing behind it to open.
  final VoidCallback? onOpen;

  String _semanticsLabel() => <String>[
    object.displayName,
    object.state.semanticsLabel,
    sourceMeasurements(
      mediaType: object.mediaType,
      sizeBytes: object.sizeBytes,
    ),
  ].join(', ');

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    // One node per row. A reader paging a thousand objects should hear one
    // stop per object, not four.
    return MergeSemantics(
      child: Semantics(
        button: onOpen != null,
        label: _semanticsLabel(),
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTap: onOpen,
            borderRadius: BorderRadius.circular(context.shape.radiusSm),
            focusColor: theme.colorScheme.primary.withValues(
              alpha: _focusFillOpacity,
            ),
            child: ExcludeSemantics(
              child: ConstrainedBox(
                // Every row is at least one target tall, so the checkbox
                // beside it is never a cramped gesture in a list of a
                // thousand.
                constraints: BoxConstraints(minHeight: context.sizes.targetMin),
                child: Padding(
                  padding: EdgeInsets.all(context.space.space2),
                  child: LayoutBuilder(
                    builder:
                        (BuildContext context, BoxConstraints constraints) =>
                            constraints.maxWidth < _compactBreakpoint
                            ? _compactBody(context, theme)
                            : _wideBody(context, theme),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// Below this content width the chip drops under the name, so it never
  /// competes with the identifier for a narrow window.
  static const double _compactBreakpoint = 420;

  Widget _name(BuildContext context) => Text(
    object.displayName,
    style: context.mono.identifier,
    maxLines: 1,
    overflow: TextOverflow.ellipsis,
  );

  Widget _measurements(BuildContext context, ThemeData theme) => Text(
    sourceMeasurements(
      mediaType: object.mediaType,
      sizeBytes: object.sizeBytes,
    ),
    style: theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    ),
    maxLines: 1,
    overflow: TextOverflow.ellipsis,
  );

  Widget _chip(BuildContext context) =>
      StatusChip.presented(object.state.presentation(context), dense: true);

  Widget _wideBody(BuildContext context, ThemeData theme) => Row(
    children: <Widget>[
      const SpecimenThumbnail(),
      SizedBox(width: context.space.space3),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _name(context),
            SizedBox(height: context.space.space1),
            _measurements(context, theme),
          ],
        ),
      ),
      SizedBox(width: context.space.space2),
      _chip(context),
    ],
  );

  Widget _compactBody(BuildContext context, ThemeData theme) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      const SpecimenThumbnail(),
      SizedBox(width: context.space.space3),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _name(context),
            SizedBox(height: context.space.space1),
            _measurements(context, theme),
            SizedBox(height: context.space.space1),
            _chip(context),
          ],
        ),
      ),
    ],
  );
}

/// The presentation for one row state, resolved against the token layer.
extension on SourceObjectState {
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

/// The focus wash, matching `QueueRow`.
const double _focusFillOpacity = 0.12;
