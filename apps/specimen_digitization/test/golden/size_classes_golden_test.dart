// Size-class goldens (north star, "Adaptation"; responsive and platform
// adaptation, section 8; accessibility, section 4.1).
//
// Every screen a reviewer can reach, at the four windows that select the four
// size classes, in both themes, and the two screens that carry the most text
// also at 200 percent text scale. A golden is evidence, not a rubber stamp:
// the verification report records what was seen in each PNG.
//
// The captures are of `SpecimenDigitizationApp`, so each one includes the
// shell that surrounds the screen, which is where the navigation pattern per
// size class actually lives.

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';

import 'golden_harness.dart';

/// Runs [body] once per window and theme.
void forEachWindowAndTheme(
  void Function(String window, Size size, String theme, Brightness brightness)
  body,
) {
  goldenWindows.forEach((String window, Size size) {
    goldenThemes.forEach((String theme, Brightness brightness) {
      body(window, size, theme, brightness);
    });
  });
}

/// The suffix a text scale contributes to a golden's name.
String scaleTag(double scale) => 'text${scale.toStringAsFixed(1)}';

/// The record screens that still lay out past the window they were given.
///
/// Finding V-1 in `design/08-verification-report.md`. The pinned source pane
/// is given a floor of [pinnedSourceMinHeight], 160, which is below the
/// height of its own fixed rows, so when the record header and the decision
/// bar leave it no more than that it draws its overflow stripe and the
/// photograph disappears. At 200 percent text the same thing happens at every
/// width, which is pass criterion 8.5 failing.
///
/// This list is a backlog, not a permission: an overflow that is not in it
/// fails the test, and an entry that stops overflowing fails it too, so the
/// list can only shrink and only on purpose. The goldens themselves show what
/// each entry looks like.
final Set<String> knownWorkbenchOverflows = <String>{
  for (final String segment in <String>['readings', 'fields', 'history']) ...{
    // Compact, at both text scales: the photograph is gone at 100 percent
    // already, because the header and the decision bar take the room first.
    'workbench-${segment}__compact-390x844__light__text1.0',
    'workbench-${segment}__compact-390x844__dark__text1.0',
    'workbench-${segment}__compact-390x844__light__text2.0',
    'workbench-${segment}__compact-390x844__dark__text2.0',
    // Every other width, at 200 percent text only.
    'workbench-${segment}__medium-768x1024__light__text2.0',
    'workbench-${segment}__medium-768x1024__dark__text2.0',
    'workbench-${segment}__expanded-1180x820__light__text2.0',
    'workbench-${segment}__expanded-1180x820__dark__text2.0',
    'workbench-${segment}__large-1440x900__light__text2.0',
    'workbench-${segment}__large-1440x900__dark__text2.0',
  },
};

/// The errors the frames of the current test reported.
///
/// Collected rather than thrown, because `flutter_test` folds a second and
/// later exception into one "multiple exceptions were detected" summary that
/// no longer says what any of them was, and an overflow is reported once per
/// frame. Every error is still inspected below: anything that is not an
/// overflow fails the test.
List<String> capturedLayoutErrors = <String>[];

/// Starts collecting this test's layout errors, and stops at the end of it.
void captureLayoutErrors() {
  final FlutterExceptionHandler? previous = FlutterError.onError;
  capturedLayoutErrors = <String>[];
  FlutterError.onError = (FlutterErrorDetails details) =>
      capturedLayoutErrors.add(details.exceptionAsString());
  addTearDown(() => FlutterError.onError = previous);
}

/// Asserts that [name] overflowed exactly when the backlog says it does.
void expectKnownOverflow(WidgetTester tester, String name) {
  final List<String> errors = capturedLayoutErrors;
  final bool overflowed = errors.any(
    (String error) => error.contains('overflowed by'),
  );
  final Iterable<String> other = errors.where(
    (String error) => !error.contains('overflowed by'),
  );
  expect(
    other,
    isEmpty,
    reason: 'a golden must not be captured from a broken frame',
  );
  if (knownWorkbenchOverflows.contains(name)) {
    expect(
      overflowed,
      isTrue,
      reason:
          '$name is listed as a known overflow but did not overflow. If that '
          'is a fix, take it out of knownWorkbenchOverflows in the same '
          'change.',
    );
  } else {
    expect(
      overflowed,
      isFalse,
      reason:
          '$name overflowed its window. Look at the golden: content that '
          'cannot be seen is pass criterion 8.5 failing.',
    );
  }
}

