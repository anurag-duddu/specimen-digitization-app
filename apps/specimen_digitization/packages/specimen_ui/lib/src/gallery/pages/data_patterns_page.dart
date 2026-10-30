/// Interactive, synthetic examples of composed data patterns.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// The composed data-pattern catalog entry.
const GalleryPage dataPatternsPage = GalleryPage(
  id: 'data-patterns',
  title: 'Data patterns',
  summary:
      'Headers, sortable tables, selection, pagination and accessible charts. Synthetic examples.',
  builder: buildDataPatternsPage,
  maxGlassPanes: 0,
);

/// Builds the interactive data-pattern catalog.
Widget buildDataPatternsPage(BuildContext context) =>
    const UiDataPatternsPage();

/// A local example with real sorting, filtering and page-selection behavior.
class UiDataPatternsPage extends StatefulWidget {
  /// Creates the gallery's synthetic data examples.
  const UiDataPatternsPage({super.key});

  @override
  State<UiDataPatternsPage> createState() => _UiDataPatternsPageState();
}

class _Specimen {
  const _Specimen(this.catalogue, this.name, this.collection, this.images);

  final String catalogue;
  final String name;
  final String collection;
  final int images;
}

class _UiDataPatternsPageState extends State<UiDataPatternsPage> {
  static const List<_Specimen> _records = <_Specimen>[
    _Specimen('DEMO-0041', 'Danaus plexippus', 'Insects', 4),
    _Specimen('DEMO-0042', 'Quercus alba', 'Botany', 2),
    _Specimen('DEMO-0043', 'Papilio polyxenes', 'Insects', 3),
    _Specimen('DEMO-0044', 'Acer saccharum', 'Botany', 2),
    _Specimen('DEMO-0045', 'Ginkgo biloba', 'Botany', 5),
    _Specimen('DEMO-0046', 'Apis mellifera', 'Insects', 1),
    _Specimen('DEMO-0047', 'Salix nigra', 'Botany', 3),
  ];
  static const int _pageSize = 3;

