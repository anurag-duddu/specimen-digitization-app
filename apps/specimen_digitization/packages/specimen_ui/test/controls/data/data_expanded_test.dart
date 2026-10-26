import 'dart:async';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'composer sends with keyboard, preserves failed and concurrent drafts',
    (tester) async {
      final controller = TextEditingController(text: 'Original draft');
      addTearDown(controller.dispose);
      var pending = Completer<void>();
      final sent = <String>[];
      await tester.pumpWidget(
        uiHarness(
          child: UiMessageComposer(
            controller: controller,
            onSend: (text) {
              sent.add(text);
              return pending.future;
            },
          ),
        ),
      );
      await tester.tap(find.byType(EditableText));
      await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pump();
      expect(sent, ['Original draft']);
      pending.completeError(StateError('Synthetic failure'));
      await tester.pump();
      expect(controller.text, 'Original draft');
      expect(
        find.text('Could not send. Your draft is preserved.'),
        findsOneWidget,
      );
      pending = Completer<void>();
      await tester.tap(find.text('Send message'));
      await tester.pump();
      controller.text = 'New draft while sending';
      pending.complete();
      await tester.pump();
      expect(controller.text, 'New draft while sending');
      pending = Completer<void>();
      await tester.tap(find.text('Send message'));
      await tester.pump();
      pending.complete();
      await tester.pump();
      expect(controller.text, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'attachment, reaction and row actions call only their host callbacks',
    (tester) async {
      var opened = 0, reacted = 0, removed = 0;
      await tester.pumpWidget(
        uiHarness(
          child: SingleChildScrollView(
            child: Column(
              children: [
                UiMessage(
                  author: 'Alex',
                  body: '',
                  timeLabel: '10:42',
                  attachments: [
                    UiMessageAttachment(
                      name: 'Label.jpg',
                      detail: 'JPEG · 2 MB',
                      onOpen: () => opened++,
                    ),
                  ],
                  reactions: [
                    UiMessageReaction(
                      label: 'Helpful',
                      count: 0,
                      onPressed: () => reacted++,
                    ),
                  ],
                ),
                UiTableActions(
                  rowLabel: 'EXAMPLE-001',
                  actions: [
                    UiTableAction(label: 'Remove', onPressed: () => removed++),
                    const UiTableAction(label: 'Edit'),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open Label.jpg'));
      await tester.tap(find.text('Helpful 0'));
      await tester.tap(find.text('Remove'));
      await tester.tap(find.text('Edit'));
      expect([opened, reacted, removed], [1, 1, 1]);
    },
  );

  testWidgets('carousel RTL keyboard and touch request controlled positions', (
    tester,
  ) async {
    final requests = <int>[];
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        child: UiCarousel(
          index: 1,
          onChanged: requests.add,
          children: const [Text('First'), Text('Second'), Text('Third')],
        ),
      ),
    );
    final element = tester.element(find.byType(UiCarousel));
    FocusScope.of(element).nextFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    expect(requests, [2]);
    expect(find.text('Second'), findsOneWidget);
    await tester.drag(find.byType(AspectRatio), const Offset(150, 0));
    expect(requests.last, 2);
    await tester.sendKeyEvent(LogicalKeyboardKey.home);
    expect(requests.last, 0);
  });

  testWidgets(
    'chart preserves zero and missing values and rejects invalid radial data',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        uiHarness(
          child: const SingleChildScrollView(
            child: UiDataVisualization(
              label: 'Counts',
              series: [
                UiChartSeries(
                  label: 'Published',
                  data: [
                    UiChartDatum(label: 'Mon', value: 0),
                    UiChartDatum(label: 'Tue', value: null),
                    UiChartDatum(label: 'Wed', value: double.nan),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      expect(find.bySemanticsLabel('Published, Mon: 0'), findsOneWidget);
      expect(
        find.bySemanticsLabel('Published, Tue: Not measured'),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel('Published, Wed: Not measured'),
        findsOneWidget,
      );
      await tester.pumpWidget(
        uiHarness(
          child: const UiDataVisualization(
            label: 'Invalid pie',
            kind: UiDataVisualizationKind.pie,
            series: [
              UiChartSeries(
                label: 'A',
                data: [UiChartDatum(label: 'Mon', value: -1)],
              ),
            ],
          ),
        ),
      );
      expect(
        find.text('This chart requires nonnegative measurements.'),
        findsOneWidget,
      );
      await tester.pumpWidget(
        uiHarness(
          child: const UiDataVisualization(
            label: 'Invalid gauge',
            kind: UiDataVisualizationKind.gauge,
            series: [
              UiChartSeries(
                label: 'A',
                data: [UiChartDatum(label: 'Mon', value: 120)],
              ),
            ],
          ),
        ),
      );
      expect(
        find.text(
          'Gauge values must be between zero and the maximum, with one value per ring.',
        ),
        findsOneWidget,
      );
      semantics.dispose();
    },
  );

  testWidgets('new data layouts render at 320 with text 2 dark RTL', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    const series = [
      UiChartSeries(
        label: 'Reviewed',
        data: [
          UiChartDatum(label: 'Jan', value: 0),
          UiChartDatum(label: 'Feb', value: 12),
          UiChartDatum(label: 'Mar', value: 6),
        ],
      ),
    ];
    final cases = <Widget>[
      for (final kind in UiDataVisualizationKind.values)
        UiDataVisualization(
          label: 'Specimens reviewed',
          series: kind == UiDataVisualizationKind.gauge
              ? const [
                  UiChartSeries(
                    label: 'Reviewed',
                    data: [UiChartDatum(label: 'Progress', value: 55)],
                  ),
                ]
              : series,
          kind: kind,
          xAxisLabel: 'Month',
          yAxisLabel: 'Count',
          legend: UiChartLegend.end,
        ),
      for (final style in UiStepsStyle.values)
        UiSteps(
          style: style,
          steps: [
            UiStep(
              label: 'Photograph',
              state: UiStepState.complete,
              onSelected: () {},
            ),
            const UiStep(label: 'Transcribe', state: UiStepState.current),
            const UiStep(label: 'Publish'),
          ],
        ),
      for (final style in UiBreadcrumbStyle.values)
        UiBreadcrumbs(
          style: style,
          divider: UiBreadcrumbDivider.slash,
          items: [
            UiBreadcrumb(
              label: 'Collections with long names',
              icon: UiIcons.sources,
              onSelected: () {},
            ),
            const UiBreadcrumb(label: 'EXAMPLE-001'),
          ],
        ),
      UiPageHeader(
        title: 'Museum collection header',
        supporting: 'Long supporting information remains available.',
        centered: true,
        identity: const UiAvatar(name: 'Alex Morgan'),
        actions: [UiButton(label: 'Add collection', onPressed: () {})],
      ),
      UiInlineCta(
        title: 'Import collection records',
        supporting: 'Choose a source to continue.',
        media: const UiIcon(UiIcons.sources, size: UiIconSize.display),
        content: const UiField(label: 'Collection email'),
        actions: [UiButton(label: 'Continue', onPressed: () {})],
      ),
      UiContentFooter(
        supporting: 'No changes saved yet',
        actions: [
          UiButton(label: 'Cancel', onPressed: () {}),
          UiButton(label: 'Save changes', onPressed: () {}),
        ],
      ),
      UiActivityFeed(
        divider: UiActivityDivider.connector,
        entries: [
          UiActivityEntry(
            title: 'Corrected original locality wording',
            timeLabel: 'Today 10:42',
            actor: 'Alex Morgan',
            unread: true,
            supporting: const Text('Original label attachment'),
            actions: [UiButton(label: 'Review event', onPressed: () {})],
          ),
          const UiActivityEntry(
            title: 'Imported record',
            timeLabel: 'Today 10:00',
          ),
        ],
      ),
      const UiLoadingState(
        label: 'Loading collection metadata',
        supporting: 'Waiting for response',
        inline: true,
      ),
      const UiMetricCard(
        label: 'Published specimens',
        value: 'Not measured',
        supporting: 'No measurement available',
      ),
      const UiCodeSnippet(
        code: '{\n  "catalogNumber": "EXAMPLE-001"\n}',
        label: 'Example JSON',
        lineNumbers: true,
        theme: UiCodeTheme.light,
        tone: UiCodeTone.brand,
      ),
    ];
    for (final (i, child) in cases.indexed) {
      await tester.pumpWidget(
        uiHarness(
          brightness: Brightness.dark,
          textScaler: const TextScaler.linear(2),
          textDirection: TextDirection.rtl,
          disableAnimations: true,
          size: const Size(320, 900),
          child: SingleChildScrollView(
            child: Padding(padding: const EdgeInsets.all(16), child: child),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 200));
      expect(
        tester.takeException(),
        isNull,
        reason: 'Case $i: ${child.runtimeType}',
      );
    }
  });

  testWidgets(
    'rating preserves null, zero and fractions and edits with RTL keys',
    (tester) async {
      final semantics = tester.ensureSemantics();
      final values = <double?>[];
      await tester.pumpWidget(
        uiHarness(
          textDirection: TextDirection.rtl,
          child: UiRating(
            label: 'Image quality',
            value: 3.5,
            onChanged: values.add,
          ),
        ),
      );
      expect(find.bySemanticsLabel('Image quality'), findsOneWidget);
      expect(find.text('3.5 of 5'), findsOneWidget);
      final thirdStar = find.byWidgetPredicate(
        (widget) =>
            widget is Pressable &&
            widget.semanticsLabel == 'Image quality, 3 of 5',
      );
      await tester.tap(thirdStar);
      await tester.pump();
      expect(values, [3]);
      expect(
        find.text('3.5 of 5'),
        findsOneWidget,
        reason: 'Only the host can commit a requested value.',
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      expect(values.last, 3);
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      expect(values.last, 4);
      await tester.sendKeyEvent(LogicalKeyboardKey.home);
      expect(values.last, 0);
      await tester.sendKeyEvent(LogicalKeyboardKey.end);
      expect(values.last, 5);
      await tester.sendKeyEvent(LogicalKeyboardKey.delete);
      expect(values.last, isNull);
      await tester.pumpWidget(
        uiHarness(child: const UiRating(label: 'Image quality', value: 0)),
      );
      expect(find.text('0 of 5'), findsOneWidget);
      await tester.pumpWidget(
        uiHarness(child: const UiRating(label: 'Image quality', value: null)),
      );
      expect(find.text('Not rated'), findsOneWidget);
      semantics.dispose();
    },
  );

  testWidgets(
    'disabled rating rejects pointer input and overflow row actions execute',
    (tester) async {
      final values = <double?>[];
      await tester.pumpWidget(
        uiHarness(
          child: UiRating(
            label: 'Image quality',
            value: 2,
            enabled: false,
            onChanged: values.add,
          ),
        ),
      );
      await tester.tap(
        find.byWidgetPredicate(
          (widget) =>
              widget is Pressable &&
              widget.semanticsLabel == 'Image quality, 5 of 5',
        ),
      );
      await tester.pump();
      expect(values, isEmpty);
      var opened = 0;
      await tester.pumpWidget(
        uiHarness(
          child: UiTableActions(
            rowLabel: 'EXAMPLE-001',
            presentation: UiTableActionsPresentation.menu,
            actions: [
              UiTableAction(
                label: 'Open record',
                icon: UiIcons.record,
                onPressed: () => opened++,
              ),
            ],
          ),
        ),
      );
      await tester.tap(find.byType(UiMenuTrigger));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Open record'));
      await tester.pumpAndSettle();
      expect(opened, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('radar category keys wrap long names outside every plot size', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final semantics = tester.ensureSemantics();
    const labels = [
      'Geographic location evidence and historical collection locality precision',
      'Taxonomic authority resolution and current accepted identification',
      'Collector attribution and original source transcription completeness',
    ];
    for (final size in UiChartSize.values) {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 900),
          textScaler: const TextScaler.linear(2),
          textDirection: TextDirection.rtl,
          child: SingleChildScrollView(
            child: UiDataVisualization(
              label: 'Collection completeness',
              kind: UiDataVisualizationKind.radar,
              size: size,
              series: [
                UiChartSeries(
                  label: 'Reviewed',
                  data: [
                    for (final (index, label) in labels.indexed)
                      UiChartDatum(label: label, value: (index + 1) * 10),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      expect(find.text('1. ${labels.first}'), findsOneWidget);
      expect(
        find.bySemanticsLabel('Reviewed, ${labels.first}: 10'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull, reason: size.name);
    }
    semantics.dispose();
  });

  testWidgets(
    'old composer completion cannot clear or unlock a new conversation',
    (tester) async {
      final first = TextEditingController(text: 'First draft');
      final second = TextEditingController(text: 'Second draft');
      addTearDown(first.dispose);
      addTearDown(second.dispose);
      final oldPending = Completer<void>();
      final newPending = Completer<void>();
      await tester.pumpWidget(
        uiHarness(
          child: UiMessageComposer(
            controller: first,
            onSend: (_) => oldPending.future,
          ),
        ),
      );
      await tester.tap(find.text('Send message'));
      await tester.pump();
      await tester.pumpWidget(
        uiHarness(
          child: UiMessageComposer(
            controller: second,
            onSend: (_) => newPending.future,
          ),
        ),
      );
      final sendFinder = find.byWidgetPredicate(
        (widget) => widget is UiButton && widget.label == 'Send message',
      );
      expect(tester.widget<UiButton>(sendFinder).loading, isFalse);
      await tester.tap(find.text('Send message'));
      await tester.pump();
      expect(tester.widget<UiButton>(sendFinder).loading, isTrue);
      oldPending.completeError(StateError('Stale conversation failed'));
      await tester.pump();
      expect(second.text, 'Second draft');
      expect(
        find.text('Could not send. Your draft is preserved.'),
        findsNothing,
      );
      expect(tester.widget<UiButton>(sendFinder).loading, isTrue);
      expect(tester.widget<UiButton>(sendFinder).onPressed, isNull);
      newPending.complete();
      await tester.pump();
      expect(second.text, isEmpty);
      expect(first.text, 'First draft');
      expect(tester.widget<UiButton>(sendFinder).loading, isFalse);
      expect(tester.takeException(), isNull);
    },
  );
}
