/// The queue (screen blueprints, section 3).
///
/// A header that states what is loaded, one row per record with the facts a
/// reviewer chooses between rows on, and a list that never moves under a
/// reviewer because a poll answered.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../app/routes.dart';
import '../../models.dart';
import '../../search_filters.dart';
import '../../theme/icons.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import '../../workspace.dart';

/// The width of the list pane in the list detail layout (responsive, 3.2).
const double queueListPaneWidth = 360;

/// How many placeholder rows stand in for the first page.
const int queueSkeletonRows = 5;

/// The contributing signals behind a queue row's risk score.
///
/// The search endpoint returns a bare composite; the signals that produced it
/// are on the record itself. The compact meter never draws this list, so this
/// names where the signals are rather than inventing one.
const List<String> queueRiskComponents = <String>[
  'Contributing signals are on the record',
];

/// One line of plain language saying why a record is in the queue.
String queueReason(Specimen specimen) {
  final Json data = specimen.data;
  final Object? blocker = data['blocker'];
  if (blocker is String && blocker.isNotEmpty) {
    return 'Blocked: ${vocabularyLabel(blocker)}';
  }
  final Object? reasons = data['reason_codes'];
  if (reasons is List && reasons.isNotEmpty) {
    return reasons
        .map((Object? code) => vocabularyLabel(code.toString()))
        .join(', ');
  }
  final Object? stage = data['stage'];
  if (stage is String && stage.isNotEmpty) {
    return 'Step ${vocabularyLabel(stage)}';
  }
  return 'No findings recorded';
}

/// When a record last changed, as a moment, or null when the server did not
/// say.
DateTime? queueUpdatedAt(Specimen specimen) {
  final Object? raw =
      specimen.data['updated_at'] ?? specimen.data['created_at'];
  if (raw is! String || raw.isEmpty) return null;
  return DateTime.tryParse(raw);
}

/// The queue route.
///
/// At large and above the list is already beside this pane, drawn by the
/// shell, so this is the placeholder half of the list detail layout. Below
/// that it is the queue itself.
class QueueScreen extends StatelessWidget {
  const QueueScreen({super.key});

  @override
  Widget build(BuildContext context) =>
      WindowClass.of(context).isAtLeast(WindowClass.large)
      ? const _NoRecordSelected()
      : const QueuePane();
}

class _NoRecordSelected extends StatelessWidget {
  const _NoRecordSelected();

  @override
  Widget build(BuildContext context) => const EmptyState(
    icon: Symbols.article,
    title: 'No record open',
    body: 'Choose a record in the queue to review it here.',
  );
}

/// The queue itself: header, controls, active filters and rows.
class QueuePane extends StatefulWidget {
  const QueuePane({super.key});

  @override
  State<QueuePane> createState() => _QueuePaneState();
}

class _QueuePaneState extends State<QueuePane> {
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode(debugLabel: 'Queue search');
  int? _cursor;

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  WorkspaceController get _controller => WorkspaceScope.read(context);

  void _move(int delta) {
    final int count = _controller.items.length;
    if (count == 0) return;
    final int from = _cursor ?? (delta > 0 ? -1 : count);
    setState(() => _cursor = (from + delta).clamp(0, count - 1));
  }

  void _openSelected() {
    final List<Specimen> items = _controller.items;
    final int? cursor = _cursor;
    if (items.isEmpty || cursor == null) return;
    _open(items[cursor.clamp(0, items.length - 1)]);
  }

  void _open(Specimen specimen) {
    final WorkspaceController controller = _controller;
    final CollectionScope? scope = controller.scope;
    if (scope == null) return;
    context.go(
      AppRoutes.specimenOf(encodeCollectionKey(scope.key), specimen.id),
    );
  }

