// The data gallery goldens (10 section 6).
//
// The taste review for the family: every control of 10 section 4.5 in every
// variant, size and state, in light and dark and at touch and pointer
// density. A change to any control in the family shows as a diff here before
// it shows on a screen.
//
// Captured at 1180 by 1600 rather than at the shared 1180 by 820. Eight
// controls do not fit one window, and the actions slot recorded the cost of
// pretending they do: its golden reviews the top of its page and leaves three
// controls below the fold. A taller window is the smaller change, and it
// belongs to this golden alone, so no other family's files move for it.
//
// The page is rendered on its own rather than inside the whole gallery, so
// these four files hold still when the other family slots register theirs.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// Tall enough for the whole page, at the width every family golden uses.
const Size dataGalleryWindow = Size(1180, 1900);

void main() {
  // The focus ring is drawn only under `FocusHighlightMode.traditional`
  // (10 section 2 clause 4), and a golden presses no key, so a focused
  // specimen would otherwise be indistinguishable from a resting one.
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  final GalleryPage page = familyPages.firstWhere(
    (GalleryPage candidate) => candidate.id == 'data',
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
          window: dataGalleryWindow,
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
