// Navigation replaces content in place on all platforms. Preserve predictive
// back and actual queue/record routing, while testing the stationary fade and
// the real Android/iOS reduced-motion signals rather than a removed wrapper.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../app/routing_test.dart' show locationOf, pumpApp, systemBack;

const Key transitionKey = ValueKey<String>('stationary-route-boundary');
const Key pageKey = ValueKey<String>('stationary-route-content');

Future<void> pumpTransition(
  WidgetTester tester, {
  TargetPlatform platform = TargetPlatform.android,
  bool disableAnimations = false,
}) async {
  final route = MaterialPageRoute<void>(
    builder: (_) => const SizedBox(key: pageKey, width: 100, height: 80),
  );
  addTearDown(route.dispose);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Builder(
        builder: (BuildContext context) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(disableAnimations: disableAnimations),
          child: Builder(
            builder: (BuildContext transitionContext) => Center(
              child: KeyedSubtree(
                key: transitionKey,
                child: specimenPageTransitions.builders[platform]!
                    .buildTransitions<void>(
                      route,
                      transitionContext,
                      const AlwaysStoppedAnimation<double>(0.5),
                      const AlwaysStoppedAnimation<double>(0),
                      const SizedBox(key: pageKey, width: 100, height: 80),
                    ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

Finder pageFade() => find.descendant(
  of: find.byKey(transitionKey),
  matching: find.byType(FadeTransition),
);

void main() {
  test('the manifest enables predictive back', () {
    final String manifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();
    expect(manifest, contains('android:enableOnBackInvokedCallback="true"'));
  });

  test('every platform uses the explicit stationary quick transition', () {
    final builders = specimenPageTransitions.builders;
    expect(builders.keys.toSet(), TargetPlatform.values.toSet());
    for (final platform in TargetPlatform.values) {
      final builder = builders[platform]!;
      expect(builder, isA<InPlacePageTransitions>(), reason: '$platform');
      expect(builder.transitionDuration, MotionTokens.quickRaw);
      expect(builder.reverseTransitionDuration, MotionTokens.quickRaw);
    }
  });

  for (final platform in TargetPlatform.values) {
    testWidgets('$platform fades the new page without shifting its geometry', (
      WidgetTester tester,
    ) async {
      await pumpTransition(tester, platform: platform);
      expect(pageFade(), findsOneWidget);
      expect(
        tester.widget<FadeTransition>(pageFade()).opacity.value,
        closeTo(MotionTokens.standardCurve.transform(0.5), 0.000001),
      );
      expect(
        find.ancestor(
          of: find.byKey(pageKey),
          matching: find.byType(SlideTransition),
        ),
        findsNothing,
      );
      final Rect before = tester.getRect(find.byKey(pageKey));
      await tester.pump();
      expect(tester.getRect(find.byKey(pageKey)), before);
      expect(before.size, const Size(100, 80));
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('Android Remove animations exposes the page on the first frame', (
    WidgetTester tester,
  ) async {
    tester.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(disableAnimations: true);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    await pumpTransition(tester, disableAnimations: true);
    expect(find.byKey(pageKey), findsOneWidget);
    expect(pageFade(), findsNothing);
    expect(tester.getSize(find.byKey(pageKey)), const Size(100, 80));
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('iOS Reduce Motion reveals the page without an opacity wrapper', (
    WidgetTester tester,
  ) async {
    tester.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(reduceMotion: true);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    await pumpTransition(tester, platform: TargetPlatform.iOS);
    expect(find.byKey(pageKey), findsOneWidget);
    expect(pageFade(), findsNothing);
    expect(tester.getSize(find.byKey(pageKey)), const Size(100, 80));
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('a record is a push on a phone, and back returns to the queue', (
    WidgetTester tester,
  ) async {
    final TransitionDurationObserver observer = TransitionDurationObserver();
    await pumpApp(
      tester,
      window: const Size(390, 844),
      observers: <NavigatorObserver>[observer],
    );

    final Finder recordRow = find.widgetWithText(QueueRow, 'fixture-001');
    expect(find.byType(QueuePane), findsOneWidget);
    await tester.ensureVisible(recordRow);
    await tester.pumpAndSettle();
    expect(recordRow.hitTestable(), findsOneWidget);
    await tester.tap(recordRow);
    // No literal here, deliberately: the platform owns this duration and it
    // changed under us once already.
    await observer.pumpPastTransition(tester);
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    expect(locationOf(tester), endsWith('/queue/fixture-001'));

    await systemBack(tester);
    await observer.pumpPastTransition(tester);
    expect(find.byType(WorkbenchScreen), findsNothing);
    expect(find.byType(QueuePane), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('at large the record cross-fades in place beside the list', (
    WidgetTester tester,
  ) async {
    final TransitionDurationObserver observer = TransitionDurationObserver();
    await pumpApp(
      tester,
      window: const Size(1440, 1200),
      observers: <NavigatorObserver>[observer],
    );

    final Finder recordRow = find.widgetWithText(QueueRow, 'fixture-001');
    expect(recordRow.hitTestable(), findsOneWidget);
    await tester.tap(recordRow);
    await observer.pumpPastTransition(tester);

    // Nothing travels between the panes, so nothing slides: the detail is a
    // fade and the list keeps its place (motion catalog, rows 17 and 20).
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    expect(find.byType(QueuePane), findsOneWidget);
    // The route's own transition is a fade. Nothing travels between the two
    // panes, so there is nothing for a container transform to transform, and
    // the list is still the same list beside it.
    expect(
      find.ancestor(
        of: find.byType(WorkbenchScreen),
        matching: find.byType(FadeTransition),
      ),
      findsWidgets,
    );

    await tester.pumpWidget(const SizedBox());
  });
}
