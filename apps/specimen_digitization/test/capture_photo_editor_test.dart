import 'dart:typed_data';
import 'dart:ui' show Rect;
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:specimen_digitization/src/capture/capture_photo_editor.dart';

Uint8List _png({required int width, required int height}) {
  final image.Image source = image.Image(width: width, height: height);
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      source.setPixelRgba(x, y, x, y, x + y, 255);
    }
  }
  return Uint8List.fromList(image.encodePng(source));
}

Uint8List _noisyPng({required int width, required int height}) {
  final image.Image source = image.Image(width: width, height: height);
  var value = 0x13579bdf;
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      value = (value * 1664525 + 1013904223) & 0xffffffff;
      source.setPixelRgba(
        x,
        y,
        value & 0xff,
        (value >> 8) & 0xff,
        (value >> 16) & 0xff,
        255,
      );
    }
  }
  return Uint8List.fromList(image.encodePng(source));
}

void main() {
  test('dimensions can be decoded off the UI isolate', () async {
    final CaptureDimensions dimensions = await captureDimensions(
      _png(width: 80, height: 40),
    );

    expect(dimensions.width, 80);
    expect(dimensions.height, 40);
  });

  test('the camera test fixture can be decoded off the UI isolate', () async {
    final CaptureDimensions dimensions = await captureDimensions(
      File('test/fixtures/synthetic-label.png').readAsBytesSync(),
    );

    expect(dimensions.width, 800);
    expect(dimensions.height, 600);
  });

  test('unchanged edits retain dimensions and emit a readable PNG', () {
    final CaptureEditResult result = applyCaptureEditSynchronously(
      CaptureEditRequest(bytes: _png(width: 80, height: 40)),
    );

    expect(result.width, 80);
    expect(result.height, 40);
    final image.Image? decoded = image.decodePng(result.bytes);
    expect(decoded, isNotNull);
    expect(decoded!.width, 80);
    expect(decoded.height, 40);
  });

  test('an oversized edited PNG is reduced below the Intake limit', () async {
    const int testLimit = 90000;
    final CaptureEditResult result = await applyCaptureEdit(
      CaptureEditRequest(
        bytes: _noisyPng(width: 240, height: 180),
        maximumBytes: testLimit,
      ),
    );

    expect(result.bytes.lengthInBytes, lessThanOrEqualTo(testLimit));
    expect(result.width, lessThan(240));
    expect(result.height, lessThan(180));
    expect(result.width / result.height, closeTo(240 / 180, 0.02));
    final image.Image? decoded = image.decodePng(result.bytes);
    expect(decoded, isNotNull);
    expect(decoded!.width, result.width);
    expect(decoded.height, result.height);
  });

  test('the production edit limit matches Intake exactly', () {
    expect(captureEditMaximumBytes, 25000000);
  });

  test('an impossible byte limit fails with clear recovery guidance', () {
    expect(
      () => applyCaptureEditSynchronously(
        CaptureEditRequest(bytes: _png(width: 2, height: 2), maximumBytes: 1),
      ),
      throwsA(
        isA<CaptureEditSizeException>()
            .having(
              (CaptureEditSizeException error) => error.message,
              'message',
              contains('could not be kept under 1 bytes'),
            )
            .having(
              (CaptureEditSizeException error) => error.message,
              'recovery',
              contains('Retake the photograph'),
            ),
      ),
    );
  });

  test('a quarter turn swaps output dimensions', () {
    final CaptureEditResult result = applyCaptureEditSynchronously(
      CaptureEditRequest(bytes: _png(width: 80, height: 40), quarterTurns: 1),
    );

    expect(result.width, 40);
    expect(result.height, 80);
  });

  test('crop and rotation run safely off the UI isolate', () async {
    final CaptureEditResult result = await applyCaptureEdit(
      CaptureEditRequest(
        bytes: _png(width: 80, height: 40),
        crop: const Rect.fromLTWH(0.25, 0.25, 0.5, 0.5),
        quarterTurns: 1,
      ),
    );

    expect(result.width, 20);
    expect(result.height, 40);
  });

  test('malformed image bytes fail with a readable format error', () async {
    await expectLater(
      captureDimensions(Uint8List.fromList(<int>[1, 2, 3])),
      throwsA(isA<FormatException>()),
    );
    expect(
      () => applyCaptureEditSynchronously(
        CaptureEditRequest(bytes: Uint8List.fromList(<int>[1, 2, 3])),
      ),
      throwsA(isA<FormatException>()),
    );
  });

  test('crop fractions are bounded to the displayed photograph', () {
    final CaptureEditResult result = applyCaptureEditSynchronously(
      CaptureEditRequest(
        bytes: _png(width: 80, height: 40),
        crop: const Rect.fromLTRB(-0.4, 0.25, 1.4, 0.75),
      ),
    );

    expect(result.width, 80);
    expect(result.height, 20);
  });

  test('a tiny crop is expanded to a non-empty in-bounds result', () {
    final CaptureEditResult result = applyCaptureEditSynchronously(
      CaptureEditRequest(
        bytes: _png(width: 80, height: 40),
        crop: const Rect.fromLTRB(0.99, 0.99, 0.991, 0.991),
      ),
    );

    expect(result.width, inInclusiveRange(1, 80));
    expect(result.height, inInclusiveRange(1, 40));
  });

  test('crop is applied before rotation', () {
    final CaptureEditResult result = applyCaptureEditSynchronously(
      CaptureEditRequest(
        bytes: _png(width: 80, height: 40),
        crop: const Rect.fromLTWH(0.25, 0.25, 0.5, 0.5),
        quarterTurns: 1,
      ),
    );

    expect(result.width, 20);
    expect(result.height, 40);
  });
}
