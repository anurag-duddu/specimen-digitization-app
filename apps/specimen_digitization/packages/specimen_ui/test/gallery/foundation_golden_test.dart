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
            UiGallery(
              // The foundation set, not the whole gallery: these goldens draw
              // the page list too, so pinning the pages is what keeps them
              // from moving every time a family slot registers a page.
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
