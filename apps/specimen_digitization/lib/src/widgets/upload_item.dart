/// One file in the intake list (10 section 5, `UploadItem`).
///
/// A `UiListRow`: a 40 dp thumbnail, the file name, one line of measurements,
/// and the state beside it. The state chip is the same component the queue
/// uses, so a state is learned once, and it carries the quiet progress ring
/// of the north star while bytes are moving. A failed transfer is operational,
/// not evidentiary, so it stays in the list with a reason and a way out
/// rather than vanishing.
///
/// The row is not a control: nothing opens behind a file on its way into a
/// collection. It publishes one node carrying every fact it draws, and the
/// remove control sits beside the row with a node of its own, which is the
/// arrangement `SelectableRow` already uses for its checkbox and for the same
/// reason: a `UiListRow` is one `Pressable` and drops the semantics of
/// whatever is in its slots.
library;

import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'specimen_status.dart';
import 'status_chip.dart';
import 'thumbnail.dart';

/// The states one file passes through on its way into a collection.
enum UploadState {
  /// Chosen, not yet examined.
  ready('Ready'),

  /// Local quality checks are running.
  checking('Checking'),

  /// Bytes are moving. Carries a determinate fraction.
  uploading('Uploading'),

  /// The server took it.
  accepted('Accepted'),

  /// The collection already holds these pixels.
  duplicate('Already in collection'),

  /// The transfer stopped part way and can be resumed.
  interrupted('Interrupted'),

  /// The reviewer took it out of this batch.
  skipped('Skipped'),

  /// The server refused it.
  failed('Failed');

  const UploadState(this.label);

  /// The visible chip word.
  final String label;

  /// The registry entry this state draws.
  ///
  /// One meaning, one glyph, chosen once in `UiIcons` rather than per call
  /// site (09 section 7).
  IconSpec get iconSpec => switch (this) {
    UploadState.ready => UiIcons.time,
    UploadState.checking => UiIcons.processing,
    UploadState.uploading => UiIcons.processing,
    UploadState.accepted => UiIcons.cleared,
    UploadState.duplicate => UiIcons.copy,
    UploadState.interrupted => UiIcons.deferred,
    UploadState.skipped => UiIcons.unmeasured,
    UploadState.failed => UiIcons.blocked,
  };

  /// The status triple this state draws from.
  ///
  /// Read straight off the token layer rather than through a string key, so
  /// the colours and the glyph are chosen in one place and cannot drift.
  UiStatusTriple tripleIn(UiThemeData ui) => switch (this) {
    UploadState.ready => ui.color.status.deferred,
    UploadState.checking => ui.color.status.processing,
    UploadState.uploading => ui.color.status.processing,
    UploadState.accepted => ui.color.status.cleared,
    UploadState.duplicate => ui.color.status.deferred,
    UploadState.interrupted => ui.color.status.needsReview,
    UploadState.skipped => ui.color.status.deferred,
    UploadState.failed => ui.color.status.blocked,
  };

  /// True for a state a reviewer has settled on rather than one in motion.
  ///
  /// A settled disposition is drawn filled (09 section 7).
  bool get isSettled => switch (this) {
    UploadState.checking || UploadState.uploading => false,
    _ => true,
  };

  /// A complete phrase for assistive technology.
  String get semanticsLabel => 'Upload: ${label.toLowerCase()}';

