// The dark mode pass of the second verification report
// (09 sections 3.1 to 3.3; `design/12-verification-report-v2.md`).
//
// `test/theme/dark_mode_test.dart` pumps each screen once, bare, on a tall
// canvas, and runs the contrast guideline over it. That answers "does dark
// read", and it answers it at one measure. This file answers the three
// questions the refactor added, at every window class, on the routed
// application:
//
//   contrast   the guideline again, but at the four windows a reviewer
//              actually has, since a window class chooses a different
//              arrangement and a different set of surfaces;
//   glass      how many frosted panes are on screen against the budget of
//              09 section 3.3, and what `ink` measures over the flat pane
//              when that pane sits over the darkest field in the system;
//   accent     how many separate marks are painted in `#E8FF47`, counted
//              off the pixels rather than off the widgets, because "one use
//              per screen" is a rule about what the eye lands on.
//
// A screen that reports more than one accent mark is not automatically a
// defect: a queue row's position marker and the navigation's current
// destination are two marks in one window by design. The number is recorded
// per screen and the report says which are intended.

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import 'fit_matrix_test.dart' show chooseSegment;
import 'verification_harness.dart';

/// The screens the dark pass sweeps, and how to open each one.
///
/// The region editor is not here: it is pushed outside the collection shell
/// and the fit matrix already draws it at every class in both containers.
/// Everything a reviewer reaches inside the shell is.
final Map<String, Future<void> Function(WidgetTester, Size)> darkScreens =
    <String, Future<void> Function(WidgetTester, Size)>{
      'sign in': (WidgetTester tester, Size size) => pumpMeasuredApp(
        tester,
        window: size,
        brightness: Brightness.dark,
        signedIn: false,
      ),
      'queue': (WidgetTester tester, Size size) => pumpMeasuredApp(
        tester,
        window: size,
        brightness: Brightness.dark,
        location: goldenQueueLocation,
      ),
      'filters': (WidgetTester tester, Size size) async {
        await pumpMeasuredApp(
          tester,
          window: size,
          brightness: Brightness.dark,
          location: goldenQueueLocation,
        );
        await tester.tap(find.text('Filters'));
        await tester.pumpAndSettle();
      },
      'intake': (WidgetTester tester, Size size) => pumpMeasuredApp(
        tester,
        window: size,
        brightness: Brightness.dark,
        location: goldenIntakeLocation,
      ),
      'sources': (WidgetTester tester, Size size) => pumpMeasuredApp(
        tester,
        window: size,
        brightness: Brightness.dark,
        location: goldenSourcesLocation,
        repository: GoldenSourceRepository(),
      ),
      'source': (WidgetTester tester, Size size) => pumpMeasuredApp(
        tester,
        window: size,
        brightness: Brightness.dark,
        location: goldenSourceLocation,
        repository: GoldenSourceRepository(),
      ),
      for (final WorkbenchSegment segment in WorkbenchSegment.values)
        'record ${segment.name}': (WidgetTester tester, Size size) async {
          await pumpMeasuredApp(
            tester,
            window: size,
            brightness: Brightness.dark,
            location: goldenSpecimenLocation,
          );
          await chooseSegment(tester, segment);
        },
      'help': (WidgetTester tester, Size size) => pumpMeasuredApp(
        tester,
        window: size,
        brightness: Brightness.dark,
        location: AppRoutes.help,
      ),
    };

/// Cells where `textContrastGuideline` reports a failure that the pixels do
/// not support.
///
/// The guideline takes the most frequent colour on each side of a luminance
/// threshold across a node's whole rectangle. Where a node's rectangle is much
/// wider than its glyphs, or where the ground under it is a gradient, both
/// frequencies land on the background and the ratio it prints is between two
/// shades of the same thing. Each entry names the run that was actually drawn
/// and what it measures, read off the checked-in dark golden with
/// [measurePair]'s method. A cell that starts passing fails this test, so the
/// list can only shrink on purpose.
const Map<String, String> guidelineArtefacts = <String, String>{
  'queue at large-1440x900':
      'the top bar title node is the whole bar (11 section 3.3 gives the '
      'title an Expanded), so the histogram reports two shades of the sky. '
      'The glyphs are ink #f2f2ef over the bar and measure 11.22:1',
  'intake at large-1440x900': 'the same top bar title node',
  'sources at large-1440x900': 'the same top bar title node',
  'source at large-1440x900': 'the same top bar title node',
  // The decision bar's count, on the record cells whose count node the
  // histogram cannot read. 13 section 3.3 makes the count the bar's
  // `Expanded` child, because the decision is what the reviewer came to make
  // and the count is what gives way, so "1 of 1" is a node the width of the
  // bar holding thirty dp of glyphs and the histogram reports two shades of
  // the pane. The glyphs are ink.secondary #b9bcc3 on the action bar's pane
  // #16171a and measure 8.98:1. From `expanded` up the decision bar sits in
  // the top bar (13 section 4.1, polish 3): at 1180 by 820 the node's
  // histogram then separates the glyphs from the bar and the guideline passes
  // the three cells, so their entries are gone; at 1440 by 900 the node is
  // 690 dp wide over the bar and still reads two shades of it.
  'record readings at medium-768x1024': 'the decision bar count node',
  'record readings at large-1440x900': 'the decision bar count node',
  'record fields at compact-390x844': 'the decision bar count node',
  'record fields at medium-768x1024': 'the decision bar count node',
  'record fields at large-1440x900': 'the decision bar count node',
  'record history at medium-768x1024': 'the decision bar count node',
  'record history at large-1440x900': 'the decision bar count node',
};

