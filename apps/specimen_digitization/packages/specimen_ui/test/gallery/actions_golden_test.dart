// The actions gallery goldens (10 section 6).
//
// The taste review for the family: every control of 10 section 4.1 in every
// variant, size and state, at 1180 by 820, in light and dark and at touch and
// pointer density. A change to any control in the family shows as a diff here
// before it shows on a screen.
//
// The page is rendered on its own rather than inside the whole gallery, so
// these four files hold still when the other four family slots register their
// pages.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  // The focus ring is drawn only under `FocusHighlightMode.traditional`
  // (10 section 2 clause 4), and a golden presses no key, so the page's
  // focused specimen would otherwise be indistinguishable from its resting
  // one. Stating the mode is what puts the ring in the review.
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  final GalleryPage page = familyPages.firstWhere(
    (GalleryPage candidate) => candidate.id == 'actions',
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
        );
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
