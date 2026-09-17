// The actions gallery goldens (10 section 6).
//
// The taste review for the family: every control of 10 section 4.1 in every
// variant, size and state, in light and dark and at touch and pointer
// density. A change to any control in the family shows as a diff here before
// it shows on a screen.
//
// Captured at the gallery's width and a height that holds the whole page.
// The window was 820 while the page ended at 1616, which 10 section 6 already
// called out as the one family still taller than its window; the fit wave
// added the Fit block of 11 section 3.5 under it and the page now ends at
// 2492. A golden that reviews the top of a page is not reviewing the controls
// below the fold, and the controls below this fold were most of the family.
// Measured against the page rather than guessed, as the inputs window was.
//
// The page is rendered on its own rather than inside the whole gallery, so
// these four files hold still when the other four family slots register their
// pages.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// The window the family golden is captured at.
///
/// The width [galleryWindow] states, and a height that holds the whole page
/// instead of the 820 that truncated it.
const Size _window = Size(1180, 2540);

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
          window: _window,
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
