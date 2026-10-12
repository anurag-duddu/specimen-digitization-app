/// Lossless metadata repair for photographs produced by the in-app camera.
///
/// Some Android camera implementations write the TIFF orientation tag as
/// zero. Zero is not one of EXIF's defined orientation values, even when the
/// JPEG pixels are already upright. The ingestion service correctly rejects
/// that malformed metadata.
///
/// This repair is deliberately narrower than an image re-encode: it changes
/// only an IFD0 Orientation entry whose type is SHORT, count is one and value
/// is zero. Every other byte, including the compressed pixels and all other
/// metadata, remains unchanged. Files without that exact condition are
/// returned untouched so server validation still owns every other malformed
/// case.
library;

import 'dart:typed_data';

/// Replaces an invalid EXIF IFD0 orientation value of zero with one.
///
/// The input is never mutated. When no repair is required, the same byte list
/// is returned without allocating a copy.
Uint8List normalizeCameraExifOrientation(Uint8List bytes) {
  final _OrientationField? field = _zeroOrientationField(bytes);
  if (field == null) return bytes;

  final Uint8List normalized = Uint8List.fromList(bytes);
  ByteData.sublistView(
    normalized,
  ).setUint16(field.valueOffset, 1, field.endian);
  return normalized;
}

class _OrientationField {
  const _OrientationField(this.valueOffset, this.endian);

  final int valueOffset;
  final Endian endian;
}

_OrientationField? _zeroOrientationField(Uint8List bytes) {
  if (bytes.lengthInBytes < 4 || bytes[0] != 0xff || bytes[1] != 0xd8) {
    return null;
  }

  int cursor = 2;
  while (cursor < bytes.lengthInBytes) {
    if (bytes[cursor] != 0xff) return null;
    while (cursor < bytes.lengthInBytes && bytes[cursor] == 0xff) {
      cursor++;
    }
    if (cursor >= bytes.lengthInBytes) return null;

    final int marker = bytes[cursor++];
    if (marker == 0xd9 || marker == 0xda) return null;
    if (marker == 0x00) return null;
    if (marker == 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
    if (cursor + 2 > bytes.lengthInBytes) return null;

    final int segmentLength = (bytes[cursor] << 8) | bytes[cursor + 1];
    if (segmentLength < 2) return null;
    final int payloadStart = cursor + 2;
    final int segmentEnd = cursor + segmentLength;
    if (segmentEnd > bytes.lengthInBytes) return null;

    if (marker == 0xe1 && _isExif(bytes, payloadStart, segmentEnd)) {
      return _orientationInExif(bytes, payloadStart + 6, segmentEnd);
    }
    cursor = segmentEnd;
  }
  return null;
}

bool _isExif(Uint8List bytes, int start, int end) =>
    end - start >= 6 &&
    bytes[start] == 0x45 &&
    bytes[start + 1] == 0x78 &&
    bytes[start + 2] == 0x69 &&
    bytes[start + 3] == 0x66 &&
    bytes[start + 4] == 0 &&
    bytes[start + 5] == 0;

_OrientationField? _orientationInExif(
  Uint8List bytes,
  int tiffStart,
  int exifEnd,
) {
  if (tiffStart + 8 > exifEnd) return null;
  final Endian endian;
  if (bytes[tiffStart] == 0x49 && bytes[tiffStart + 1] == 0x49) {
    endian = Endian.little;
  } else if (bytes[tiffStart] == 0x4d && bytes[tiffStart + 1] == 0x4d) {
    endian = Endian.big;
  } else {
    return null;
  }

  final ByteData data = ByteData.sublistView(bytes);
  if (data.getUint16(tiffStart + 2, endian) != 42) return null;
  final int ifdOffset = data.getUint32(tiffStart + 4, endian);
  if (ifdOffset < 8 || ifdOffset > exifEnd - tiffStart) return null;
  final int ifdStart = tiffStart + ifdOffset;
  if (ifdStart + 2 > exifEnd) return null;

  final int entryCount = data.getUint16(ifdStart, endian);
  final int entriesStart = ifdStart + 2;
  final int availableEntryBytes = exifEnd - entriesStart - 4;
  if (availableEntryBytes < 0 || entryCount > availableEntryBytes ~/ 12) {
    return null;
  }

  _OrientationField? zero;
  bool foundOrientation = false;
  for (int index = 0; index < entryCount; index++) {
    final int entry = entriesStart + index * 12;
    if (data.getUint16(entry, endian) != 0x0112) continue;
    if (foundOrientation) return null;
    foundOrientation = true;

    final int type = data.getUint16(entry + 2, endian);
    final int count = data.getUint32(entry + 4, endian);
    if (type != 3 || count != 1) return null;

    final int valueOffset = entry + 8;
    final int value = data.getUint16(valueOffset, endian);
    if (value == 0) {
      zero = _OrientationField(valueOffset, endian);
    } else if (value < 1 || value > 8) {
      return null;
    }
  }
  return zero;
}
