import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/widgets/intake_photo.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../intake_harness.dart' show chooseFiles;
import '../intake_layout_test.dart' show pumpIntake, verticalScrollables;
import 'golden_harness.dart';
import '../widgets/harness.dart' show expectAccessible;

bool _focusInside(Finder finder) {
  final context = FocusManager.instance.primaryFocus?.context;
  if (context == null) return false;
  final targets = finder.evaluate().toSet();
  var found = targets.contains(context);
  context.visitAncestorElements((element) {
    found = found || targets.contains(element);
    return !found;
  });
  return found;
}

void main() {
  for (final brightness in [Brightness.light, Brightness.dark]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets(
        'routed selected phone photo with sticky Send $brightness text $scale',
        (tester) async {
          SharedPreferences.setMockInitialValues({});
          final repo = GoldenRepository();
          await pumpGoldenApp(
            tester,
            window: const Size(390, 844),
            brightness: brightness,
            textScale: scale,
            location: goldenIntakeLocation,
            repository: repo,
          );
          final screen = tester.widget<IntakeScreen>(find.byType(IntakeScreen));
          final session = intakeTransferSession(
            repo,
            screen.scope,
            screen.userId,
          );
          session.entries.add(
            ManifestEntry(
              digest: 'selected',
              name: 'selected.png',
              state: UploadState.ready,
              file: IntakeFile(
                name: 'selected.png',
                bytes: goldenPreviewBytes,
                sha256: 'selected',
                mimeType: 'image/png',
                method: 'files',
                sensitive: true,
              ),
            ),
          );
          session.changed();
          await tester.pumpAndSettle();
          final row = find.byType(IntakeManifestRow);
          expect(tester.getRect(row).top, lessThan(844));
          final send = find.byKey(const ValueKey('intake-upload'));
          expect(send.hitTestable(), findsOneWidget);
          expect(tester.getRect(send).bottom, lessThanOrEqualTo(844));
          expect(
            tester.getRect(row).bottom,
            lessThanOrEqualTo(tester.getRect(send).top),
          );
          await expectAccessible(tester);
          await settleImages(tester);
          await expectGoldenFinder(
            tester,
            find.byType(MaterialApp),
            'intake-selected__routed-390x844__${brightness.name}__text$scale',
          );
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox.shrink());
        },
      );
    }
  }

  for (final size in <Size>[
    const Size(390, 844),
    const Size(768, 1024),
    const Size(1440, 900),
  ]) {
    for (final dark in <bool>[false, true]) {
      for (final scale in <double>[1, 2]) {
        testWidgets(
          'selected photo is visible at $size, dark=$dark, text=$scale',
          (tester) async {
            await pumpIntake(
              tester,
              size,
              selectedFile: true,
              textScale: scale,
              dark: dark,
            );
            final photo = find.descendant(
              of: find.byType(UploadItem),
              matching: find.byType(Image),
            );
            final rect = tester.getRect(photo);
            expect(rect.top, greaterThanOrEqualTo(0));
            expect(rect.bottom, lessThan(size.height));
            expect(rect.left, greaterThanOrEqualTo(0));
            expect(rect.right, lessThanOrEqualTo(size.width));
            expect(rect.width, greaterThanOrEqualTo(40));
            final image = tester.widget<Image>(photo);
            expect(image.fit, BoxFit.contain);
            expect(find.byType(IntakeCaptureCard), findsOneWidget);
            expect(find.text('Photos'), findsOneWidget);
            expect(verticalScrollables(), findsOneWidget);
            await expectAccessible(tester);
            expect(tester.takeException(), isNull);
            await settleImages(tester);
            await expectGoldenFinder(
              tester,
              find.byType(IntakeScreen),
              'intake-selected__${size.width.toInt()}x${size.height.toInt()}__'
              '${dark ? 'dark' : 'light'}__text${scale.toStringAsFixed(1)}',
            );
          },
        );
      }
    }
  }

  testWidgets(
    'adding controls stay visible without losing the selected photo',
    (tester) async {
      await pumpIntake(tester, const Size(390, 844), selectedFile: true);
      expect(
        find.byKey(const ValueKey('intake-choose-files')).hitTestable(),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('intake-add-photos')), findsNothing);
      await chooseFiles(tester);
      expect(find.byType(UploadItem), findsOneWidget);
      expect(find.text('layout-label.png'), findsOneWidget);
      expect(find.text('Already in the list'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  for (final dark in <bool>[false, true]) {
    testWidgets(
      'photo preview opens by keyboard and returns focus, dark=$dark',
      (tester) async {
        final semantics = tester.ensureSemantics();
        await pumpIntake(
          tester,
          const Size(768, 1024),
          selectedFile: true,
          dark: dark,
        );
        final photo = find.byType(UploadItem);
        for (var step = 0; step < 30 && !_focusInside(photo); step++) {
          await tester.sendKeyEvent(LogicalKeyboardKey.tab);
          await tester.pumpAndSettle();
        }
        expect(_focusInside(photo), isTrue);
        expect(
          tester
              .widgetList<FocusRing>(
                find.descendant(of: photo, matching: find.byType(FocusRing)),
              )
              .any((ring) => ring.visible),
          isTrue,
        );
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pumpAndSettle();
        expect(find.textContaining('Checksum (SHA-256)'), findsOneWidget);
        await tester.tap(find.byType(IntakePhoto));
        await tester.pumpAndSettle();
        expect(find.text('Photo preview'), findsOneWidget);
        final close = find.byWidgetPredicate(
          (widget) => widget is UiButton && widget.label == 'Close preview',
        );
        expect(_focusInside(close), isTrue);
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
        expect(find.text('Photo preview'), findsNothing);
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
        expect(_focusInside(photo), isTrue);
        expect(find.text('Ready'), findsOneWidget);
        expect(tester.takeException(), isNull);
        semantics.dispose();
      },
    );
  }

  testWidgets('send mode is visible and can enable immediate submission', (
    tester,
  ) async {
    await pumpIntake(tester, const Size(390, 844));
    expect(find.text(cameraReviewFirst), findsOneWidget);
    expect(find.byKey(const ValueKey('intake-camera-settings')), findsNothing);
    final toggle = find.byKey(const ValueKey('intake-auto-ingest'));
    expect(tester.widget<UiSegmented<bool>>(toggle).value, isFalse);
    await tester.ensureVisible(toggle);
    await tester.tap(find.text(cameraSendImmediatelyLabel));
    await tester.pumpAndSettle();
    expect(tester.widget<UiSegmented<bool>>(toggle).value, isTrue);
    expect(find.text(cameraSendImmediatelyLabel), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