/// Cells where the guideline reports a failure and the pixels agree.
///
/// A gate in the shape of `knownWorkbenchOverflows`: a cell that starts
/// passing fails this test too, so a fix has to take its entry out in the same
/// change. Every entry is written up in `design/12-verification-report-v2.md`
/// with its owner.
const Map<String, String> knownDarkContrastDefects = <String, String>{
  'queue at compact-390x844':
      'V2-2. The queue freshness line is ink.tertiary over the sun field, '
      'which measures 3.87:1 where the table only ever checked it over the '
      'three opaque surfaces',
  'queue at medium-768x1024': 'V2-2, 4.04:1',
  'queue at expanded-1180x820': 'V2-2, 4.05:1',
};

/// The WCAG 2.2 AA floor for body text.
const double bandPairFloor = 4.5;

/// What the environment band's own tokens declare, per mode.
///
/// `environmentOnFill` on `environmentFill`: 9.31:1 in light and 8.21:1 in
/// dark, comfortably clear of the floor. This is what the band measures
/// wherever it is painted over the sky rather than under it.
const Map<String, double> declaredBandPair = <String, double>{
  'light': 9.31,
  'dark': 8.21,
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('the dark tokens over the darkest field', () {
    test('ink on the flat pane over the matte clears the AA text floor', () {
      final UiThemeData dark = UiThemeData.dark();
      final Color pane = Color.alphaBlend(
        dark.glass.flat.fill,
        dark.color.matte,
      );
      final double ratio = contrastRatio(dark.color.ink, pane);
      debugPrint(
        'DARKROW|glass|flat over matte|'
        'pane=${_hex(pane)}|ink=${_hex(dark.color.ink)}|'
        'ratio=${ratio.toStringAsFixed(2)}',
      );
      expect(
        ratio,
        greaterThanOrEqualTo(4.5),
        reason:
            'a frosted pane over the darkest field in the system is the worst '
            'ground `ink` is asked to sit on (09 section 3.3)',
      );
    });

    test('the opaque fallback is no worse than the blurred pane', () {
      final UiThemeData dark = UiThemeData.dark();
      final Color blurred = Color.alphaBlend(
        dark.glass.modal.fill,
        dark.color.matte,
      );
      final Color opaque = Color.alphaBlend(
        dark.glass.modal.opaqueFallback,
        dark.color.matte,
      );
      final double blurredRatio = contrastRatio(dark.color.ink, blurred);
      final double opaqueRatio = contrastRatio(dark.color.ink, opaque);
      debugPrint(
        'DARKROW|glass|modal over matte|'
        'blurred=${blurredRatio.toStringAsFixed(2)}|'
        'opaque=${opaqueRatio.toStringAsFixed(2)}',
      );
      // `GlassQuality.off` is the setting a slow device gets, so the reader it
      // is chosen for must not read worse than the reader it is taken from.
      expect(opaqueRatio, greaterThanOrEqualTo(blurredRatio));
      expect(opaqueRatio, greaterThanOrEqualTo(4.5));
    });
  });

  // Both modes, because the defect this group holds is worse in light than it
  // is in dark and a dark only sweep would have reported the better half.
  // Everything from here on reads rendered pixels; it runs where the goldens
  // are drawn (`pixelInstrumentsCompare`) and is marked skipped elsewhere.
  if (!pixelInstrumentsCompare) {
    test('the pixel measurements run on macOS only', () {
      markTestSkipped(pixelInstrumentSkip);
    });
    return;
  }

  group('the environment band over the sky', () {
    goldenThemes.forEach((String mode, Brightness brightness) {
      goldenWindows.forEach((String window, Size size) {
        testWidgets('the band on sign in at $window in $mode', (
          WidgetTester tester,
        ) async {
          await pumpMeasuredApp(
            tester,
            window: size,
            brightness: brightness,
            signedIn: false,
          );
          final ({double ratio, int ground, int run}) pair = await measurePair(
            tester,
            tester.getRect(find.byType(UiBanner)),
          );
          debugPrint(
            'BANDROW|sign in|$window|$mode|fill=${hexOf(pair.ground)}'
            '|run=${hexOf(pair.run)}|ratio=${pair.ratio.toStringAsFixed(2)}',
          );
          // Defect V2-1 of the report measured 3.31:1 to 5.91:1 here: the sky
          // field painted over the band. The field painter clips to its own
          // layer since 4973420, so the band on an entry screen measures the
          // pair its tokens declare, and the report's addendum says so.
          expect(
            pair.ratio,
            closeTo(declaredBandPair[mode]!, 0.05),
            reason:
                'the band on an entry screen measures the pair its tokens '
                'declare, ${declaredBandPair[mode]}:1, now that the sky is '
                'clipped to its own layer (V2-1, fixed). A lower number means '
                'something paints over the band again.',
          );
        });

        testWidgets('the band on the queue at $window in $mode', (
          WidgetTester tester,
        ) async {
          await pumpMeasuredApp(
            tester,
            window: size,
            brightness: brightness,
            location: goldenQueueLocation,
          );
          final ({double ratio, int ground, int run}) pair = await measurePair(
            tester,
            tester.getRect(find.byType(UiBanner)),
          );
          debugPrint(
            'BANDROW|queue|$window|$mode|fill=${hexOf(pair.ground)}'
            '|run=${hexOf(pair.run)}|ratio=${pair.ratio.toStringAsFixed(2)}',
          );
          expect(
            pair.ratio,
            greaterThanOrEqualTo(bandPairFloor),
            reason:
                'inside the scaffold the band is painted over the sky rather '
                'than under it, so it keeps the pair the tokens declare: '
                '9.31:1 in light and 8.21:1 in dark',
          );
        });
      });
    });
  });

  darkScreens.forEach((
    String screen,
    Future<void> Function(WidgetTester, Size) open,
  ) {
    group('$screen in dark', () {
      goldenWindows.forEach((String window, Size size) {
        testWidgets('$screen at $window in dark', (WidgetTester tester) async {
          final SemanticsHandle handle = tester.ensureSemantics();
          captureLayoutErrors();
          await open(tester, size);
          final String variant = navigationVariant(tester);
          final bool scrolls = anyScrollableHasExtent(tester);
          final ({int panes, int modal}) glass = glassPanes();
          final int accent = await accentRegions(tester);
          final String contrast = await measureContrast(tester);
          final bool overflowed = stopAndReportOverflow(tester);
          reportCell(
            screen: screen,
            window: window,
            scale: 1.0,
            mode: 'dark',
            variant: variant,
            scrolls: scrolls,
            overflowed: overflowed,
            accent: accent,
            panes: glass.panes,
          );
          debugPrint(
            'DARKROW|$screen|$window|contrast=$contrast'
            '|modal=${glass.modal}',
          );
          handle.dispose();

          expect(
            overflowed,
            isFalse,
            reason: '$screen laid out past a $window window in dark',
          );
          expect(
            glass.panes,
            lessThanOrEqualTo(UiGlass.maxPanesPerWindow),
            reason:
                'there are ${glass.panes} frosted panes on $screen at '
                '$window and the budget is ${UiGlass.maxPanesPerWindow} '
                '(09 section 3.3). Every pane is a save layer.',
          );
          expect(
            glass.modal,
            lessThanOrEqualTo(UiGlass.maxModalPanes),
            reason: 'two modals at once is a question nobody can answer',
          );
          final String key = '$screen at $window';
          if (guidelineArtefacts.containsKey(key)) {
            expect(
              contrast,
              isNot('pass'),
              reason:
                  '$key is recorded as an instrument artefact and the '
                  'guideline now passes it. Take the entry out in the same '
                  'change: ${guidelineArtefacts[key]}',
            );
          } else if (knownDarkContrastDefects.containsKey(key)) {
            expect(
              contrast,
              isNot('pass'),
              reason:
                  '$key is a recorded defect and it now passes. If that is '
                  'the fix, take it out of knownDarkContrastDefects in the '
                  'same change: ${knownDarkContrastDefects[key]}',
            );
          } else {
            expect(
              contrast,
              'pass',
              reason:
                  '$screen at $window in dark failed the WCAG AA text '
                  'contrast guideline. The token table is not the whole of '
                  'contrast: a pair is only as good as the ground it landed '
                  'on.',
            );
          }
        });
      });
    });
  });
}

/// Runs the AA text contrast guideline and says what it found.
///
/// Returned rather than thrown, so a sweep records every window before it
/// fails on one. The guideline is never relaxed: a failure is a token misuse
/// to fix, and the string it returns is what the report quotes.
Future<String> measureContrast(WidgetTester tester) async {
  try {
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    return 'pass';
  } on TestFailure catch (error) {
    return (error.message ?? '$error')
        .replaceAll('\n', ' ')
        .replaceAll('|', '/');
  }
}

/// The WCAG 2.2 contrast ratio between two opaque colours.
double contrastRatio(Color foreground, Color background) {
  final double a = _luminance(foreground);
  final double b = _luminance(background);
  final double lighter = math.max(a, b);
  final double darker = math.min(a, b);
  return (lighter + 0.05) / (darker + 0.05);
}

double _luminance(Color color) => Color.fromARGB(
  0xFF,
  (color.r * 0xFF).round(),
  (color.g * 0xFF).round(),
  (color.b * 0xFF).round(),
).computeLuminance();

String _hex(Color color) =>
    '#${((color.r * 0xFF).round() << 16 | (color.g * 0xFF).round() << 8 | (color.b * 0xFF).round()).toRadixString(16).padLeft(6, '0')}';
