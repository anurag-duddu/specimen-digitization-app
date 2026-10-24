import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'bulk_intake_test.dart' show BulkFixtureRepository;
import 'golden/golden_harness.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets(
    'attention replaces passive saving with a reachable recovery action',
    (tester) async {
      final repo = BulkFixtureRepository(20, state: 'needs_attention');
      await pumpGoldenApp(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.light,
        textScale: 2,
        location: goldenIntakeLocation,
        repository: repo,
      );
      expect(
        find.text('20 photos · 20 need attention').hitTestable(),
        findsOneWidget,
      );
      expect(find.text('Submit 0 photos'), findsNothing);
      final review = find.widgetWithText(UiButton, 'Review 20 photos');
      expect(review.hitTestable(), findsOneWidget);
      await tester.tap(review);
      await tester.pumpAndSettle();
      expect(find.byType(BulkPhotoInspector), findsOneWidget);
      expect(find.text('Choose the original photo again.'), findsWidgets);
      expect(repo.submitted, isFalse);
      expect(repo.photos.length, 20);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  for (final size in [
    const Size(320, 740),
    const Size(390, 844),
    const Size(768, 1024),
    const Size(1440, 900),
  ]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('intake source workspace fits $size at $scale', (
        tester,
      ) async {
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: scale == 1 ? Brightness.light : Brightness.dark,
          textScale: scale,
          location: goldenIntakeLocation,
          repository: BulkFixtureRepository(0),
        );

        expect(find.byType(BulkIntakeScreen), findsOneWidget);
        expect(find.byType(UiBrandHero), findsNothing);
        expect(find.text('Add photos'), findsOneWidget);
        final sources = find.widgetWithText(
          UiDisclosure,
          'Import from a source',
        );
        expect(find.widgetWithText(UiListRow, 'Google Drive'), findsNothing);
        final firstSource = find.widgetWithText(
          UiButton,
          size.width < WindowClass.mediumMin ? 'Take photos' : 'Choose files',
        );
        expect(firstSource.hitTestable(), findsOneWidget);
        final scroll = find.byKey(const ValueKey('bulk-photo-grid'));
        expect(tester.widget(scroll), isA<CustomScrollView>());
        expect(
          find.descendant(of: scroll, matching: find.byType(Scrollable)),
          findsOneWidget,
        );
        for (final label in ['Take photos', 'Choose files']) {
          final button = find.widgetWithText(UiButton, label);
          await tester.ensureVisible(button);
          await tester.pumpAndSettle();
          expect(button.hitTestable(), findsOneWidget);
          expect(tester.getSize(button).height, greaterThanOrEqualTo(48));
          expect(tester.takeException(), isNull);
        }
        await tester.ensureVisible(sources);
        await tester.tap(find.text('Import from a source'));
        await tester.pumpAndSettle();
        for (final label in [
          'Google Drive',
          'Dropbox',
          'Storage',
          'Import links',
        ]) {
          final row = find.widgetWithText(UiListRow, label);
          await tester.ensureVisible(row);
          await tester.pumpAndSettle();
          expect(row.hitTestable(), findsOneWidget);
          expect(tester.getSize(row).height, greaterThanOrEqualTo(48));
          expect(tester.takeException(), isNull);
        }
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }

    testWidgets('intake draft scroll keeps submit available at $size', (
      tester,
    ) async {
      final repo = BulkFixtureRepository(100);
      await pumpGoldenApp(
        tester,
        window: size,
        brightness: Brightness.light,
        textScale: 2,
        location: goldenIntakeLocation,
        repository: repo,
      );
      expect(find.byType(UiBrandHero), findsNothing);
      expect(find.widgetWithText(UiButton, 'Batches'), findsOneWidget);
      expect(
        find.text('Saved'),
        findsNothing,
        reason: 'The shared tile suppresses the repeated settled baseline.',
      );
      final scroll = find.byKey(const ValueKey('bulk-photo-grid'));
      final submit = find.widgetWithText(UiButton, 'Submit 100 photos');
      expect(submit.hitTestable(), findsOneWidget);
      final gallery = tester.getRect(scroll);
      final firstPhoto = tester.getRect(find.byType(UiPhotoTile).first);
      expect(
        firstPhoto.intersect(gallery).height,
        greaterThanOrEqualTo(48),
        reason: 'A draft photo remains visible below the initial header.',
      );
      final before = tester.getBottomRight(submit);
      await tester.drag(scroll, const Offset(0, -500));
      await tester.pumpAndSettle();
      expect(submit.hitTestable(), findsOneWidget);
      // Touch input can increase the control's density on a wide window;
      // its bottom anchor must still stay fixed while the gallery scrolls.
      expect(tester.getBottomRight(submit), before);
      expect(find.byType(UiPhotoTile).evaluate().length, lessThan(100));
      expect(
        find.descendant(of: scroll, matching: find.byType(Scrollable)),
        findsOneWidget,
      );
      expect(repo.submitted, isFalse);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets('selection commands stay reachable deep in a draft', (
    tester,
  ) async {
    final repo = BulkFixtureRepository(100);
    await pumpGoldenApp(
      tester,
      window: const Size(390, 844),
      brightness: Brightness.light,
      textScale: 2,
      location: goldenIntakeLocation,
      repository: repo,
    );
    final scroll = find.byKey(const ValueKey('bulk-photo-grid'));
    await tester.drag(scroll, const Offset(0, -900));
    await tester.pumpAndSettle();
    final viewport = tester.getRect(scroll);
    final tile = find.byType(UiPhotoTile).evaluate().firstWhere((element) {
      final bounds = tester.getRect(find.byWidget(element.widget));
      return bounds.top >= viewport.top && bounds.top < viewport.bottom;
    });
    (tile.widget as UiPhotoTile).onSelected(true);
    await tester.pumpAndSettle();
    final edit = find.widgetWithText(UiButton, 'Edit 1 selected');
    expect(edit.hitTestable(), findsOneWidget);
    expect(find.text('Submit 100 photos').hitTestable(), findsOneWidget);
    await tester.tap(edit);
    await tester.pumpAndSettle();
    final exclude = find.widgetWithText(UiButton, 'Exclude selected').last;
    await tester.ensureVisible(exclude);
    await tester.tap(exclude);
    await tester.pumpAndSettle();
    expect(find.text('Submit 99 photos').hitTestable(), findsOneWidget);
    expect(repo.photos.where((photo) => photo['included'] == false).length, 1);
    expect(repo.submitted, isFalse);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