void main() {
  // No golden reaches the platform preference store.
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('sign in', () {
    forEachWindowAndTheme((
      String window,
      Size size,
      String theme,
      Brightness brightness,
    ) {
      testWidgets('sign in at $window in $theme', (WidgetTester tester) async {
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: brightness,
          signedIn: false,
        );
        await expectGolden(tester, 'signin__${window}__$theme');
      });
    });
  });

  group('queue', () {
    forEachWindowAndTheme((
      String window,
      Size size,
      String theme,
      Brightness brightness,
    ) {
      testWidgets('queue at $window in $theme', (WidgetTester tester) async {
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: brightness,
          location: goldenQueueLocation,
        );
        await expectGolden(tester, 'queue__${window}__$theme');
      });
    });
  });

  group('filters', () {
    forEachWindowAndTheme((
      String window,
      Size size,
      String theme,
      Brightness brightness,
    ) {
      testWidgets('filters at $window in $theme', (WidgetTester tester) async {
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: brightness,
          location: goldenQueueLocation,
        );
        // The filter surface is a bottom sheet on a compact window and a
        // constrained dialog above it, which is the adaptation this golden
        // exists to show.
        await tester.tap(find.widgetWithText(OutlinedButton, 'Filters'));
        await tester.pumpAndSettle();
        expect(find.text('Filter the queue'), findsOneWidget);
        await expectGolden(tester, 'filters__${window}__$theme');
      });
    });
  });

  group('intake', () {
    for (final double scale in <double>[1.0, 2.0]) {
      forEachWindowAndTheme((
        String window,
        Size size,
        String theme,
        Brightness brightness,
      ) {
        testWidgets('intake at $window in $theme at ${scaleTag(scale)}', (
          WidgetTester tester,
        ) async {
          await pumpGoldenApp(
            tester,
            window: size,
            brightness: brightness,
            textScale: scale,
            location: goldenIntakeLocation,
          );
          await expectGolden(
            tester,
            'intake__${window}__${theme}__${scaleTag(scale)}',
          );
        });
      });
    }
  });

  group('workbench', () {
    for (final WorkbenchSegment segment in WorkbenchSegment.values) {
      for (final double scale in <double>[1.0, 2.0]) {
        forEachWindowAndTheme((
          String window,
          Size size,
          String theme,
          Brightness brightness,
        ) {
          final String name = segment.name;
          testWidgets(
            'workbench $name at $window in $theme at ${scaleTag(scale)}',
            (WidgetTester tester) async {
              captureLayoutErrors();
              await pumpGoldenApp(
                tester,
                window: size,
                brightness: brightness,
                textScale: scale,
                location: goldenSpecimenLocation,
              );
              // History leaves the selector once it has a pane of its own, so
              // on a large window the History golden is the persistent pane
              // rather than a third segment.
              //
              // Scoped to the selector, and scrolled into view first: the
              // segment word also appears in the help sheet and in the
              // history pane's own heading, and an unscoped finder at 200
              // percent text taps whatever happens to sit under the first
              // match instead.
              final Finder tab = find
                  .descendant(
                    of: find.byType(SegmentedButton<WorkbenchSegment>),
                    matching: find.text(segment.label),
                  )
                  .first;
              if (tab.evaluate().isNotEmpty) {
                await tester.ensureVisible(tab);
                await tester.pumpAndSettle();
                await tester.tap(tab);
                await tester.pumpAndSettle();
                await settleImages(tester);
              }
              // A golden of the record must be a golden of the record, not of
              // a dialog a stray tap opened over it.
              expect(
                find.byType(Dialog),
                findsNothing,
                reason: 'the segment tap must not open a route',
              );
              final String golden =
                  'workbench-$name'
                  '__${window}__${theme}__${scaleTag(scale)}';
              expectKnownOverflow(tester, golden);
              await expectGolden(tester, golden);
            },
          );
        });
      }
    }
  });

  group('region editor', () {
    forEachWindowAndTheme((
      String window,
      Size size,
      String theme,
      Brightness brightness,
    ) {
      testWidgets('region editor at $window in $theme', (
        WidgetTester tester,
      ) async {
        // Opened directly rather than through the record, because the record
        // fixture carries an original whose orientation is unverified and the
        // workbench correctly refuses region correction on one of those. The
        // editor still has to be laid out at every width, so it is pumped on
        // the product theme the way the app opens it.
        await pumpGoldenDialog(
          tester,
          window: size,
          brightness: brightness,
          dialog: RegionEditor(
            regions: goldenRegions,
            asset: goldenEditableAsset(),
          ),
        );
        expect(find.byType(RegionEditor), findsOneWidget);
        await expectGoldenFinder(
          tester,
          find.byType(MaterialApp),
          'region-editor__${window}__$theme',
        );
      });
    });
  });

  group('help', () {
    testWidgets('the help and shortcut list at a compact window', (
      WidgetTester tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: goldenWindows['compact-390x844']!,
        brightness: Brightness.light,
        location: AppRoutes.help,
      );
      await expectGolden(tester, 'help__compact-390x844__light');
    });
  });
}