  /// Resolves the colour triple and pairs it with the glyph and the word.
  ///
  /// [progress] is drawn as a determinate ring in place of the glyph. It is a
  /// measurement, so it keeps its motion under reduced motion.
  StatusPresentation presentation(BuildContext context, {double? progress}) {
    final UiStatusTriple triple = tripleIn(context.ui);
    return StatusPresentation(
      content: triple.content,
      fill: triple.fill,
      onFill: triple.onFill,
      icon: iconSpec.resolve(),
      label: label,
      semanticsLabel: semanticsLabel,
      progress: this == UploadState.uploading ? progress : null,
      spec: iconSpec,
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
    this.removeBlockedReason,
    this.details,
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

  /// Takes the file out of the batch. Null with no [removeBlockedReason]
  /// means the row has no remove control at all, so a row that can never be
  /// removed does not spend a 48dp target saying so.
  final VoidCallback? onRemove;

  /// Why the file cannot be taken out of the batch. Draws the control
  /// disabled, with the reason as its tooltip and its semantic hint, rather
  /// than as a bare disabled button.
  final String? removeBlockedReason;

  /// Supplementary content for this file: measurements, a server check
  /// result, an evidence disclosure. Rendered inside the item, under the
  /// state, so a manifest row is one component rather than a component in a
  /// column of loose widgets.
  final Widget? details;

  /// The remove control's name, fixed so the tests and the copy cannot drift.
  static const String removeLabel = 'Remove from this batch';

  /// Bytes per megabyte, decimal, matching how operating systems report a
  /// camera card.
  static const int bytesPerMegabyte = 1000000;

  /// The row width at which the state fits beside the file name rather than
  /// under it.
  ///
  /// A within-row content decision, not a window size class: the same row is
  /// drawn in a 420 dp capture column and across a 1440 dp manifest, and what
  /// decides the layout is the width this row was given (05 section 1). The
  /// same number and the same reason as `QueueRow`, because the two rows have
  /// the same anatomy.
  static const double _stateBesideNameMin = 500;

  /// The share of a wide row the state may take.
  ///
  /// A `UiListRow` bounds a trailing it cannot measure to the room left once
  /// the title has its minimum, which is generous at ordinary text size; this
  /// keeps a long status word from taking half the row before that bound
  /// bites.
  static const double _stateWidthShare = 0.4;

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

  /// Everything the row draws, as one phrase.
  ///
  /// The row is one merged node, so a reader hears the file, its state, its
  /// measurements and the reason as one stop rather than four
  /// (02 section 4.16).
  String _semanticsLabel(String line) {
    final StringBuffer buffer = StringBuffer()
      ..write(name)
      ..write(', ')
      ..write(state.semanticsLabel)
      ..write(', ')
      ..write(line);
    final String? why = reason;
    if (why != null) buffer.write(', $why');
    return buffer.toString();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) =>
        _item(context, constraints.maxWidth),
  );

  Widget _item(BuildContext context, double available) {
    final UiThemeData ui = context.ui;
    final String? blocked = removeBlockedReason;
    final String line = measurements(
      sizeBytes: sizeBytes,
      width: pixelWidth,
      height: pixelHeight,
    );
    final bool beside = !available.isFinite || available >= _stateBesideNameMin;
    final Widget chip = StatusChip.presented(
      state.presentation(context, progress: progress),
      dense: true,
    );

    // The row itself publishes no button: a file on its way into a collection
    // has nothing behind it to open. The label carries every fact the row
    // draws and the slots' own semantics are dropped, which is one stop per
    // file for a reader working through a batch of two hundred.
    final Widget row = Semantics(
      container: true,
      label: _semanticsLabel(line),
      excludeSemantics: true,
      child: UiListRow(
        title: name,
        subtitle: line,
        leading: SpecimenThumbnail(bytes: thumbnail),
        trailing: beside
            ? ConstrainedBox(
                constraints: BoxConstraints(
                  maxWidth: available.isFinite
                      ? available * _stateWidthShare
                      : double.infinity,
                ),
                child: chip,
              )
            : null,
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(child: row),
            // Beside the row rather than in its trailing slot, because a
            // `UiListRow` is one `Pressable` and a control inside it has
            // neither a press nor a name of its own.
            if (onRemove != null || blocked != null)
              UiIconButton(
                icon: UiIcons.close,
                semanticsLabel: removeLabel,
                onPressed: onRemove,
                // A disabled control names why, rather than leaving the
                // reviewer to guess at a greyed out button.
                disabledReason: blocked,
              ),
          ],
        ),
        // A narrow row keeps the file name and its measurements readable and
        // moves the state to a line of its own. The words are already on the
        // row's node, so the line says nothing a reader has not heard.
        if (!beside)
          ExcludeSemantics(
            child: Padding(
              padding: EdgeInsetsDirectional.only(
                start: _textInset(ui),
                bottom: ui.space.s1,
              ),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: chip,
              ),
            ),
          ),
        if (reason != null)
          ExcludeSemantics(
            child: Padding(
              padding: EdgeInsetsDirectional.only(
                start: _textInset(ui),
                bottom: ui.space.s1,
              ),
              child: Text(
                reason!,
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
            ),
          ),
        if (details != null)
          Padding(
            padding: EdgeInsetsDirectional.only(
              start: _textInset(ui),
              top: ui.space.s2,
            ),
            child: details!,
          ),
      ],
    );
  }

  /// Where the row's own text starts, so a line under the row lines up with
  /// the file name rather than with the thumbnail.
  double _textInset(UiThemeData ui) =>
      ui.shape.stroke.bar +
      ui.space.s3 +
      UiListRowStyle.leadingExtent +
      ui.space.s3;
}
