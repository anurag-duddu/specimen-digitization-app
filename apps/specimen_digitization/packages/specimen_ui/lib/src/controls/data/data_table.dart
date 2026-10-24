/// A typed, controlled table assembled from owned controls.
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/pressable.dart';
import '../../primitives/focus_ring.dart';
import '../../primitives/surface.dart';
import '../../primitives/popover.dart';
import '../actions/button.dart';
import '../actions/icon_button.dart';
import '../inputs/checkbox.dart';
import 'empty_state.dart';
import 'hairline.dart';
import 'progress.dart';
import 'skeleton.dart';

/// Requested ordering for a sortable column.
enum UiSortDirection {
  /// Smallest or earliest first.
  ascending,

  /// Largest or latest first.
  descending,
}

/// Row separation treatments share the same data and selection semantics.
enum UiTableDividers {
  /// Hairlines between consecutive rows.
  lines,

  /// Alternating neutral row surfaces.
  striped,
}

/// One typed column. The host keeps domain formatting and comparison logic.
@immutable
class UiDataColumn<T> {
  /// Defines a column and its cells.
  const UiDataColumn({
    required this.id,
    required this.label,
    required this.cellBuilder,
    this.semanticValue,
    this.sortable = false,
    this.numeric = false,
    this.flex = 1,
    this.helpText,
    this.sortEnabled = true,
  }) : assert(flex > 0);

  /// Stable identifier used by the sort callback.
  final String id;

  /// Visible column heading.
  final String label;

  /// Builds a cell from a typed row value. Text wraps within its column.
  final Widget Function(BuildContext context, T value) cellBuilder;

  /// Plain-language value read with the column label.
  ///
  /// Supply this for passive rich cells. Omit it for interactive cells so
  /// their controls keep their own semantics and actions.
  final String Function(T value)? semanticValue;

  /// Enables sorting when the table also supplies an `onSort` callback.
  final bool sortable;

  /// Aligns both header and cell at the trailing edge.
  final bool numeric;

  /// Relative allocation, including when the table scrolls horizontally.
  final int flex;

  /// Definition exposed by a separate help control on hover, focus or activation.
  /// Opening help never changes the sort order.
  final String? helpText;

  /// Whether sorting is currently available for this column.
  final bool sortEnabled;
}

/// A value with stable identity and a complete name for its selection control.
@immutable
class UiDataRow<T> {
  /// Creates a row. IDs must be unique within one table.
  const UiDataRow({
    required this.id,
    required this.value,
    required this.label,
    this.selectable = true,
  });

  /// Stable identity retained across sorting and pagination.
  final Object id;

  /// The domain value passed to column builders.
  final T value;

  /// Human-readable row identity, for example a catalogue number.
  final String label;

  /// False excludes this row from individual and select-all changes.
  final bool selectable;
}

/// Token-derived table paint and geometry.
@immutable
class UiDataTableStyle {
  /// Resolves the readable minimum and density from the current theme.
  UiDataTableStyle.resolve(UiThemeData ui)
    : cellPadding = EdgeInsetsDirectional.symmetric(
        horizontal: ui.space.s4,
        vertical: ui.space.s3,
      ),
      columnMin = ui.space.labelMin + ui.space.s8,
      selectionWidth = ui.space.targetMin + ui.space.s4,
      rowMin = ui.space.targetMin,
      gap = ui.space.s2,
      statePadding = ui.space.s6,
      header = ui.type.label.copyWith(color: ui.color.inkSecondary),
      body = ui.type.bodySmall.copyWith(color: ui.color.ink),
      headerFill = ui.color.ground,
      selectedFill = Color.alphaBlend(
        ui.color.stateLayer(ui.color.hoverOpacity),
        ui.color.paper,
      );

  /// Content inset in each cell.
  final EdgeInsetsGeometry cellPadding;

  /// Minimum readable width per flex unit before text scaling.
  final double columnMin;

  /// Width reserved for selection controls.
  final double selectionWidth;

  /// Minimum row height, preserving the shared hit target.
  final double rowMin;

  /// Icon-to-text and loading-copy spacing.
  final double gap;

