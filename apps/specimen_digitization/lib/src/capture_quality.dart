import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';

import 'widgets/caveat_text.dart';

/// Descriptive thumbnail measurements, not calibrated blur or readability grades.
class CaptureQuality {
  const CaptureQuality({
    required this.mean,
    required this.contrast,
    required this.darkFraction,
    required this.brightFraction,
    required this.gradient,
    required this.width,
    required this.height,
  });
  final double mean, contrast, darkFraction, brightFraction, gradient;
  final int width, height;
  static CaptureQuality measure(Uint8List rgba, int width, int height) {
    if (width < 1 ||
        height < 1 ||
        width > 256 ||
        height > 256 ||
        rgba.length != width * height * 4) {
      throw ArgumentError('Expected a bounded RGBA thumbnail');
    }
    final values = List<double>.generate(width * height, (i) {
      final alpha = rgba[i * 4 + 3] / 255;
      return (rgba[i * 4] * .299 +
                  rgba[i * 4 + 1] * .587 +
                  rgba[i * 4 + 2] * .114) *
              alpha +
          255 * (1 - alpha);
    });
    final mean = values.reduce((a, b) => a + b) / values.length;
    var gradient = 0.0;
    var edges = 0;
    for (var y = 0; y < height; y++) {
      for (var x = 0; x < width; x++) {
        final value = values[y * width + x];
        if (x > 0) {
          gradient += (value - values[y * width + x - 1]).abs();
          edges++;
        }
        if (y > 0) {
          gradient += (value - values[(y - 1) * width + x]).abs();
          edges++;
        }
      }
    }
    return CaptureQuality(
      mean: mean,
      contrast: math.sqrt(
        values.fold<double>(0, (sum, v) => sum + math.pow(v - mean, 2)) /
            values.length,
      ),
      darkFraction: values.where((v) => v < 6).length / values.length,
      brightFraction: values.where((v) => v >= 250).length / values.length,
      gradient: edges == 0 ? 0 : gradient / edges,
      width: width,
      height: height,
    );
  }

  static Future<CaptureQuality> fromImage(
    Uint8List bytes,
    int width,
    int height,
  ) async {
    final scale = math.min(1.0, 256 / math.max(width, height));
    final codec = await ui.instantiateImageCodec(
      bytes,
      targetWidth: math.max(1, (width * scale).round()),
      targetHeight: math.max(1, (height * scale).round()),
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final rgba = await frame.image.toByteData(
          format: ui.ImageByteFormat.rawRgba,
        );
        if (rgba == null) throw StateError('Thumbnail pixels unavailable');
        return measure(
          rgba.buffer.asUint8List(),
          frame.image.width,
          frame.image.height,
        );
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  }
}

class CaptureQualityView extends StatelessWidget {
  const CaptureQualityView({
    super.key,
    required this.quality,
    this.previewBytes,
  });
  final CaptureQuality? quality;
  final Uint8List? previewBytes;
  @override
  Widget build(BuildContext context) {
    final q = quality;
    return ExpansionTile(
      initiallyExpanded: true,
      title: const Text('Before-upload image check'),
      subtitle: Text(
        q == null
            ? 'Not measured'
            : 'Not calibrated. Measured from a thumbnail.',
      ),
      children: [
        if (previewBytes != null && q != null)
          SizedBox(
            height: 160,
            child: Image.memory(
              previewBytes!,
              cacheWidth: q.width,
              cacheHeight: q.height,
              fit: BoxFit.contain,
              semanticLabel: 'Selected source photograph before upload',
            ),
          ),
        Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (q != null) ...[
                Text(
                  'Brightness ${q.mean.toStringAsFixed(1)} / 255 · Contrast ${q.contrast.toStringAsFixed(1)}',
                ),
                Text(
                  'Near-black pixels ${(q.darkFraction * 100).toStringAsFixed(1)}% · Near-white pixels ${(q.brightFraction * 100).toStringAsFixed(1)}%',
                ),
                Text(
                  'Neighbor contrast ${q.gradient.toStringAsFixed(1)} / 255 · Sample ${q.width} × ${q.height}',
                ),
                const CaveatText(
                  label: 'Clipping or low contrast can hide text.',
                  why:
                      'Compare the preview with the original. These measurements '
                      'do not show sharpness or readability.',
                ),
              ] else
                const CaveatText(
                  label:
                      'This device cannot preview this image. Check the original '
                      'in another viewer before you confirm readability.',
                  why:
                      'Your original file is uploaded unchanged. The server decodes '
                      'it and records its dimensions. If it cannot, the upload stays '
                      'and you can retry.',
                ),
              const CaveatText(
                label:
                    'Focus, glare, framing and label coverage are not checked '
                    'automatically.',
                why:
                    'Check the smallest text, any reflections, and that every label '
                    'is in the frame. Retake the photograph if it is not.',
              ),
            ],
          ),
        ),
      ],
    );
  }
}
