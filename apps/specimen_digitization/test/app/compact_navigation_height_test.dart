// The compact bottom tab bar is one brand component on every platform
// (10 section 4.4, `UiTabBar`; 09 section 2 principle 5).
//
// It replaced a fork that drew `CupertinoTabBar` on iOS and a Material
// `NavigationBar` elsewhere. The owner's words, 2026-10-17: "btw ios nav
// behaves perfectly but android has too much padding/space". So this file
// holds three kinds of assertion: the geometry the owner approved on the
// iPhone (56 dp of content at normal text, growing as
// `max(56, 32 + scaled 16 + 4)` with the text, plus the system inset), that it
// is the same widget and the same pixels on iOS and Android, and that every
// edge of it is a usable target above each system inset.
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' as material;
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../widget_test.dart' show TestSession;

Finder get _bar => find.byKey(const ValueKey('mobile-navigation'));

Finder _label(String label) =>
    find.descendant(of: _bar, matching: find.text(label));

/// The whole cell of one destination, which is the hit target.
Finder _target(int index) =>
    find.descendant(of: _bar, matching: find.byType(Pressable)).at(index);

/// The content height before the system inset: `max(56, 32 + scaled 16 + 4)`.
///
/// 56 at normal text is what the owner approved on the iPhone. The `+ 4` is
/// the gap the cell pads under its label, which the first version of the
/// formula left out, so at 200 percent the glyph sat about 3 dp under the top
/// line; with it the bar is 68 dp there (2026-10-17 correction).
final Map<double, double> _contentHeight = <double, double>{
  1.0: 56.0,
  1.3: 32 + 16 * 1.3 + 4,
  2.0: 68.0,
};