  /// Inset around loading, error and empty content.
  final double statePadding;

  /// Column-heading typography.
  final TextStyle header;

  /// Default cell typography.
  final TextStyle body;

  /// Quiet header surface.
  final Color headerFill;

  /// Neutral selected-row surface; the checkbox also states selection.
  final Color selectedFill;
}

/// A table with typed cells, controlled sorting and optional row selection.
///
/// Designed for a bounded page of rows: the host owns fetching, sorting and
/// pagination. Wide content scrolls horizontally rather than shrinking text.
/// Header, filter toolbar and footer stay outside that horizontal viewport.
/// Loading and error states replace row actions, so stale data cannot be
/// selected while a replacement result is pending.
class UiDataTable<T> extends StatelessWidget {
  /// Creates a table with optional composed header, filters and footer.
  const UiDataTable({
    super.key,
    required this.label,
    required this.columns,
    required this.rows,
    this.header,
    this.toolbar,
    this.footer,
    this.sortColumnId,
    this.sortDirection = UiSortDirection.ascending,
    this.onSort,
    this.selectedIds = const <Object>{},
    this.onSelectionChanged,
    this.loading = false,
    this.loadingLabel = 'Loading records',
    this.loadingContent,
    this.error,
    this.empty,
    this.dividers = UiTableDividers.lines,
    this.shadedHeader = true,
  }) : assert(columns.length > 0);

  /// Accessible name for the table region.
  final String label;

  /// Columns with unique IDs, in reading order.
  final List<UiDataColumn<T>> columns;

  /// Current page of rows with unique IDs.
  final List<UiDataRow<T>> rows;

  /// Usually a `UiSectionHeader` in its card role.
  final Widget? header;

  /// Search, filters and batch actions. The caller owns their state.
  final Widget? toolbar;

  /// Usually controlled pagination, optionally with a count summary.
  final Widget? footer;

  /// Current sorted column ID, or null for no ordering.
  final String? sortColumnId;

  /// Current direction for [sortColumnId].
  final UiSortDirection sortDirection;

  /// Requests sorting without mutating or reordering [rows].
  final void Function(String columnId, UiSortDirection direction)? onSort;

  /// Controlled row selection, which may include rows on other pages.
  final Set<Object> selectedIds;

  /// Requests a new immutable set. Null hides the selection column.
  ///
  /// Select all changes only selectable rows on this page, preserving every
  /// other ID. A partially selected page becomes fully selected.
  final ValueChanged<Set<Object>>? onSelectionChanged;

  /// Replaces rows with a loading view and suppresses sorting and selection.
  final bool loading;

  /// Visible and announced loading status.
  final String loadingLabel;

  /// Custom loading body; its semantics should describe the wait once.
  final Widget? loadingContent;

  /// Error content, typically an owned empty-state or banner with retry.
  /// Takes precedence over loading and rows, retaining the composed header.
  final Widget? error;

  /// Content shown when loading finished successfully with no rows.
  final Widget? empty;

  /// Whether rows use hairlines or alternating neutral fills.
  final UiTableDividers dividers;

  /// Whether the column headings have a distinct neutral fill.
  final bool shadedHeader;

  bool get _selectable => onSelectionChanged != null;

  void _select(UiDataRow<T> row, bool selected) {
    if (loading || error != null || !row.selectable) return;
    final Set<Object> next = <Object>{...selectedIds};
    selected ? next.add(row.id) : next.remove(row.id);
    onSelectionChanged?.call(Set<Object>.unmodifiable(next));
  }

  void _selectPage(bool selected) {
    if (loading || error != null) return;
    final Set<Object> next = <Object>{...selectedIds};
    for (final UiDataRow<T> row in rows.where(
      (UiDataRow<T> r) => r.selectable,
    )) {
      selected ? next.add(row.id) : next.remove(row.id);
    }
    onSelectionChanged?.call(Set<Object>.unmodifiable(next));
  }

