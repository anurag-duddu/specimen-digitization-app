import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' show ImageByteFormat;

import 'package:camera/camera.dart' show XFile;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as image;
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'capture_screen_test.dart'
    show FakeCaptureCamera, takeOne, waitForCameraCondition;
import 'golden/golden_harness.dart' show settleImages;

class _WholePhotoCamera extends FakeCaptureCamera {
  @override
  Widget preview(BuildContext context) => Image.memory(
    FakeCaptureCamera.frame,
    key: const ValueKey('whole-camera-photo'),
    fit: BoxFit.contain,
    semanticLabel: 'Synthetic whole camera photograph',
  );
}

Future<void> _reach(WidgetTester tester, Finder control) async {
  await tester.ensureVisible(control);
  await tester.pumpAndSettle();
  expect(control.hitTestable(), findsOneWidget);
  final Rect bounds = tester.getRect(control);
  final Size window = tester.view.physicalSize / tester.view.devicePixelRatio;
  expect(bounds.top, greaterThanOrEqualTo(0));
  expect(bounds.bottom, lessThanOrEqualTo(window.height));
  expect(bounds.left, greaterThanOrEqualTo(0));
  expect(bounds.right, lessThanOrEqualTo(window.width));
}

Finder _button(String label) => find.byWidgetPredicate(
  (widget) =>
      (widget is UiButton && widget.label == label) ||
      (widget is UiIconButton && widget.semanticsLabel == label),
);

Future<void> _snapshot(WidgetTester tester, String name) async {
  if (!const bool.fromEnvironment('CAPTURE_REVIEW_SCREENSHOTS')) return;
  final Finder photograph = find.byType(Image);
  if (photograph.evaluate().isNotEmpty) {
    await tester.runAsync(
      () => precacheImage(
        tester.widget<Image>(photograph).image,
        tester.element(photograph),
      ),
    );
    await tester.pumpAndSettle();
  }
  final RenderRepaintBoundary boundary = tester.renderObject(
    find.byKey(const ValueKey('capture-synthetic-frame')),
  );
  await tester.runAsync(() async {
    final pixels = await boundary.toImage(pixelRatio: 1);
    try {
      final data = await pixels.toByteData(format: ImageByteFormat.png);
      final directory = Directory(
        const String.fromEnvironment(
          'CAPTURE_REVIEW_SCREENSHOT_DIRECTORY',
          defaultValue: 'build/capture-review-synthetic',
        ),
      );
      await directory.create(recursive: true);
      await File('${directory.path}/$name.png').writeAsBytes(
        data!.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
      );
    } finally {
      pixels.dispose();
    }
  });
}

