// The inputs family gallery golden (10 sections 4.2 and 6).
//
// The family page at 1180 by 820, in light and dark, at touch and pointer
// density. These are the taste review: a change to a field's edge, a switch's
// thumb or a checkbox's mark shows as a diff here before it shows on a screen.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

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