  @override
  Widget build(BuildContext context) {
    assert(
      columns.map((UiDataColumn<T> c) => c.id).toSet().length == columns.length,
      'Column IDs must be unique.',
    );
    assert(
      rows.map((UiDataRow<T> r) => r.id).toSet().length == rows.length,
      'Row IDs must be unique.',
    );
    assert(
      sortColumnId == null ||
          columns.any((UiDataColumn<T> c) => c.id == sortColumnId),
      'The sorted column must exist.',
    );
    final UiThemeData ui = context.ui;
    final UiDataTableStyle style = UiDataTableStyle.resolve(ui);
    Widget inset(Widget child) =>
        Padding(padding: EdgeInsets.all(style.statePadding), child: child);
    final Widget body;
    if (error != null) {
      body = Semantics(liveRegion: true, child: inset(error!));
    } else if (loading) {
      body = inset(
        loadingContent ??
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Semantics(
                  liveRegion: true,
                  child: Text(loadingLabel, style: style.body),
                ),
                SizedBox(height: style.gap),
                ExcludeSemantics(
                  child: UiProgress.bar(semanticsLabel: loadingLabel),
                ),
                SizedBox(height: style.statePadding),
                const UiSkeleton.row(),
                const UiSkeleton.row(),
              ],
            ),
      );
    } else if (rows.isEmpty) {
      body = inset(
        empty ??
            const UiEmptyState(
              icon: UiIcons.noResults,
              title: 'No records',
              body: 'Records will appear here when they are available.',
            ),
      );
    } else {
      body = _grid(context, style);
    }
    return Semantics(
      container: true,
      label: label,
      child: Surface(
        hairline: true,
        radius: ui.shape.tile,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (header != null) inset(header!),
            if (toolbar != null) ...<Widget>[
              if (header != null) const UiHairline(),
              inset(toolbar!),
            ],
            body,
            if (footer != null) ...<Widget>[const UiHairline(), inset(footer!)],
          ],
        ),
      ),
    );
  }

  Widget _grid(BuildContext context, UiDataTableStyle style) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final UiThemeData ui = context.ui;
      final double scale = math.max(
        1,
        UiType.lineHeightOf(style.body, context) /
            UiType.unscaledLineHeightOf(style.body),
      );
      final int flexTotal = columns.fold<int>(
        0,
        (int n, UiDataColumn<T> c) => n + c.flex,
      );
      final double minimum =
          style.columnMin * flexTotal * scale +
          (_selectable ? style.selectionWidth : 0);
      final double width = math.max(
        minimum,
        constraints.hasBoundedWidth ? constraints.maxWidth : minimum,
      );
      final double available = width - (_selectable ? style.selectionWidth : 0);
      final List<UiDataRow<T>> eligible = rows
          .where((UiDataRow<T> r) => r.selectable)
          .toList();
      final int selected = eligible
          .where((UiDataRow<T> r) => selectedIds.contains(r.id))
          .length;
      Widget cell(Widget child, {bool numeric = false}) => Padding(
        padding: style.cellPadding,
        child: Align(
          alignment: numeric
              ? AlignmentDirectional.centerEnd
              : AlignmentDirectional.centerStart,
          child: child,
        ),
      );
      final Widget table = SizedBox(
        width: width,
        child: Table(
          defaultVerticalAlignment: TableCellVerticalAlignment.middle,
          columnWidths: <int, TableColumnWidth>{
            if (_selectable) 0: FixedColumnWidth(style.selectionWidth),
            for (int i = 0; i < columns.length; i++)
              i + (_selectable ? 1 : 0): FixedColumnWidth(
                available * columns[i].flex / flexTotal,
              ),
          },
          border: dividers == UiTableDividers.lines
              ? TableBorder(
                  horizontalInside: BorderSide(
                    color: ui.color.hairline,
                    width: ui.shape.stroke.hairline,
                  ),
                )
              : null,
          children: <TableRow>[
            TableRow(
              decoration: BoxDecoration(
                color: shadedHeader ? style.headerFill : ui.color.paper,
              ),
              children: <Widget>[
                if (_selectable)
                  UiCheckbox(
                    label: 'Select all rows on this page',
                    showLabel: false,
                    value: selected == 0
                        ? false
                        : selected == eligible.length
                        ? true
                        : null,
                    onChanged: eligible.isEmpty ? null : _selectPage,
                  ),
                for (final UiDataColumn<T> column in columns)
                  _heading(context, column, style),
              ],
            ),
            for (final (index, row) in rows.indexed)
              TableRow(
                key: ValueKey<Object>(row.id),
                decoration: selectedIds.contains(row.id)
                    ? BoxDecoration(color: style.selectedFill)
                    : dividers == UiTableDividers.striped && index.isOdd
                    ? BoxDecoration(color: ui.color.ground)
                    : null,
                children: <Widget>[
                  if (_selectable)
                    UiCheckbox(
                      label: 'Select ${row.label}',
                      showLabel: false,
                      value: selectedIds.contains(row.id),
                      onChanged: row.selectable
                          ? (bool value) => _select(row, value)
                          : null,
                    ),
                  for (final UiDataColumn<T> column in columns)
                    ConstrainedBox(
                      constraints: BoxConstraints(minHeight: style.rowMin),
                      child: cell(
                        DefaultTextStyle(
                          style: style.body,
                          child: column.semanticValue == null
                              ? column.cellBuilder(context, row.value)
                              : Semantics(
                                  container: true,
                                  excludeSemantics: true,
                                  label:
                                      '${column.label}: ${column.semanticValue!(row.value)}',
                                  child: column.cellBuilder(context, row.value),
                                ),
                        ),
                        numeric: column.numeric,
                      ),
                    ),
                ],
              ),
          ],
        ),
      );
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (constraints.hasBoundedWidth && width > constraints.maxWidth)
            Padding(
              padding: style.cellPadding,
              child: Text(
                'Scroll horizontally to see all columns.',
                style: style.body.copyWith(color: ui.color.inkSecondary),
              ),
            ),
          _HorizontalTableViewport(
            label: label,
            overflowing:
                constraints.hasBoundedWidth && width > constraints.maxWidth,
            child: table,
          ),
        ],
      );
    },
  );

  Widget _heading(
    BuildContext context,
    UiDataColumn<T> column,
    UiDataTableStyle style,
  ) {
    final bool active = sortColumnId == column.id;
    final bool enabled =
        column.sortable && column.sortEnabled && onSort != null;
    final UiSortDirection next =
        active && sortDirection == UiSortDirection.ascending
        ? UiSortDirection.descending
        : UiSortDirection.ascending;
    final bool hasHelp = column.helpText?.trim().isNotEmpty ?? false;
    final Widget content = Padding(
      padding: hasHelp ? EdgeInsets.zero : style.cellPadding,
      child: Row(
        mainAxisAlignment: column.numeric
            ? MainAxisAlignment.end
            : MainAxisAlignment.start,
        children: <Widget>[
          Flexible(child: Text(column.label, style: style.header)),
          if (column.sortable) ...<Widget>[
            SizedBox(width: style.gap),
            UiIcon(
              active && sortDirection == UiSortDirection.ascending
                  ? UiIcons.collapse
                  : UiIcons.expand,
              size: UiIconSize.small,
              color: active
                  ? context.ui.color.ink
                  : context.ui.color.inkSecondary,
            ),
          ],
        ],
      ),
    );
    final Widget heading = column.sortable
        ? Semantics(
            header: true,
            child: Pressable(
              semanticsLabel: 'Sort by ${column.label}',
              semanticsValue: active
                  ? 'Sorted ${sortDirection.name}'
                  : 'Not sorted',
              onPressed: enabled ? () => onSort!(column.id, next) : null,
              builder: (BuildContext context, Set<WidgetState> states) =>
                  content,
            ),
          )
        : Semantics(header: true, child: content);
    if (!hasHelp) return heading;
    return Padding(
      padding: style.cellPadding,
      child: Row(
        children: [
          Expanded(child: heading),
          SizedBox(width: style.gap),
          _TableColumnHelp(
            key: ValueKey(column.id),
            label: column.label,
            message: column.helpText!,
          ),
        ],
      ),
    );
  }
}

