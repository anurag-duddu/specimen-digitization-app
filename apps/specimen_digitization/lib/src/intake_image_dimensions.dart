import 'dart:typed_data';

/// Pixel dimensions declared by an encoded image's native header.
///
/// These dimensions describe the stored pixel grid, before EXIF orientation
/// is applied. They are therefore safe to send as source-image coordinates.
final class EncodedImageDimensions {
  const EncodedImageDimensions({required this.width, required this.height});

  final int width;
  final int height;
}

/// Reads encoded JPEG or PNG dimensions without decoding pixels.
///
/// Malformed and unsupported inputs return null so dimensions remain an
/// optional upload claim. The caller and server still perform their normal
/// full image validation.
EncodedImageDimensions? readEncodedImageDimensions(
  Uint8List bytes, {
  required String mimeType,
}) {
  return switch (mimeType) {
    'image/jpeg' => _readJpegDimensions(bytes),
    'image/png' => _readPngDimensions(bytes),
    _ => null,
  };
}

EncodedImageDimensions? _readPngDimensions(Uint8List bytes) {
  const List<int> signature = <int>[
    0x89,
    0x50,
    0x4e,
    0x47,
    0x0d,
    0x0a,
    0x1a,
    0x0a,
  ];
  // Signature + length/type + the complete 13-byte IHDR + its CRC.
  if (bytes.lengthInBytes < 33) return null;
  for (int index = 0; index < signature.length; index++) {
    if (bytes[index] != signature[index]) return null;
  }

  // A valid PNG begins with one 13-byte IHDR chunk. Width and height are its
  // first eight data bytes, stored big-endian.
  if (_uint32(bytes, 8) != 13 ||
      bytes[12] != 0x49 ||
      bytes[13] != 0x48 ||
      bytes[14] != 0x44 ||
      bytes[15] != 0x52) {
    return null;
  }
  final int width = _uint32(bytes, 16);
  final int height = _uint32(bytes, 20);
  // PNG dimensions are unsigned on the wire but the specification caps each
  // axis at 2^31 - 1.
  if (width == 0 || height == 0 || width > 0x7fffffff || height > 0x7fffffff) {
    return null;
  }
  return EncodedImageDimensions(width: width, height: height);
}

EncodedImageDimensions? _readJpegDimensions(Uint8List bytes) {
  if (bytes.lengthInBytes < 4 || bytes[0] != 0xff || bytes[1] != 0xd8) {
    return null;
  }

  int offset = 2;
  while (offset < bytes.lengthInBytes) {
    if (bytes[offset] != 0xff) return null;
    while (offset < bytes.lengthInBytes && bytes[offset] == 0xff) {
      offset++;
    }
    if (offset >= bytes.lengthInBytes) return null;

    final int marker = bytes[offset++];
    if (marker == 0x00 || marker == 0xd9 || marker == 0xda) return null;
    if (marker == 0x01 || (marker >= 0xd0 && marker <= 0xd8)) {
      continue;
    }
    if (offset + 2 > bytes.lengthInBytes) return null;

    final int segmentLength = _uint16(bytes, offset);
    if (segmentLength < 2 || offset + segmentLength > bytes.lengthInBytes) {
      return null;
    }
    if (_isStartOfFrame(marker)) {
      if (segmentLength < 8) return null;
      final int componentCount = bytes[offset + 7];
      if (componentCount == 0 || segmentLength < 8 + 3 * componentCount) {
        return null;
      }
      final int height = _uint16(bytes, offset + 3);
      final int width = _uint16(bytes, offset + 5);
      if (width == 0 || height == 0) return null;
      return EncodedImageDimensions(width: width, height: height);
    }
    offset += segmentLength;
  }
  return null;
}

bool _isStartOfFrame(int marker) =>
    marker >= 0xc0 &&
    marker <= 0xcf &&
    marker != 0xc4 &&
    marker != 0xc8 &&
    marker != 0xcc;

int _uint16(Uint8List bytes, int offset) =>
    (bytes[offset] << 8) | bytes[offset + 1];

int _uint32(Uint8List bytes, int offset) =>
    bytes[offset] * 0x1000000 +
    bytes[offset + 1] * 0x10000 +
    bytes[offset + 2] * 0x100 +
    bytes[offset + 3];
