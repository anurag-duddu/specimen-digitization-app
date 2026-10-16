import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart' as cupertino;
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

Finder _target(TargetPlatform platform, int index) => find
    .descendant(
      of: _bar,
      matching: platform == TargetPlatform.iOS
          ? find.byWidgetPredicate(
              (widget) => widget is GestureDetector && widget.onTap != null,
            )
          : find.byWidgetPredicate((widget) => widget is material.InkResponse),
    )
    .at(index);

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

void _expectGeometry(
  WidgetTester tester,
  TargetPlatform platform, {
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
    final targetBounds = tester.getRect(_target(platform, i));
    final semantics = tester.getSemantics(label);
    expect(semantics.flagsCollection.isSelected.toBoolOrNull(), i == 0);
    expect(semantics.getSemanticsData().hasAction(SemanticsAction.tap), isTrue);
    expect(targetBounds.width, greaterThanOrEqualTo(48));
    expect(targetBounds.height, greaterThanOrEqualTo(48));
    for (final rect in [labelBounds, iconBounds, targetBounds]) {
      expect(rect.left, greaterThanOrEqualTo(content.left));
      expect(rect.right, lessThanOrEqualTo(content.right));
      expect(rect.top, greaterThanOrEqualTo(content.top));
      expect(rect.bottom, lessThanOrEqualTo(window.height - bottom));
    }
    expect(iconBounds.bottom, lessThanOrEqualTo(labelBounds.top));
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
      'platform': platform.name,
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

// The local native-font evidence runner loads Apple's font without bundling it.
void main({bool nativeCupertinoFont = false}) {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets(
    'Android normal content bar is 64 dp',
    (tester) async {
      final semantics = tester.ensureSemantics();
      try {
        await _pump(tester);
        _expectGeometry(
          tester,
          TargetPlatform.android,
          window: const Size(390, 844),
          contentHeight: 64,
          bottom: 0,
        );
      } finally {
        semantics.dispose();
      }
    },
    variant: TargetPlatformVariant.only(TargetPlatform.android),
  );

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
                // Flutter tests substitute Ahem for CupertinoSystemText. Its
                // square glyphs wrap at 320/2x. The local native-font runner
                // covers that cross-case; portable 2x coverage starts at 390.
                if (platform == TargetPlatform.iOS &&
                    scale == 2 &&
                    widths[index] == 320 &&
                    !nativeCupertinoFont) {
                  continue;
                }
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
                  final height = platform == TargetPlatform.iOS
                      ? (scale == 2 ? 64.0 : 56.0)
                      : {1.0: 64.0, 1.3: 68.875, 2.0: 80.25}[scale]!;
                  _expectGeometry(
                    tester,
                    platform,
                    window: window,
                    contentHeight: height,
                    bottom: insets[index],
                  );
                  if (platform == TargetPlatform.android &&
                      brightness == Brightness.dark) {
                    expect(
                      tester
                          .widget<material.NavigationBar>(_bar)
                          .animationDuration,
                      Duration.zero,
                    );
                  }
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
              final target = tester.getRect(_target(platform, index));
              final point = corner.withinRect(target.deflate(1));
              await tester.tapAt(point);
              await tester.pumpAndSettle();
              expect(
                router.routerDelegate.currentConfiguration.uri.path,
                index == 1 ? goldenIntakeLocation : goldenQueueLocation,
              );
              final selected = platform == TargetPlatform.iOS
                  ? tester.widget<cupertino.CupertinoTabBar>(_bar).currentIndex
                  : tester.widget<material.NavigationBar>(_bar).selectedIndex;
              expect(selected, index);
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
          expect(
            tester.getSize(_bar).height,
            (platform == TargetPlatform.iOS ? 56 : 64) + bottom,
          );
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox());
        }
      },
      variant: TargetPlatformVariant.only(platform),
    );
  }

  for (final brightness in Brightness.values) {
    for (final scale in [1.0, 1.3, 2.0]) {
      testWidgets(
        'Android $brightness scale $scale paints focus and activates with keyboard',
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
            final focus = Focus.of(tester.element(_label('Intake')));
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
              'Android focus $brightness scale=$scale changedChannels=$changed',
            );
            final router = GoRouter.of(tester.element(_bar));
            await tester.sendKeyEvent(LogicalKeyboardKey.space);
            await tester.pumpAndSettle();
            expect(
              router.routerDelegate.currentConfiguration.uri.path,
              goldenIntakeLocation,
            );
            expect(
              tester.widget<material.NavigationBar>(_bar).selectedIndex,
              1,
            );
            expect(tester.takeException(), isNull);
          } finally {
            FocusManager.instance.highlightStrategy = previous;
          }
        },
        variant: TargetPlatformVariant.only(TargetPlatform.android),
      );
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
}
