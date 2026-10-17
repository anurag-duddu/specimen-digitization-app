import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/widgets/intake_photo.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../intake_harness.dart' show chooseFiles;
import '../intake_layout_test.dart' show pumpIntake, verticalScrollables;
import 'golden_harness.dart' show expectGoldenFinder, settleImages;
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
            final photo = find.byType(IntakePhoto);
            final rect = tester.getRect(photo);
            expect(rect.top, greaterThanOrEqualTo(0));
            expect(rect.bottom, lessThan(size.height));
            expect(rect.left, greaterThanOrEqualTo(0));
            expect(rect.right, lessThanOrEqualTo(size.width));
            expect(rect.width, greaterThanOrEqualTo(96));
            final image = tester.widget<Image>(
              find.descendant(of: photo, matching: find.byType(Image)),
            );
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
      expect(find.byType(IntakePhoto), findsOneWidget);
      expect(find.text('layout-label.png'), findsOneWidget);
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
        final photo = find.byType(IntakePhoto);
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
        expect(find.text('Photo preview'), findsOneWidget);
        final close = find.byWidgetPredicate(
          (widget) => widget is UiButton && widget.label == 'Close preview',
        );
        expect(_focusInside(close), isTrue);
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
        expect(find.text('Photo preview'), findsNothing);
        expect(_focusInside(photo), isTrue);
        expect(find.text('Waiting to upload'), findsOneWidget);
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
