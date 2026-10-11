/// Local, explicit edits made on the camera review screen.
///
/// The editor always emits a PNG with metadata stripped. The operator sees
/// the exact pixels that will enter intake; the untouched camera file remains
/// available until they choose "Send for processing".
library;

import 'dart:ui' show Rect;

import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as image;

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
  });

  final Uint8List bytes;
  final int quarterTurns;

  /// A crop in displayed-image fractions, from zero to one.
  final Rect? crop;
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

  return CaptureEditResult(
    bytes: image.encodePng(edited),
    width: edited.width,
    height: edited.height,
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
