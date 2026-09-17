import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widgets/caveat_text.dart';
import 'widgets/not_calibrated_chip.dart';

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

/// A coarse brightness reading taken from one live camera preview frame.
///
/// This is the same class of measurement [CaptureQuality] makes, taken from a
/// stream rather than a file, and it carries the same honesty boundary: it is
/// a histogram, never a focus, glare or readability grade, and never a pass.
/// The responsive spec, section 7, requires the hint be advisory and never a
/// capture gate.
@immutable
class CapturePreviewReading {
  const CapturePreviewReading({
    required this.mean,
    required this.darkFraction,
    required this.brightFraction,
  });

  /// Mean luma, 0 to 255.
  final double mean;

  /// Share of sampled pixels at or below the near-black threshold.
  final double darkFraction;

  /// Share of sampled pixels at or above the near-white threshold.
  final double brightFraction;

  /// Below this, a sample counts as near-black.
  static const int darkThreshold = 6;

  /// At or above this, a sample counts as near-white.
  static const int brightThreshold = 250;

  /// Share of clipped highlights that is worth mentioning.
  static const double glareHintFraction = 0.05;

  /// Share of crushed shadows that is worth mentioning.
  static const double shadowHintFraction = 0.2;

  /// At most this many samples are read from one frame, so the reading costs
  /// the same whether the sensor is 2 or 48 megapixels.
  static const int sampleBudget = 4096;

  /// Reads a luma plane, sampling on a stride so the cost is bounded.
  ///
  /// [bytesPerPixel] and [bytesPerRow] describe the plane's layout, which
  /// differs between the YUV420 plane the Android preview delivers and the
  /// BGRA8888 buffer the iOS preview delivers.
  static CapturePreviewReading fromPlane(
    Uint8List plane, {
    required int width,
    required int height,
    int bytesPerPixel = 1,
    int? bytesPerRow,
    bool bgra = false,
  }) {
    if (width < 1 || height < 1 || bytesPerPixel < 1) {
      throw ArgumentError('Expected a positive preview plane geometry');
    }
    final int rowStride = bytesPerRow ?? width * bytesPerPixel;
    final int step = math.max(
      1,
      math.sqrt(width * height / sampleBudget).ceil(),
    );
    var total = 0.0;
    var dark = 0;
    var bright = 0;
    var samples = 0;
    for (var y = 0; y < height; y += step) {
      final int rowStart = y * rowStride;
      for (var x = 0; x < width; x += step) {
        final int index = rowStart + x * bytesPerPixel;
        if (index + (bgra ? 2 : 0) >= plane.length) continue;
        final double value = bgra
            ? plane[index + 2] * .299 +
                  plane[index + 1] * .587 +
                  plane[index] * .114
            : plane[index].toDouble();
        total += value;
        if (value < darkThreshold) dark++;
        if (value >= brightThreshold) bright++;
        samples++;
      }
    }
    if (samples == 0) {
      throw ArgumentError('Expected at least one readable preview sample');
    }
    return CapturePreviewReading(
      mean: total / samples,
      darkFraction: dark / samples,
      brightFraction: bright / samples,
    );
  }

  /// One short sentence, or null when the histogram says nothing worth
  /// saying. Never a verdict on the photograph.
  String? get hint {
    if (brightFraction > glareHintFraction) {
      return 'Bright areas are clipping. Check for glare before you capture.';
    }
    if (darkFraction > shadowHintFraction) {
      return 'Dark areas are clipping. Check the lighting before you capture.';
    }
    return null;
  }

  /// The three values, as they are spoken and shown.
  String get summary =>
      'Brightness ${mean.toStringAsFixed(0)} of 255. '
      'Clipped dark ${(darkFraction * 100).toStringAsFixed(0)}%. '
      'Clipped bright ${(brightFraction * 100).toStringAsFixed(0)}%.';
}

/// The three local measurements as short labelled values, with the
/// calibration boundary attached (screen blueprints, section 5).
///
/// Three values, because a reader who is deciding whether to retake a
/// photograph can hold three. The full set stays in [CaptureQualityView].
class CaptureQualitySummary extends StatelessWidget {
  const CaptureQualitySummary({super.key, required this.quality});

