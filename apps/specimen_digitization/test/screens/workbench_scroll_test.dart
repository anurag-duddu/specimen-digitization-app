// The evidence pane has to scroll on a phone (smoke test defect 1), and the
// decision bar must never sit on top of the last thing in it (defect 2).
//
// Both are asserted by dragging, not by inspecting the tree: a pane that
// contains a `Scrollable` and still does not move under a finger is exactly
// the bug these tests exist to catch.

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/workbench.dart';

import '../app/routing_test.dart' show pumpApp;
import '../workbench_harness.dart';
import '../ui_finders.dart';

void main() {
  final Uint8List labelBytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();

  Specimen record() => Specimen(<String, dynamic>{
    'specimen_id': 'scroll-001',
    'display_name': 'Synthetic scrolling record',
    'revision': 4,
    'disposition': 'needs_human_review',
    'available_actions': const <String>['field', 'transcription', 'coverage'],
    'assets': <Json>[
      <String, dynamic>{
        'width': 1000,
        'height': 520,
        'preview_bytes': labelBytes,
      },
    ],
    'regions': const <Json>[
      <String, dynamic>{
        'region_id': 'r1',
        'bbox': <int>[100, 52, 400, 212],
      },
    ],
    // Enough readings that the pane is certainly taller than a phone.
    'observations': <Json>[
      for (int i = 0; i < 8; i++)
        <String, dynamic>{
          'id': 'o$i',
          'model_id': 'Reader $i',
          'provider': 'synthetic',
          'region_id': 'r1',
          'literal_text': 'Chicago 19$i$i',
        },
    ],
    'fields': const <Json>[
      <String, dynamic>{
        'field_key': 'country',
        'display_name': 'Country',
        'required': true,
        'state': 'unknown',
        'literal_value': null,
      },
    ],
    'validation_findings': const <Json>[],
  });

  Widget host() => workbenchHost(
    ReviewWorkbench(
      specimen: record(),
      onChange: (Json _) async => true,
      onRetry: (String _) async {},
      onRefresh: () {},
    ),
  );

  /// The evidence pane's own scrollable, addressed by key rather than by
  /// position: the source pane's chip strip is a scroll view too.
  Finder evidenceScrollable() => find
      .descendant(
        of: find.byKey(evidenceScrollKey),
        matching: find.byType(Scrollable),
      )
      .first;

  testWidgets('the evidence pane scrolls on a phone', (
    WidgetTester tester,
  ) async {
    useWindow(tester, compactWindow);
    await tester.pumpWidget(host());
    await tester.pumpAndSettle();

    final ScrollableState state = tester.state<ScrollableState>(
      evidenceScrollable(),
    );
    expect(
      state.position.maxScrollExtent,
      greaterThan(0),
      reason:
          'the evidence pane had nothing to scroll, so the drag below '
          'would prove nothing',
    );
    expect(state.position.pixels, 0);

    await tester.drag(evidenceScrollable(), const Offset(0, -200));
    await tester.pumpAndSettle();
    expect(
      state.position.pixels,
      greaterThan(0),
      reason: 'a swipe on the evidence pane moved nothing',
    );
  });

  routedScrolling();

  testWidgets(
    'the evidence pane still scrolls when a device takes the height back',
    (WidgetTester tester) async {
      // A phone hands the workbench far less than the window: an app bar, a
      // navigation bar, an environment band, a progress row and a gesture
      // inset all come off first. Reading the window instead of the pane is
      // what collapsed the evidence pane to nothing on a device.
      useWindow(tester, const Size(390, 560));
      await tester.pumpWidget(
        workbenchHost(
          Builder(
            builder: (BuildContext context) => MediaQuery(
              data: MediaQuery.of(context).copyWith(
                padding: const EdgeInsets.only(bottom: 48),
                viewPadding: const EdgeInsets.only(bottom: 48),
              ),
              child: ReviewWorkbench(
                specimen: record(),
                onChange: (Json _) async => true,
                onRetry: (String _) async {},
                onRefresh: () {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final ScrollableState state = tester.state<ScrollableState>(
        evidenceScrollable(),
      );
      // The pane keeps a viewport, whatever the photograph would have liked.
      // A viewport of zero is what "the screen does not scroll" looks like
      // from the inside, so this is the assertion that matters.
      expect(state.position.viewportDimension, greaterThan(0));
      expect(state.position.maxScrollExtent, greaterThan(0));
      await tester.drag(evidenceScrollable(), const Offset(0, -160));
      await tester.pumpAndSettle();
      expect(state.position.pixels, greaterThan(0));
      expect(tester.takeException(), isNull);
    },
  );

  test('the photograph never takes the evidence pane below its floor', () {
    // `free` is what is left once every fixed row has had its height: the
    // record header, the decision bar and the source pane's own chrome. What
    // this function decides is how many pixels of photograph sit inside the
    // pane, never how tall the pane itself is (finding V-1).
    //
    // Room for both: the blueprint's forty percent of the pane, outright.
    expect(pinnedSourceHeight(1000, 900), closeTo(400, 0.001));
    // The chrome has taken enough that the two cannot both be satisfied. The
    // evidence floor wins and the photograph takes the difference.
    expect(pinnedSourceHeight(1000, 500), closeTo(320, 0.001));
    // Below the height the photograph can be read at, it stops shrinking and
    // takes its minimum instead, as long as the evidence pane can still
    // scroll at its hard minimum.
    expect(pinnedSourceHeight(600, 300), sourceImageMinHeight);
    expect(pinnedSourceHeight(600, 260), sourceImageMinHeight);
    // Less room than even that: the pinned photograph goes, and the workbench
    // scrolls the whole record instead so the pixels are still on screen.
    expect(pinnedSourceHeight(600, 200), 0);
    expect(pinnedSourceHeight(600, 160), 0);
    expect(pinnedSourceHeight(600, 100), 0);
  });

  testWidgets(
    'the photograph survives 200 percent text on a phone, without an overflow',
    (WidgetTester tester) async {
      // Finding V-1, and pass criteria 6.1 and 8.5: at 200 percent text the
      // record header and the decision bar leave the pinned pane less than
      // its own chrome. It used to draw at a floor smaller than that chrome
      // and overflow, and the photograph was what disappeared.
      final List<String> errors = <String>[];
      final FlutterExceptionHandler? previous = FlutterError.onError;
      FlutterError.onError = (FlutterErrorDetails details) =>
          errors.add(details.exceptionAsString());
      addTearDown(() => FlutterError.onError = previous);

      useWindow(tester, compactWindow);
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();

      expect(
        errors.where((String e) => e.contains('overflowed by')),
        isEmpty,
        reason: 'the record laid out past the window it was given',
      );
      expect(
        find.byType(InteractiveViewer),
        findsOneWidget,
        reason: 'the photograph is not on the screen',
      );
      expect(
        tester.getSize(find.byType(InteractiveViewer)).height,
        greaterThanOrEqualTo(sourceImageMinHeight - 0.5),
      );
      // The evidence pane is still reachable, which is what the whole-record
      // scroll buys at this text scale.
      expect(find.byKey(evidenceScrollKey), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('the photograph collapses and comes back on a phone', (
    WidgetTester tester,
  ) async {
    // Blueprint 6.1: the pinned pane is collapsible, and the control that
    // brings it back is explicit rather than a second tap on the same word.
    useWindow(tester, compactWindow);
    await tester.pumpWidget(host());
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsOneWidget);

    await tester.tap(uiIconButton('Collapse the photograph'));
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsNothing);
    // With the photograph put away there is still a way to the pixels.
    expect(uiIconButton('Open the photograph full screen'), findsOneWidget);

    await tester.tap(uiIconButton('Show the photograph'));
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the decision bar never covers the end of the evidence', (
    WidgetTester tester,
  ) async {
    useWindow(tester, compactWindow);
    await tester.pumpWidget(host());
    await tester.pumpAndSettle();

    final ScrollableState state = tester.state<ScrollableState>(
      evidenceScrollable(),
    );
    state.position.jumpTo(state.position.maxScrollExtent);
    await tester.pumpAndSettle();

    // The bar is pinned below the scroll view, so the two never overlap and
    // the reviewer can reach the last row without the bar sitting on it.
    final Rect bar = tester.getRect(find.byType(WorkbenchDecisionBar));
    final Rect pane = tester.getRect(evidenceScrollable());
    expect(
      pane.bottom,
      lessThanOrEqualTo(bar.top + 0.5),
      reason: 'the decision bar overlaps the evidence pane',
    );
  });
}

/// The same two assertions against the real routed application, because the
/// smoke test that found this ran the app, not a component in a scaffold.
/// The shell, the route and the back control all sit above the workbench and
/// any one of them can take the height the evidence pane needs.
void routedScrolling() {
  testWidgets('the routed workbench scrolls on a phone', (
    WidgetTester tester,
  ) async {
    await pumpApp(tester, window: const Size(390, 844));
    await tester.scrollUntilVisible(
      find.text('Synthetic insect label'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Synthetic insect label'));
    await tester.pumpAndSettle();

    final Finder pane = find
        .descendant(
          of: find.byKey(evidenceScrollKey),
          matching: find.byType(Scrollable),
        )
        .first;
    final ScrollableState state = tester.state<ScrollableState>(pane);
    expect(state.position.maxScrollExtent, greaterThan(0));
    await tester.drag(pane, const Offset(0, -200));
    await tester.pumpAndSettle();
    expect(
      state.position.pixels,
      greaterThan(0),
      reason: 'a swipe on the routed evidence pane moved nothing',
    );
    await tester.pumpWidget(const SizedBox());
  });
}
