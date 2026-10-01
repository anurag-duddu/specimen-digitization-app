// Intake uses one page scroll at every width. Capture, classification, the
// selected-file manifest and the release action stay in that order. The old
// fixed 420dp/two-column policy was replaced by the qualified image-first UI.

import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'intake_harness.dart' show chooseFiles;
import 'widget_test.dart' show TestRepository;

const CollectionScope scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Synthetic insects',
  permissions: <String>['upload'],
);

final Finder sensitivity = find.byKey(
  const ValueKey<String>('intake-sensitivity'),
);
final Finder upload = find.byKey(const ValueKey<String>('intake-upload'));

Future<void> pumpIntake(
  WidgetTester tester,
  Size size, {
  bool selectedFile = false,
  double textScale = 1,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  final bytes = selectedFile
      ? File('test/fixtures/synthetic-label.png').readAsBytesSync()
      : null;
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: IntakeScreen(
          repository: TestRepository(),
          scope: scope,
          userId: 'owner',
          onComplete: () {},
          pickImages: (bool _) async => bytes == null
              ? <XFile>[]
              : <XFile>[
                  XFile.fromData(
                    bytes,
                    path: 'layout-label.png',
                    name: 'layout-label.png',
                  ),
                ],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  if (selectedFile) await chooseFiles(tester);
}

Finder verticalScrollables() => find.byWidgetPredicate(
  (Widget widget) =>
      widget is Scrollable &&
      axisDirectionToAxis(widget.axisDirection) == Axis.vertical,
);

void main() {
  testWidgets(
    'empty intake offers capture without an empty manifest or upload',
    (WidgetTester tester) async {
      await pumpIntake(tester, const Size(599, 1400));
      expect(find.byType(IntakeCaptureCard), findsOneWidget);
      expect(sensitivity, findsOneWidget);
      expect(find.byType(IntakeManifest), findsNothing);
      expect(upload, findsNothing);
      expect(verticalScrollables(), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  for (final double width in <double>[400, 600, 900, 1400]) {
    testWidgets(
      'capture, classification and chosen manifest stack at $width dp',
      (WidgetTester tester) async {
        await pumpIntake(tester, Size(width, 1800), selectedFile: true);
        final Rect card = tester.getRect(find.byType(IntakeCaptureCard));
        final Rect classification = tester.getRect(sensitivity);
        final Rect manifest = tester.getRect(find.byType(IntakeManifest));
        expect(classification.top, greaterThanOrEqualTo(card.bottom));
        expect(manifest.top, greaterThanOrEqualTo(classification.bottom));
        expect(card.left, greaterThanOrEqualTo(0));
        expect(card.right, lessThanOrEqualTo(width));
        expect(manifest.left, greaterThanOrEqualTo(card.left));
        expect(manifest.right, lessThanOrEqualTo(card.right));
        expect(
          tester.widget<IntakeManifest>(find.byType(IntakeManifest)).scrollable,
          isFalse,
          reason: 'the manifest is a section of the only page scroll',
        );
        expect(verticalScrollables(), findsOneWidget);
        await tester.ensureVisible(upload);
        await tester.pumpAndSettle();
        expect(upload.hitTestable(), findsOneWidget);
        expect(tester.widget<UiButton>(upload).onPressed, isNotNull);
        expect(
          tester.getRect(upload).top,
          greaterThanOrEqualTo(
            tester.getRect(find.byType(IntakeManifest)).bottom,
          ),
          reason:
              'the unframed host releases the batch after its file evidence',
        );
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets(
    'wide intake grows capture while keeping file evidence readable',
    (WidgetTester tester) async {
      await pumpIntake(tester, const Size(600, 1800), selectedFile: true);
      final double narrow = tester
          .getSize(find.byType(IntakeCaptureCard))
          .width;
      tester.view.physicalSize = const Size(1400, 1800);
      await tester.pumpAndSettle();
      final double wide = tester.getSize(find.byType(IntakeCaptureCard)).width;
      expect(wide, greaterThan(narrow));
      expect(
        tester.getSize(find.byType(IntakeManifest)).width,
        lessThan(wide),
        reason:
            'file evidence keeps a readable measure instead of filling a pane',
      );
      expect(verticalScrollables(), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('classification and release remain reachable at enlarged text', (
    WidgetTester tester,
  ) async {
    await pumpIntake(
      tester,
      const Size(390, 844),
      selectedFile: true,
      textScale: 2,
    );
    await tester.ensureVisible(sensitivity);
    await tester.pumpAndSettle();
    final bool before = tester.widget<UiCheckbox>(sensitivity).value ?? false;
    await tester.tap(sensitivity);
    await tester.pumpAndSettle();
    expect(tester.widget<UiCheckbox>(sensitivity).value, !before);
    await tester.ensureVisible(upload);
    await tester.pumpAndSettle();
    expect(upload.hitTestable(), findsOneWidget);
    expect(verticalScrollables(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('desktop offers files and does not offer unavailable camera', (
    WidgetTester tester,
  ) async {
    final previousPlatform = debugDefaultTargetPlatformOverride;
    try {
      debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
      await pumpIntake(tester, const Size(1200, 1400));
      expect(
        find.byKey(const ValueKey<String>('intake-take-photograph')),
        findsNothing,
      );
      final Finder files = find.byKey(
        const ValueKey<String>('intake-choose-files'),
      );
      expect(files.hitTestable(), findsOneWidget);
      expect(tester.widget<UiButton>(files).onPressed, isNotNull);
    } finally {
      debugDefaultTargetPlatformOverride = previousPlatform;
    }
  });

  testWidgets(
    'a native phone offers camera and files as usable source choices',
    (WidgetTester tester) async {
      final previousPlatform = debugDefaultTargetPlatformOverride;
      try {
        debugDefaultTargetPlatformOverride = TargetPlatform.android;
        await pumpIntake(tester, const Size(1200, 1400));
        final Finder camera = find.byKey(
          const ValueKey<String>('intake-take-photograph'),
        );
        expect(camera.hitTestable(), findsOneWidget);
        expect(tester.widget<UiButton>(camera).onPressed, isNotNull);
        expect(
          find.byKey(const ValueKey<String>('intake-choose-files')),
          findsOneWidget,
        );
      } finally {
        debugDefaultTargetPlatformOverride = previousPlatform;
      }
    },
  );
}