  int _page = 1;
  String _query = '';
  String _state = 'data';
  String _sort = 'catalogue';
  UiSortDirection _direction = UiSortDirection.ascending;
  Set<Object> _selection = <Object>{};
  UiChartKind _chart = UiChartKind.bars;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<_Specimen> results = _records
        .where(
          (_Specimen record) =>
              '${record.catalogue} ${record.name} ${record.collection}'
                  .toLowerCase()
                  .contains(_query.toLowerCase()),
        )
        .toList();
    results.sort((_Specimen a, _Specimen b) {
      final int comparison = switch (_sort) {
        'name' => a.name.compareTo(b.name),
        'images' => a.images.compareTo(b.images),
        _ => a.catalogue.compareTo(b.catalogue),
      };
      return _direction == UiSortDirection.ascending ? comparison : -comparison;
    });
    final int pages = (results.length / _pageSize).ceil();
    final int page = pages == 0 ? 0 : math.min(_page, pages);
    final List<_Specimen> visible = page == 0
        ? <_Specimen>[]
        : results.skip((page - 1) * _pageSize).take(_pageSize).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        const UiSectionHeader(
          title: 'Data that stays legible',
          role: UiSectionHeaderRole.page,
          supporting:
              'Synthetic specimen data. Sort, search, select rows and change pages; no production data is connected.',
        ),
        SizedBox(height: ui.space.s6),
        UiSegmented<String>(
          label: 'Table state',
          value: _state,
          onChanged: (String value) => setState(() => _state = value),
          segments: const <UiSegment<String>>[
            UiSegment(value: 'data', label: 'Data'),
            UiSegment(value: 'loading', label: 'Loading'),
            UiSegment(value: 'empty', label: 'Empty'),
            UiSegment(value: 'error', label: 'Error'),
          ],
        ),
        SizedBox(height: ui.space.s4),
        UiDataTable<_Specimen>(
          label: 'Synthetic specimen records',
          header: UiSectionHeader(
            title: 'Specimen records',
            role: UiSectionHeaderRole.card,
            supporting: '${_selection.length} selected across all pages',
            meta: Text(
              '${results.length} records',
              style: ui.type.labelSmall.copyWith(color: ui.color.inkSecondary),
            ),
            actions: <Widget>[
              UiButton(
                label: 'Clear selection',
                variant: UiButtonVariant.secondary,
                onPressed: _selection.isEmpty
                    ? null
                    : () => setState(() => _selection = <Object>{}),
              ),
            ],
          ),
          toolbar: UiSearchField(
            label: 'Search synthetic records',
            clearLabel: 'Clear record search',
            hintText: 'Catalogue, taxon or collection',
            onChanged: (String value) => setState(() {
              _query = value;
              _page = 1;
            }),
          ),
          columns: <UiDataColumn<_Specimen>>[
            UiDataColumn<_Specimen>(
              id: 'catalogue',
              label: 'Catalogue',
              sortable: true,
              semanticValue: (_Specimen record) => record.catalogue,
              cellBuilder: (BuildContext context, _Specimen record) =>
                  Text(record.catalogue, style: ui.type.mono.identifier),
            ),
            UiDataColumn<_Specimen>(
              id: 'name',
              label: 'Taxon',
              flex: 2,
              sortable: true,
              semanticValue: (_Specimen record) =>
                  '${record.name}, ${record.collection}',
              cellBuilder: (BuildContext context, _Specimen record) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(record.name),
                  Text(
                    record.collection,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ],
              ),
            ),
            UiDataColumn<_Specimen>(
              id: 'images',
              label: 'Images',
              numeric: true,
              sortable: true,
              semanticValue: (_Specimen record) => '${record.images}',
              cellBuilder: (BuildContext context, _Specimen record) =>
                  Text('${record.images}', style: ui.type.mono.identifier),
            ),
          ],
          rows: _state == 'empty'
              ? <UiDataRow<_Specimen>>[]
              : <UiDataRow<_Specimen>>[
                  for (final _Specimen record in visible)
                    UiDataRow(
                      id: record.catalogue,
                      value: record,
                      label: record.catalogue,
                    ),
                ],
          sortColumnId: _sort,
          sortDirection: _direction,
          onSort: (String column, UiSortDirection direction) => setState(() {
            _sort = column;
            _direction = direction;
          }),
          selectedIds: _selection,
          onSelectionChanged: (Set<Object> value) =>
              setState(() => _selection = value),
          loading: _state == 'loading',
          error: _state == 'error'
              ? UiEmptyState(
                  icon: UiIcons.error,
                  title: 'Records could not load',
                  body:
                      'This is an example error. Retry restores the local sample.',
                  action: UiButton(
                    label: 'Retry loading',
                    leading: UiIcons.retry,
                    onPressed: () => setState(() => _state = 'data'),
                  ),
                )
              : null,
          footer: UiPagination(
            page: _state == 'empty' ? 0 : page,
            pageCount: _state == 'empty' ? 0 : pages,
            busy: _state == 'loading',
            onChanged: _state == 'error'
                ? null
                : (int value) => setState(() => _page = value),
          ),
        ),
        SizedBox(height: ui.space.s8),
        UiSectionHeader(
          title: 'Measured values, always visible',
          supporting:
              'One brand hue. Missing observations remain missing; zero remains zero.',
          actions: <Widget>[
            UiSegmented<UiChartKind>(
              value: _chart,
              label: 'Chart style',
              onChanged: (UiChartKind value) => setState(() => _chart = value),
              segments: const <UiSegment<UiChartKind>>[
                UiSegment(value: UiChartKind.bars, label: 'Bars'),
                UiSegment(value: UiChartKind.line, label: 'Line'),
              ],
            ),
          ],
        ),
        SizedBox(height: ui.space.s4),
        Surface(
          hairline: true,
          radius: ui.shape.tile,
          padding: EdgeInsets.all(ui.space.s6),
          child: UiChart(
            label: 'Synthetic records checked per day',
            kind: _chart,
            data: const <UiChartDatum>[
              UiChartDatum(label: 'Monday', value: 18),
              UiChartDatum(label: 'Tuesday', value: 26),
              UiChartDatum(label: 'Wednesday', value: null),
              UiChartDatum(label: 'Thursday', value: 0),
              UiChartDatum(label: 'Friday', value: 31),
            ],
          ),
        ),
      ],
    );
  }
}