class _TableColumnHelp extends StatefulWidget {
  const _TableColumnHelp({
    super.key,
    required this.label,
    required this.message,
  });

  final String label;
  final String message;

  @override
  State<_TableColumnHelp> createState() => _TableColumnHelpState();
}

class _TableColumnHelpState extends State<_TableColumnHelp> {
  final PopoverController _controller = PopoverController();
  final FocusNode _triggerFocus = FocusNode();
  final FocusNode _closeFocus = FocusNode();

  @override
  void initState() {
    super.initState();
    _controller.addListener(_focusChanged);
  }

  void _focusChanged() {
    final open = _controller.isOpen;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _controller.isOpen != open) return;
      final target = open ? _closeFocus : _triggerFocus;
      if (target.context != null && target.canRequestFocus) {
        target.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _controller.removeListener(_focusChanged);
    _controller.dispose();
    _triggerFocus.dispose();
    _closeFocus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Popover(
      controller: _controller,
      surface: PopoverSurface.paper,
      flipWhenClipped: true,
      semanticsLabel: 'About ${widget.label}',
      overlayBuilder: (_) => ConstrainedBox(
        constraints: BoxConstraints(maxWidth: ui.space.readingMax / 2),
        child: SingleChildScrollView(
          child: Padding(
            padding: EdgeInsets.all(ui.space.s3),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.message,
                  style: ui.type.bodySmall.copyWith(color: ui.color.ink),
                ),
                SizedBox(height: ui.space.s2),
                UiButton(
                  label: 'Close help',
                  variant: UiButtonVariant.ghost,
                  focusNode: _closeFocus,
                  onPressed: _controller.close,
                ),
              ],
            ),
          ),
        ),
      ),
      child: UiIconButton(
        icon: UiIcons.info,
        semanticsLabel: 'About ${widget.label}',
        tooltip: widget.message,
        focusNode: _triggerFocus,
        onPressed: _controller.toggle,
      ),
    );
  }
}

