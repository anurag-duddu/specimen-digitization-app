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
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../app/routing_test.dart' show pumpApp;
import '../composition/composition_harness.dart'
    show nativeNavigation, contentAboveNativeNavigation;
import '../workbench_harness.dart';
import '../ui_finders.dart';
import '../reading_region_comparison_test.dart' show selectLabel;

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

  Widget host({Specimen? specimen}) => workbenchHost(
    ReviewWorkbench(
      specimen: specimen ?? record(),
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
    await selectLabel(tester, 1);

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
    state.position.jumpTo(0);
    await tester.pumpAndSettle();
    expect(state.position.pixels, 0);

    await tester.drag(evidenceScrollable(), const Offset(0, -200));
    await tester.pumpAndSettle();
    expect(
      state.position.pixels,
      greaterThan(state.position.maxScrollExtent.clamp(0, 100) / 2),
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
      await selectLabel(tester, 1);
      final ScrollableState state = tester.state<ScrollableState>(
        evidenceScrollable(),
      );
      // The pane keeps a viewport, whatever the photograph would have liked.
      // A viewport of zero is what "the screen does not scroll" looks like
      // from the inside, so this is the assertion that matters.
      expect(state.position.viewportDimension, greaterThan(0));
      expect(state.position.maxScrollExtent, greaterThan(0));
      state.position.jumpTo(0);
      await tester.pumpAndSettle();
      await tester.drag(evidenceScrollable(), const Offset(0, -160));
      await tester.pumpAndSettle();
      expect(
        state.position.pixels,
        greaterThan(state.position.maxScrollExtent.clamp(0, 80) / 2),
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('the fitted mobile photo scrolls away without changing height', (
    WidgetTester tester,
  ) async {
    useWindow(tester, compactWindow);
    // Keep enough content below the photograph to prove page scrolling
    // after Reset hands fitted-image drags back to the page.
    await tester.pumpWidget(
      host(
        specimen: Specimen({
          ...record().data,
          'regions': [
            for (var index = 1; index <= 16; index++)
              {
                'region_id': 'r$index',
                'bbox': [100, 52, 400, 212],
              },
          ],
        }),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(UiCollapsingHeader), findsNothing);
    final state = tester.state<ScrollableState>(evidenceScrollable());
    await selectLabel(tester, 1);
    state.position.jumpTo(0);
    await tester.pumpAndSettle();
    // Label selection enters image inspection; Reset returns drag ownership
    // to the page without changing the photograph's allocated height.
    await tester.tap(uiButton('Reset view'));
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsNothing);
    expect(uiButton('Reset view'), findsNothing);
    expect(tester.state<ScrollableState>(evidenceScrollable()), same(state));
    expect(state.position.maxScrollExtent, greaterThan(100));
    final before = tester.getRect(find.byType(SourceMatte));
    await tester.drag(
      find.byKey(const ValueKey('source-photo-viewport')),
      const Offset(15, -180),
    );
    await tester.pumpAndSettle();
    final after = tester.getRect(find.byType(SourceMatte));
    expect(state.position.pixels, greaterThan(100));
    expect(after.width, closeTo(before.width, .01));
    expect(after.height, closeTo(before.height, .01));
    expect(after.top, lessThan(before.top));
    state.position.jumpTo(state.position.maxScrollExtent);
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('source-photo-viewport')).hitTestable(),
      findsNothing,
    );
    await tester.pumpWidget(const SizedBox());
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
        errors,
        isEmpty,
        reason: 'enlarged-text review must not report layout or runtime errors',
      );
      expect(
        find.byKey(const ValueKey('source-photo-viewport')),
        findsOneWidget,
        reason: 'the photograph is not on the screen',
      );
      expect(
        tester
            .getSize(find.byKey(const ValueKey('source-photo-viewport')))
            .height,
        greaterThanOrEqualTo(sourceImageMinHeight - 0.5),
      );
      // The evidence pane is still reachable, which is what the whole-record
      // scroll buys at this text scale.
      expect(find.byKey(evidenceScrollKey), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'the photograph and inspection action return when the page scrolls back',
    (WidgetTester tester) async {
      useWindow(tester, compactWindow);
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();
      await selectLabel(tester, 1);
      final ScrollableState state = tester.state<ScrollableState>(
        evidenceScrollable(),
      );
      expect(state.position.maxScrollExtent, greaterThan(0));
      state.position.jumpTo(0);
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('source-photo-viewport')),
        findsOneWidget,
      );
      expect(uiIconButton('Collapse the photograph'), findsNothing);

      state.position.jumpTo(state.position.maxScrollExtent);
      await tester.pumpAndSettle();
      expect(
        state.position.pixels,
        closeTo(state.position.maxScrollExtent, .5),
      );
      expect(
        find.byKey(const ValueKey('source-photo-viewport')).hitTestable(),
        findsNothing,
      );
      expect(uiIconButton('Open photograph').hitTestable(), findsNothing);

      state.position.jumpTo(0);
      await tester.pumpAndSettle();
      expect(state.position.pixels, 0);
      expect(tester.state<ScrollableState>(evidenceScrollable()), same(state));
      expect(
        find.byKey(const ValueKey('source-photo-viewport')).hitTestable(),
        findsOneWidget,
      );
      expect(uiIconButton('Open photograph').hitTestable(), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('the decision bar never covers the end of the evidence', (
    WidgetTester tester,
  ) async {
    useWindow(tester, compactWindow);
    await tester.pumpWidget(host());
    await tester.pumpAndSettle();
    await selectLabel(tester, 1);

    final ScrollableState state = tester.state<ScrollableState>(
      evidenceScrollable(),
    );
    expect(state.position.maxScrollExtent, greaterThan(0));
    state.position.jumpTo(state.position.maxScrollExtent);
    await tester.pumpAndSettle();

    // The review column now reserves a decision row below the scrolling
    // evidence. Its measured viewport must clear the actual row.
    final Rect bar = tester.getRect(find.byType(WorkbenchDecisionBar));
    final Rect evidence = tester.getRect(find.byKey(evidenceScrollKey));
    expect(
      evidence.bottom,
      lessThanOrEqualTo(bar.top + 0.5),
      reason: 'the decision bar sits on the end of the evidence',
    );
  });
}

/// The same two assertions against the real routed application, because the
/// smoke test that found this ran the app, not a component in a scaffold.
/// The shell, the route and the back control all sit above the workbench and
/// any one of them can take the height the evidence pane needs.
void routedScrolling() {
  testWidgets(
    'the routed workbench scrolls on a phone',
    (WidgetTester tester) async {
      await pumpApp(tester, window: const Size(390, 844));
      await tester.scrollUntilVisible(
        find.text('fixture-001'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('fixture-001'));
      await tester.pumpAndSettle();

      expect(nativeNavigation(), findsOneWidget);
      final Rect navigation = tester.getRect(nativeNavigation());
      final Rect content = contentAboveNativeNavigation(tester);

      final Finder pane = find
          .descendant(
            of: find.byKey(evidenceScrollKey),
            matching: find.byType(Scrollable),
          )
          .first;
      final ScrollableState state = tester.state<ScrollableState>(pane);
      expect(state.position.maxScrollExtent, greaterThan(0));
      state.position.jumpTo(0);
      await tester.pumpAndSettle();
      expect(state.position.pixels, 0);
      await tester.drag(pane, const Offset(0, -200));
      await tester.pumpAndSettle();
      expect(
        state.position.pixels,
        greaterThan(state.position.maxScrollExtent.clamp(0, 100) / 2),
        reason: 'a swipe on the routed evidence pane moved nothing',
      );
      final Rect decision = tester.getRect(find.byType(WorkbenchDecisionBar));
      final Rect viewport = tester.getRect(find.byKey(evidenceScrollKey));
      expect(viewport.height, greaterThan(0));
      expect(viewport.bottom, lessThanOrEqualTo(decision.top + .5));
      expect(decision.bottom, lessThanOrEqualTo(content.bottom + .5));
      expect(content.bottom, navigation.top);
      expect(tester.getRect(nativeNavigation()), navigation);
      await tester.pumpWidget(const SizedBox());
    },
    variant: TargetPlatformVariant({
      TargetPlatform.iOS,
      TargetPlatform.android,
    }),
  );
}
