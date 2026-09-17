// The fit matrix of the verification report (11 section 3.5; north star,
// "Adaptation"; 12-verification-report-v2.md).
//
// The size-class goldens cover four windows in two themes, and two text
// scales on the two screens that carry the most text. The fit lens the
// refactor added asks for a third scale, 1.3, on every screen, because that
// is the scale a reviewer with ordinary presbyopia actually runs and it is
// the one no PNG in this repository pictures.
//
// So this file measures rather than pictures. For every screen, at the four
// window classes and at 1.0, 1.3 and 2.0, it records three facts: which
// navigation arrangement the shell chose, whether the screen had to scroll,
// and whether anything laid out past the window it was given. The verdict per
// cell in the report is derived from those three, and the run that produced
// it is this test.
//
// It is a gate as well as an instrument: an overflow anywhere fails it.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';
import 'verification_harness.dart';

/// The three text scales the fit lens asks for (11 section 2.1).
const List<double> matrixScales = <double>[1.0, 1.3, 2.0];

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final MatrixScreen screen in matrixScreens) {
    group(screen.name, () {
      goldenWindows.forEach((String window, Size size) {
        for (final double scale in matrixScales) {
          testWidgets('${screen.name} at $window at $scale', (
            WidgetTester tester,
          ) async {
            captureLayoutErrors();
            await screen.open(tester, size, scale, Brightness.light);
            final String variant = navigationVariant(tester);
            final bool scrolls = anyScrollableHasExtent(tester);
            final bool overflowed = stopAndReportOverflow(tester);
            reportCell(
              screen: screen.name,
              window: window,
              scale: scale,
              mode: 'light',
              variant: variant,
              scrolls: scrolls,
              overflowed: overflowed,
            );
            expect(
              overflowed,
              isFalse,
              reason:
                  '${screen.name} laid out past a $window window at text '
                  'scale $scale. Content a reviewer cannot see is pass '
                  'criterion 8.5 failing.',
            );
          });
        }
      });
    });
  }
}

/// One screen the matrix measures, and how to put it on screen.
class MatrixScreen {
  /// Names the screen and binds its opener.
  const MatrixScreen(this.name, this.open);

  /// The name the report's matrix uses.
  final String name;

  /// Puts the screen on screen at one window, scale and mode.
  final Future<void> Function(WidgetTester, Size, double, Brightness) open;
}

/// Every screen a reviewer can reach, in the order the report lists them.
final List<MatrixScreen> matrixScreens = <MatrixScreen>[
  MatrixScreen('sign in', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpGoldenApp(
      tester,
      window: size,
      brightness: brightness,
      textScale: scale,
      signedIn: false,
    );
  }),
  MatrixScreen('queue', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpGoldenApp(
      tester,
      window: size,
      brightness: brightness,
      textScale: scale,
      location: goldenQueueLocation,
    );
  }),
  MatrixScreen('filters', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpGoldenApp(
      tester,
      window: size,
      brightness: brightness,
      textScale: scale,
      location: goldenQueueLocation,
    );
    await tester.tap(find.text('Filters'));
    await tester.pumpAndSettle();
    expect(find.text('Filter the queue'), findsOneWidget);
  }),
  MatrixScreen('intake', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpGoldenApp(
      tester,
      window: size,
      brightness: brightness,
      textScale: scale,
      location: goldenIntakeLocation,
    );
  }),
  MatrixScreen('sources', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpGoldenApp(
      tester,
      window: size,
      brightness: brightness,
      textScale: scale,
      location: goldenSourcesLocation,
      repository: GoldenSourceRepository(),
    );
  }),
  MatrixScreen('source', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpGoldenApp(
      tester,
      window: size,
      brightness: brightness,
      textScale: scale,
      location: goldenSourceLocation,
      repository: GoldenSourceRepository(),
    );
  }),
  for (final WorkbenchSegment segment in WorkbenchSegment.values)
    MatrixScreen('record ${segment.name}', (
      WidgetTester tester,
      Size size,
      double scale,
      Brightness brightness,
    ) async {
      await pumpGoldenApp(
        tester,
        window: size,
        brightness: brightness,
        textScale: scale,
        location: goldenSpecimenLocation,
      );
      await chooseSegment(tester, segment);
    }),
  MatrixScreen('region editor', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpRegionEditor(tester, size, scale, brightness);
  }),
  MatrixScreen('help', (
    WidgetTester tester,
    Size size,
    double scale,
    Brightness brightness,
  ) async {
    await pumpGoldenApp(
      tester,
      window: size,
      brightness: brightness,
      textScale: scale,
      location: AppRoutes.help,
    );
  }),
];

/// Moves the record to [segment] with its shortcut, and returns the scroll
/// views to their tops.
///
/// The same method the size-class goldens use, and for the same reason: at
/// 200 percent text on a phone the record scrolls as one, so the selector's
/// position depends on the scroll offset and a tap would first have to move
/// the pane.
Future<void> chooseSegment(
  WidgetTester tester,
  WorkbenchSegment segment,
) async {
  final Finder tab = find.descendant(
    of: uiTabs(evidenceTabsLabel),
    matching: find.text(segment.label),
  );
  if (tab.evaluate().isNotEmpty) {
    await tester.sendKeyEvent(switch (segment) {
      WorkbenchSegment.readings => LogicalKeyboardKey.keyR,
      WorkbenchSegment.fields => LogicalKeyboardKey.keyF,
      WorkbenchSegment.history => LogicalKeyboardKey.keyH,
    });
    await tester.pumpAndSettle();
    await settleImages(tester);
  }
  for (final ScrollableState scroll in tester.stateList<ScrollableState>(
    find.byType(Scrollable),
  )) {
    if (scroll.position.hasPixels && scroll.position.pixels != 0) {
      scroll.position.jumpTo(0);
    }
  }
  await tester.pumpAndSettle();
}

/// Opens the region editor in the container the window class gives it.
Future<void> pumpRegionEditor(
  WidgetTester tester,
  Size size,
  double scale,
  Brightness brightness,
) async {
  tester.platformDispatcher.textScaleFactorTestValue = scale;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  if (size.width >= expandedWindowFloor) {
    await pumpGoldenDialog(
      tester,
      window: size,
      brightness: brightness,
      semanticsLabel: regionEditorTitle,
      dialog: RegionEditor(
        regions: goldenRegions,
        asset: goldenEditableAsset(),
      ),
    );
  } else {
    await pumpGoldenRoute(
      tester,
      window: size,
      brightness: brightness,
      child: UiScaffold(
        sky: SkyPreset.none,
        topBar: const UiTopBar(title: regionEditorTitle),
        body: RegionEditorBody(
          regions: goldenRegions,
          asset: goldenEditableAsset(),
        ),
      ),
    );
  }
}
