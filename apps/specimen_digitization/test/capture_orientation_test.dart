import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/capture/capture_orientation.dart';

void main() {
  group('camera EXIF orientation normalization', () {
    for (final Endian endian in <Endian>[Endian.little, Endian.big]) {
      test('repairs zero losslessly for ${_endianName(endian)} TIFF', () {
        final Uint8List source = _jpegWithOrientation(0, endian: endian);
        final Uint8List before = Uint8List.fromList(source);

        final Uint8List normalized = normalizeCameraExifOrientation(source);

        expect(source, orderedEquals(before), reason: 'input must not mutate');
        final List<int> changed = <int>[
          for (int index = 0; index < source.lengthInBytes; index++)
            if (source[index] != normalized[index]) index,
        ];
        expect(changed, hasLength(1));
        expect(normalized[changed.single], 1);
        expect(_orientationValue(normalized), 1);
      });

      test(
        'leaves all valid values unchanged for ${_endianName(endian)} TIFF',
        () {
          for (int orientation = 1; orientation <= 8; orientation++) {
            final Uint8List source = _jpegWithOrientation(
              orientation,
              endian: endian,
            );
            final Uint8List normalized = normalizeCameraExifOrientation(source);
            expect(identical(normalized, source), isTrue);
            expect(normalized, orderedEquals(source));
          }
        },
      );
    }

    test('leaves a JPEG with no orientation tag unchanged', () {
      final Uint8List source = _jpegWithOrientation(null);
      expect(identical(normalizeCameraExifOrientation(source), source), isTrue);
    });

    test('leaves a non-JPEG unchanged', () {
      final Uint8List source = Uint8List.fromList(<int>[
        0x89,
        0x50,
        0x4e,
        0x47,
        0x0d,
        0x0a,
        0x1a,
        0x0a,
      ]);
      expect(identical(normalizeCameraExifOrientation(source), source), isTrue);
    });

    test('leaves invalid orientation shapes and values unchanged', () {
      for (final Uint8List source in <Uint8List>[
        _jpegWithOrientation(9),
        _jpegWithOrientation(0, orientationType: 4),
        _jpegWithOrientation(0, orientationCount: 2),
        _jpegWithDuplicateOrientation(),
      ]) {
        expect(
          identical(normalizeCameraExifOrientation(source), source),
          isTrue,
        );
      }
    });

    test('truncated JPEG and EXIF structures fail closed without throwing', () {
      final Uint8List complete = _jpegWithOrientation(0);
      final List<Uint8List> truncated = <Uint8List>[
        Uint8List(0),
        Uint8List.fromList(<int>[0xff]),
        Uint8List.fromList(<int>[0xff, 0xd8, 0xff, 0xe1, 0x00]),
        Uint8List.fromList(complete.sublist(0, 10)),
        Uint8List.fromList(complete.sublist(0, complete.lengthInBytes - 8)),
        _jpegWithOrientation(0, ifdOffset: 7),
      ];

      for (final Uint8List source in truncated) {
        expect(() => normalizeCameraExifOrientation(source), returnsNormally);
        expect(
          identical(normalizeCameraExifOrientation(source), source),
          isTrue,
        );
      }
    });
  });
}

String _endianName(Endian endian) =>
    endian == Endian.little ? 'little-endian' : 'big-endian';

Uint8List _jpegWithOrientation(
  int? orientation, {
  Endian endian = Endian.little,
  int orientationType = 3,
  int orientationCount = 1,
  int ifdOffset = 8,
}) => _jpegWithEntries(
  <({int tag, int type, int count, int value})>[
    if (orientation != null)
      (
        tag: 0x0112,
        type: orientationType,
        count: orientationCount,
        value: orientation,
      ),
    (tag: 0x0100, type: 4, count: 1, value: 1080),
  ],
  endian: endian,
  ifdOffset: ifdOffset,
);

Uint8List _jpegWithDuplicateOrientation() =>
    _jpegWithEntries(<({int tag, int type, int count, int value})>[
      (tag: 0x0112, type: 3, count: 1, value: 0),
      (tag: 0x0112, type: 3, count: 1, value: 1),
    ]);

Uint8List _jpegWithEntries(
  List<({int tag, int type, int count, int value})> entries, {
  Endian endian = Endian.little,
  int ifdOffset = 8,
}) {
  final int tiffLength = 8 + 2 + entries.length * 12 + 4;
  final ByteData tiff = ByteData(tiffLength);
  if (endian == Endian.little) {
    tiff.setUint8(0, 0x49);
    tiff.setUint8(1, 0x49);
  } else {
    tiff.setUint8(0, 0x4d);
    tiff.setUint8(1, 0x4d);
  }
  tiff.setUint16(2, 42, endian);
  tiff.setUint32(4, ifdOffset, endian);
  tiff.setUint16(8, entries.length, endian);
  for (int index = 0; index < entries.length; index++) {
    final entry = entries[index];
    final int offset = 10 + index * 12;
    tiff.setUint16(offset, entry.tag, endian);
    tiff.setUint16(offset + 2, entry.type, endian);
    tiff.setUint32(offset + 4, entry.count, endian);
    if (entry.type == 3 && entry.count == 1) {
      tiff.setUint16(offset + 8, entry.value, endian);
    } else {
      tiff.setUint32(offset + 8, entry.value, endian);
    }
  }

  final Uint8List tiffBytes = tiff.buffer.asUint8List();
  final int app1Length = 2 + 6 + tiffBytes.lengthInBytes;
  return Uint8List.fromList(<int>[
    0xff,
    0xd8,
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
    0xff,
    0xd9,
  ]);
}

int? _orientationValue(Uint8List jpeg) {
  final int tiffStart = 12;
  final Endian endian = jpeg[tiffStart] == 0x49 ? Endian.little : Endian.big;
  final ByteData data = ByteData.sublistView(jpeg);
  final int ifd = tiffStart + data.getUint32(tiffStart + 4, endian);
  final int count = data.getUint16(ifd, endian);
  for (int index = 0; index < count; index++) {
    final int entry = ifd + 2 + index * 12;
    if (data.getUint16(entry, endian) == 0x0112) {
      return data.getUint16(entry + 8, endian);
    }
  }
  return null;
}
