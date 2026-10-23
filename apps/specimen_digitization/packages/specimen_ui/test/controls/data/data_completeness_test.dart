import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'a nonsortable table heading exposes its help to keyboard focus',
    (tester) async {
      const explanation =
          'The identifier assigned when this specimen was received.';
      await tester.pumpWidget(
        uiHarness(
          child: UiDataTable<String>(
            label: 'Accession records',
            columns: [
              UiDataColumn(
                id: 'accession',
                label: 'Accession',
                helpText: explanation,
                cellBuilder: (_, value) => Text(value),
              ),
            ],
            rows: const [
              UiDataRow(id: 'one', value: 'EXAMPLE-001', label: 'EXAMPLE-001'),
            ],
          ),
        ),
      );
      expect(find.text(explanation), findsNothing);
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      expect(find.text(explanation), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(find.text(explanation), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'table help activation preserves sorting and has a close command',
    (tester) async {
      final sorts = <String>[];
      await tester.pumpWidget(
        uiHarness(
          child: UiDataTable<String>(
            label: 'Accession records',
            onSort: (id, _) => sorts.add(id),
            columns: [
              UiDataColumn(
                id: 'accession',
                label: 'Accession',
                helpText: 'The original accession identifier.',
                sortable: true,
                cellBuilder: (_, value) => Text(value),
              ),
            ],
            rows: const [
              UiDataRow(id: 'one', value: 'EXAMPLE-001', label: 'EXAMPLE-001'),
            ],
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('About Accession'));
      await tester.pumpAndSettle();
      expect(find.text('The original accession identifier.'), findsOneWidget);
      expect(sorts, isEmpty);
      await tester.tap(find.text('Close help'));
      await tester.pumpAndSettle();
      expect(find.text('Close help'), findsNothing);
      await tester.tap(find.bySemanticsLabel('Sort by Accession'));
      expect(sorts, ['accession']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('long table help stays readable in a narrow scaled RTL pane', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final explanation = List.filled(
      6,
      'This collection identifier refers to the original accession ledger.',
    ).join(' ');
    await tester.pumpWidget(
      uiHarness(
        size: const Size(320, 900),
        textScaler: const TextScaler.linear(2),
        textDirection: TextDirection.rtl,
        child: UiDataTable<String>(
          label: 'Accession records',
          columns: [
            UiDataColumn(
              id: 'accession',
              label: 'Accession',
              helpText: explanation,
              cellBuilder: (_, value) => Text(value),
            ),
          ],
          rows: const [
            UiDataRow(id: 'one', value: 'EXAMPLE-001', label: 'EXAMPLE-001'),
          ],
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('About Accession'));
    await tester.pumpAndSettle();
    expect(find.text(explanation), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.text('Close help'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Close help'));
    await tester.pumpAndSettle();
    expect(find.text('Close help'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'compact stacked chart retains extreme signed values at large text',
    (tester) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 900),
          textScaler: const TextScaler.linear(2),
          textDirection: TextDirection.rtl,
          child: SingleChildScrollView(
            child: SizedBox(
              width: 200,
              child: UiDataVisualization(
                label: 'Extreme comparison',
                kind: UiDataVisualizationKind.stackedBars,
                size: UiChartSize.xxs,
                series: [
                  for (var i = 0; i < 2; i++)
                    UiChartSeries(
                      label: 'Series $i',
                      data: const [
                        UiChartDatum(label: 'Positive', value: 1.7e308),
                        UiChartDatum(label: 'Negative', value: -1.7e308),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(find.text('Above numeric range'), findsOneWidget);
      expect(find.text('Below numeric range'), findsOneWidget);
      expect(find.text('1.7e+308'), findsNWidgets(2));
      expect(find.text('-1.7e+308'), findsNWidgets(2));
    },
  );

  testWidgets(
    'a bounded many-page carousel keeps media and controls reachable',
    (tester) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final requests = <int>[];
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 900),
          textScaler: const TextScaler.linear(2),
          textDirection: TextDirection.rtl,
          child: SizedBox(
            height: 240,
            child: UiCarousel(
              index: 0,
              onChanged: requests.add,
              children: [for (var i = 0; i < 20; i++) Text('Image ${i + 1}')],
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(tester.getSize(find.byType(AspectRatio)).height, greaterThan(0));
      await tester.tap(find.bySemanticsLabel('Next page'));
      expect(requests, [1]);
    },
  );

  testWidgets(
    'a disabled carousel does not consume its hosts navigation keys',
    (tester) async {
      var hostRequests = 0;
      await tester.pumpWidget(
        uiHarness(
          child: CallbackShortcuts(
            bindings: {
              const SingleActivator(LogicalKeyboardKey.arrowRight): () =>
                  hostRequests++,
            },
            child: UiCarousel(
              index: 0,
              children: [
                UiButton(
                  label: 'Inspect image',
                  autofocus: true,
                  onPressed: () {},
                ),
                const Text('Second image'),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      expect(hostRequests, 1);
    },
  );

  for (final direction in TextDirection.values) {
    testWidgets(
      'a bounded carousel reveals the controlled active mark $direction',
      (tester) async {
        tester.view.physicalSize = const Size(320, 900);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        var index = 0;
        await tester.pumpWidget(
          uiHarness(
            size: const Size(320, 900),
            textScaler: const TextScaler.linear(2),
            textDirection: direction,
            child: StatefulBuilder(
              builder: (context, setState) => SizedBox(
                height: 240,
                child: UiCarousel(
                  index: index,
                  onChanged: (value) => setState(() => index = value),
                  children: [
                    for (var i = 0; i < 20; i++) Text('Image ${i + 1}'),
                  ],
                ),
              ),
            ),
          ),
        );
        FocusScope.of(tester.element(find.byType(UiCarousel))).nextFocus();
        await tester.pump();
        await tester.sendKeyEvent(LogicalKeyboardKey.end);
        await tester.pumpAndSettle();
        expect(index, 19);
        expect(find.text('Image 20'), findsOneWidget);
        final viewport = tester.getRect(find.byType(UiCarousel));
        final active = tester.getRect(find.bySemanticsLabel('Page 20 of 20'));
        expect(active.left, greaterThanOrEqualTo(viewport.left));
        expect(active.right, lessThanOrEqualTo(viewport.right));
        expect(active.top, greaterThanOrEqualTo(viewport.top));
        expect(active.bottom, lessThanOrEqualTo(viewport.bottom));
        expect(tester.takeException(), isNull);
      },
    );
  }
}
