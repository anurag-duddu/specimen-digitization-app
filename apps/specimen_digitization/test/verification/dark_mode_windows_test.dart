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
import '../ui_finders.dart';
import 'package:specimen_digitization/src/widgets/environment_banner.dart';

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
      'status filters': (WidgetTester tester, Size size) async {
        await pumpMeasuredApp(
          tester,
          window: size,
          brightness: Brightness.dark,
          location: goldenQueueLocation,
          repository: GoldenQueueRepository(goldenQueue(0)),
        );
        await chooseDeferredQueue(tester);
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

// The former sky/count-node exceptions describe the previous presentation.
// Every current routed cell must pass the unmodified contrast guideline.

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

        testWidgets(
          'the environment explanation on the queue at $window in $mode',
          (WidgetTester tester) async {
            await pumpMeasuredApp(
              tester,
              window: size,
              brightness: brightness,
              location: goldenQueueLocation,
            );
            final compactControl = uiIconButton('Test environment');
            final contextControl = compactControl.evaluate().isNotEmpty
                ? compactControl
                : find.byWidgetPredicate(
                    (widget) =>
                        widget is UiButton &&
                        widget.semanticsLabel ==
                            EnvironmentBanner.headlineFor('synthetic'),
                  );
            expect(contextControl.hitTestable(), findsOneWidget);
            await tester.tap(contextControl);
            await tester.pumpAndSettle();
            final explanation = find.textContaining(EnvironmentBanner.detail);
            expect(explanation.hitTestable(), findsOneWidget);
            final ({double ratio, int ground, int run}) pair =
                await measurePair(tester, tester.getRect(explanation));
            debugPrint(
              'BANDROW|queue|$window|$mode|fill=${hexOf(pair.ground)}'
              '|run=${hexOf(pair.run)}|ratio=${pair.ratio.toStringAsFixed(2)}',
            );
            expect(
              pair.ratio,
              greaterThanOrEqualTo(bandPairFloor),
              reason:
                  'the environment explanation reached from the current contextual '
                  'control must retain AA body-text contrast in rendered pixels',
            );
          },
        );
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
          try {
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
            expect(
              contrast,
              'pass',
              reason:
                  '$screen at $window failed the rendered WCAG AA text '
                  'contrast guideline. A token pair alone is not a pixel result.',
            );
          } finally {
            stopCapturingLayoutErrors();
            handle.dispose();
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
