/// Local, explicit edits made on the camera review screen.
///
/// The editor always emits a PNG with metadata stripped. The operator sees
/// the exact pixels that will enter intake; the untouched camera file remains
/// available until they choose "Send for processing". Full resolution is
/// retained whenever the encoded edit fits Intake's upload limit. An
/// oversized edit is proportionally reduced until that same accepted PNG
/// format fits, rather than reaching Intake only to be rejected.
library;

import 'dart:math' as math;

import 'dart:ui' show Rect;

import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as image;

/// Intake's current per-file upload contract, in decimal bytes.
///
/// This is intentionally local to the editor so the capture package does not
/// depend on the Intake screen that presents it.
const int captureEditMaximumBytes = 25000000;

/// The edited photograph could not be represented within Intake's size limit.
class CaptureEditSizeException implements Exception {
  const CaptureEditSizeException(this.maximumBytes);

  final int maximumBytes;

  String get message {
    final String limit = maximumBytes == captureEditMaximumBytes
        ? '25 MB'
        : '$maximumBytes bytes';
    return 'This edit could not be kept under $limit. Retake the photograph '
        'at a smaller size, or send the original unchanged.';
  }

  @override
  String toString() => message;
}

/// The decoded result of one review-screen edit.
@immutable
class CaptureEditResult {
  const CaptureEditResult({
    required this.bytes,
    required this.width,
    required this.height,
  });

  final Uint8List bytes;
  final int width;
  final int height;
}

/// A request that can cross the isolate boundary used by [applyCaptureEdit].
@immutable
class CaptureEditRequest {
  const CaptureEditRequest({
    required this.bytes,
    this.quarterTurns = 0,
    this.crop,
    this.maximumBytes = captureEditMaximumBytes,
  });

  final Uint8List bytes;
  final int quarterTurns;

  /// A crop in displayed-image fractions, from zero to one.
  final Rect? crop;

  /// Maximum encoded bytes accepted by Intake.
  ///
  /// Callers use the production default. The explicit value also lets tests
  /// exercise the size-safety path without allocating a 25 MB fixture.
  final int maximumBytes;
}

/// Pixel dimensions after EXIF orientation is applied for display.
@immutable
class CaptureDimensions {
  const CaptureDimensions(this.width, this.height);

  final int width;
  final int height;
}

Future<CaptureDimensions> captureDimensions(Uint8List bytes) =>
    compute<Uint8List, CaptureDimensions>(_captureDimensions, bytes);

CaptureDimensions _captureDimensions(Uint8List bytes) {
  final image.Image? decoded = _decode(bytes);
  if (decoded == null) {
    throw const FormatException('The captured photograph could not be read.');
  }
  final image.Image displayed = image.bakeOrientation(decoded);
  return CaptureDimensions(displayed.width, displayed.height);
}

/// Decodes and edits camera pixels away from the UI isolate.
Future<CaptureEditResult> applyCaptureEdit(CaptureEditRequest request) =>
    compute<CaptureEditRequest, CaptureEditResult>(
      applyCaptureEditSynchronously,
      request,
    );

/// The synchronous pixel operation, public so deterministic unit tests can
/// verify dimensions and bounds without waiting on an isolate.
CaptureEditResult applyCaptureEditSynchronously(CaptureEditRequest request) {
  final image.Image? decoded = _decode(request.bytes);
  if (decoded == null) {
    throw const FormatException('The captured photograph could not be edited.');
  }

  image.Image edited = image.bakeOrientation(decoded);
  final Rect? requestedCrop = request.crop;
  if (requestedCrop != null) {
    final Rect crop = _boundedCrop(requestedCrop);
    final int x = (crop.left * edited.width).floor().clamp(0, edited.width - 1);
    final int y = (crop.top * edited.height).floor().clamp(
      0,
      edited.height - 1,
    );
    final int width = (crop.width * edited.width).round().clamp(
      1,
      edited.width - x,
    );
    final int height = (crop.height * edited.height).round().clamp(
      1,
      edited.height - y,
    );
    edited = image.copyCrop(edited, x: x, y: y, width: width, height: height);
  }

  final int turns = request.quarterTurns % 4;
  if (turns != 0) {
    edited = image.copyRotate(edited, angle: turns * 90);
  }

  return _encodeWithinLimit(edited, request.maximumBytes);
}

CaptureEditResult _encodeWithinLimit(image.Image edited, int maximumBytes) {
  if (maximumBytes <= 0) {
    throw CaptureEditSizeException(maximumBytes);
  }

  image.Image candidate = edited;
  double cumulativeScale = 1;
  Uint8List encoded = image.encodePng(candidate, level: 9, singleFrame: true);
  while (encoded.lengthInBytes > maximumBytes) {
    if (candidate.width == 1 && candidate.height == 1) {
      throw CaptureEditSizeException(maximumBytes);
    }

    // PNG size is content-dependent, but for photographs it tracks pixel
    // count closely. The square root converts the required byte ratio to a
    // linear scale; a small margin avoids repeated near-limit encodes.
    final double byteScale = math.sqrt(maximumBytes / encoded.lengthInBytes);
    final double scale = math.min(0.95, byteScale * 0.97);
    cumulativeScale *= scale;
    final int width = math.max(1, (edited.width * cumulativeScale).floor());
    final int height = math.max(1, (edited.height * cumulativeScale).floor());
    final int nextWidth = math.min(
      width,
      candidate.width > 1 ? candidate.width - 1 : 1,
    );
    final int nextHeight = math.min(
      height,
      candidate.height > 1 ? candidate.height - 1 : 1,
    );

    candidate = image.copyResize(
      edited,
      width: nextWidth,
      height: nextHeight,
      interpolation: image.Interpolation.cubic,
    );
    encoded = image.encodePng(candidate, level: 9, singleFrame: true);
  }

  return CaptureEditResult(
    bytes: encoded,
    width: candidate.width,
    height: candidate.height,
  );
}

image.Image? _decode(Uint8List bytes) {
  try {
    return image.decodeImage(bytes);
  } catch (_) {
    throw const FormatException('The captured photograph could not be read.');
  }
}

Rect _boundedCrop(Rect crop) {
  const double minimum = 0.08;
  final double left = crop.left.clamp(0.0, 1.0 - minimum);
  final double top = crop.top.clamp(0.0, 1.0 - minimum);
  final double right = crop.right.clamp(left + minimum, 1.0);
  final double bottom = crop.bottom.clamp(top + minimum, 1.0);
  return Rect.fromLTRB(left, top, right, bottom);
}