  Future<void> _openFilters() async {
    final WorkspaceController controller = _controller;
    final CollectionScope? scope = controller.scope;
    controller.holdList();
    try {
      final Map<String, String>? values =
          await showAdaptiveForm<Map<String, String>>(
            context,
            builder: (BuildContext sheetContext) => SearchFilters(
              initial: controller.filters,
              configuration: scope?.configuration ?? const <String, dynamic>{},
            ),
          );
      if (values != null && mounted) await controller.applyFilters(values);
    } finally {
      controller.releaseList();
    }
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    if (_search.text != controller.query && !_searchFocus.hasFocus) {
      _search.text = controller.query;
    }

    return Shortcuts(
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.keyJ): _MoveSelectionIntent(1),
        SingleActivator(LogicalKeyboardKey.arrowDown): _MoveSelectionIntent(1),
        SingleActivator(LogicalKeyboardKey.keyK): _MoveSelectionIntent(-1),
        SingleActivator(LogicalKeyboardKey.arrowUp): _MoveSelectionIntent(-1),
        SingleActivator(LogicalKeyboardKey.enter): _OpenSelectionIntent(),
        SingleActivator(LogicalKeyboardKey.slash): _FocusSearchIntent(),
        SingleActivator(LogicalKeyboardKey.keyF): _OpenFiltersIntent(),
      },
      child: Actions(
        actions: <Type, Action<Intent>>{
          _MoveSelectionIntent: CallbackAction<_MoveSelectionIntent>(
            onInvoke: (_MoveSelectionIntent intent) {
              if (_searchFocus.hasFocus) return null;
              _move(intent.delta);
              return null;
            },
          ),
          _OpenSelectionIntent: CallbackAction<_OpenSelectionIntent>(
            onInvoke: (_) {
              if (_searchFocus.hasFocus) return null;
              _openSelected();
              return null;
            },
          ),
          _FocusSearchIntent: CallbackAction<_FocusSearchIntent>(
            onInvoke: (_) {
              if (_searchFocus.hasFocus) return null;
              _searchFocus.requestFocus();
              return null;
            },
          ),
          _OpenFiltersIntent: CallbackAction<_OpenFiltersIntent>(
            onInvoke: (_) {
              if (_searchFocus.hasFocus) return null;
              unawaited(_openFilters());
              return null;
            },
          ),
        },
        // One node so the queue receives key events before anything inside it
        // has been focused. The list's own hold node sits lower, around the
        // rows, so this node holding focus never freezes the poll.
        child: Focus(
          autofocus: true,
          skipTraversal: true,
          child: _body(context, controller),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, WorkspaceController controller) {
    final List<Specimen> items = controller.items;
    final bool first = controller.loading && items.isEmpty;
    final double gutter = WindowClass.of(context).isCompact
        ? context.space.space4
        : context.space.space6;

    return ListView(
      controller: controller.queueScroll,
      padding: EdgeInsets.symmetric(
        horizontal: gutter,
        vertical: context.space.space4,
      ),
      children: <Widget>[
        _QueueHeader(controller: controller),
        SizedBox(height: context.space.space4),
        TextField(
          controller: _search,
          focusNode: _searchFocus,
          decoration: const InputDecoration(
            labelText: 'Search by specimen ID',
            helperText: 'Exact match. Use Filters for anything else.',
            prefixIcon: Icon(Symbols.search),
          ),
          onChanged: controller.search,
        ),
        SizedBox(height: context.space.space4),
        _DispositionSegments(controller: controller),
        SizedBox(height: context.space.space2),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: OutlinedButton.icon(
            onPressed: () => unawaited(_openFilters()),
            icon: const Icon(Symbols.filter_list),
            label: Text(
              controller.activeFilterCount == 0
                  ? 'Filters'
                  : 'Filters (${controller.activeFilterCount})',
            ),
          ),
        ),
        _ActiveFilterChips(controller: controller),
        SizedBox(height: context.space.space4),
        if (first) ...<Widget>[
          const LoadingAnnouncement(thing: 'queue'),
          for (int index = 0; index < queueSkeletonRows; index++)
            Padding(
              padding: EdgeInsets.symmetric(vertical: context.space.space2),
              child: const SkeletonRow(),
            ),
        ] else if (items.isEmpty) ...<Widget>[
          if (controller.unfiltered)
            EmptyState(
              icon: Symbols.inventory_2,
              title: 'No specimens yet',
              body: 'Upload a photograph to create the first record.',
              actionLabel: 'Add photographs',
              onAction: () {
                final CollectionScope? scope = controller.scope;
                if (scope == null) return;
                context.go(AppRoutes.intakeOf(encodeCollectionKey(scope.key)));
              },
            )
          else
            EmptyState(
              icon: Symbols.search_off,
              title: 'No records match these filters',
              body: 'Clear the search and filters to see the whole queue.',
              actionLabel: 'Clear all',
              onAction: () => unawaited(controller.clearFilters()),
            ),
        ] else
          _rows(context, controller, items),
        if (controller.nextCursor != null) ...<Widget>[
          SizedBox(height: context.space.space4),
          OutlinedButton(
            onPressed: controller.loadingMore || controller.loading
                ? null
                : () => unawaited(controller.loadMore()),
            child: Text(
              controller.loadingMore ? 'Loading more…' : 'Load more records',
            ),
          ),
        ],
      ],
    );
  }

