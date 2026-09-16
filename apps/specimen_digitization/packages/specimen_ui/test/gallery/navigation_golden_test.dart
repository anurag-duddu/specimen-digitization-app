// The navigation gallery goldens (10 sections 4.4 and 6).
//
// The taste review for slot C4: the pill at two, three and five destinations,
// the rail collapsed and extended, the sidebar, a page frame with a sky, a top
// bar, an action bar and a pill, and the top bar at rest and scrolled under.
// A change to any of them shows as a diff here before it shows on a screen.
//
// The page is rendered on its own rather than inside the whole gallery, so
// these four files hold still when the other four family slots register their
// pages. It is captured at 1180 by 940 rather than the gallery's own 1180 by
// 820, because a family whose largest specimen is a page frame does not fit in
// one window's height and a truncated golden reviews only what fits.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// Tall enough to hold the whole page, at the gallery's own width.
const Size navigationWindow = Size(1180, 940);

void main() {
  final GalleryPage page = familyPages.firstWhere(
    (GalleryPage candidate) => candidate.id == 'navigation',
  );

  for (final Brightness mode in Brightness.values) {
    for (final UiDensityMode density in UiDensityMode.values) {
      final String name =
          '${page.id}-${mode == Brightness.dark ? 'dark' : 'light'}-'
          '${density.name}.png';
      testWidgets(name, (WidgetTester tester) async {
        await goldenGalleryPage(
          tester,
          UiGallery(pages: <GalleryPage>[page]),
          mode: mode,
          density: density,
          window: navigationWindow,
        );
        // A specimen sheet states its own number out loud rather than the
        // golden quietly skipping the check. A product window is held to the
        // four in 09 section 3.3, which is what the frame's own test asserts:
        // a top bar, an action bar and a pill are three panes.
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
