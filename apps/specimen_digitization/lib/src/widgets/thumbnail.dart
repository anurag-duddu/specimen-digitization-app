/// The small leading image used by the queue and the intake list
/// (10 section 5, `Thumbnail`).
///
/// Bytes when there are bytes, and a placeholder glyph when there are not or
/// when the bytes do not decode. A missing thumbnail is a fact about the
/// record, so it is drawn rather than left as a hole in the row.
library;

import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// A square image on the matte, at `radius.inner`.
class SpecimenThumbnail extends StatelessWidget {
  const SpecimenThumbnail({super.key, this.bytes, this.label});

  /// Encoded image bytes, in any format Flutter can decode.
  final Uint8List? bytes;

  /// What the image shows. Null hides the image from assistive technology,
  /// which is right for a thumbnail beside a row that already names itself.
  final String? label;

  /// The side of the square.
  ///
  /// The row's leading slot, so a thumbnail, a glyph and a checkbox all leave
  /// the title's edge in one place (10 section 4.5).
  static const double side = UiListRowStyle.leadingExtent;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Uint8List? data = bytes;
    final Widget placeholder = Center(
      child: UiIcon(
        UiIcons.image,
        size: UiIconSize.inline,
        color: ui.color.inkTertiary,
      ),
    );

    return ExcludeSemantics(
      excluding: label == null,
      child: Semantics(
        image: true,
        label: label,
        child: SizedBox.square(
          dimension: side,
          child: Surface(
            // The same matte the source pane letterboxes a photograph on, so
            // a specimen sits on one ground wherever it appears
            // (09 section 3.1).
            role: SurfaceRole.matte,
            radius: ui.shape.inner,
            clip: true,
            child: data == null
                ? placeholder
                : Image.memory(
                    data,
                    width: side,
                    height: side,
                    fit: BoxFit.cover,
                    gaplessPlayback: true,
                    errorBuilder: (BuildContext _, Object _, StackTrace? _) =>
                        placeholder,
                  ),
          ),
        ),
      ),
    );
  }
}