class _HorizontalTableViewport extends StatefulWidget {
  const _HorizontalTableViewport({
    required this.label,
    required this.overflowing,
    required this.child,
  });

  final String label;
  final bool overflowing;
  final Widget child;

  @override
  State<_HorizontalTableViewport> createState() =>
      _HorizontalTableViewportState();
}

class _HorizontalTableViewportState extends State<_HorizontalTableViewport> {
  final ScrollController _scroll = ScrollController();
  final FocusNode _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(_focusChanged);
  }

  void _focusChanged() => setState(() {});

  @override
  void dispose() {
    _focus.removeListener(_focusChanged);
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (!widget.overflowing || !_scroll.hasClients || event is KeyUpEvent) {
      return KeyEventResult.ignored;
    }
    final LogicalKeyboardKey key = event.logicalKey;
    final double sign = Directionality.of(context) == TextDirection.rtl
        ? -1
        : 1;
    final ScrollPosition position = _scroll.position;
    final double? destination = key == LogicalKeyboardKey.arrowRight
        ? position.pixels + position.viewportDimension / 3 * sign
        : key == LogicalKeyboardKey.arrowLeft
        ? position.pixels - position.viewportDimension / 3 * sign
        : key == LogicalKeyboardKey.home
        ? position.minScrollExtent
        : key == LogicalKeyboardKey.end
        ? position.maxScrollExtent
        : null;
    if (destination == null) return KeyEventResult.ignored;
    position.jumpTo(
      destination.clamp(position.minScrollExtent, position.maxScrollExtent),
    );
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) => Focus(
    focusNode: _focus,
    canRequestFocus: widget.overflowing,
    skipTraversal: !widget.overflowing,
    onKeyEvent: _key,
    child: Semantics(
      label: widget.overflowing ? '${widget.label} columns' : null,
      hint: widget.overflowing
          ? 'Use left and right arrow keys to scroll horizontally.'
          : null,
      child: FocusRing(
        visible: _focus.hasPrimaryFocus,
        child: SingleChildScrollView(
          controller: _scroll,
          scrollDirection: Axis.horizontal,
          child: widget.child,
        ),
      ),
    ),
  );
}
