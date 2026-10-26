// The thumbnail decodes at display size without changing the photograph's
// shape.
//
// The intake manifest hands this widget the full camera photograph. Decoding
// it to a fixed square with both cache dimensions set stretches a 4:3 or 3:2
// frame into 1:1 before `BoxFit.cover` ever sees it, so the thumbnail shows a
// squashed photograph where it used to show a centre crop.

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:specimen_digitization/src/widgets/thumbnail.dart';

import 'harness.dart';

Uint8List _png(int width, int height) => Uint8List.fromList(
  image.encodePng(image.Image(width: width, height: height)),
);

/// The pixel size the thumbnail's image provider actually decodes to.
///
/// The widget's own decode started inside the test's fake-async zone, where a
/// codec never completes. The cache is cleared so the provider decodes again
/// in the real zone, inside `runAsync`, exactly as it would on a device.
Future<Size> _decodedSize(WidgetTester tester) async {
  final Image shown = tester.widget<Image>(find.byType(Image));
  PaintingBinding.instance.imageCache.clear();
  PaintingBinding.instance.imageCache.clearLiveImages();
  final Size? size = await tester.runAsync(() async {
    final Completer<Size> decoded = Completer<Size>();
    final ImageStream stream = shown.image.resolve(ImageConfiguration.empty);
    final ImageStreamListener listener = ImageStreamListener(
      (ImageInfo info, bool _) {
        decoded.complete(
          Size(info.image.width.toDouble(), info.image.height.toDouble()),
        );
      },
      onError: (Object error, StackTrace? stack) =>
          decoded.completeError(error, stack),
    );
    stream.addListener(listener);
    try {
      return await decoded.future.timeout(const Duration(seconds: 10));
    } finally {
      stream.removeListener(listener);
    }
  });
  return size!;
}

void main() {
  const double pixelRatio = 3;
  final int cacheSide = (SpecimenThumbnail.side * pixelRatio).ceil();

  for (final ({String shape, int width, int height}) photo
      in <({String shape, int width, int height})>[
        (shape: 'landscape 2:1', width: 800, height: 400),
        (shape: 'landscape 4:3', width: 1024, height: 768),
        (shape: 'portrait 3:4', width: 768, height: 1024),
      ]) {
    testWidgets('a ${photo.shape} photograph keeps its shape when decoded', (
      WidgetTester tester,
    ) async {
      tester.view.devicePixelRatio = pixelRatio;
      await pumpComponent(
        tester,
        SpecimenThumbnail(bytes: _png(photo.width, photo.height)),
      );

      final Size decoded = await _decodedSize(tester);

      expect(
        decoded.width / decoded.height,
        closeTo(photo.width / photo.height, 0.02),
        reason: 'decoded ${decoded.width}x${decoded.height}',
      );
    });
  }

  testWidgets(
    'a photograph larger than the thumbnail decodes at display size',
    (WidgetTester tester) async {
      tester.view.devicePixelRatio = pixelRatio;
      await pumpComponent(tester, SpecimenThumbnail(bytes: _png(1600, 1200)));

      final Size decoded = await _decodedSize(tester);

      expect(decoded.width, cacheSide.toDouble());
      expect(decoded.height, lessThan(1200));
    },
  );
}