  /// The measurement, or null when this device could not decode the image.
  final CaptureQuality? quality;

  /// What the three slots are called, in order.
  static const List<String> labels = <String>[
    'Brightness',
    'Contrast',
    'Neighbour contrast',
  ];

  /// The three values for [quality], with an abstention for each slot when
  /// nothing was measured.
  static List<String> valuesOf(CaptureQuality? quality) => quality == null
      ? const <String>['Not measured', 'Not measured', 'Not measured']
      : <String>[
          '${quality.mean.toStringAsFixed(0)} of 255',
          quality.contrast.toStringAsFixed(0),
          '${quality.gradient.toStringAsFixed(0)} of 255',
        ];

  @override
  Widget build(BuildContext context) {
    final UiThemeData tokens = context.ui;
    final List<String> values = valuesOf(quality);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Wrap(
          spacing: tokens.space.s6,
          runSpacing: tokens.space.s2,
          crossAxisAlignment: WrapCrossAlignment.end,
          children: <Widget>[
            for (int i = 0; i < labels.length; i++)
              Semantics(
                container: true,
                label: '${labels[i]}: ${values[i]}, not calibrated',
                excludeSemantics: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      labels[i],
                      style: tokens.type.labelSmall.copyWith(
                        color: tokens.color.inkSecondary,
                      ),
                    ),
                    Text(
                      values[i],
                      style: tokens.type.body.copyWith(color: tokens.color.ink),
                    ),
                  ],
                ),
              ),
            const NotCalibratedChip(),
          ],
        ),
      ],
    );
  }
}

/// The full set of local measurements, behind one disclosure.
///
/// Every number here is descriptive: a histogram of a thumbnail, never a
/// focus, glare or readability grade and never a pass. The boundary is stated
/// twice, once as the summary line a reader meets before opening anything and
/// once as the caveats inside.
class CaptureQualityView extends StatelessWidget {
  const CaptureQualityView({
    super.key,
    required this.quality,
    this.previewBytes,
  });

  /// The measurement, or null when this device could not decode the image.
  final CaptureQuality? quality;

  /// The decoded thumbnail, when there is one to show beside the numbers.
  final Uint8List? previewBytes;

  /// The disclosure's own title.
  static const String title = 'Before-upload image check';

  @override
  Widget build(BuildContext context) {
    final UiThemeData tokens = context.ui;
    final CaptureQuality? q = quality;
    final Uint8List? bytes = previewBytes;
    return UiDisclosure(
      initiallyExpanded: true,
      title: title,
      summary: q == null
          ? 'Not measured'
          : 'Not calibrated. Measured from a thumbnail.',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (bytes != null && q != null) ...<Widget>[
            // The thumbnail's own shape, so the preview is never letterboxed
            // into a height nobody measured.
            Surface(
              role: SurfaceRole.matte,
              radius: tokens.shape.inner,
              clip: true,
              child: AspectRatio(
                aspectRatio: q.width / q.height,
                child: Image.memory(
                  bytes,
                  cacheWidth: q.width,
                  cacheHeight: q.height,
                  fit: BoxFit.contain,
                  semanticLabel: 'Selected source photograph before upload',
                ),
              ),
            ),
            SizedBox(height: tokens.space.s3),
          ],
          if (q != null) ...<Widget>[
            Text(
              'Brightness ${q.mean.toStringAsFixed(1)} of 255 · Contrast '
              '${q.contrast.toStringAsFixed(1)}',
              style: tokens.type.body.copyWith(color: tokens.color.ink),
            ),
            Text(
              'Near-black pixels '
              '${(q.darkFraction * 100).toStringAsFixed(1)}% · Near-white '
              'pixels ${(q.brightFraction * 100).toStringAsFixed(1)}%',
              style: tokens.type.body.copyWith(color: tokens.color.ink),
            ),
            Text(
              'Neighbour contrast ${q.gradient.toStringAsFixed(1)} of 255 · '
              'Sample ${q.width} by ${q.height}',
              style: tokens.type.body.copyWith(color: tokens.color.ink),
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
    );
  }
}
