// The foundation gallery goldens (10 section 6).
//
// These are the taste review. Every foundation page at 1180 by 820, in light
// and dark, at touch and pointer density: a change to a token shows as a diff
// here before it shows on a screen.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  for (final GalleryPage page in foundationPages) {
    for (final Brightness mode in Brightness.values) {
      for (final UiDensityMode density in UiDensityMode.values) {
        final String name = galleryGoldenName(
          'foundation',
          page.id,
          mode: mode,
          density: density,
        );
        testWidgets(name, (WidgetTester tester) async {
          await goldenGalleryPage(
            tester,
            // Pinned to the foundation's own list. The shell shows the family
            // pages beside these, and without the pin every family that
            // registers one moves all 24 of these goldens by adding a row to
            // the page list. A golden belongs to the slot that renders it
            // (build plan section 8).
            UiGallery(
              pages: foundationPages,
              initialPage: foundationPages.indexOf(page),
            ),
            mode: mode,
            density: density,
          );
          // The gallery is one window like any other, and the budget holds.
          // A page that states a larger number is a specimen sheet saying so
          // out loud, not the golden skipping the check.
          expectGlassBudget(
            tester,
            maxPanes: page.maxGlassPanes,
            window: page.id,
          );
          await expectLater(
            find.byType(UiGallery),
            matchesGoldenFile('goldens/$name'),
          );
        });
      }
    }
  }
}
