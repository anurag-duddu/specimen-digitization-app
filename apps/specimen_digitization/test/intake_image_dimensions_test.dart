import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:specimen_digitization/src/intake_image_dimensions.dart';

void main() {
  group('encoded intake image dimensions', () {
    for (final ({int width, int height, String shape}) source
        in <({int width, int height, String shape})>[
          (width: 3, height: 2, shape: 'landscape'),
          (width: 2, height: 3, shape: 'portrait'),
        ]) {
      for (int orientation = 1; orientation <= 8; orientation++) {
        test('keeps the stored ${source.shape} grid for EXIF $orientation', () {
          final Uint8List bytes = _jpegWithOrientation(
            width: source.width,
            height: source.height,
            orientation: orientation,
          );
          final Uint8List before = Uint8List.fromList(bytes);

          final EncodedImageDimensions? dimensions = readEncodedImageDimensions(
            bytes,
            mimeType: 'image/jpeg',
          );

          expect(dimensions, isNotNull);
          expect(dimensions!.width, source.width);
          expect(dimensions.height, source.height);
          expect(
            bytes,
            orderedEquals(before),
            reason: 'metadata reads are lossless',
          );
        });
      }
    }

    test('reads PNG IHDR dimensions without decoding pixels', () {
      final Uint8List bytes = Uint8List.fromList(
        image.encodePng(image.Image(width: 7, height: 5)),
      );

      final EncodedImageDimensions? dimensions = readEncodedImageDimensions(
        bytes,
        mimeType: 'image/png',
      );

      expect(dimensions, isNotNull);
      expect(dimensions!.width, 7);
      expect(dimensions.height, 5);
    });

    test('fails closed for malformed or unsupported headers', () {
      final List<({Uint8List bytes, String mimeType})> inputs =
          <({Uint8List bytes, String mimeType})>[
            (bytes: Uint8List(0), mimeType: 'image/jpeg'),
            (
              bytes: Uint8List.fromList(<int>[0xff, 0xd8, 0xff, 0xe1, 0xff]),
              mimeType: 'image/jpeg',
            ),
            (
              bytes: Uint8List.fromList(<int>[
                0x89,
                0x50,
                0x4e,
                0x47,
                0x0d,
                0x0a,
                0x1a,
                0x0a,
              ]),
              mimeType: 'image/png',
            ),
            (
              bytes: Uint8List.fromList(<int>[0x49, 0x49, 0x2a, 0x00]),
              mimeType: 'image/tiff',
            ),
            (
              bytes: Uint8List.fromList(<int>[0x00, 0x00, 0x00, 0x18]),
              mimeType: 'image/heic',
            ),
          ];

      for (final input in inputs) {
        expect(
          () =>
              readEncodedImageDimensions(input.bytes, mimeType: input.mimeType),
          returnsNormally,
        );
        expect(
          readEncodedImageDimensions(input.bytes, mimeType: input.mimeType),
          isNull,
        );
      }
    });

    test('reads oversized JPEG dimensions without allocating pixel blocks', () {
      final Uint8List bytes = _minimalJpegHeader(width: 65535, height: 65535);

      final EncodedImageDimensions? dimensions = readEncodedImageDimensions(
        bytes,
        mimeType: 'image/jpeg',
      );

      expect(dimensions, isNotNull);
      expect(dimensions!.width, 65535);
      expect(dimensions.height, 65535);
    });

    for (final ({int marker, String encoding}) frame
        in <({int marker, String encoding})>[
          (marker: 0xc0, encoding: 'baseline'),
          (marker: 0xc2, encoding: 'progressive'),
        ]) {
      test('reads ${frame.encoding} JPEG SOF dimensions', () {
        final Uint8List bytes = _minimalJpegHeader(
          width: 640,
          height: 480,
          frameMarker: frame.marker,
        );

        final EncodedImageDimensions? dimensions = readEncodedImageDimensions(
          bytes,
          mimeType: 'image/jpeg',
        );

        expect(dimensions, isNotNull);
        expect(dimensions!.width, 640);
        expect(dimensions.height, 480);
      });
    }

    test('every truncated JPEG prefix fails safely', () {
      final Uint8List complete = _minimalJpegHeader(width: 640, height: 480);

      for (int length = 0; length < complete.lengthInBytes; length++) {
        final Uint8List prefix = Uint8List.fromList(
          complete.sublist(0, length),
        );
        expect(
          () => readEncodedImageDimensions(prefix, mimeType: 'image/jpeg'),
          returnsNormally,
          reason: 'prefix length $length',
        );
      }
    });

    test('malformed JPEG marker and segment bounds fail closed', () {
      final List<Uint8List> malformed = <Uint8List>[
        Uint8List.fromList(<int>[0xff, 0xd8, 0x00, 0xe1]),
        Uint8List.fromList(<int>[0xff, 0xd8, 0xff, 0x00]),
        Uint8List.fromList(<int>[0xff, 0xd8, 0xff, 0xe1]),
        Uint8List.fromList(<int>[0xff, 0xd8, 0xff, 0xe1, 0x00, 0x01]),
        Uint8List.fromList(<int>[0xff, 0xd8, 0xff, 0xe1, 0xff, 0xff]),
        Uint8List.fromList(<int>[
          0xff,
          0xd8,
          0xff,
          0xc0,
          0x00,
          0x07,
          0x08,
          0x00,
          0x02,
          0x00,
          0x03,
        ]),
        Uint8List.fromList(<int>[
          0xff,
          0xd8,
          0xff,
          0xc0,
          0x00,
          0x08,
          0x08,
          0x00,
          0x02,
          0x00,
          0x03,
          0x01,
        ]),
      ];

      for (final Uint8List bytes in malformed) {
        expect(
          () => readEncodedImageDimensions(bytes, mimeType: 'image/jpeg'),
          returnsNormally,
        );
        expect(
          readEncodedImageDimensions(bytes, mimeType: 'image/jpeg'),
          isNull,
        );
      }
    });

    test('reads the largest permitted PNG header dimension', () {
      final Uint8List bytes = _minimalPngHeader(width: 0x7fffffff, height: 1);

      final EncodedImageDimensions? dimensions = readEncodedImageDimensions(
        bytes,
        mimeType: 'image/png',
      );

      expect(dimensions, isNotNull);
      expect(dimensions!.width, 0x7fffffff);
      expect(dimensions.height, 1);
    });

    test('rejects PNG dimensions above the specification limit', () {
      final Uint8List bytes = _minimalPngHeader(width: 0x80000000, height: 1);

      expect(readEncodedImageDimensions(bytes, mimeType: 'image/png'), isNull);
    });
  });
}

