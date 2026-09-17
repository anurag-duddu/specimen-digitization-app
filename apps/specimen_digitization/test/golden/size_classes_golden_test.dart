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
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'golden_harness.dart';
import '../ui_finders.dart';

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
/// Finding V-1 in `design/08-verification-report.md` is fixed, so this set is
/// empty. It stays here because it is a gate rather than a note: an overflow
/// that is not listed fails the test, and an entry that stops overflowing
/// fails it too, so the list can only change on purpose.
final Set<String> knownWorkbenchOverflows = <String>{};

/// The errors the frames of the current test reported.
///
/// Collected rather than thrown, because `flutter_test` folds a second and
/// later exception into one "multiple exceptions were detected" summary that
/// no longer says what any of them was, and an overflow is reported once per
/// frame. Every error is still inspected below: anything that is not an
/// overflow fails the test.
List<String> capturedLayoutErrors = <String>[];

/// The handler in place before this test installed its collector.
FlutterExceptionHandler? _previousOnError;

/// Starts collecting this test's layout errors, and stops at the end of it.
void captureLayoutErrors() {
  _previousOnError = FlutterError.onError;
  capturedLayoutErrors = <String>[];
  FlutterError.onError = (FlutterErrorDetails details) =>
      capturedLayoutErrors.add(details.exceptionAsString());
  addTearDown(stopCapturingLayoutErrors);
}

/// Puts the framework's own handler back.
///
/// Called before the assertions below rather than only in the tear down: an
/// `expect` that fails while the collector is installed is swallowed by it,
/// and the binding then reports "a test overrode FlutterError.onError"
/// instead of the failure that actually happened.
void stopCapturingLayoutErrors() {
  if (_previousOnError == null) return;
  FlutterError.onError = _previousOnError;
  _previousOnError = null;
}

/// Asserts that [name] overflowed exactly when the backlog says it does.
void expectKnownOverflow(WidgetTester tester, String name) {
  stopCapturingLayoutErrors();
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
    reason: 'a golden must not be captured from a broken frame: $other',
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
          'cannot be seen is pass criterion 8.5 failing. $errors',
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
        expectGlassBudget(tester, window: window);
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
        expectGlassBudget(tester, window: window);
        await expectGolden(tester, 'queue__${window}__$theme');
      });
    });
  });

  // The queue with a live selection: the checkbox column, the count, and the
  // sentence that says how far a select all reached. The selection is the one
  // state of this screen that the plain queue golden cannot show, and it is
  // the state a bulk decision is taken from.
  group('queue with a selection', () {
    forEachWindowAndTheme((
      String window,
      Size size,
      String theme,
      Brightness brightness,
    ) {
      testWidgets('queue selection at $window in $theme', (
        WidgetTester tester,
      ) async {
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: brightness,
          location: goldenQueueLocation,
          repository: GoldenQueueRepository(goldenQueue(4)),
        );
        // A compact window has no column until a long press opens one, which
        // is the adaptation this golden exists to show alongside the wider
        // ones. The long press also selects the row it was on
        // (`queue_screen.dart`, `onLongPress`), so the selection already
        // exists there; tapping a checkbox afterwards would undo it and leave
        // the bar with nothing to show.
        final Finder rowBoxes = find.descendant(
          of: find.byType(SelectableRow),
          matching: find.byType(UiCheckbox),
        );
        if (rowBoxes.evaluate().isEmpty) {
          await tester.longPress(find.text('Pinned beetle 1'));
          await tester.pumpAndSettle();
        } else {
          await tester.tap(rowBoxes.first);
          await tester.pumpAndSettle();
        }
        await tester.tap(find.text(SelectionBar.selectAllLabel));
        await tester.pumpAndSettle();
        expect(find.text('4 records selected'), findsOneWidget);
        expectGlassBudget(tester, window: window);
        await expectGolden(tester, 'queue-selection__${window}__$theme');
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
        await tester.tap(find.text('Filters'));
        await tester.pumpAndSettle();
        expect(find.text('Filter the queue'), findsOneWidget);
        expectGlassBudget(tester, window: window);
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
          expectGlassBudget(tester, window: window);
          await expectGolden(
            tester,
            'intake__${window}__${theme}__${scaleTag(scale)}',
          );
        });
      });
    }
  });

  group('sources', () {
    forEachWindowAndTheme((
      String window,
      Size size,
      String theme,
      Brightness brightness,
    ) {
      testWidgets('source at $window in $theme', (WidgetTester tester) async {
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: brightness,
          location: goldenSourceLocation,
          repository: GoldenSourceRepository(),
        );
        // The checkbox column is open from medium up and revealed by a long
        // press below it, which is the adaptation this golden exists to show.
        expect(find.text('microscopic-slides'), findsOneWidget);
        expectGlassBudget(tester, window: window);
        await expectGolden(tester, 'source__${window}__$theme');
      });
    });
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
              // Chosen from the keyboard rather than by tapping. At 200
              // percent text on a phone the record scrolls as one, so the
              // selector's position depends on the scroll offset, and a
              // capture that had to scroll the pane to reach a control is a
              // capture of a scrolled pane. The shortcut moves the segment
              // without moving anything else, and it is the same binding the
              // keyboard walkthrough proves.
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
                expect(
                  tester
                      .widget<UiTabs>(uiTabs(evidenceTabsLabel))
                      .selected
                      .value,
                  segment.index,
                  reason: 'the golden is of the wrong segment',
                );
              }
              // Every scroll view is returned to its top before the capture.
              // Focus pulls a scroll view to the control it lands on, and
              // which control that is depends on timing, so without this the
              // same screen is captured scrolled on one run and not on the
              // next. A capture of a scrolled pane is not a capture of the
              // screen.
              for (final ScrollableState scroll
                  in tester.stateList<ScrollableState>(
                    find.byType(Scrollable),
                  )) {
                if (scroll.position.hasPixels && scroll.position.pixels != 0) {
                  scroll.position.jumpTo(0);
                }
              }
              await tester.pumpAndSettle();

              // A golden of the record must be a golden of the record, not of
              // a modal a stray tap opened over it.
              expect(
                find.byType(Scrim),
                findsNothing,
                reason: 'the segment tap must not open a route',
              );
              final String golden =
                  'workbench-$name'
                  '__${window}__${theme}__${scaleTag(scale)}';
              expectKnownOverflow(tester, golden);
              expectGlassBudget(tester, window: window);
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
        //
        // `showRegionEditor` picks the container from the window class: a
        // dialog at expanded and above, a full screen route below. The golden
        // used to pump the dialog at every width, so the compact PNG finding
        // V-7 was written against showed a container a phone never gets. It
        // now takes the same branch the app takes.
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
          expect(find.byType(RegionEditor), findsOneWidget);
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
          expect(find.byType(RegionEditorBody), findsOneWidget);
        }
        expectGlassBudget(tester, window: window);
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
      expectGlassBudget(tester, window: 'compact-390x844');
      await expectGolden(tester, 'help__compact-390x844__light');
    });
  });
}
