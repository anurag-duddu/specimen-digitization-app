/// The small leading image used by the queue and the intake list.
///
/// Bytes when there are bytes, and a placeholder glyph when there are not or
/// when the bytes do not decode. A missing thumbnail is a fact about the
/// record, so it is drawn rather than left as a hole in the row.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';

/// A square image with a placeholder fallback.
class SpecimenThumbnail extends StatelessWidget {
  const SpecimenThumbnail({super.key, this.bytes, this.label});

  /// Encoded image bytes, in any format Flutter can decode.
  final Uint8List? bytes;

  /// What the image shows. Null hides the image from assistive technology,
  /// which is right for a thumbnail beside a row that already names itself.
  final String? label;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final double side = context.sizes.iconDisplay;
    final Widget placeholder = Icon(
      Symbols.image,
      size: context.sizes.iconInline,
      color: theme.colorScheme.onSurfaceVariant,
    );
    final Uint8List? data = bytes;

    return ExcludeSemantics(
      excluding: label == null,
      child: Semantics(
        image: true,
        label: label,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(context.shape.radiusXs),
          child: Container(
            width: side,
            height: side,
            // The same matte the source pane uses, so a photograph sits on
            // the same ground wherever it appears (blueprint 12).
            color: context.sourceMatte,
            alignment: Alignment.center,
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
