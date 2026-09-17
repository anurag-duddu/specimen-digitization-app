/// One photograph in a source listing (07 section 13).
///
/// The same anatomy as `UploadItem` and `QueueRow`: a `UiListRow` with a
/// leading image, the file name, one line of measurements and a `StatusChip`.
/// A reviewer who has learned the intake list has already learned this row.
///
/// Selection lives outside the row, in `SelectableRow`, exactly as it does in
/// the queue. The body opens only where there is something to open, which is
/// an object that has already become a specimen. An object that has not been
/// imported has nothing behind it, so its body carries no tap and announces no
/// button: the row is then one plain node carrying the same words rather than
/// a disabled button, because a photograph that is not a record is not a
/// control the server has withdrawn.
///
/// The image is a placeholder, and that is a decision rather than an omission.
/// An object that has not been imported has no asset, so `GET
/// /assets/{id}/content` does not address it, and sending originals to fill a
/// grid would be tens of megabytes for one screen of rows. Until a source
/// thumbnail endpoint exists the row draws the same placeholder the intake
/// list draws for a file it cannot preview.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../sources.dart';
import 'specimen_status.dart';
import 'status_chip.dart';
import 'thumbnail.dart';
import 'upload_item.dart';

/// The chip presentation for one row state.
extension SourceObjectStatePresentation on SourceObjectState {
  /// The status triple this state draws from.
  UiStatusTriple tripleIn(UiThemeData ui) => switch (this) {
    // Quiet: the ordinary state of most rows, carrying no outcome yet.
    SourceObjectState.available => ui.color.status.deferred,
    // Settled: this object is already a record.
    SourceObjectState.imported => ui.color.status.cleared,
    SourceObjectState.unsupportedMediaType => ui.color.status.blocked,
  };

  /// The visible chip word.
  String get label => switch (this) {
    SourceObjectState.available => 'Available',
    SourceObjectState.imported => 'In the queue',
    SourceObjectState.unsupportedMediaType => 'Unsupported format',
  };

  /// The registry entry this state draws.
  IconSpec get iconSpec => switch (this) {
    SourceObjectState.available => UiIcons.time,
    SourceObjectState.imported => UiIcons.cleared,
    SourceObjectState.unsupportedMediaType => UiIcons.blocked,
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

  /// Below this content width the chip drops under the name, so it never
  /// competes with the identifier for a narrow window.
  ///
  /// A within-row content decision rather than a window size class: the same
  /// row is drawn beside a checkbox column and without one (05 section 1).
  static const double _chipBesideNameMin = 420;

  /// The share of a wide row the chip may take before its own label is cut.
  static const double _chipWidthShare = 0.4;

  String _semanticsLabel() => <String>[
    object.displayName,
    object.state.semanticsLabel,
    sourceMeasurements(
      mediaType: object.mediaType,
      sizeBytes: object.sizeBytes,
    ),
  ].join(', ');

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) =>
        _row(context, constraints.maxWidth),
  );

  Widget _row(BuildContext context, double available) {
    final UiThemeData ui = context.ui;
    final String line = sourceMeasurements(
      mediaType: object.mediaType,
      sizeBytes: object.sizeBytes,
    );
    final bool beside = !available.isFinite || available >= _chipBesideNameMin;
    final Widget chip = StatusChip.presented(
      object.state.presentation(context),
      dense: true,
    );

    // One node per row. A reader paging a thousand objects hears one stop per
    // object, not four, so the label carries every fact the slots draw.
    final Widget row = UiListRow(
      title: object.displayName,
      subtitle: line,
      semanticsLabel: _semanticsLabel(),
      leading: const SpecimenThumbnail(),
      onPressed: onOpen,
      trailing: beside
          ? ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: available.isFinite
                    ? available * _chipWidthShare
                    : double.infinity,
              ),
              child: chip,
            )
          : null,
    );

    // A row with nothing behind it announces no button. `UiListRow` is a
    // `Pressable` whatever it was given, so a row with no callback would
    // otherwise read as a button the server had withdrawn, which is a
    // different fact from a photograph that is simply not a record yet.
    final Widget body = onOpen == null
        ? Semantics(
            container: true,
            label: _semanticsLabel(),
            excludeSemantics: true,
            child: row,
          )
        : row;

    if (beside) return body;

    // A narrow row keeps the identifier and the measurements readable and
    // moves the state to a line of its own. The word is already on the row's
    // node, so the line says nothing a reader has not heard.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        body,
        ExcludeSemantics(
          child: Padding(
            padding: EdgeInsetsDirectional.only(
              start:
                  ui.shape.stroke.bar +
                  ui.space.s3 +
                  UiListRowStyle.leadingExtent +
                  ui.space.s3,
              end: ui.space.s3,
              bottom: ui.space.s2,
            ),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: chip,
            ),
          ),
        ),
      ],
    );
  }
}

/// The presentation for one row state, resolved against the token layer.
extension on SourceObjectState {
  StatusPresentation presentation(BuildContext context) {
    final UiStatusTriple triple = tripleIn(context.ui);
    return StatusPresentation(
      content: triple.content,
      fill: triple.fill,
      onFill: triple.onFill,
      icon: iconSpec.resolve(),
      // A settled row is drawn filled; a row still waiting is not
      // (09 section 7).
      fill01: this == SourceObjectState.available ? 0 : 1,
      label: label,
      semanticsLabel: semanticsLabel,
      spec: iconSpec,
    );
  }
}
