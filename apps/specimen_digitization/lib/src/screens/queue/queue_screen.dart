/// The queue (screen blueprints, section 3).
///
/// A header that states what is loaded, one row per record with the facts a
/// reviewer chooses between rows on, and a list that never moves under a
/// reviewer because a poll answered.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../app/routes.dart';
import '../../models.dart';
import '../../search_filters.dart';
import '../../theme/icons.dart';
import '../../theme/motion.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import '../../workspace.dart';

/// The width of the list pane in the list detail layout (responsive, 3.2).
const double queueListPaneWidth = 360;

/// How many placeholder rows stand in for the first page.
const int queueSkeletonRows = 5;

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

    final Widget list = ListView(
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
        // Placeholders to rows, and one result set to the next, are the same
        // cross-fade: nothing slides, nothing staggers, and a poll that
        // answered with the same records produces no motion at all, because
        // the key does not change (motion catalog, rows 13, 24 and 28).
        AnimatedSwitcher(
          duration: context.motion.standard,
          switchInCurve: MotionTokens.standardCurve,
          switchOutCurve: MotionTokens.standardCurve,
          // The incoming child is pinned to the top left, so a swap never
          // lurches the scroll position.
          layoutBuilder: (Widget? current, List<Widget> previous) => Stack(
            alignment: AlignmentDirectional.topStart,
            children: <Widget>[...previous, ?current],
          ),
          child: KeyedSubtree(
            key: ValueKey<String>(_bodyKey(controller, first, items)),
            child: first
                ? _skeleton(context)
                : items.isEmpty
                ? _empty(context, controller)
                : _rows(context, controller, items),
          ),
        ),
        if (controller.nextCursor != null) ...<Widget>[
          SizedBox(height: context.space.space4),
          _LoadMoreButton(controller: controller),
        ],
      ],
    );

    // Pull to refresh is a touch gesture, and on the web it fights the
    // browser's own pull to refresh, so it is offered on the two touch
    // platforms only (motion catalog, row 21). The list is never cleared
    // while the refresh is out: the rows that are there stay there.
    return _pullToRefresh
        ? RefreshIndicator(onRefresh: () => controller.refresh(), child: list)
        : list;
  }

  /// True on the two platforms whose pull gesture is the app's to own.
  bool get _pullToRefresh =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.android);

  /// What identity the list body has right now.
  ///
  /// Only three things change it: the placeholders giving way to an answer,
  /// the answer being empty or not, and a new result set. A twenty second
  /// poll that returns the same page keeps the same generation and therefore
  /// the same key, which is what makes row 14 true.
  String _bodyKey(
    WorkspaceController controller,
    bool first,
    List<Specimen> items,
  ) {
    if (first) return 'skeleton';
    if (items.isEmpty) return 'empty-${controller.unfiltered}';
    return 'rows-${controller.listGeneration}';
  }

  Widget _skeleton(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: <Widget>[
      const LoadingAnnouncement(thing: 'queue'),
      for (int index = 0; index < queueSkeletonRows; index++)
        Padding(
          padding: EdgeInsets.symmetric(vertical: context.space.space2),
          child: const SkeletonRow(),
        ),
    ],
  );

  Widget _empty(BuildContext context, WorkspaceController controller) =>
      controller.unfiltered
      ? EmptyState(
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
      : EmptyState(
          icon: Symbols.search_off,
          title: 'No records match these filters',
          body: 'Clear the search and filters to see the whole queue.',
          actionLabel: 'Clear all',
          onAction: () => unawaited(controller.clearFilters()),
        );

  /// The rows, under one node that holds the list still while a row has
  /// keyboard focus (screen blueprints, section 3).
  ///
  /// The rows themselves never animate in: they existed before the rebuild,
  /// and an entrance animation on an existing row is on the blocklist.
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
              // The search endpoint answers a bare composite and leaves the
              // contributing signals on the record. The compact meter never
              // draws them, so the row says nothing rather than naming a
              // signal the list response did not carry.
              riskComponents: const <String>[],
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
    // Adding and removing a filter changes the height of the row above the
    // list, so the chips arrive and leave through the shared reveal rather
    // than snapping the rows down (motion catalog, rows 10 and 23).
    return MotionReveal(
      visible: filters.isNotEmpty,
      child: filters.isEmpty
          ? const SizedBox(width: double.infinity)
          : Padding(
              padding: EdgeInsets.only(top: context.space.space2),
              child: Wrap(
                spacing: context.space.space2,
                runSpacing: context.space.space1,
                children: <Widget>[
                  for (final MapEntry<String, String> entry in filters.entries)
                    InputChip(
                      key: ValueKey<String>('filter-chip-${entry.key}'),
                      label: Text(
                        '${searchFieldLabel(entry.key)}: ${entry.value}',
                      ),
                      onDeleted: () =>
                          unawaited(controller.removeFilter(entry.key)),
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
            ),
    );
  }
}

/// The load more control (motion catalog, row 27).
///
/// The label swaps for an inline indicator of the same height, so the button
/// keeps its footprint while the request is out. The appended rows have no
/// entrance animation: they arrive below the fold, and animating something
/// nobody can see is decoration.
class _LoadMoreButton extends StatelessWidget {
  const _LoadMoreButton({required this.controller});

  final WorkspaceController controller;

  /// The label, fixed so the copy and the tests cannot drift.
  static const String label = 'Load more records';

  @override
  Widget build(BuildContext context) {
    final bool busy = controller.loadingMore;
    return OutlinedButton(
      onPressed: busy || controller.loading
          ? null
          : () => unawaited(controller.loadMore()),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          InFlightGlyph(busy: busy, resting: null),
          Flexible(child: Text(busy ? 'Loading more…' : label)),
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
