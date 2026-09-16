// The gallery route (10 section 6).
//
// It is how the direction is reviewed by eye, so it has to open with no
// session and no collection, and it must not exist in a release build.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_ui/gallery.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('it opens with no session', (WidgetTester tester) async {
    await tester.pumpWidget(
      const SpecimenDigitizationApp(initialLocation: AppRoutes.gallery),
    );
    await tester.pumpAndSettle();
    expect(
      find.byType(UiGallery),
      findsOneWidget,
      reason:
          'the gallery reads no collection data, so the redirect that sends '
          'a window with no session to setup must let it through',
    );
  });

  testWidgets('every foundation page opens from the page list', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const SpecimenDigitizationApp(initialLocation: AppRoutes.gallery),
    );
    await tester.pumpAndSettle();
    for (final GalleryPage page in foundationPages) {
      await tester.tap(find.bySemanticsLabel(page.title).first);
      await tester.pumpAndSettle();
      expect(find.text(page.summary), findsOneWidget, reason: page.id);
    }
  });

  test('the gallery is a global location, like help', () {
    // Both open over whatever the reviewer had open and name no collection,
    // so the redirect must not read one out of them.
    expect(AppRoutes.isGlobalLocation(AppRoutes.gallery), isTrue);
    expect(AppRoutes.isEntryLocation(AppRoutes.gallery), isFalse);
  });
}