Future<void> _pump(
  WidgetTester tester, {
  Size window = const Size(390, 844),
  Brightness brightness = Brightness.light,
  double scale = 1,
  double bottom = 0,
  bool reducedMotion = false,
}) async {
  tester.view.padding = FakeViewPadding(bottom: bottom);
  tester.view.viewPadding = FakeViewPadding(bottom: bottom);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  tester.platformDispatcher.platformBrightnessTestValue = brightness;
  tester.platformDispatcher.textScaleFactorTestValue = scale;
  tester.platformDispatcher.accessibilityFeaturesTestValue =
      FakeAccessibilityFeatures(disableAnimations: reducedMotion);
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  final session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    RepaintBoundary(
      key: const ValueKey('compact-nav-frame'),
      child: SpecimenDigitizationApp(
        session: session,
        repository: GoldenQueueRepository(goldenQueue(3)),
        initialLocation: goldenQueueLocation,
        motionPreferences: MemoryMotionPreferenceStore(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await settleImages(tester);
}

/// The pixels from the top of the bar to the bottom of the frame.
Future<List<int>> _barPixels(WidgetTester tester) async {
  final bounds = tester.getRect(_bar);
  final boundary = tester.renderObject<RenderRepaintBoundary>(
    find.byKey(const ValueKey('compact-nav-frame')),
  );
  return (await tester.runAsync(() async {
    final image = await boundary.toImage();
    try {
      final data = (await image.toByteData(
        format: ui.ImageByteFormat.rawRgba,
      ))!;
      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );
      return bytes.sublist(bounds.top.ceil() * image.width * 4);
    } finally {
      image.dispose();
    }
  }))!;
}

List<double> _rect(Rect rect) => [rect.left, rect.top, rect.width, rect.height];

/// Runs [body] as if the app were on [platform], and puts the override back
/// before the test body returns, because the binding checks the foundation
/// debug variables before tear downs run.
Future<T> _on<T>(TargetPlatform platform, Future<T> Function() body) async {
  debugDefaultTargetPlatformOverride = platform;
  try {
    return await body();
  } finally {
    debugDefaultTargetPlatformOverride = null;
  }
}

void _expectGeometry(
  WidgetTester tester, {
  required Size window,
  required double contentHeight,
  required double bottom,
}) {
  final bounds = tester.getRect(_bar);
  final content = Rect.fromLTWH(0, bounds.top, window.width, contentHeight);
  final labels = <Map<String, Object>>[];
  for (var i = 0; i < 2; i++) {
    final name = ['Specimens', 'Intake'][i];
    final label = _label(name);
    final paragraph = tester.renderObject<RenderParagraph>(label);
    final icon = find.byKey(ValueKey('mobile-nav-${name.toLowerCase()}'));
    final labelBounds = tester.getRect(label);
    final iconBounds = tester.getRect(icon);
    final targetBounds = tester.getRect(_target(i));
    final semantics = tester.getSemantics(label);
    expect(semantics.flagsCollection.isSelected.toBoolOrNull(), i == 0);
    expect(semantics.getSemanticsData().hasAction(SemanticsAction.tap), isTrue);
    expect(targetBounds.width, greaterThanOrEqualTo(48));
    expect(targetBounds.height, greaterThanOrEqualTo(48));
    expect(
      targetBounds.height,
      closeTo(contentHeight, .001),
      reason: 'the whole content height of the bar is the hit target',
    );
    for (final rect in [labelBounds, iconBounds, targetBounds]) {
      expect(rect.left, greaterThanOrEqualTo(content.left));
      expect(rect.right, lessThanOrEqualTo(content.right));
      expect(rect.top, greaterThanOrEqualTo(content.top));
      expect(rect.bottom, lessThanOrEqualTo(window.height - bottom));
    }
    expect(iconBounds.bottom, lessThanOrEqualTo(labelBounds.top));
    // The glyph keeps its air at every text scale: 4 dp under the bar's top
    // edge and 4 dp above the label. At 200 percent text the first version of
    // the height left the glyph about 3 dp from the top line.
    expect(
      iconBounds.top - bounds.top,
      greaterThanOrEqualTo(4),
      reason: '$name glyph is too close to the top line at this text scale',
    );
    expect(
      labelBounds.top - iconBounds.bottom,
      greaterThanOrEqualTo(4),
      reason: '$name label is too close to its glyph at this text scale',
    );
    expect(paragraph.didExceedMaxLines, isFalse);
    final boxes = paragraph.getBoxesForSelection(
      TextSelection(baseOffset: 0, extentOffset: name.length),
    );
    expect(boxes, isNotEmpty);
    expect(boxes.map((box) => box.top).toSet(), hasLength(1));
    labels.add({
      'label': name,
      'labelRect': _rect(labelBounds),
      'iconRect': _rect(iconBounds),
      'targetRect': _rect(targetBounds),
      'semanticsRect': _rect(semantics.rect),
      'fontScale': paragraph.textScaler.scale(1),
    });
  }
  debugPrint(
    jsonEncode({
      'platform': defaultTargetPlatform.name,
      'window': [window.width, window.height],
      'scale': MediaQuery.textScalerOf(tester.element(_bar)).scale(1),
      'barRect': _rect(bounds),
      'bottomInset': bottom,
      'contentHeight': bounds.height - bottom,
      'labels': labels,
    }),
  );
  expect(bounds.bottom, window.height);
  expect(bounds.height, closeTo(contentHeight + bottom, .001));
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    testWidgets(
      '$platform draws the brand tab bar and no stock bar',
      (tester) async {
        await _pump(tester);
        expect(find.byType(UiTabBar), findsOneWidget);
        expect(_bar, findsOneWidget);
        expect(tester.widget(_bar), isA<UiTabBar>());
        expect(find.byType(cupertino.CupertinoTabBar), findsNothing);
        expect(find.byType(material.NavigationBar), findsNothing);
        expect(find.byType(material.NavigationIndicator), findsNothing);
      },
      variant: TargetPlatformVariant.only(platform),
    );

    testWidgets(
      '$platform normal content bar is 56 dp, the iPhone metric',
      (tester) async {
        final semantics = tester.ensureSemantics();
        try {
          await _pump(tester);
          _expectGeometry(
            tester,
            window: const Size(390, 844),
            contentHeight: 56,
            bottom: 0,
          );
        } finally {
          semantics.dispose();
        }
      },
      variant: TargetPlatformVariant.only(platform),
    );
  }

  testWidgets('for the same inset the Android bar is exactly as tall as '
      'the iOS bar', (tester) async {
    for (final scale in [1.0, 1.3, 2.0]) {
      for (final bottom in [0.0, 24.0, 34.0, 48.0]) {
        final heights = <TargetPlatform, double>{};
        for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
          await _on(platform, () async {
            await _pump(tester, scale: scale, bottom: bottom);
            heights[platform] = tester.getSize(_bar).height;
            await tester.pumpWidget(const SizedBox());
          });
        }
        expect(
          heights[TargetPlatform.android],
          heights[TargetPlatform.iOS],
          reason: 'scale $scale, inset $bottom: $heights',
        );
        expect(
          heights[TargetPlatform.android],
          closeTo(_contentHeight[scale]! + bottom, .001),
          reason: 'content plus inset at scale $scale, inset $bottom',
        );
      }
    }
  });

  testWidgets('the bar paints the same pixels on iOS and on Android', (
    tester,
  ) async {
    for (final brightness in Brightness.values) {
      for (final scale in [1.0, 2.0]) {
        final pixels = <TargetPlatform, List<int>>{};
        for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
          await _on(platform, () async {
            await _pump(
              tester,
              brightness: brightness,
              scale: scale,
              bottom: 34,
              reducedMotion: true,
            );
            pixels[platform] = await _barPixels(tester);
            await tester.pumpWidget(const SizedBox());
          });
        }
        expect(pixels[TargetPlatform.iOS], isNotEmpty);
        expect(
          pixels[TargetPlatform.android],
          orderedEquals(pixels[TargetPlatform.iOS]!),
          reason: 'identity does not adapt: $brightness at scale $scale',
        );
      }
    }
  });

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    for (final brightness in Brightness.values) {
      for (final scale in [1.0, 1.3, 2.0]) {
        testWidgets(
          '$platform $brightness scale $scale compact navigation geometry',
          (tester) async {
            final semantics = tester.ensureSemantics();
            try {
              // Cover design-class edges without changing the shell's separate
              // width < 768 * scale policy. System insets are paired across widths.
              const widths = [320.0, 390.0, 599.0, 600.0, 840.0];
              const insets = [0.0, 24.0, 34.0, 48.0, 34.0];
              for (var index = 0; index < widths.length; index++) {
                final window = Size(widths[index], 844);
                await _pump(
                  tester,
                  window: window,
                  brightness: brightness,
                  scale: scale,
                  bottom: insets[index],
                  reducedMotion: brightness == Brightness.dark,
                );
                if (window.width >= 768 * scale) {
                  expect(_bar, findsNothing);
                  expect(
                    find.byKey(const ValueKey('global-rail')),
                    findsOneWidget,
                  );
                } else {
                  _expectGeometry(
                    tester,
                    window: window,
                    contentHeight: _contentHeight[scale]!,
                    bottom: insets[index],
                  );
                }
                expect(tester.takeException(), isNull);
                await tester.pumpWidget(const SizedBox());
              }
            } finally {
              semantics.dispose();
            }
          },
          variant: TargetPlatformVariant.only(platform),
        );
      }
    }

    testWidgets(
      '$platform root destinations accept edge taps above each system inset',
      (tester) async {
        for (final bottom in [0.0, 24.0, 34.0, 48.0]) {
          await _pump(tester, bottom: bottom, reducedMotion: true);
          final router = GoRouter.of(tester.element(_bar));
          for (final corner in [
            Alignment.topLeft,
            Alignment.topRight,
            Alignment.bottomLeft,
            Alignment.bottomRight,
          ]) {
            for (final index in [1, 0]) {
              final target = tester.getRect(_target(index));
              final point = corner.withinRect(target.deflate(1));
              await tester.tapAt(point);
              await tester.pumpAndSettle();
              expect(
                router.routerDelegate.currentConfiguration.uri.path,
                index == 1 ? goldenIntakeLocation : goldenQueueLocation,
              );
              expect(tester.widget<UiTabBar>(_bar).currentIndex, index);
              debugPrint(
                'edge tap ${platform.name} inset=$bottom at=$point selected=$index',
              );
            }
          }
          // Keyboard collapse must not leave an empty bar or a doubled inset.
          tester.view.viewInsets = const FakeViewPadding(bottom: 300);
          tester.view.padding = FakeViewPadding.zero;
          await tester.pumpAndSettle();
          expect(_bar, findsNothing);
          tester.view.viewInsets = FakeViewPadding.zero;
          tester.view.padding = FakeViewPadding(bottom: bottom);
          await tester.pumpAndSettle();
          expect(tester.getSize(_bar).height, 56 + bottom);
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox());
        }
      },
      variant: TargetPlatformVariant.only(platform),
    );
  }

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    for (final brightness in Brightness.values) {
      for (final scale in [1.0, 1.3, 2.0]) {
        testWidgets(
          '$platform $brightness scale $scale paints focus and activates with keyboard',
          (tester) async {
            final previous = FocusManager.instance.highlightStrategy;
            FocusManager.instance.highlightStrategy =
                FocusHighlightStrategy.alwaysTraditional;
            try {
              await _pump(
                tester,
                brightness: brightness,
                scale: scale,
                bottom: 34,
              );
              final before = await _barPixels(tester);
              final focus = Focus.of(
                tester.element(find.byKey(const ValueKey('mobile-nav-intake'))),
              );
              focus.requestFocus();
              await tester.pumpAndSettle();
              expect(focus.hasPrimaryFocus, isTrue);
              final focused = await _barPixels(tester);
              expect(
                focused,
                isNot(orderedEquals(before)),
                reason: 'keyboard focus must paint',
              );
              final changed = Iterable.generate(
                before.length,
              ).where((i) => before[i] != focused[i]).length;
              debugPrint(
                '${platform.name} focus $brightness scale=$scale changedChannels=$changed',
              );
              final router = GoRouter.of(tester.element(_bar));
              await tester.sendKeyEvent(LogicalKeyboardKey.space);
              await tester.pumpAndSettle();
              expect(
                router.routerDelegate.currentConfiguration.uri.path,
                goldenIntakeLocation,
              );
              expect(tester.widget<UiTabBar>(_bar).currentIndex, 1);
              expect(tester.takeException(), isNull);
            } finally {
              FocusManager.instance.highlightStrategy = previous;
            }
          },
          variant: TargetPlatformVariant.only(platform),
        );
      }
    }
  }

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    testWidgets(
      '$platform preserves actual shell width and short-window boundaries',
      (tester) async {
        for (final scale in [1.0, 1.3, 2.0]) {
          await _pump(tester, scale: scale);
          final boundary = 768 * scale;
          for (final window in [
            Size(boundary - 1, 844),
            Size(boundary, 844),
            Size(boundary + 100, 599),
            Size(boundary + 100, 600),
          ]) {
            tester.view.physicalSize = window;
            await tester.pumpAndSettle();
            final mobile = window.width < boundary || window.height < 600;
            expect(_bar, mobile ? findsOneWidget : findsNothing);
            expect(
              find.byKey(const ValueKey('global-rail')),
              mobile ? findsNothing : findsOneWidget,
            );
            expect(tester.takeException(), isNull);
          }
          await tester.pumpWidget(const SizedBox());
        }
      },
      variant: TargetPlatformVariant.only(platform),
    );
  }

  test('the shell has no platform fork and imports no stock navigation', () {
    // The fork is what the owner objected to, and nothing else would stop it
    // coming back: a test that only pumps the shell on two platforms passes
    // if the two forks happen to measure the same.
    final source = File('lib/src/app/shell.dart').readAsStringSync();
    final code = source.replaceAll(RegExp(r'//.*'), '');
    expect(code, isNot(contains('defaultTargetPlatform')));
    expect(code, isNot(contains('TargetPlatform')));
    expect(code, isNot(contains("package:flutter/cupertino.dart")));
    expect(code, isNot(contains("package:flutter/material.dart")));
    expect(code, isNot(contains('CupertinoTabBar')));
    expect(code, isNot(contains('NavigationBar(')));
    expect(code, contains('UiTabBar('));
  });
}
