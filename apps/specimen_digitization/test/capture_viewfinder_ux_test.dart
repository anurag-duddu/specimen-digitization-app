import 'dart:math' as math;
import 'dart:typed_data';

import 'package:camera/camera.dart' show XFile;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/not_calibrated_chip.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'capture_screen_test.dart'
    show FakeCaptureCamera, takeOne, waitForCameraCondition;

Finder _button(String label) => find.byWidgetPredicate(
  (widget) => widget is UiButton && widget.label == label,
);

Future<void> _pump(
  WidgetTester tester,
  CaptureScreen screen, {
  Size size = const Size(390, 844),
  double scale = 1,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(textScaler: TextScaler.linear(scale)),
        child: child!,
      ),
      home: screen,
    ),
  );
  await tester.pumpAndSettle();
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
  });
}

// Text builds a RichText child. Count that content once, plus standalone
// RichText, and only where it is painted and hittable on this route.
List<String> _visibleCopy(WidgetTester tester) => find
    .descendant(
      of: find.byType(CaptureScreen),
      matching: find.byWidgetPredicate(
        (widget) => widget is Text || widget is RichText,
      ),
    )
    .hitTestable()
    .evaluate()
    .where((element) => element.findAncestorWidgetOfExactType<Icon>() == null)
    .where(
      (element) =>
          element.widget is Text ||
          element.findAncestorWidgetOfExactType<Text>() == null,
    )
    .map((element) {
      final widget = element.widget;
      return (widget is Text
              ? widget.data ?? widget.textSpan!.toPlainText()
              : (widget as RichText).text.toPlainText())
          .trim();
    })
    .where((text) => text.isNotEmpty)
    .toList();

int _wordCount(Iterable<String> texts) =>
    texts.fold(0, (count, text) => count + text.split(RegExp(r'\s+')).length);

class _DistinctCaptureCamera extends FakeCaptureCamera {
  @override
  Future<XFile> capture() async => XFile.fromData(
    Uint8List.fromList(FakeCaptureCamera.frame),
    name: 'distinct.png',
    mimeType: 'image/png',
  );
}

Future<Object> _cachedKey(WidgetTester tester, Finder photo) async {
  final provider = tester.widget<Image>(photo).image;
  await tester.runAsync(() => precacheImage(provider, tester.element(photo)));
  await tester.pumpAndSettle();
  final key = await provider.obtainKey(ImageConfiguration.empty);
  expect(PaintingBinding.instance.imageCache.containsKey(key), isTrue);
  return key;
}

void _expectEvicted(Object key) {
  final cache = PaintingBinding.instance.imageCache;
  expect(cache.containsKey(key), isFalse, reason: 'obsolete photo cached');
  expect(cache.statusForKey(key).live, isFalse, reason: 'obsolete photo live');
}

