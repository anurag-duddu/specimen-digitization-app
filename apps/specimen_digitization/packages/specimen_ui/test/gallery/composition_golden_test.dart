// The composition gallery goldens (13 section 3; 10 section 6).
//
// The taste review for slot A1: the record screen's compact composition built
// from the patterns the package now provides, at rest and scrolled, beside the
// pieces it is made of. It exists so that the arrangement 13 specifies is
// pictured before any screen adopts it, which is what nobody had when the
// record screen was drawn the first time.
//
// Three windows rather than the gallery's one, because a composition is an
// arrangement and an arrangement is only evidence at more than one width: 390
// is the phone 13 section 0 measured the defect on, 768 a tablet in portrait
// and 1180 the window every other gallery golden uses. Each is captured at the
// height its page needs, measured against the page, so the review is of the
// whole page rather than of the part above a fold. Touch density, because the
// composition rules are about a window a thumb works in; the matrix under
// `goldens/matrix/` covers the same page at pointer density and three text
// scales.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';

import '../harness/control_contract.dart';

/// The three windows, each at the height the page measures in it.
///
/// Heights are the first value with nothing left to scroll: 2768, 2566 and
/// 1558 measured, rounded up to the grid.
const Map<String, Size> compositionWindows = <String, Size>{
  '390': Size(390, 2780),
  '768': Size(768, 2580),
  '1180': Size(1180, 1560),
};

void main() {
  final GalleryPage page = galleryPages.firstWhere(
    (GalleryPage candidate) => candidate.id == 'composition',
  );

  for (final MapEntry<String, Size> window in compositionWindows.entries) {
    for (final Brightness mode in Brightness.values) {
      final String name =
          '${page.id}-${window.key}-'
          '${mode == Brightness.dark ? 'dark' : 'light'}.png';
      testWidgets(name, (WidgetTester tester) async {
        await goldenGalleryPage(
          tester,
          UiGallery(pages: <GalleryPage>[page]),
          mode: mode,
          window: window.value,
        );
        // The page states its own number and the golden checks it rather
        // than skipping the budget: two page frames, each with an action bar
        // and a hidden pill, the scrolled one with its top bar's fill and the
        // pane behind its collapsed chrome, and the shell's page list.
        expectGlassBudget(tester, maxPanes: page.maxGlassPanes, window: name);
        await expectLater(
          find.byType(UiGallery),
          matchesGoldenFile('goldens/$name'),
        );
      });
    }
  }
}
