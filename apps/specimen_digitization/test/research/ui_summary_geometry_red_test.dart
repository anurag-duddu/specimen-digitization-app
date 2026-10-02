import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'probe_helpers.dart';

Future<void> pumpProbeCard(
  WidgetTester tester,
  ResearchNetworkState state, {
  double width = 640,
}) async {
  tester.view.physicalSize = Size(width, 1200);
  tester.view.devicePixelRatio = 1;
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: TextScaler.linear(2), disableAnimations: true),
          child: Scaffold(
            body: SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: ResearchThreadCard(
                  scope: probeScope(),
                  recordRevision: 100,
                  fieldKey: 'taxon',
                  fieldLabel: 'Taxon',
                  field: probeThread().field('taxon'),
                  networkState: state,
                  onRetry: () {},
                  onRefresh: () {},
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

Finder retryButton() => find.byWidgetPredicate(
  (widget) =>
      widget is UiButton && widget.semanticsLabel == 'Retry Taxon research',
);

Finder refreshButton() => find.byWidgetPredicate(
  (widget) => widget is UiButton && widget.variant == UiButtonVariant.ghost,
);

void main() {
  testWidgets('expanded status is shown and announced once', (tester) async {
    addTearDown(tester.view.reset);
    await pumpProbeCard(tester, ResearchNetworkState.ready);
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(find.text('Research interrupted'), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Text &&
            RegExp(
              r'research(?:\s+was)?\s+interrupted',
              caseSensitive: false,
            ).hasMatch(widget.data ?? widget.textSpan?.toPlainText() ?? ''),
      ),
      findsOneWidget,
      reason:
          'The interruption phase must not repeat as a differently worded blocker.',
    );
    final header = tester.widget<Semantics>(
      find.byWidgetPredicate(
        (widget) => widget is Semantics && widget.properties.expanded == true,
      ),
    );
    expect(header.properties.label, isNot(contains('Research interrupted')));
  });

  for (final width in [320.0, 640.0]) {
    testWidgets(
      'submitting uses a stable retry label and accurate refresh at $width',
      (tester) async {
        addTearDown(tester.view.reset);
        await pumpProbeCard(tester, ResearchNetworkState.ready, width: width);
        await tester.tap(find.text('Research'));
        await tester.pump();
        final initialRetry = tester.widget<UiButton>(retryButton());
        final initialRefresh = tester.widget<UiButton>(refreshButton());
        await pumpProbeCard(
          tester,
          ResearchNetworkState.submitting,
          width: width,
        );
        final pendingRetry = tester.widget<UiButton>(retryButton());
        final pendingRefresh = tester.widget<UiButton>(refreshButton());
        expect(pendingRetry.label, initialRetry.label);
        expect(initialRetry.busyLabel, isNotNull);
        expect(pendingRetry.busyLabel, initialRetry.busyLabel);
        expect(pendingRetry.loading, isTrue);
        expect(pendingRetry.onPressed, isNull);
        expect(pendingRefresh.label, initialRefresh.label);
        expect(pendingRefresh.loading, isFalse);
        expect(find.text('Loading research'), findsNothing);
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets(
      'retry and neighboring refresh retain geometry while submitting at $width',
      (tester) async {
        addTearDown(tester.view.reset);
        await pumpProbeCard(tester, ResearchNetworkState.ready, width: width);
        await tester.tap(find.text('Research'));
        await tester.pump();
        final initialRetry = tester.getRect(retryButton());
        final initialRefresh = tester.getRect(refreshButton());
        await pumpProbeCard(
          tester,
          ResearchNetworkState.submitting,
          width: width,
        );
        final pendingRetry = tester.getRect(retryButton());
        final pendingRefresh = tester.getRect(refreshButton());
        expect(pendingRetry.width, closeTo(initialRetry.width, 0.5));
        expect(pendingRetry.height, closeTo(initialRetry.height, 0.5));
        expect(pendingRefresh.width, closeTo(initialRefresh.width, 0.5));
        expect(pendingRefresh.left, closeTo(initialRefresh.left, 0.5));
        expect(pendingRefresh.top, closeTo(initialRefresh.top, 0.5));
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets('refresh reserves its loading label and geometry at $width', (
      tester,
    ) async {
      addTearDown(tester.view.reset);
      await pumpProbeCard(tester, ResearchNetworkState.ready, width: width);
      await tester.tap(find.text('Research'));
      await tester.pump();
      final initial = tester.widget<UiButton>(refreshButton());
      final initialRect = tester.getRect(refreshButton());
      await pumpProbeCard(tester, ResearchNetworkState.loading, width: width);
      final loading = tester.widget<UiButton>(refreshButton());
      final loadingRect = tester.getRect(refreshButton());
      expect(loading.label, initial.label);
      expect(initial.busyLabel, isNotNull);
      expect(loading.busyLabel, initial.busyLabel);
      expect(loading.loading, isTrue);
      expect(loading.onPressed, isNull);
      expect(loadingRect.width, closeTo(initialRect.width, 0.5));
      expect(loadingRect.height, closeTo(initialRect.height, 0.5));
      expect(tester.takeException(), isNull);
    });
  }
}