void main() {
  for (final wired in [false, true]) {
    testWidgets(
      'INT-UX-010 viewfinder has one instruction and no caveats onCaptured=$wired',
      (tester) async {
        await _pump(
          tester,
          CaptureScreen(
            camera: () async => FakeCaptureCamera(),
            onCaptured: wired ? (_) {} : null,
          ),
        );
        expect(find.byType(NotCalibratedChip), findsNothing);
        expect(find.text('Fit specimen and labels inside'), findsOneWidget);
        final texts = _visibleCopy(tester);
        expect(
          texts,
          unorderedEquals([
            'Review',
            'Send now',
            'Fit specimen and labels inside',
            if (wired) 'Sensitive',
            '0',
            'Done',
          ]),
        );
        expect(
          _wordCount(
            texts.where(
              (text) => ![
                'Review',
                'Send now',
                'Sensitive',
                '0',
                'Done',
              ].contains(text),
            ),
          ),
          lessThanOrEqualTo(6),
        );
        expect(
          find.textContaining('Framing, focus and label coverage'),
          findsNothing,
        );
        expect(find.textContaining('skip review'), findsNothing);
        expect(
          find.text('Review and adjust each photo before sending it.'),
          findsNothing,
        );
      },
    );
  }

  for (final review in [false, true]) {
    testWidgets(
      'F1 legacy callback hides Sensitive in ${review ? 'review' : 'viewfinder'}',
      (tester) async {
        final accepted = <XFile>[];
        await _pump(
          tester,
          CaptureScreen(
            camera: () async => FakeCaptureCamera(),
            onAccepted: accepted.add,
          ),
        );
        if (review) await takeOne(tester);
        expect(find.byKey(const ValueKey('capture-sensitive')), findsNothing);
        expect(
          find.byKey(const ValueKey('capture-review-sensitive')),
          findsNothing,
        );
        expect(find.text('Sensitive'), findsNothing);
        if (review) {
          await tester.tap(_button('Send'));
          await tester.pumpAndSettle();
          expect(accepted, hasLength(1));
        }
      },
    );
  }

  testWidgets(
    'F2 Send now evicts replaced thumbnails and disposes the last one',
    (tester) async {
      var accepted = 0;
      final camera = _DistinctCaptureCamera();
      await _pump(
        tester,
        CaptureScreen(
          camera: () async => camera,
          autoIngest: true,
          onAccepted: (_) => accepted++,
        ),
      );
      final unrelated = MemoryImage(
        Uint8List.fromList(FakeCaptureCamera.frame),
      );
      await tester.runAsync(
        () => precacheImage(
          unrelated,
          tester.element(find.byType(CaptureScreen)),
        ),
      );
      await tester.pumpAndSettle();
      final unrelatedKey = await unrelated.obtainKey(ImageConfiguration.empty);
      addTearDown(unrelated.evict);
      final keys = <Object>[];
      for (var count = 1; count <= 4; count++) {
        await tester.tap(find.byKey(const ValueKey('capture-shutter')));
        await waitForCameraCondition(tester, () => accepted == count);
        expect(accepted, count);
        await tester.pumpAndSettle();
        final photo = find.descendant(
          of: find.byKey(const ValueKey('capture-last-shot')),
          matching: find.byType(Image),
        );
        final key = await _cachedKey(tester, photo);
        expect(
          keys,
          isNot(contains(key)),
          reason: 'each capture uses a distinct buffer',
        );
        for (final previous in keys) {
          _expectEvicted(previous);
        }
        keys.add(key);
        expect(
          PaintingBinding.instance.imageCache.containsKey(unrelatedKey),
          isTrue,
        );
      }
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      for (final key in keys) {
        _expectEvicted(key);
      }
      expect(
        PaintingBinding.instance.imageCache.containsKey(unrelatedKey),
        isTrue,
      );
    },
  );

  testWidgets(
    'F2 review evicts edited and retaken photos and disposes the last one',
    (tester) async {
      await _pump(
        tester,
        CaptureScreen(camera: () async => _DistinctCaptureCamera()),
      );
      await takeOne(tester);
      final photo = find.byWidgetPredicate(
        (widget) =>
            widget is Image && widget.semanticLabel == 'The photo you took',
      );
      final original = await _cachedKey(tester, photo);
      await tester.tap(_button('Rotate'));
      await tester.pump();
      await waitForCameraCondition(
        tester,
        () => _button('Rotate').evaluate().isNotEmpty,
      );
      await tester.pumpAndSettle();
      final edited = await _cachedKey(tester, photo);
      expect(edited, isNot(original));
      _expectEvicted(original);
      await tester.tap(_button('Retake'));
      await tester.pumpAndSettle();
      _expectEvicted(edited);
      await takeOne(tester);
      final last = await _cachedKey(tester, photo);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      _expectEvicted(last);
    },
  );

  for (final size in [const Size(568, 320), const Size(667, 375)]) {
    testWidgets(
      'F3 short review keeps photo and equal reachable decisions at $size scale=2.0',
      (tester) async {
        await _pump(
          tester,
          CaptureScreen(
            camera: () async => FakeCaptureCamera(),
            onCaptured: (_) {},
          ),
          scale: 2,
        );
        await takeOne(tester);
        final photo = find.byWidgetPredicate(
          (widget) =>
              widget is Image && widget.semanticLabel == 'The photo you took',
        );
        await _cachedKey(tester, photo);
        tester.view.padding = const FakeViewPadding(top: 24);
        tester.view.viewPadding = const FakeViewPadding(top: 24);
        tester.view.physicalSize = size;
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(
          tester.getSize(photo).height,
          greaterThanOrEqualTo(math.max(80, size.height / 4)),
        );
        for (final label in ['Retake', 'Send']) {
          await tester.ensureVisible(_button(label));
          await tester.pumpAndSettle();
          expect(_button(label).hitTestable(), findsOneWidget);
          expect(
            tester.getSize(_button(label)).height,
            greaterThanOrEqualTo(48),
          );
        }
        expect(
          tester.getSize(_button('Retake')).width,
          tester.getSize(_button('Send')).width,
        );
        expect(
          tester.getSize(
            find.byKey(const ValueKey('capture-review-Retake-surface')),
          ),
          tester.getSize(
            find.byKey(const ValueKey('capture-review-Send-surface')),
          ),
        );
        expect(tester.takeException(), isNull);
      },
    );
  }

  for (final wired in [false, true]) {
    testWidgets(
      'F4 INT-UX-021 visible review copy is at most eight words onCaptured=$wired',
      (tester) async {
        await _pump(
          tester,
          CaptureScreen(
            camera: () async => FakeCaptureCamera(),
            onCaptured: wired ? (_) {} : null,
          ),
        );
        for (var count = 0; count < 3; count++) {
          await takeOne(tester);
          await tester.tap(_button('Send'));
          await tester.pumpAndSettle();
        }
        await takeOne(tester);
        final visible = _visibleCopy(tester);
        expect(visible, contains('Photo 4'));
        expect(visible, contains('All labels sharp and in frame?'));
        if (wired) expect(visible, contains('Sensitive'));
        final prose = visible.where(
          (text) =>
              !['Photo 4', 'Retake', 'Send', 'Crop', 'Rotate'].contains(text),
        );
        expect(_wordCount(prose), lessThanOrEqualTo(8));
      },
    );
  }

  for (final kind in CaptureUnavailable.values) {
    testWidgets(
      'F5 unavailable $kind Close exits without fallback and leaves one body action',
      (tester) async {
        final semantics = tester.ensureSemantics();
        try {
          CaptureResult? result;
          await tester.pumpWidget(
            MaterialApp(
              theme: AppTheme.light(),
              home: Builder(
                builder: (context) => TextButton(
                  onPressed: () async {
                    result = await Navigator.of(context).push(
                      CaptureScreen.route(
                        () async => FakeCaptureCamera(unavailable: kind),
                      ),
                    );
                  },
                  child: const Text('Open'),
                ),
              ),
            ),
          );
          await tester.tap(find.text('Open'));
          await tester.pumpAndSettle();
          final close = find.byWidgetPredicate(
            (widget) =>
                widget is UiIconButton &&
                widget.semanticsLabel == CaptureScreen.closeLabel,
          );
          expect(close, findsOneWidget);
          expect(
            tester.widget<UiIconButton>(close).tooltip,
            CaptureScreen.closeLabel,
          );
          expect(
            tester.getCenter(close).dx,
            lessThan(tester.view.physicalSize.width / 2),
          );
          final spokenClose = find.descendant(
            of: close,
            matching: find.bySemanticsLabel(CaptureScreen.closeLabel),
          );
          expect(spokenClose, findsOneWidget);
          final spokenData = tester
              .getSemantics(spokenClose)
              .getSemanticsData();
          expect(spokenData.label, CaptureScreen.closeLabel);
          expect(spokenData.tooltip, CaptureScreen.closeLabel);
          expect(find.byType(UiButton), findsOneWidget);
          expect(
            _wordCount(
              _visibleCopy(tester).where(
                (text) => !['Choose files', 'Use phone camera'].contains(text),
              ),
            ),
            lessThanOrEqualTo(10),
          );
          await tester.tap(close);
          await tester.pumpAndSettle();
          expect(result, isNotNull);
          expect(result!.unavailable, isNull);
          expect(result!.needsFallback, isFalse);
          expect(find.byType(CaptureScreen), findsNothing);
        } finally {
          semantics.dispose();
        }
      },
    );
  }

  testWidgets('INT-UX-011 send segments sit above preview and report changes', (
    tester,
  ) async {
    final changes = <bool>[];
    await _pump(
      tester,
      CaptureScreen(
        camera: () async => FakeCaptureCamera(),
        onAutoIngestChanged: changes.add,
      ),
    );
    final mode = find.byType(UiSegmented<bool>);
    expect(mode, findsOneWidget);
    expect(
      tester.getBottomLeft(mode).dy,
      lessThanOrEqualTo(
        tester.getTopLeft(find.byKey(const ValueKey('fake-preview'))).dy,
      ),
    );
    await tester.tap(find.text('Send now'));
    await tester.pumpAndSettle();
    expect(changes, [true]);
    expect(tester.widget<UiSegmented<bool>>(mode).value, isTrue);
    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();
    expect(changes, [true, false]);
  });

  testWidgets(
    'INT-UX-012 two captures show last photo and count beside shutter',
    (tester) async {
      var accepted = 0;
      final camera = FakeCaptureCamera();
      await _pump(
        tester,
        CaptureScreen(
          camera: () async => camera,
          autoIngest: true,
          onAccepted: (_) => accepted++,
        ),
      );
      for (var count = 1; count <= 2; count++) {
        await tester.tap(find.byKey(const ValueKey('capture-shutter')));
        await waitForCameraCondition(tester, () => accepted == count);
        await tester.pumpAndSettle();
      }
      expect(tester.widget<UiBadge>(find.byType(UiBadge)).count, 2);
      expect(find.text('2'), findsOneWidget);
      expect(find.textContaining('in this batch'), findsNothing);
      final thumbnail = find.byKey(const ValueKey('capture-last-shot'));
      expect(
        find.descendant(of: thumbnail, matching: find.byType(Image)),
        findsOneWidget,
      );
      final shutter = tester.getCenter(
        find.byKey(const ValueKey('capture-shutter')),
      );
      expect(tester.getCenter(thumbnail).dx, lessThan(shutter.dx));
      expect(shutter.dx, 195);
      expect(tester.getCenter(_button('Done')).dx, greaterThan(shutter.dx));
    },
  );

  testWidgets('INT-UX-014 sensitivity starts off and stays visibly on', (
    tester,
  ) async {
    await _pump(
      tester,
      CaptureScreen(
        camera: () async => FakeCaptureCamera(),
        onCaptured: (_) {},
      ),
    );
    final sensitive = find.byWidgetPredicate(
      (widget) => widget is UiSwitch && widget.label == 'Sensitive',
    );
    expect(sensitive, findsOneWidget);
    expect(tester.widget<UiSwitch>(sensitive).value, isFalse);
    await tester.tap(sensitive);
    await tester.pumpAndSettle();
    expect(tester.widget<UiSwitch>(sensitive).value, isTrue);
    expect(find.text('Sensitive'), findsOneWidget);
  });

  testWidgets(
    'INT-UX-015 absent and clean readings show no exposure text or pass',
    (tester) async {
      final camera = FakeCaptureCamera();
      await _pump(tester, CaptureScreen(camera: () async => camera));
      expect(
        find.text('Exposure is not measured on this device.'),
        findsNothing,
      );
      camera.emit(
        const CapturePreviewReading(
          mean: 128,
          darkFraction: 0,
          brightFraction: 0,
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('No clipping measured in this frame.'), findsNothing);
      expect(find.byKey(const ValueKey('capture-exposure-hint')), findsNothing);
      expect(
        find.byWidgetPredicate(
          (widget) => widget is UiIcon && widget.spec == UiIcons.check,
        ),
        findsNothing,
      );
    },
  );

  testWidgets('INT-UX-015 bright exposure has exactly the short hint', (
    tester,
  ) async {
    final camera = FakeCaptureCamera();
    await _pump(tester, CaptureScreen(camera: () async => camera));
    camera.emit(
      const CapturePreviewReading(
        mean: 220,
        darkFraction: 0,
        brightFraction: 0.4,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Bright spots. Check for glare.'), findsOneWidget);
    expect(find.textContaining('Bright areas are clipping'), findsNothing);
    camera.emit(
      const CapturePreviewReading(
        mean: 128,
        darkFraction: 0,
        brightFraction: 0,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Bright spots. Check for glare.'), findsNothing);
  });

  for (final (kind, device, message, action) in [
    (CaptureUnavailable.noCamera, true, 'No camera found.', 'Choose files'),
    (
      CaptureUnavailable.permission,
      true,
      'Camera access is off. Turn it on in Settings.',
      'Choose files',
    ),
    (
      CaptureUnavailable.failed,
      true,
      'Camera did not start.',
      'Use phone camera',
    ),
    (CaptureUnavailable.failed, false, 'Camera did not start.', 'Choose files'),
  ]) {
    testWidgets(
      'INT-UX-016 $kind device=$device has one real fallback action',
      (tester) async {
        CaptureResult? result;
        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light(),
            home: Builder(
              builder: (context) => TextButton(
                onPressed: () async {
                  result = await Navigator.of(context).push(
                    CaptureScreen.route(
                      () async => FakeCaptureCamera(unavailable: kind),
                      deviceFallbackAvailable: device,
                    ),
                  );
                },
                child: const Text('Open'),
              ),
            ),
          ),
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();
        expect(find.text(message), findsOneWidget);
        expect(message.split(RegExp(r'\s+')).length, lessThanOrEqualTo(10));
        expect(find.byType(UiButton), findsOneWidget);
        expect(_button(action), findsOneWidget);
        await tester.tap(_button(action));
        await tester.pumpAndSettle();
        expect(result?.unavailable, kind);
        expect(result?.needsFallback, isTrue);
      },
    );
  }

  testWidgets('INT-UX-018 close is at top start', (tester) async {
    await _pump(tester, CaptureScreen(camera: () async => FakeCaptureCamera()));
    final close = find.byWidgetPredicate(
      (widget) =>
          widget is UiIconButton &&
          widget.semanticsLabel == CaptureScreen.closeLabel,
    );
    expect(tester.getCenter(close).dx, lessThan(195));
  });

  for (final size in [const Size(390, 844), const Size(844, 390)]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets(
        'INT-UX-020 and 021 equal decisions and one question at $size scale=$scale',
        (tester) async {
          await _pump(
            tester,
            CaptureScreen(camera: () async => FakeCaptureCamera()),
            size: size,
            scale: scale,
          );
          for (var count = 0; count < 3; count++) {
            await takeOne(tester);
            await tester.tap(find.byKey(const ValueKey('capture-send')));
            await tester.pumpAndSettle();
          }
          await takeOne(tester);
          expect(find.text('Photo 4'), findsOneWidget);
          expect(find.text('All labels sharp and in frame?'), findsOneWidget);
          expect(find.textContaining('Check the smallest text'), findsNothing);
          expect(_button('Retake'), findsOneWidget);
          expect(_button('Send'), findsOneWidget);
          expect(
            tester.getSize(_button('Send')).width,
            tester.getSize(_button('Retake')).width,
          );
          expect(
            tester.getSize(
              find.byKey(const ValueKey('capture-review-Send-surface')),
            ),
            tester.getSize(
              find.byKey(const ValueKey('capture-review-Retake-surface')),
            ),
          );
          for (final label in ['Send', 'Retake']) {
            final text = find.descendant(
              of: _button(label),
              matching: find.byType(RichText),
            );
            expect(
              tester.renderObject<RenderParagraph>(text).didExceedMaxLines,
              isFalse,
            );
            expect(_button(label).hitTestable(), findsOneWidget);
          }
          expect(
            find.ancestor(
              of: _button('Send'),
              matching: find.byType(UiButtonRow),
            ),
            findsOneWidget,
          );
        },
      );
    }
  }

  testWidgets('INT-UX-022 crop nudges are one row of labelled icon buttons', (
    tester,
  ) async {
    await _pump(tester, CaptureScreen(camera: () async => FakeCaptureCamera()));
    await takeOne(tester);
    expect(
      tester.getCenter(_button('Rotate')).dy,
      tester.getCenter(_button('Crop')).dy,
    );
    await tester.tap(_button('Crop'));
    await tester.pumpAndSettle();
    final nudges = find.byWidgetPredicate(
      (widget) =>
          widget is UiIconButton &&
          [
            'Move left',
            'Move right',
            'Move up',
            'Move down',
            'Expand frame',
            'Reduce frame',
          ].contains(widget.semanticsLabel),
    );
    expect(nudges, findsNWidgets(6));
    final positions = nudges
        .evaluate()
        .map((element) => tester.getCenter(find.byWidget(element.widget)).dy)
        .toSet();
    expect(positions, hasLength(1));
    for (final button in tester.widgetList<UiIconButton>(nudges)) {
      expect(button.tooltip, button.semanticsLabel);
      expect(
        tester.getSize(find.byWidget(button)).shortestSide,
        greaterThanOrEqualTo(48),
      );
    }
  });

  testWidgets(
    'INT-UX-014 sensitivity is not remembered on a new camera session',
    (tester) async {
      await _pump(
        tester,
        CaptureScreen(
          camera: () async => FakeCaptureCamera(),
          onCaptured: (_) {},
        ),
      );
      final toggle = find.byKey(const ValueKey('capture-sensitive'));
      await tester.tap(toggle);
      await tester.pumpAndSettle();
      expect(tester.widget<UiSwitch>(toggle).value, isTrue);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: CaptureScreen(
            camera: () async => FakeCaptureCamera(),
            onCaptured: (_) {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.widget<UiSwitch>(toggle).value, isFalse);
    },
  );

  // These tests exercise the additive lane-2 interface. Their main-branch red
  // proof is a compile failure because the new constructor fields do not exist.
  testWidgets(
    'INT-UX-013 direct summary uses blocked tone only when requested',
    (tester) async {
      final camera = FakeCaptureCamera();
      await _pump(
        tester,
        CaptureScreen(
          camera: () async => camera,
          statusLabel: '1 to fix',
          statusBlocked: true,
        ),
      );
      final ui = tester.element(find.byType(CaptureScreen)).ui;
      expect(
        tester.widget<Text>(find.text('1 to fix')).style!.color,
        ui.color.status.blocked.content,
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: CaptureScreen(
            camera: () async => camera,
            statusLabel: '2 sent',
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.widget<Text>(find.text('2 sent')).style!.color,
        ui.color.inkSecondary,
      );
      expect(find.text('1 to fix'), findsNothing);
    },
  );

  for (final initial in [false, true]) {
    testWidgets('INT-UX-014 initial sensitivity $initial reaches onCaptured', (
      tester,
    ) async {
      final captured = <CapturedPhoto>[];
      await _pump(
        tester,
        CaptureScreen(
          camera: () async => FakeCaptureCamera(),
          initialSensitive: initial,
          autoIngest: true,
          onCaptured: captured.add,
        ),
      );
      final toggle = find.byKey(const ValueKey('capture-sensitive'));
      expect(tester.widget<UiSwitch>(toggle).value, initial);
      await tester.tap(find.byKey(const ValueKey('capture-shutter')));
      await waitForCameraCondition(tester, () => captured.isNotEmpty);
      expect(captured.single.sensitive, initial);
      expect(
        await captured.single.file.readAsBytes(),
        orderedEquals(FakeCaptureCamera.frame),
      );
      expect(tester.widget<UiSwitch>(toggle).value, initial);
    });
  }

  testWidgets(
    'INT-UX-014 toggle sends sensitive photo to both callbacks once',
    (tester) async {
      final captured = <CapturedPhoto>[];
      final legacy = <XFile>[];
      await _pump(
        tester,
        CaptureScreen(
          camera: () async => FakeCaptureCamera(),
          onCaptured: captured.add,
          onAccepted: legacy.add,
        ),
      );
      await tester.tap(find.byKey(const ValueKey('capture-sensitive')));
      await tester.pumpAndSettle();
      await takeOne(tester);
      expect(
        tester
            .widget<UiSwitch>(
              find.byKey(const ValueKey('capture-review-sensitive')),
            )
            .value,
        isTrue,
      );
      await tester.tap(_button('Send'));
      await tester.pumpAndSettle();
      expect(captured, hasLength(1));
      expect(legacy, hasLength(1));
      expect(captured.single.sensitive, isTrue);
      expect(captured.single.file, same(legacy.single));
    },
  );

  testWidgets(
    'INT-UX-023 review override survives edits without changing next shot',
    (tester) async {
      final captured = <CapturedPhoto>[];
      await _pump(
        tester,
        CaptureScreen(
          camera: () async => FakeCaptureCamera(),
          initialSensitive: true,
          onCaptured: captured.add,
        ),
      );
      await takeOne(tester);
      final reviewToggle = find.byKey(
        const ValueKey('capture-review-sensitive'),
      );
      await tester.tap(reviewToggle);
      await tester.pumpAndSettle();
      await tester.tap(_button('Rotate'));
      await tester.pump();
      await waitForCameraCondition(
        tester,
        () => _button('Rotate').evaluate().isNotEmpty,
      );
      await tester.pumpAndSettle();
      expect(tester.widget<UiSwitch>(reviewToggle).value, isFalse);
      await tester.tap(_button('Crop'));
      await tester.pumpAndSettle();
      await tester.tap(_button('Apply crop'));
      await tester.pump();
      await waitForCameraCondition(
        tester,
        () => _button('Send').evaluate().isNotEmpty,
      );
      await tester.pumpAndSettle();
      await tester.tap(_button('Send'));
      await tester.pumpAndSettle();
      expect(captured.single.sensitive, isFalse);
      expect(
        tester
            .widget<UiSwitch>(find.byKey(const ValueKey('capture-sensitive')))
            .value,
        isTrue,
      );
      await takeOne(tester);
      expect(tester.widget<UiSwitch>(reviewToggle).value, isTrue);
    },
  );

  testWidgets(
    'INT-UX-014 route forwards sensitivity and streams without duplicate result files',
    (tester) async {
      final captured = <CapturedPhoto>[];
      CaptureResult? result;
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                result = await Navigator.of(context).push(
                  CaptureScreen.route(
                    () async => FakeCaptureCamera(),
                    initialSensitive: true,
                    autoIngest: true,
                    onCaptured: captured.add,
                    statusLabel: '1 held',
                    statusBlocked: false,
                  ),
                );
              },
              child: const Text('Open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      expect(find.text('1 held'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('capture-shutter')));
      await waitForCameraCondition(tester, () => captured.isNotEmpty);
      await tester.tap(_button('Done'));
      await tester.pumpAndSettle();
      expect(captured.single.sensitive, isTrue);
      expect(result!.streamed, isTrue);
      expect(result!.files, isEmpty);
      expect(result!.needsFallback, isFalse);
    },
  );
}
