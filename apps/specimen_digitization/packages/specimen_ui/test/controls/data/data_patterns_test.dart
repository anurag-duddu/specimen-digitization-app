import 'dart:ui' show CheckedState, Tristate;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/src/gallery/pages/data_patterns_page.dart';

import '../../harness/control_contract.dart';

const List<UiDataRow<String>> _rows = <UiDataRow<String>>[
  UiDataRow(id: 'a', value: 'Aster', label: 'DEMO-A'),
  UiDataRow(id: 'b', value: 'Birch', label: 'DEMO-B'),
  UiDataRow(id: 'c', value: 'Cedar', label: 'DEMO-C', selectable: false),
];

List<UiDataColumn<String>> _columns({bool sortable = true}) =>
    <UiDataColumn<String>>[
      UiDataColumn<String>(
        id: 'name',
        label: 'Name',
        sortable: sortable,
        semanticValue: (String value) => value,
        cellBuilder: (BuildContext context, String value) => Text(value),
      ),
    ];

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('pagination meets the shared control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => SizedBox(
        width: 320,
        child: UiPagination(page: 1, pageCount: 2, onChanged: (int _) {}),
      ),
      semanticsLabel: 'Next page',
    );
  });

  testWidgets('table sorting meets the shared control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiDataTable<String>(
        label: 'Plants',
        columns: _columns(),
        rows: _rows,
        onSort: (String _, UiSortDirection _) {},
      ),
      semanticsLabel: 'Sort by Name',
    );
  });

  testWidgets('pagination requests changes without changing the caller state', (
    WidgetTester tester,
  ) async {
    final List<int> requested = <int>[];
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiPagination(page: 1, pageCount: 3, onChanged: requested.add),
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Previous page'));
    expect(requested, isEmpty);
    await tester.tap(find.bySemanticsLabel('Next page'));
    expect(requested, <int>[2]);
    expect(find.text('Page 1 of 3'), findsOneWidget);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiPagination(page: 3, pageCount: 3, onChanged: requested.add),
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Next page'));
    expect(requested, <int>[2]);
    await tester.tap(find.bySemanticsLabel('Previous page'));
    expect(requested, <int>[2, 2]);
    semantics.dispose();
  });

  testWidgets('pagination blocks empty, busy and disabled requests', (
    WidgetTester tester,
  ) async {
    final List<int> requested = <int>[];
    final SemanticsHandle semantics = tester.ensureSemantics();
    for (final UiPagination pagination in <UiPagination>[
      UiPagination(page: 0, pageCount: 0, onChanged: requested.add),
      UiPagination(page: 2, pageCount: 3, onChanged: requested.add, busy: true),
      const UiPagination(page: 2, pageCount: 3),
    ]) {
      await tester.pumpWidget(
        uiHarness(child: SizedBox(width: 320, child: pagination)),
      );
      for (final String label in <String>['Previous page', 'Next page']) {
        expect(
          tester
              .getSemantics(find.bySemanticsLabel(label))
              .getSemanticsData()
              .flagsCollection
              .isEnabled,
          Tristate.isFalse,
        );
        await tester.tap(find.bySemanticsLabel(label));
      }
    }
    expect(requested, isEmpty);
    semantics.dispose();
  });

  testWidgets('page numbers have current semantics and bounded ellipses', (
    WidgetTester tester,
  ) async {
    final List<int> requested = <int>[];
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: UiPagination(page: 50, pageCount: 100, onChanged: requested.add),
      ),
    );
    expect(find.text('…'), findsNWidgets(2));
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Page 50'))
          .getSemanticsData()
          .value,
      'Current page',
    );
    await tester.tap(find.bySemanticsLabel('Page 51'));
    expect(requested, <int>[51]);
    await tester.tap(find.bySemanticsLabel('Page 50'));
    expect(requested, <int>[51]);
    semantics.dispose();
  });

  testWidgets('sorting requests a direction but leaves data in caller order', (
    WidgetTester tester,
  ) async {
    final List<(String, UiSortDirection)> changes =
        <(String, UiSortDirection)>[];
    final SemanticsHandle semantics = tester.ensureSemantics();
    Widget table(UiSortDirection direction) => UiDataTable<String>(
      label: 'Plants',
      columns: _columns(),
      rows: _rows,
      sortColumnId: 'name',
      sortDirection: direction,
      onSort: (String id, UiSortDirection next) => changes.add((id, next)),
    );
    await tester.pumpWidget(uiHarness(child: table(UiSortDirection.ascending)));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    expect(changes, <(String, UiSortDirection)>[
      ('name', UiSortDirection.descending),
    ]);
    expect(
      tester.getTopLeft(find.text('Aster')).dy,
      lessThan(tester.getTopLeft(find.text('Birch')).dy),
    );
    await tester.pumpWidget(
      uiHarness(child: table(UiSortDirection.descending)),
    );
    await tester.tap(find.bySemanticsLabel('Sort by Name'));
    expect(changes.last, ('name', UiSortDirection.ascending));
    semantics.dispose();
  });

  testWidgets('selection preserves other pages and excludes disabled rows', (
    WidgetTester tester,
  ) async {
    Set<Object> selected = <Object>{'outside', 'a'};
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) =>
              UiDataTable<String>(
                label: 'Plants',
                columns: _columns(),
                rows: _rows,
                selectedIds: selected,
                onSelectionChanged: (Set<Object> value) =>
                    setState(() => selected = value),
              ),
        ),
      ),
    );
    final Finder all = find.bySemanticsLabel('Select all rows on this page');
    expect(
      tester.getSemantics(all).getSemanticsData().flagsCollection.isChecked,
      CheckedState.mixed,
    );
    await tester.tap(all);
    await tester.pump();
    expect(selected, <Object>{'outside', 'a', 'b'});
    expect(() => selected.add('mutation'), throwsUnsupportedError);
    await tester.tap(all);
    await tester.pump();
    expect(selected, <Object>{'outside'});
    await tester.tap(find.bySemanticsLabel('Select DEMO-C'));
    expect(selected, <Object>{'outside'});
    await tester.tap(find.bySemanticsLabel('Select DEMO-B'));
    await tester.pump();
    expect(selected, <Object>{'outside', 'b'});
    semantics.dispose();
  });

  testWidgets('loading and error replace stale rows but preserve composition', (
    WidgetTester tester,
  ) async {
    Widget table({
      bool loading = false,
      Widget? error,
      List<UiDataRow<String>> rows = _rows,
    }) => UiDataTable<String>(
      label: 'Plants',
      columns: _columns(),
      rows: rows,
      header: const Text('Plant collection'),
      toolbar: const Text('Filters'),
      footer: const Text('Page summary'),
      loading: loading,
      error: error,
      empty: const Text('No matching plants'),
      onSort: (String _, UiSortDirection _) {},
      onSelectionChanged: (Set<Object> _) {},
    );
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: table(loading: true)),
    );
    expect(find.text('Loading records'), findsOneWidget);
    expect(find.text('Aster'), findsNothing);
    expect(find.byType(UiCheckbox), findsNothing);
    await tester.pumpWidget(
      uiHarness(
        child: table(loading: true, error: const Text('Request failed')),
      ),
    );
    expect(find.text('Request failed'), findsOneWidget);
    expect(find.text('Loading records'), findsNothing);
    expect(find.text('Aster'), findsNothing);
    for (final String label in <String>[
      'Plant collection',
      'Filters',
      'Page summary',
    ]) {
      expect(find.text(label), findsOneWidget);
    }
    await tester.pumpWidget(
      uiHarness(child: table(rows: <UiDataRow<String>>[])),
    );
    expect(find.text('No matching plants'), findsOneWidget);
  });

  testWidgets('wide tables scroll and label each value with its column', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiDataTable<String>(
            label: 'Plants',
            rows: _rows,
            columns: <UiDataColumn<String>>[
              ..._columns(),
              UiDataColumn(
                id: 'origin',
                label: 'Collection',
                cellBuilder: (BuildContext context, String value) =>
                    const Text('Botany'),
                semanticValue: (String value) => 'Botany',
              ),
              UiDataColumn(
                id: 'evidence',
                label: 'Evidence',
                cellBuilder: (BuildContext context, String value) =>
                    const Text('Photograph available'),
              ),
            ],
          ),
        ),
      ),
    );
    expect(
      find.text('Scroll horizontally to see all columns.'),
      findsOneWidget,
    );
    expect(find.bySemanticsLabel('Name: Aster'), findsOneWidget);
    final ScrollableState scroll = tester.state(find.byType(Scrollable));
    expect(scroll.position.maxScrollExtent, greaterThan(0));
    await tester.drag(
      find.byType(SingleChildScrollView),
      const Offset(-240, 0),
    );
    await tester.pumpAndSettle();
    expect(scroll.position.pixels, greaterThan(0));
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets(
    'chart distinguishes missing, zero and signed values visibly and accessibly',
    (WidgetTester tester) async {
      final SemanticsHandle semantics = tester.ensureSemantics();
      for (final UiChartKind kind in UiChartKind.values) {
        await tester.pumpWidget(
          uiHarness(
            child: SizedBox(
              width: 320,
              child: UiChart(
                label: 'Change in records',
                kind: kind,
                data: const <UiChartDatum>[
                  UiChartDatum(label: 'Monday', value: -3),
                  UiChartDatum(label: 'Tuesday', value: null),
                  UiChartDatum(label: 'Wednesday', value: 0),
                  UiChartDatum(
                    label: 'Thursday',
                    value: 5,
                    displayValue: '5 records',
                  ),
                ],
              ),
            ),
          ),
        );
        expect(find.bySemanticsLabel('Monday: -3'), findsOneWidget);
        expect(find.bySemanticsLabel('Tuesday: Not measured'), findsOneWidget);
        expect(find.bySemanticsLabel('Wednesday: 0'), findsOneWidget);
        expect(find.text('5 records'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
      semantics.dispose();
    },
  );

  testWidgets(
    'chart renders empty, all-zero, huge and nonfinite data without false measurements',
    (WidgetTester tester) async {
      for (final List<UiChartDatum> data in <List<UiChartDatum>>[
        <UiChartDatum>[],
        <UiChartDatum>[const UiChartDatum(label: 'Zero', value: 0)],
        <UiChartDatum>[
          const UiChartDatum(label: 'High', value: 1.7e308),
          const UiChartDatum(label: 'Low', value: -1.7e308),
        ],
        <UiChartDatum>[
          const UiChartDatum(label: 'Unknown', value: double.nan),
          const UiChartDatum(label: 'Infinite', value: double.infinity),
        ],
      ]) {
        await tester.pumpWidget(
          uiHarness(
            child: SizedBox(
              width: 320,
              child: UiChart(label: 'Records', data: data),
            ),
          ),
        );
        expect(tester.takeException(), isNull);
        if (data.isEmpty) expect(find.text('No measurements'), findsOneWidget);
        if (data.any((UiChartDatum d) => !d.measured)) {
          expect(find.text('Not measured'), findsNWidgets(2));
        }
      }
    },
  );

  testWidgets(
    'horizontal tables can be scrolled with a keyboard in either direction',
    (WidgetTester tester) async {
      for (final TextDirection direction in TextDirection.values) {
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            child: SizedBox(
              width: 320,
              child: UiDataTable<String>(
                key: ValueKey<TextDirection>(direction),
                label: 'Plants',
                rows: _rows,
                columns: <UiDataColumn<String>>[
                  for (final String label in <String>[
                    'Name',
                    'Collection',
                    'Evidence',
                  ])
                    UiDataColumn(
                      id: label,
                      label: label,
                      cellBuilder: (BuildContext context, String value) =>
                          Text('$label $value'),
                    ),
                ],
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        final ScrollableState scroll = tester.state(find.byType(Scrollable));
        expect(scroll.position.pixels, 0);
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.sendKeyEvent(
          direction == TextDirection.rtl
              ? LogicalKeyboardKey.arrowLeft
              : LogicalKeyboardKey.arrowRight,
        );
        expect(scroll.position.pixels, greaterThan(0));
        await tester.sendKeyEvent(LogicalKeyboardKey.end);
        expect(scroll.position.pixels, scroll.position.maxScrollExtent);
        await tester.sendKeyEvent(LogicalKeyboardKey.home);
        expect(scroll.position.pixels, 0);
        expect(tester.takeException(), isNull);
      }
    },
  );

  testWidgets('data patterns fit width, mode, direction and 200 percent text', (
    WidgetTester tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.devicePixelRatio = 1;
    for (final double width in <double>[320, 390, 768, 1180, 1440]) {
      tester.view.physicalSize = Size(width, 1200);
      for (final Brightness brightness in Brightness.values) {
        for (final TextDirection direction in TextDirection.values) {
          for (final double scale in <double>[1, 2]) {
            await tester.pumpWidget(
              uiHarness(
                brightness: brightness,
                textDirection: direction,
                textScaler: TextScaler.linear(scale),
                size: Size(width, 1200),
                child: const SingleChildScrollView(child: UiDataPatternsPage()),
              ),
            );
            await tester.pump();
            expect(
              tester.takeException(),
              isNull,
              reason: '$width / $brightness / $direction / $scale',
            );
          }
        }
      }
    }
  });

  testWidgets('gallery search and pagination operate on local examples', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const SingleChildScrollView(child: UiDataPatternsPage()),
      ),
    );
    expect(find.text('DEMO-0041'), findsOneWidget);
    await tester.ensureVisible(find.bySemanticsLabel('Next page'));
    await tester.tap(find.bySemanticsLabel('Next page'));
    await tester.pump();
    expect(find.text('DEMO-0044'), findsOneWidget);
    await tester.enterText(find.byType(EditableText), 'Ginkgo');
    await tester.pump();
    expect(find.text('DEMO-0045'), findsOneWidget);
    expect(find.text('DEMO-0044'), findsNothing);
    semantics.dispose();
  });
}
