import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';

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
      semanticLabel: semanticLabel,
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
    if (det == 0 || width <= 0) return const Text('Invalid source transform.');
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