void main() {
  for (final dark in <bool>[false, true]) {
    for (final problem in <bool>[false, true]) {
      testWidgets(
        '${dark ? 'dark' : 'light'} compact viewfinder keeps a useful whole photo '
        'at 200% text, problem=$problem',
        (tester) async {
          tester.view.devicePixelRatio = 1;
          tester.view.physicalSize = const Size(390, 844);
          tester.view.padding = const FakeViewPadding(top: 44, bottom: 34);
          tester.view.viewPadding = const FakeViewPadding(top: 44, bottom: 34);
          addTearDown(tester.view.reset);
          final activity = ValueNotifier(
            CaptureActivity(
              label: problem
                  ? '2 photographs processing, 1 needs attention'
                  : 'No photographs yet',
              progress: problem ? 0.4 : null,
              problem: problem,
            ),
          );
          addTearDown(activity.dispose);
          await tester.pumpWidget(
            MaterialApp(
              theme: dark ? AppTheme.dark() : AppTheme.light(),
              builder: (context, child) => MediaQuery(
                data: MediaQuery.of(context).copyWith(
                  textScaler: TextScaler.linear(2),
                  disableAnimations: true,
                ),
                child: child!,
              ),
              home: CaptureScreen(
                camera: () async => _WholePhotoCamera(),
                activity: activity,
                activitySnapshot: () => activity.value,
              ),
            ),
          );
          await tester.pumpAndSettle();
          await settleImages(tester);
          final photo = find.byKey(const ValueKey('whole-camera-photo'));
          final painted = applyBoxFit(
            BoxFit.contain,
            const Size(800, 600),
            tester.getSize(photo),
          ).destination;
          // A whole 4:3 photograph must span most of the compact window, not
          // regress to the observed 100x75 thumbnail beneath secondary copy.
          expect(painted.width, greaterThanOrEqualTo(390 * 0.85));
          expect(painted.height, greaterThanOrEqualTo(844 * 0.30));
          final shutter = find.byKey(const ValueKey('capture-shutter'));
          final automatic = find.byKey(const ValueKey('capture-auto-ingest'));
          for (final control in [shutter, _button('Done'), automatic]) {
            await _reach(tester, control);
            expect(tester.getSize(control).height, greaterThanOrEqualTo(48));
          }
          final shutterBefore = tester.getRect(shutter);
          await tester.ensureVisible(find.text(activity.value.label));
          await tester.pumpAndSettle();
          expect(find.text(activity.value.label).hitTestable(), findsOneWidget);
          expect(tester.getRect(shutter), shutterBefore);
          expect(tester.widget<UiSegmented<bool>>(automatic).value, isFalse);
          expect(
            find.text('Exposure is not measured on this device.'),
            findsNothing,
          );
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox.shrink());
          await tester.pumpAndSettle();
        },
      );
    }
  }

  for (final (String theme, ThemeData data) in [
    ('light', AppTheme.light()),
    ('dark', AppTheme.dark()),
  ]) {
    for (final Size size in [const Size(390, 844), const Size(844, 390)]) {
      testWidgets(
        '$theme $size camera controls remain reachable at 200% text',
        (WidgetTester tester) async {
          tester.view.devicePixelRatio = 1;
          tester.view.physicalSize = size;
          addTearDown(tester.view.reset);
          final FakeCaptureCamera camera = FakeCaptureCamera();
          await tester.pumpWidget(
            MaterialApp(
              theme: data,
              builder: (context, child) => MediaQuery(
                data: MediaQuery.of(context).copyWith(
                  textScaler: TextScaler.linear(2),
                  disableAnimations: true,
                ),
                child: RepaintBoundary(
                  key: const ValueKey('capture-synthetic-frame'),
                  child: child!,
                ),
              ),
              home: CaptureScreen(camera: () async => camera),
            ),
          );
          await tester.pumpAndSettle();
          expect(
            MediaQuery.textScalerOf(
              tester.element(find.byType(CaptureScreen)),
            ).scale(10),
            20,
          );
          expect(tester.takeException(), isNull);
          await _reach(
            tester,
            find.byKey(const ValueKey('capture-auto-ingest')),
          );
          await _reach(tester, _button('Done'));
          final Finder shutter = find.byKey(const ValueKey('capture-shutter'));
          await _reach(tester, shutter);
          final String scene =
              '$theme-${size.width.toInt()}x${size.height.toInt()}';
          await _snapshot(tester, '$scene-viewfinder');
          await takeOne(tester);
          expect(tester.takeException(), isNull);

          for (final label in ['Retake', 'Send', 'Rotate', 'Crop']) {
            await _reach(tester, _button(label));
          }
          await _snapshot(tester, '$scene-review');
          await tester.tap(_button('Crop'));
          await tester.pumpAndSettle();
          for (final label in [
            'Move left',
            'Move right',
            'Move up',
            'Move down',
            'Expand frame',
            'Reduce frame',
            'Apply crop',
            'Cancel crop',
          ]) {
            await _reach(tester, _button(label));
          }
          await _snapshot(tester, '$scene-crop');
          await tester.tap(_button('Cancel crop'));
          await tester.pumpAndSettle();
          expect(
            (tester.widget<Image>(find.byType(Image)).image as MemoryImage)
                .bytes,
            orderedEquals(camera.captureBytes),
          );
          expect(tester.takeException(), isNull);
        },
      );
    }
  }

  testWidgets(
    'review sends the applied pixels once and crop cancel keeps bytes',
    (WidgetTester tester) async {
      final FakeCaptureCamera camera = FakeCaptureCamera();
      final Uint8List original = Uint8List.fromList(camera.captureBytes);
      final List<XFile> accepted = [];
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: CaptureScreen(
            camera: () async => camera,
            onAccepted: accepted.add,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await takeOne(tester);
      expect(accepted, isEmpty);

      await _reach(tester, _button('Rotate'));
      await tester.tap(_button('Rotate'));
      await tester.pump();
      await waitForCameraCondition(
        tester,
        () => _button('Rotate').evaluate().isNotEmpty,
      );
      final Uint8List rotated = Uint8List.fromList(
        (tester.widget<Image>(find.byType(Image)).image as MemoryImage).bytes,
      );
      final image.Image decoded = image.decodePng(rotated)!;
      expect((decoded.width, decoded.height), (600, 800));

      await _reach(tester, _button('Crop'));
      await tester.tap(_button('Crop'));
      await tester.pumpAndSettle();
      await _reach(tester, _button('Move left'));
      await tester.tap(_button('Move left'));
      await tester.pump();
      await _reach(tester, _button('Cancel crop'));
      await tester.tap(_button('Cancel crop'));
      await tester.pumpAndSettle();
      expect(
        (tester.widget<Image>(find.byType(Image)).image as MemoryImage).bytes,
        orderedEquals(rotated),
      );
      expect(accepted, isEmpty);

      await _reach(tester, _button('Crop'));
      await tester.tap(_button('Crop'));
      await tester.pumpAndSettle();
      await _reach(tester, _button('Apply crop'));
      await tester.tap(_button('Apply crop'));
      await tester.pump();
      await waitForCameraCondition(
        tester,
        () => _button('Send').evaluate().isNotEmpty,
      );
      final Uint8List cropped =
          (tester.widget<Image>(find.byType(Image)).image as MemoryImage).bytes;
      final image.Image decodedCrop = image.decodePng(cropped)!;
      expect((decodedCrop.width, decodedCrop.height), (528, 704));
      // The accepted output must match the displayed crop, including its pixels.
      expect(
        decodedCrop.getPixel(0, 0).toList(),
        decoded.getPixel(36, 48).toList(),
      );
      expect(accepted, isEmpty);
      await _reach(tester, _button('Send'));
      await tester.tap(_button('Send'));
      await tester.tap(_button('Send'));
      await tester.pumpAndSettle();
      expect(accepted, hasLength(1));
      expect(await accepted.single.readAsBytes(), orderedEquals(cropped));
      expect(camera.captureBytes, orderedEquals(original));
      expect(find.text('1'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('crop reduction keeps the current minimum frame extent', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    final FakeCaptureCamera camera = FakeCaptureCamera();
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(500, 900);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: CaptureScreen(camera: () async => camera),
      ),
    );
    await tester.pumpAndSettle();
    await takeOne(tester);
    await _reach(tester, _button('Crop'));
    await tester.tap(_button('Crop'));
    await tester.pumpAndSettle();
    await _reach(tester, _button('Reduce frame'));
    for (var step = 0; step < 25; step++) {
      await tester.tap(_button('Reduce frame'));
      await tester.pump();
    }
    expect(CaptureScreen.minimumCropExtent, 0.16);
    final Finder selection = find.bySemanticsLabel(RegExp('Crop selection\\.'));
    expect(tester.getSemantics(selection).value, contains('width 16 percent'));
    expect(tester.getSemantics(selection).value, contains('height 16 percent'));
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });
}