Uint8List _jpegWithOrientation({
  required int width,
  required int height,
  required int orientation,
}) {
  final Uint8List jpeg = Uint8List.fromList(
    image.encodeJpg(image.Image(width: width, height: height), quality: 90),
  );
  final ByteData tiff = ByteData(26)
    ..setUint8(0, 0x49)
    ..setUint8(1, 0x49)
    ..setUint16(2, 42, Endian.little)
    ..setUint32(4, 8, Endian.little)
    ..setUint16(8, 1, Endian.little)
    ..setUint16(10, 0x0112, Endian.little)
    ..setUint16(12, 3, Endian.little)
    ..setUint32(14, 1, Endian.little)
    ..setUint16(18, orientation, Endian.little);
  final Uint8List tiffBytes = tiff.buffer.asUint8List();
  final int app1Length = 2 + 6 + tiffBytes.lengthInBytes;
  return Uint8List.fromList(<int>[
    ...jpeg.sublist(0, 2),
    0xff,
    0xe1,
    app1Length >> 8,
    app1Length & 0xff,
    0x45,
    0x78,
    0x69,
    0x66,
    0,
    0,
    ...tiffBytes,
    ...jpeg.sublist(2),
  ]);
}

Uint8List _minimalJpegHeader({
  required int width,
  required int height,
  int frameMarker = 0xc0,
}) {
  return Uint8List.fromList(<int>[
    0xff,
    0xd8,
    0xff,
    frameMarker,
    0x00,
    0x0b,
    0x08,
    height >> 8,
    height & 0xff,
    width >> 8,
    width & 0xff,
    0x01,
    0x01,
    0x11,
    0x00,
  ]);
}

Uint8List _minimalPngHeader({required int width, required int height}) {
  final ByteData header = ByteData(33)
    ..setUint8(0, 0x89)
    ..setUint8(1, 0x50)
    ..setUint8(2, 0x4e)
    ..setUint8(3, 0x47)
    ..setUint8(4, 0x0d)
    ..setUint8(5, 0x0a)
    ..setUint8(6, 0x1a)
    ..setUint8(7, 0x0a)
    ..setUint32(8, 13)
    ..setUint8(12, 0x49)
    ..setUint8(13, 0x48)
    ..setUint8(14, 0x44)
    ..setUint8(15, 0x52)
    ..setUint32(16, width)
    ..setUint32(20, height)
    ..setUint8(24, 8)
    ..setUint8(25, 2);
  return header.buffer.asUint8List();
}
