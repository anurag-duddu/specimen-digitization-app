// The inputs family gallery golden (10 sections 4.2 and 6).
//
// The family page in light and dark, at touch and pointer density. These are
// the taste review: a change to a field's edge, a switch's thumb or a
// checkbox's mark shows as a diff here before it shows on a screen.
//
// Captured at the gallery's width and a height that holds the whole page
// rather than the shell's 820. Seven controls in every state do not fit one
// window, and a golden that reviews the top of a page is not reviewing the
// three controls below the fold.
//
// The height moved from 1180 to 1600 when the fit wave added the box section
// of 11 section 4: eight specimens of the box itself, in each shape, at rest,
// focused, and focused with a value under the caret. Measured against the
// page, which ends at 1550, rather than guessed (10 section 6).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// The window the family golden is captured at.
///
/// The width [galleryWindow] states, and a height that holds the whole page
/// instead of the 820 that truncates it.
const Size _window = Size(1180, 1600);

void main() {
  // Found through the shell's own list rather than imported from the page
  // file, so the golden covers the page exactly as a reviewer opening
  // `/gallery` sees it: registered, in the family order.
  final GalleryPage page = familyPages.firstWhere(
    (GalleryPage candidate) => candidate.id == 'inputs',
  );

  for (final Brightness mode in Brightness.values) {
    for (final UiDensityMode density in UiDensityMode.values) {
      final String name =
          'inputs-${mode == Brightness.dark ? 'dark' : 'light'}-'
          '${density.name}.png';
      testWidgets(name, (WidgetTester tester) async {
        await goldenGalleryPage(
          tester,
          UiGallery(pages: <GalleryPage>[page]),
          mode: mode,
          density: density,
          window: _window,
        );
        // One window like any other. A page of controls is where a stray
        // frosted pane would first appear, so the budget is checked here.
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
