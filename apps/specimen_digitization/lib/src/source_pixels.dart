/// The immutable original, drawn as the reviewer's coordinates see it.
///
/// The derivative a browser can decode carries an EXIF display transform; the
/// recorded region coordinates do not. This undoes the transform so an
/// overlay, a crop and a typed coordinate all land on the same pixel. The
/// original bytes are never rewritten.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'review_context.dart';
import 'vocabulary.dart';
import 'widgets/evidence_drawer.dart';

/// Undo the derivative's EXIF display transform so overlays and crops share
/// original pixel-edge coordinates. The immutable bytes are never rewritten.
class SourcePixels extends StatelessWidget {
  const SourcePixels({
    super.key,
    required this.asset,
    required this.semanticLabel,
  });
  final Json asset;
  final String semanticLabel;
  @override
  Widget build(BuildContext context) {
    final transform = objectOf(objectOf(asset['view_derivative'])['transform']);
    final matrix = transform['matrix'];
    Widget image() => Image.memory(
      asset['preview_bytes'],
      fit: BoxFit.fill,
      // The photograph stays on screen while a rebuild resolves the same
      // bytes again. Without this a panel change, which rebuilds the row the
      // image sits in, blanks the specimen for a frame: the reviewer sees a
      // black rectangle where the evidence was, which is the one thing this
      // screen must never do (motion and microinteractions, 5.4).
      gaplessPlayback: true,
      semanticLabel: asset['processing_derivative'] is Map
          ? 'Decoded source preview. The original file is kept.'
          : semanticLabel,
      errorBuilder: (_, _, _) => const Center(
        child: Text('Source preview unavailable. Refresh to retry.'),
      ),
    );
    if (asset['preview_is_derivative'] != true) return image();
    if (matrix is! List || matrix.length != 6 || matrix.any((v) => v is! num)) {
      return const Center(
        child: Text('Source geometry is unavailable. Refresh evidence.'),
      );
    }
    final m = matrix.cast<num>();
    final det = m[0] * m[4] - m[1] * m[3];
    final width = (transform['original_width'] as num).toDouble();
    final viewWidth = (transform['view_width'] as num).toDouble();
    final viewHeight = (transform['view_height'] as num).toDouble();
    if (det == 0 || width <= 0) {
      return const Text('The source transform could not be read.');
    }
    return LayoutBuilder(
      builder: (context, c) {
        final scale = c.maxWidth / width;
        final inverse = Matrix4.identity()
          ..setEntry(0, 0, m[4] / det)
          ..setEntry(0, 1, -m[1] / det)
          ..setEntry(1, 0, -m[3] / det)
          ..setEntry(1, 1, m[0] / det)
          ..setEntry(0, 3, (m[1] * m[5] - m[4] * m[2]) / det * scale)
          ..setEntry(1, 3, (m[3] * m[2] - m[0] * m[5]) / det * scale);
        return ClipRect(
          child: Stack(
            children: [
              Positioned(
                left: 0,
                top: 0,
                width: viewWidth * scale,
                height: viewHeight * scale,
                child: Transform(
                  transform: inverse,
                  alignment: Alignment.topLeft,
                  child: image(),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class SourceBasisNotice extends StatelessWidget {
  const SourceBasisNotice({super.key, required this.asset});
  final Json asset;
  @override
  Widget build(BuildContext context) {
    final processing = objectOf(asset['processing_derivative']);
    if (processing.isEmpty) return const SizedBox.shrink();
    final basis = textOf(asset['pixel_basis']);
    final ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          basis == 'decoded_heif_primary_pixel_edges'
              ? 'Coordinates use the decoded HEIF primary image after container orientation. The original HEIC file is kept, and mapping to its encoded grid is unavailable.'
              : 'Source coordinate basis: ${vocabularyLabel(basis)}. The preview is decoded from the original, and the original bytes are kept.',
          style: ui.type.bodySmall,
        ),
        // The decoder and the conversion are provenance rather than a
        // statement about the record, so they sit under the basis in the
        // secondary ink the rest of the source details use.
        Text(
          'Decoder: ${textOf(processing['codec'])} ${textOf(processing['codec_version'])} · Conversion: ${processing['conversion'] ?? 'Not recorded'}',
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        ),
        EvidenceDrawer(
          title: 'Codec and source coordinate provenance',
          payload: {'pixel_basis': basis, 'processing_derivative': processing},
        ),
      ],
    );
  }
}
