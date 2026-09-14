// Route transitions and predictive back
// (motion and microinteractions, sections 6.1 and 6.3 A; catalog rows 17, 18,
// 19 and 20).
//
// Flutter 3.38 is the release that moved the Android default from
// `ZoomPageTransitionsBuilder` to `PredictiveBackPageTransitionsBuilder`, and
// with it the transition length from 300 ms to 450 ms. A test that pumps a
// hard-coded 300 ms past a push no longer clears the transition, so every
// test here uses `TransitionDurationObserver` and never names a duration.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';

import '../app/routing_test.dart' show pumpApp, systemBack;

void main() {
  test('the manifest enables predictive back', () {
    // Without this the Android 13 and later back gesture falls back to the
    // old behaviour and the peel-back never runs.
    final String manifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();
    expect(manifest, contains('android:enableOnBackInvokedCallback="true"'));
  });

  test('the page transitions are the platform defaults, restated', () {
    final Map<TargetPlatform, PageTransitionsBuilder> builders =
        specimenPageTransitions.builders;
    // Restated rather than left implicit, so a future SDK change to a default
    // arrives as a visible diff rather than as a silent change of feel.
    expect(
      builders[TargetPlatform.android],
      isA<PredictiveBackPageTransitionsBuilder>(),
    );
    expect(
      builders[TargetPlatform.iOS],
      isA<CupertinoPageTransitionsBuilder>(),
    );
    expect(
      builders[TargetPlatform.macOS],
      isA<CupertinoPageTransitionsBuilder>(),
    );
    // Desktop and web move off the zoom transition onto the Material 3
    // forward transition.
    for (final TargetPlatform platform in <TargetPlatform>[
      TargetPlatform.windows,
      TargetPlatform.linux,
      TargetPlatform.fuchsia,
    ]) {
      expect(
        builders[platform],
        isA<FadeForwardsPageTransitionsBuilder>(),
        reason: '$platform',
      );
    }
    // Every platform is named. A missing entry silently falls back to the
    // SDK default, which is the thing this table exists to pin.
    expect(builders.keys.toSet(), TargetPlatform.values.toSet());
  });

  testWidgets('a record is a push on a phone, and back returns to the queue', (
    WidgetTester tester,
  ) async {
    final TransitionDurationObserver observer = TransitionDurationObserver();
    await pumpApp(
      tester,
      window: const Size(800, 1400),
      observers: <NavigatorObserver>[observer],
    );

    await tester.scrollUntilVisible(
      find.text('Synthetic insect label'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Synthetic insect label'));
    // No literal here, deliberately: the platform owns this duration and it
    // changed under us once already.
    await observer.pumpPastTransition(tester);
    expect(find.byType(WorkbenchScreen), findsOneWidget);

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

    await tester.tap(find.text('Synthetic insect label'));
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
