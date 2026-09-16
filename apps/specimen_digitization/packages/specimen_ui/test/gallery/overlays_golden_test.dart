// The overlays gallery goldens (10 sections 4.3 and 6).
//
// The family page at 1180 by 820 in light and dark at both densities, plus one
// window per mode with the sheet open and one with the dialog open, so the
// modal chrome is reviewed rather than only its trigger.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';
// The page itself rather than the shell's list, so this golden captures the
// overlays page whatever position the family slots end up in.
import 'package:specimen_ui/src/gallery/pages/overlays_page.dart';

import '../harness/control_contract.dart';

/// The one page this golden renders.
const List<GalleryPage> _pages = <GalleryPage>[overlaysPage];

/// The window the family page is captured at.
///
/// Taller than the 1180 by 820 every other gallery golden uses, because the
/// page is 922 logical pixels of content at touch density and a golden that
/// stops at 820 reviews the banners and nothing else. The modal goldens below
/// keep the standard window: a sheet and a dialog are judged against the
/// window they are drawn over, not against the page behind them.
const Size _pageWindow = Size(1180, 1000);

/// `light` or `dark`, as the file names spell it.
String _mode(Brightness mode) => mode == Brightness.dark ? 'dark' : 'light';

void main() {
  for (final Brightness mode in Brightness.values) {
    for (final UiDensityMode density in UiDensityMode.values) {
      final String name = 'overlays-${_mode(mode)}-${density.name}.png';
      testWidgets(name, (WidgetTester tester) async {
        await goldenGalleryPage(
          tester,
          const UiGallery(pages: _pages),
          mode: mode,
          density: density,
          window: _pageWindow,
        );
        expectGlassBudget(tester, window: name);
        await expectLater(
          find.byType(UiGallery),
          matchesGoldenFile('goldens/$name'),
        );
      });
    }
  }

  for (final Brightness mode in Brightness.values) {
    for (final (String surface, void Function(BuildContext) open)
        in <(String, void Function(BuildContext))>[
          ('sheet', openGallerySheet),
          ('dialog', openGalleryDialog),
        ]) {
      final String name = 'overlays-$surface-${_mode(mode)}.png';
      testWidgets(name, (WidgetTester tester) async {
        await _pumpModalWindow(tester, mode);
        open(tester.element(find.byType(UiGallery)));
        await tester.pumpAndSettle();

        expectGlassBudget(tester, window: name);
        await expectLater(
          // The whole window, because the modal is pushed above the page
          // rather than inside it.
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/$name'),
        );
      });
    }
  }
}

/// Pumps the gallery in a window whose tokens sit above the navigator.
///
/// `uiHarness` publishes `UiTheme` inside `home`, which is below the navigator,
/// so a route pushed over the page finds no scope and falls back to the light
/// tokens: a dark mode modal golden taken through it shows a light pane. The
/// application wraps `MaterialApp.router` in `UiTheme`, which is above every
/// route, so this mirrors the application rather than the harness. `Density`
/// is lifted for the same reason, so the chrome is drawn at the density the
/// page is.
Future<void> _pumpModalWindow(WidgetTester tester, Brightness mode) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = galleryWindow;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    UiTheme(
      data: mode == Brightness.dark
          ? UiThemeData.dark()
          : UiThemeData.light(),
      child: Density(
        initialMode: UiDensityMode.touch,
        child: uiHarness(
          brightness: mode,
          size: galleryWindow,
          child: const SizedBox.expand(child: UiGallery(pages: _pages)),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}
