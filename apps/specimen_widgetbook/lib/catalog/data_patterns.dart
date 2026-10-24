import 'package:flutter/widgets.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

/// Individually inspectable data components, with local synthetic state.
List<WidgetbookComponent> get dataPatternComponents => <WidgetbookComponent>[
  WidgetbookComponent(
    name: 'Section header',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Compact contextual action',
        builder: (_) => const _DataFrame(
          description:
              'A named contextual command remains beside the wrapping heading at large text sizes. The target stays 48 dp.',
          child: _CompactHeaderExample(),
        ),
      ),
      for (final avatar in [false, true])
        for (final tabs in [false, true])
          for (final command in ['Actions', 'Search', 'Button group'])
            WidgetbookUseCase(
              name:
                  '${avatar ? 'Avatar' : 'Text'} · ${tabs ? 'tabs' : 'no tabs'} · $command',
              builder: (_) => _HeaderAnatomyExample(
                avatar: avatar,
                tabs: tabs,
                command: command,
              ),
            ),
      for (final UiSectionHeaderRole role in UiSectionHeaderRole.values)
        WidgetbookUseCase(
          name: '${role.name} · title, count, supporting text and actions',
          builder: (BuildContext context) => _DataFrame(
            description:
                'Long titles wrap. Actions move below the heading in narrow allocations or at large text sizes.',
            child: _HeaderExample(role: role),
          ),
        ),
      WidgetbookUseCase(
        name: 'Long content',
        builder: (BuildContext context) => _DataFrame(
          description:
              'Heading and supporting copy remain complete at 200 percent text and in right-to-left layouts.',
          child: UiSectionHeader(
            title: context.knobs.string(
              label: 'Title',
              initialValue:
                  'Review newly digitized specimens from the entomology collection',
            ),
            supporting:
                'Resolve competing readings while preserving the original label transcription and source photographs.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Pagination',
    useCases: <WidgetbookUseCase>[
      for (final (String, int, int, bool, bool) state
          in <(String, int, int, bool, bool)>[
            ('First page', 1, 12, false, true),
            ('Middle page with ellipses', 6, 12, false, true),
            ('Last page', 12, 12, false, true),
            ('Single page', 1, 1, false, true),
            ('Empty result', 0, 0, false, true),
            ('Busy', 6, 12, true, true),
            ('Unavailable', 6, 12, false, false),
          ])
        WidgetbookUseCase(
          name: state.$1,
          builder: (BuildContext context) => _DataFrame(
            description:
                'Controlled one-based pages. Pending requests cannot be submitted twice. Narrow layouts retain Previous, page status and Next.',
            child: _PaginationExample(
              key: ValueKey<String>(state.$1),
              initialPage: state.$2,
              pageCount: state.$3,
              busy: state.$4,
              enabled: state.$5,
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'Data table',
    useCases: <WidgetbookUseCase>[
      for (final _TableState state in _TableState.values)
        WidgetbookUseCase(
          name: state.name,
          builder: (BuildContext context) => _DataFrame(
            description:
                'Synthetic rows. Sort headings with Enter or Space; page selection preserves IDs outside the current page. Wide tables scroll rather than shrinking content.',
            child: _TableExample(
              key: ValueKey<_TableState>(state),
              state: state,
            ),
          ),
        ),
      WidgetbookUseCase(
        name: 'Header, filters, table and pagination',
        builder: (BuildContext context) => const _DataFrame(
          description:
              'Complete local composition. Search, sorting, selection and pagination operate on synthetic examples only.',
          child: UiDataPatternsPage(),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Chart',
    useCases: <WidgetbookUseCase>[
      for (final UiChartKind kind in UiChartKind.values)
        WidgetbookUseCase(
          name: '${kind.name} · measured and missing observations',
          builder: (BuildContext context) => _DataFrame(
            description:
                'One Iris series with a zero baseline. Exact textual values are always visible; missing observations break the trace.',
            child: UiChart(
              label: 'Synthetic records checked per day',
              kind: kind,
              data: const <UiChartDatum>[
                UiChartDatum(label: 'Monday', value: 18),
                UiChartDatum(label: 'Tuesday', value: 26),
                UiChartDatum(label: 'Wednesday', value: null),
                UiChartDatum(label: 'Thursday', value: 0),
                UiChartDatum(label: 'Friday', value: 31),
              ],
            ),
          ),
        ),
      WidgetbookUseCase(
        name: 'Signed values',
        builder: (BuildContext context) => const _DataFrame(
          description:
              'Negative and positive values share a truthful zero baseline.',
          child: UiChart(
            label: 'Synthetic change in records',
            data: <UiChartDatum>[
              UiChartDatum(label: 'Monday', value: -4),
              UiChartDatum(label: 'Tuesday', value: 0),
              UiChartDatum(label: 'Wednesday', value: 7),
            ],
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'All zero',
        builder: (BuildContext context) => const _DataFrame(
          description:
              'Zero is measured. It is shown as zero and never confused with missing data.',
          child: UiChart(
            label: 'Synthetic daily total',
            data: <UiChartDatum>[
              UiChartDatum(label: 'Monday', value: 0),
              UiChartDatum(label: 'Tuesday', value: 0),
            ],
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Empty',
        builder: (BuildContext context) => const _DataFrame(
          description:
              'An empty series is stated explicitly, with no invented measurements.',
          child: UiChart(
            label: 'Synthetic daily total',
            data: <UiChartDatum>[],
          ),
        ),
      ),
    ],
  ),
];

class _DataFrame extends StatelessWidget {
  const _DataFrame({required this.description, required this.child});

  final String description;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SingleChildScrollView(
      child: Padding(
        padding: EdgeInsets.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(
              description,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
            SizedBox(height: ui.space.s6),
            child,
          ],
        ),
      ),
    );
  }
}

class _CompactHeaderExample extends StatefulWidget {
  const _CompactHeaderExample();

  @override
  State<_CompactHeaderExample> createState() => _CompactHeaderExampleState();
}

class _CompactHeaderExampleState extends State<_CompactHeaderExample> {
  bool _selecting = false;

  @override
  Widget build(BuildContext context) => UiSectionHeader(
    title: 'Review queue',
    supporting: _selecting ? 'Selection mode' : null,
    trailingAction: UiIconButton(
      icon: _selecting ? UiIcons.check : UiIcons.selectAll,
      semanticsLabel: _selecting ? 'Done selecting' : 'Select specimens',
      onPressed: () => setState(() => _selecting = !_selecting),
    ),
  );
}

class _HeaderExample extends StatefulWidget {
  const _HeaderExample({required this.role});

  final UiSectionHeaderRole role;

  @override
  State<_HeaderExample> createState() => _HeaderExampleState();
}

class _HeaderExampleState extends State<_HeaderExample> {
  bool _details = false;

  @override
  Widget build(BuildContext context) => UiSectionHeader(
    title: 'Specimen records',
    role: widget.role,
    supporting: _details
        ? '7 synthetic records across Insects and Botany. No production data is connected.'
        : 'Review the latest specimens in this collection.',
    meta: Text(
      '7 records',
      style: context.ui.type.labelSmall.copyWith(
        color: context.ui.color.inkSecondary,
      ),
    ),
    actions: <Widget>[
      UiButton(
        label: _details ? 'Hide details' : 'Show details',
        variant: UiButtonVariant.secondary,
        onPressed: () => setState(() => _details = !_details),
      ),
    ],
  );
}

class _PaginationExample extends StatefulWidget {
  const _PaginationExample({
    super.key,
    required this.initialPage,
    required this.pageCount,
    required this.busy,
    required this.enabled,
  });

  final int initialPage;
  final int pageCount;
  final bool busy;
  final bool enabled;

  @override
  State<_PaginationExample> createState() => _PaginationExampleState();
}

class _PaginationExampleState extends State<_PaginationExample> {
  late int _page = widget.initialPage;

  @override
  Widget build(BuildContext context) => UiPagination(
    page: _page,
    pageCount: widget.pageCount,
    busy: widget.busy,
    onChanged: widget.enabled
        ? (int value) => setState(() => _page = value)
        : null,
  );
}

enum _TableState {
  basic,
  sortable,
  selection,
  loading,
  empty,
  error,
  longContent,
}

class _TableExample extends StatefulWidget {
  const _TableExample({super.key, required this.state});

  final _TableState state;

  @override
  State<_TableExample> createState() => _TableExampleState();
}

class _TableExampleState extends State<_TableExample> {
  Set<Object> _selected = <Object>{'outside-this-page', 'DEMO-0041'};
  UiSortDirection _direction = UiSortDirection.ascending;
  String _sort = 'name';
  bool _retried = false;

  @override
  Widget build(BuildContext context) {
    final bool sorting =
        widget.state == _TableState.sortable ||
        widget.state == _TableState.selection;
    final List<(String, String)> values = <(String, String)>[
      ('DEMO-0041', 'Danaus plexippus'),
      ('DEMO-0042', 'Quercus alba'),
      (
        'DEMO-0043',
        widget.state == _TableState.longContent
            ? 'A lengthy working identification retained in full until the reviewer resolves the source evidence'
            : 'Papilio polyxenes',
      ),
    ];
    if (sorting) {
      values.sort(((String, String) a, (String, String) b) {
        final int result = (_sort == 'id' ? a.$1 : a.$2).compareTo(
          _sort == 'id' ? b.$1 : b.$2,
        );
        return _direction == UiSortDirection.ascending ? result : -result;
      });
    }
    return UiDataTable<(String, String)>(
      label: 'Synthetic specimens',
      header: UiSectionHeader(
        title: 'Synthetic specimens',
        role: UiSectionHeaderRole.card,
        supporting: widget.state == _TableState.selection
            ? '${_selected.length} selected, including selections on other pages. The final row cannot be selected.'
            : 'Typed cells with caller-owned formatting.',
      ),
      columns: <UiDataColumn<(String, String)>>[
        UiDataColumn<(String, String)>(
          id: 'id',
          label: 'Catalogue',
          sortable: sorting,
          cellBuilder: (BuildContext context, (String, String) value) =>
              Text(value.$1),
          semanticValue: ((String, String) value) => value.$1,
        ),
        UiDataColumn<(String, String)>(
          id: 'name',
          label: 'Taxon',
          flex: 2,
          sortable: sorting,
          cellBuilder: (BuildContext context, (String, String) value) =>
              Text(value.$2),
          semanticValue: ((String, String) value) => value.$2,
        ),
      ],
      rows: widget.state == _TableState.empty
          ? <UiDataRow<(String, String)>>[]
          : <UiDataRow<(String, String)>>[
              for (final (String, String) value in values)
                UiDataRow<(String, String)>(
                  id: value.$1,
                  value: value,
                  label: value.$1,
                  selectable: value.$1 != 'DEMO-0043',
                ),
            ],
      loading: widget.state == _TableState.loading,
      error: widget.state == _TableState.error && !_retried
          ? UiEmptyState(
              icon: UiIcons.error,
              title: 'Records could not load',
              body: 'This synthetic error demonstrates a retry action.',
              action: UiButton(
                label: 'Retry loading',
                onPressed: () => setState(() => _retried = true),
              ),
            )
          : null,
      selectedIds: _selected,
      onSelectionChanged: widget.state == _TableState.selection
          ? (Set<Object> values) => setState(() => _selected = values)
          : null,
      sortColumnId: sorting ? _sort : null,
      sortDirection: _direction,
      onSort: sorting
          ? (String column, UiSortDirection direction) => setState(() {
              _sort = column;
              _direction = direction;
            })
          : null,
    );
  }
}

class _HeaderAnatomyExample extends StatefulWidget {
  const _HeaderAnatomyExample({
    required this.avatar,
    required this.tabs,
    required this.command,
  });
  final bool avatar, tabs;
  final String command;
  @override
  State<_HeaderAnatomyExample> createState() => _HeaderAnatomyExampleState();
}

class _HeaderAnatomyExampleState extends State<_HeaderAnatomyExample> {
  final selected = ValueNotifier(0);
  final _helpFocus = FocusNode(debugLabel: 'About collection records');
  String receipt = 'All records';
  @override
  void dispose() {
    selected.dispose();
    _helpFocus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _DataFrame(
    description:
        'Card and section headers support identity, help, working tabs and filter/tool regions.',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        UiSectionHeader(
          title: 'Collection records',
          role: UiSectionHeaderRole.card,
          supporting: 'Review complete original evidence.',
          leading: widget.avatar ? const UiAvatar(name: 'Field Museum') : null,
          help: UiIconButton(
            icon: UiIcons.info,
            focusNode: _helpFocus,
            semanticsLabel: 'About collection records',
            tooltip: 'Includes all records in this collection',
            onPressed: () {
              _helpFocus.requestFocus();
              FocusManager.instance.applyFocusChangesIfNeeded();
              UiDialog.showAdaptive<void>(
                context: context,
                title: 'Collection records',
                body: (_) =>
                    const Text('Includes all records in this collection'),
                primaryAction: (dialogContext) => UiButton(
                  label: 'Close help',
                  onPressed: () => Navigator.of(dialogContext).pop(),
                ),
              );
            },
          ),
          toolbar: widget.command == 'Search'
              ? UiSearchField(
                  label: 'Search records',
                  clearLabel: 'Clear search',
                  onChanged: (value) =>
                      setState(() => receipt = 'Search: $value'),
                )
              : null,
          tabs: widget.tabs
              ? UiTabs(
                  tabs: const [
                    UiTab(label: 'All records'),
                    UiTab(label: 'Reviewed'),
                  ],
                  selected: selected,
                  semanticsLabel: 'Record views',
                  onSelected: (value) => setState(
                    () => receipt = value == 0
                        ? 'All records'
                        : 'Reviewed records',
                  ),
                )
              : null,
          actions: [
            UiButton(
              label: widget.command == 'Button group'
                  ? 'Previous'
                  : 'Add records',
              onPressed: () => setState(
                () => receipt = widget.command == 'Button group'
                    ? 'Previous requested'
                    : 'Add requested',
              ),
            ),
            if (widget.command == 'Button group')
              UiButton(
                label: 'Next',
                variant: UiButtonVariant.secondary,
                onPressed: () => setState(() => receipt = 'Next requested'),
              ),
          ],
        ),
        Text(receipt),
      ],
    ),
  );
}