  /// The rows, under one node that holds the list still while a row has
  /// keyboard focus (screen blueprints, section 3).
  Widget _rows(
    BuildContext context,
    WorkspaceController controller,
    List<Specimen> items,
  ) => Focus(
    canRequestFocus: false,
    skipTraversal: true,
    onFocusChange: (bool focused) =>
        focused ? controller.holdList() : controller.releaseList(),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (int index = 0; index < items.length; index++)
          Padding(
            key: ValueKey<String>('queue-row-${items[index].id}'),
            padding: EdgeInsets.symmetric(vertical: context.space.space1),
            child: QueueRow(
              id: items[index].id,
              title: items[index].title,
              reason: queueReason(items[index]),
              status: SpecimenStatus.fromWire(
                items[index].disposition ?? items[index].state,
              ),
              riskComposite: items[index].data['risk'] as num?,
              riskComponents: queueRiskComponents,
              riskCalibrated: items[index].data['risk_calibrated'] == true,
              updatedAt: queueUpdatedAt(items[index]),
              selected:
                  index == _cursor || items[index].id == controller.selectedId,
              onOpen: () {
                setState(() => _cursor = index);
                _open(items[index]);
              },
            ),
          ),
      ],
    ),
  );
}

/// The title, the live summary line and when the list was last answered.
class _QueueHeader extends StatefulWidget {
  const _QueueHeader({required this.controller});

  final WorkspaceController controller;

  @override
  State<_QueueHeader> createState() => _QueueHeaderState();
}

class _QueueHeaderState extends State<_QueueHeader> {
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    // One tick a second, and only while there is an answer to age. Nothing
    // animates: a counted number is a fact, not a transition
    // (motion catalog, row 6).
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && widget.controller.updatedAt != null) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  /// The summary never implies a total the server did not send: the API
  /// answers a page, so the line says what is loaded (audit, 1.1).
  String _summary() {
    final WorkspaceController controller = widget.controller;
    final int count = controller.items.length;
    final String loaded = count == 1
        ? '1 record loaded'
        : '$count records loaded';
    return '$loaded. ${controller.needsReview} need review, '
        '${controller.blocked} blocked.';
  }

  String? _updated() {
    final DateTime? moment = widget.controller.updatedAt;
    if (moment == null) return null;
    final Duration age = DateTime.now().difference(moment);
    if (age.inMinutes < 1) return 'Updated ${age.inSeconds.clamp(0, 59)} s ago';
    if (age.inHours < 1) return 'Updated ${age.inMinutes} min ago';
    return 'Updated ${age.inHours} h ago';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? updated = _updated();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text('Queue', style: theme.textTheme.headlineSmall),
        SizedBox(height: context.space.space1),
        Semantics(liveRegion: true, child: Text(_summary())),
        if (updated != null) ...<Widget>[
          SizedBox(height: context.space.space1),
          Text(
            updated,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ],
    );
  }
}

/// The disposition segments. Six options, so they scroll sideways rather than
/// shrink on a narrow window.
class _DispositionSegments extends StatelessWidget {
  const _DispositionSegments({required this.controller});

  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: SegmentedButton<String>(
      showSelectedIcon: false,
      segments: <ButtonSegment<String>>[
        for (final MapEntry<String, String> entry in queueDispositions.entries)
          ButtonSegment<String>(value: entry.key, label: Text(entry.value)),
      ],
      selected: <String>{controller.disposition},
      onSelectionChanged: (Set<String> values) =>
          unawaited(controller.selectDisposition(values.first)),
    ),
  );
}

/// One removable chip per active filter, so a filter is never invisible once
/// the sheet closes (audit, pass criterion 6.4).
class _ActiveFilterChips extends StatelessWidget {
  const _ActiveFilterChips({required this.controller});

  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final Map<String, String> filters = controller.filters;
    if (filters.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: EdgeInsets.only(top: context.space.space2),
      child: Wrap(
        spacing: context.space.space2,
        runSpacing: context.space.space1,
        children: <Widget>[
          for (final MapEntry<String, String> entry in filters.entries)
            InputChip(
              key: ValueKey<String>('filter-chip-${entry.key}'),
              label: Text('${searchFieldLabel(entry.key)}: ${entry.value}'),
              onDeleted: () => unawaited(controller.removeFilter(entry.key)),
              deleteIcon: const Icon(Symbols.close),
              deleteButtonTooltipMessage:
                  'Remove the ${searchFieldLabel(entry.key)} filter',
            ),
          TextButton(
            onPressed: () => unawaited(controller.clearFilters()),
            child: const Text('Clear all'),
          ),
        ],
      ),
    );
  }
}

class _MoveSelectionIntent extends Intent {
  const _MoveSelectionIntent(this.delta);

  final int delta;
}

class _OpenSelectionIntent extends Intent {
  const _OpenSelectionIntent();
}

class _FocusSearchIntent extends Intent {
  const _FocusSearchIntent();
}

class _OpenFiltersIntent extends Intent {
  const _OpenFiltersIntent();
}
