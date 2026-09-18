// The two intake layouts (screen blueprints, section 5; responsive, 3.4).
//
// One column below 600dp; two columns at 600dp and above, with the capture
// card fixed at 420dp on the left and the manifest scrolling on the right.
// The branch reads the window, never the platform, so both cases are driven
// by resizing the surface alone.

import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/layout/window_class.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import 'widget_test.dart' show TestRepository;

const CollectionScope scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Synthetic insects',
);

final Finder captureColumn = find.byKey(
  const ValueKey<String>('intake-capture-column'),
);

Future<void> pumpIntake(WidgetTester tester, Size size) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  // The layout branch reads `MediaQuery.sizeOf`, which comes from the view,
  // so the view is what the test resizes.
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: IntakeScreen(
          repository: TestRepository(),
          scope: scope,
          userId: 'owner',
          onComplete: () {},
          pickImages: (bool _) async => <XFile>[],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('below 600dp the capture card sits above the manifest', (
    WidgetTester tester,
  ) async {
    await pumpIntake(tester, const Size(599, 1400));
    expect(captureColumn, findsNothing);
    final Rect card = tester.getRect(find.byType(IntakeCaptureCard));
    final Rect manifest = tester.getRect(find.byType(IntakeManifest));
    expect(
      manifest.top,
      greaterThanOrEqualTo(card.bottom),
      reason: 'one column stacks the manifest below the capture card',
    );
    final Rect checks = tester.getRect(find.byType(IntakeChecks));
    expect(
      checks.top,
      greaterThanOrEqualTo(manifest.bottom),
      reason:
          'the checks sit under the manifest, next to the action that sends '
          'the batch (13 section 2.5: the manifest is above the fold)',
    );
    expect(card.width, lessThan(WindowClass.mediumMin));
  });

  testWidgets('at 600dp the capture card is fixed at 420dp on the left', (
    WidgetTester tester,
  ) async {
    await pumpIntake(tester, const Size(WindowClass.mediumMin, 1400));
    expect(captureColumn, findsOneWidget);
    expect(tester.getSize(captureColumn).width, intakeCaptureColumnWidth);
    final Rect card = tester.getRect(find.byType(IntakeCaptureCard));
    final Rect manifest = tester.getRect(find.byType(IntakeManifest));
    expect(
      manifest.left,
      greaterThanOrEqualTo(card.right),
      reason: 'the manifest fills beside the button, not below it',
    );
    expect(manifest.top, lessThan(card.bottom));
  });

  testWidgets('a wider window widens the manifest, never the capture card', (
    WidgetTester tester,
  ) async {
    await pumpIntake(tester, const Size(1400, 1000));
    expect(tester.getSize(captureColumn).width, intakeCaptureColumnWidth);
    expect(
      tester.getSize(find.byType(IntakeManifest)).width,
      greaterThan(intakeCaptureColumnWidth),
    );
  });

  testWidgets('the manifest scrolls on its own at 600dp and above', (
    WidgetTester tester,
  ) async {
    await pumpIntake(tester, const Size(900, 700));
    expect(
      tester.widget<IntakeManifest>(find.byType(IntakeManifest)).scrollable,
      isTrue,
    );
  });

  testWidgets('one column has one scroll position, not two', (
    WidgetTester tester,
  ) async {
    await pumpIntake(tester, const Size(400, 2000));
    expect(
      tester.widget<IntakeManifest>(find.byType(IntakeManifest)).scrollable,
      isFalse,
      reason: 'the page is the one scroll and the manifest is a section of it',
    );
    // 13 section 2.1: one vertical scroll per screen. The manifest used to
    // shrink wrap a `ListView` inside the page's own, which is the nesting
    // the clause names.
    expect(
      find
          .byWidgetPredicate(
            (Widget widget) =>
                widget is Scrollable &&
                axisDirectionToAxis(widget.axisDirection) == Axis.vertical,
          )
          .evaluate(),
      hasLength(1),
    );
  });

  testWidgets('the camera button is hidden where this client has no camera', (
    WidgetTester tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
    await pumpIntake(tester, const Size(1200, 1400));
    expect(
      find.byKey(const ValueKey<String>('intake-take-photograph')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('intake-choose-files')),
      findsOneWidget,
    );
    expect(
      find.text(
        'Camera capture runs in the Android and iOS apps. Here, '
        'choose a file.',
      ),
      findsOneWidget,
      reason: 'a missing button still needs an explanation',
    );
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('the camera button is offered on a phone or tablet', (
    WidgetTester tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    await pumpIntake(tester, const Size(1200, 1400));
    expect(
      find.byKey(const ValueKey<String>('intake-take-photograph')),
      findsOneWidget,
    );
    debugDefaultTargetPlatformOverride = null;
  });
}
