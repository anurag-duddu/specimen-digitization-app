/// The queue (07 section 3).
///
/// A header that states what is loaded, one row per record with the facts a
/// reviewer chooses between rows on, and a list that never moves under a
/// reviewer because a poll answered.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../app/routes.dart';
import '../../models.dart';
import '../../reason_codes.dart';
import '../../saved_filters.dart';
import '../../search_filters.dart';
import '../../selection.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import '../../workspace.dart';

/// The width of the list pane in the list detail layout (05 section 3.2).
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
  Widget build(BuildContext context) => const UiEmptyState(
    icon: UiIcons.record,
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

  /// The records this reviewer has picked out of the loaded page.
  ///
  /// Shared with every other list a reviewer picks from, so the browse screen
  /// over a data source gets the same reach, the same keyboard behaviour and
  /// the same honesty about what a select all could not see.
  final PagedSelection<Specimen> _selection = PagedSelection<Specimen>(
    identify: (Specimen specimen) => specimen.id,
  );

  /// True while this pane is holding the list still for a live selection.
  bool _holdingForSelection = false;

  /// A context inside the toast layer.
  ///
  /// `UiToasts.show` walks up from the context it is given, and this pane's
  /// own context is above the layer it installs, so a toast raised from here
  /// would find no host at all.
  final GlobalKey _toastScope = GlobalKey(debugLabel: 'Queue toast scope');

  /// One focus node per record on screen, so the cursor and the focus ring
  /// are the same thing.
  ///
  /// Keyed by the record's identifier rather than by its position, so a poll
  /// that reorders the page does not move the ring onto another record.
  final Map<String, FocusNode> _rowFocus = <String, FocusNode>{};

  /// The controller this pane is listening to, so the listener is removed
  /// from the same object it was added to.
  WorkspaceController? _listening;

  /// This reviewer's own recent reasons, offered as chips in the
  /// confirmation exactly as the workbench offers them.
  List<String> _recentReasons = <String>[];
  RecentReasonStore _reasonStore = const RecentReasonStore('');

  @override
  void initState() {
    super.initState();
    _selection.addListener(_onSelectionChanged);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final WorkspaceController controller = _controller;
    if (!identical(_listening, controller)) {
      _listening?.removeListener(_syncSelection);
      controller.addListener(_syncSelection);
      _listening = controller;
      _syncSelection();
    }
    final String reviewer = controller.session.userId;
    if (_reasonStore.userId != reviewer) {
      _reasonStore = RecentReasonStore(reviewer);
      _recentReasons = <String>[];
      unawaited(_loadRecentReasons());
    }
  }

  @override
  void dispose() {
    _listening?.removeListener(_syncSelection);
    _selection.removeListener(_onSelectionChanged);
    if (_holdingForSelection) _listening?.releaseList();
    _selection.dispose();
    _search.dispose();
    _searchFocus.dispose();
    for (final FocusNode node in _rowFocus.values) {
      node.dispose();
    }
    super.dispose();
  }

  Future<void> _loadRecentReasons() async {
    final List<String> stored = await _reasonStore.load();
    if (mounted) setState(() => _recentReasons = stored);
  }

  /// Keeps the selection a subset of what is loaded.
  ///
  /// Driven from the controller rather than from `build`, because reconciling
  /// the selection can release the list hold, and a widget must not push a
  /// change back into the thing it is drawing.
  void _syncSelection() {
    final WorkspaceController controller = _controller;
    _selection.syncLoaded(
      controller.items,
      moreToLoad: controller.nextCursor != null,
    );
  }

  /// A selection that is live holds the list still.
  ///
  /// The poll already defers while a row has focus or a sheet is open, for
  /// the same reason: a count a reviewer is about to act on must not change
  /// under them between reading it and confirming it.
  void _onSelectionChanged() {
    final bool hold = _selection.isNotEmpty;
    if (hold != _holdingForSelection) {
      _holdingForSelection = hold;
      hold ? _controller.holdList() : _controller.releaseList();
    }
    if (mounted) setState(() {});
  }

  /// Asks for one reason, then takes [kind] across the whole selection.
  ///
  /// The confirmation names the exact count before anything is written,
  /// because this product has no true delete: a bulk decision is recorded on
  /// the version it was taken against and superseded by a later one, never
  /// removed. That is what the reason sheet's own finality sentence says, and
  /// it is why the count comes first.
  Future<void> _decideOnSelection(BulkDecisionKind kind) async {
    final WorkspaceController controller = _controller;
    final List<Specimen> chosen = _selection.items;
    if (chosen.isEmpty || controller.mutating) return;
    final Map<String, String> names = <String, String>{
      for (final Specimen specimen in chosen) specimen.id: specimen.title,
    };
    final int count = chosen.length;
    controller.holdList();
    final String? reason;
    try {
      reason = await showReasonSheet(
        context,
        title: kind.title(count),
        action: kind.action(count),
        consequence: kind.consequence(count),
        retained: kind.retained,
        recentReasons: _recentReasons,
      );
    } finally {
      controller.releaseList();
    }
    if (reason == null || !mounted) return;
    final BulkDecisionReport? report = await controller.reviewSelection(
      chosen,
      kind,
      reason,
    );
    if (!mounted) return;
    // A call that did not complete leaves the selection alone: the reviewer's
    // work is still on screen, and the controller's banner says what happened.
    if (report == null) return;
    unawaited(_rememberReason(reason));
    _selection.clear();
    await controller.refresh();
    if (!mounted) return;
    if (report.complete) {
      _toast(kind.done(report.applied));
      return;
    }
    // Anything less than whole is something the reviewer has to act on, so it
    // is a surface they dismiss rather than one that times out.
    await showBulkOutcome(
      context,
      report: report,
      nameOf: (String id) => names[id] ?? id,
    );
  }

  /// Raises [message] on the nearest toast layer.
  void _toast(String message) {
    final BuildContext? scope = _toastScope.currentContext;
    if (scope == null) return;
    UiToasts.show(scope, message: message, icon: UiIcons.cleared);
  }

  Future<void> _rememberReason(String reason) async {
    final List<String> stored = await _reasonStore.remember(reason);
    if (mounted) setState(() => _recentReasons = stored);
  }

  WorkspaceController get _controller => WorkspaceScope.read(context);

  /// The node row [id] takes focus on.
  FocusNode _rowFocusNode(String id) =>
      _rowFocus.putIfAbsent(id, () => FocusNode(debugLabel: 'Queue row $id'));

  void _move(int delta) {
    final List<Specimen> items = _controller.items;
    if (items.isEmpty) return;
    final int from = _cursor ?? (delta > 0 ? -1 : items.length);
    final int next = (from + delta).clamp(0, items.length - 1);
    setState(() => _cursor = next);
    // Focus follows the cursor, so the ring is where the cursor is and
    // `Enter` reaches the row's own activation rather than whichever control
    // happened to be focused when the reviewer started arrowing. The request
    // waits a frame because the row may be building for the first time.
    final FocusNode node = _rowFocusNode(items[next].id);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) node.requestFocus();
    });
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
      final Map<String, String>? values = await SearchFilters.show(
        context,
        initial: controller.filters,
        configuration: scope?.configuration ?? const <String, dynamic>{},
        savedFilters: scope == null ? null : SavedFilterStore(scope.key),
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
        SingleActivator(LogicalKeyboardKey.escape): _ClearSelectionIntent(),
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
          // The way out of a selection without reaching for a control. Not
          // suppressed while the search field has focus, because leaving a
          // selection is what a reviewer means by Escape wherever they are.
          _ClearSelectionIntent: CallbackAction<_ClearSelectionIntent>(
            onInvoke: (_) {
              _selection.clear();
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
          child: _ToastLayer(
            child: KeyedSubtree(
              key: _toastScope,
              child: _body(context, controller),
            ),
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, WorkspaceController controller) {
    final UiThemeData ui = context.ui;
    final List<Specimen> items = controller.items;
    // Placeholders until the server has answered at least once, never a claim
    // about the collection. A deep link used to cancel the queue load and
    // leave this pane saying "No specimens yet" about a collection with
    // records (finding V-5); a list that has never been answered says only
    // that it is loading.
    final bool first = items.isEmpty && !controller.listAnswered;
    final double gutter = WindowClass.of(context).isCompact
        ? ui.space.s4
        : ui.space.s6;

    final Widget list = ListView(
      // The offset survives a push to a record and back, on a window too
      // narrow to keep the list mounted beside it (pass criterion 6.5).
      key: const PageStorageKey<String>('queue-list'),
      controller: controller.queueScroll,
      // The last row scrolls clear of the floating navigation on a phone: the
      // scaffold says how much clearance its bar takes (verification report
      // v2, V2-3), and it is zero where the navigation is a rail or sidebar.
      padding: EdgeInsetsDirectional.only(
        start: gutter,
        end: gutter,
        top: ui.space.s4,
        bottom: ui.space.s4 + UiScaffold.of(context).bottomInset,
      ),
      children: <Widget>[
        _QueueHeader(controller: controller),
        SizedBox(height: ui.space.s4),
        UiSearchField(
          label: _searchLabel,
          hintText: _searchLabel,
          clearLabel: 'Clear the search',
          helpText: 'Exact match. Use Filters for anything else.',
          controller: _search,
          focusNode: _searchFocus,
          onChanged: controller.search,
        ),
        SizedBox(height: ui.space.s4),
        _DispositionChips(controller: controller),
        SizedBox(height: ui.space.s2),
        _FiltersControl(
          count: controller.activeFilterCount,
          onPressed: () => unawaited(_openFilters()),
        ),
        _ActiveFilterChips(controller: controller),
        SizedBox(height: ui.space.s4),
        // Placeholders to rows, and one result set to the next, are the same
        // cross-fade: nothing slides, nothing staggers, and a poll that
        // answered with the same records produces no motion at all, because
        // the key does not change (motion catalog, rows 13, 24 and 28).
        AnimatedSwitcher(
          duration: ui.motion.standard,
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
                ? _skeleton(ui, controller)
                : items.isEmpty
                ? _empty(context, controller)
                : _rows(context, controller, items),
          ),
        ),
        if (controller.nextCursor != null) ...<Widget>[
          SizedBox(height: ui.space.s4),
          _LoadMoreButton(controller: controller),
        ],
      ],
    );

    // Pull to refresh is a touch gesture, and on the web it fights the
    // browser's own pull to refresh, so it is offered on the two touch
    // platforms only (motion catalog, row 21). The list is never cleared
    // while the refresh is out: the rows that are there stay there.
    final Widget scrollable = _pullToRefresh
        ? _PullToRefresh(onRefresh: controller.refresh, child: list)
        : list;

    // The bar floats over the list rather than being welded across it,
    // because the count has to stay on screen while the reviewer scrolls the
    // records they are counting (07 section 3, "the selection count always
    // visible") and a band would take a row's worth of the list at every
    // width.
    return Stack(
      children: <Widget>[
        Positioned.fill(child: scrollable),
        PositionedDirectional(
          start: 0,
          end: 0,
          bottom: 0,
          child: MotionReveal(
            alignment: Alignment.bottomLeft,
            visible: _selection.isNotEmpty,
            child: SelectionBar(
              count: _selection.count,
              loadedCount: _selection.loadedCount,
              moreToLoad: _selection.moreToLoad,
              allLoadedSelected: _selection.allLoadedSelected,
              onSelectAllLoaded: _selection.selectAllLoaded,
              onClear: _selection.clear,
              busy: controller.mutating,
              actions: <SelectionAction>[
                for (final BulkDecisionKind kind in BulkDecisionKind.values)
                  (
                    label: kind.label,
                    icon: kind.icon,
                    onPressed: () => unawaited(_decideOnSelection(kind)),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  /// The search field's one label, so the control, its hint and the tests
  /// cannot word it three ways.
  static const String _searchLabel = 'Search by specimen ID';

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

  Widget _skeleton(UiThemeData ui, WorkspaceController controller) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: <Widget>[
      // Keyed on the collection, so switching collections while the first
      // load is still out builds a new announcer and says "Loading queue"
      // again. The body's own key is the same string in both loads, so
      // without this the element was reused and the second collection loaded
      // in silence: the placeholders are hidden from the semantics tree and
      // there is nothing else on the screen to hear.
      LoadingAnnouncement(
        key: ValueKey<String>('queue-loading-${controller.scope?.key}'),
        thing: 'queue',
      ),
      for (int index = 0; index < queueSkeletonRows; index++)
        Padding(
          padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s2),
          child: const UiSkeleton.row(),
        ),
    ],
  );

  Widget _empty(BuildContext context, WorkspaceController controller) =>
      controller.unfiltered
      ? UiEmptyState(
          icon: UiIcons.queue,
          title: 'No specimens yet',
          body: 'Upload a photograph to create the first record.',
          action: UiButton(
            label: 'Add photographs',
            onPressed: () {
              final CollectionScope? scope = controller.scope;
              if (scope == null) return;
              context.go(AppRoutes.intakeOf(encodeCollectionKey(scope.key)));
            },
          ),
        )
      : UiEmptyState(
          icon: UiIcons.noResults,
          title: 'No records match these filters',
          body: 'Clear the search and filters to see the whole queue.',
          action: UiButton(
            label: 'Clear all',
            onPressed: () => unawaited(controller.clearFilters()),
          ),
        );

  /// The rows, under one node that holds the list still while a row has
  /// keyboard focus (07 section 3).
  ///
  /// The rows themselves never animate in: they existed before the rebuild,
  /// and an entrance animation on an existing row is on the blocklist.
  Widget _rows(
    BuildContext context,
    WorkspaceController controller,
    List<Specimen> items,
  ) {
    // A window wide enough for a checkbox column keeps one open, so a
    // reviewer on a pointer never has to discover a gesture. A narrow one
    // reveals it on a long press and hides it again when the selection
    // empties (07 section 3, "Multi-select"). The window decides, never the
    // platform.
    final bool column =
        WindowClass.of(context).isAtLeast(WindowClass.medium) ||
        _selection.active;
    return Focus(
      canRequestFocus: false,
      skipTraversal: true,
      onFocusChange: (bool focused) =>
          focused ? controller.holdList() : controller.releaseList(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          for (int index = 0; index < items.length; index++)
            KeyedSubtree(
              key: ValueKey<String>('queue-row-${items[index].id}'),
              child: SelectableRow(
                selected: _selection.isSelected(items[index]),
                label: items[index].title,
                showCheckbox: column,
                onToggle: () => _selection.toggle(items[index]),
                onExtend: () => _selection.selectRange(items[index]),
                onLongPress: column
                    ? null
                    : () => _selection.select(items[index]),
                child: QueueRow(
                  id: items[index].id,
                  title: items[index].title,
                  reason: queueReason(items[index]),
                  status: SpecimenStatus.fromWire(
                    items[index].disposition ?? items[index].state,
                  ),
                  riskComposite: items[index].data['risk'] as num?,
                  // The search endpoint answers a bare composite and leaves
                  // the contributing signals on the record. The compact meter
                  // never draws them, so the row says nothing rather than
                  // naming a signal the list response did not carry.
                  riskComponents: const <String>[],
                  riskCalibrated: items[index].data['risk_calibrated'] == true,
                  updatedAt: queueUpdatedAt(items[index]),
                  focusNode: _rowFocusNode(items[index].id),
                  selected:
                      index == _cursor ||
                      items[index].id == controller.selectedId,
                  onOpen: () {
                    setState(() => _cursor = index);
                    _open(items[index]);
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Installs a toast layer only where there is not one already.
///
/// `UiScaffold` hosts the layer for a page built on it. The shell this queue
/// renders inside is still the Material one, so the queue carries its own
/// host until it is not the nearest one any more, at which point this stops
/// installing anything and the shell's layer takes over.
class _ToastLayer extends StatelessWidget {
  const _ToastLayer({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) =>
      UiToastHost.maybeOf(context) == null ? UiToastHost(child: child) : child;
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
    // One record needs review; two need it. The count is read aloud as part
    // of a live region, so the verb has to agree with it.
    final int review = controller.needsReview;
    final String needs = review == 1 ? '1 needs review' : '$review need review';
    return '$loaded. $needs, ${controller.blocked} blocked.';
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
    final UiThemeData ui = context.ui;
    final String? updated = _updated();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Semantics(
            // Its own node, so the screen's name is not read as one phrase
            // with the age of the last answer.
            container: true,
            header: true,
            child: Text(
              'Queue',
              style: ui.type.headline.copyWith(color: ui.color.ink),
            ),
          ),
        ),
        SizedBox(height: ui.space.s1),
        Announcer(
          child: Text(
            _summary(),
            style: ui.type.body.copyWith(color: ui.color.ink),
          ),
        ),
        if (updated != null) ...<Widget>[
          SizedBox(height: ui.space.s1),
          // Outside the live region on purpose: this line changes every
          // second, and a live region that carries it announces the queue
          // once a second rather than when the count moves.
          Semantics(
            container: true,
            child: Text(
              updated,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
            ),
          ),
        ],
      ],
    );
  }
}

/// The disposition filter.
///
/// Six options, which is one more than a `UiSegmented` track takes, so they
/// are filter chips that wrap. A `UiCapsuleToggle` in single mode was the
/// other candidate and was declined: it clears when its chosen option is
/// chosen again, and this filter already has a cleared state of its own
/// called "All", so the control and the product would have had two spellings
/// for one thing. Wrapping also keeps every option reachable, where the
/// horizontal scroll this replaces hid two of the six on a phone.
class _DispositionChips extends StatelessWidget {
  const _DispositionChips({required this.controller});

  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Wrap(
      spacing: ui.space.s2,
      runSpacing: ui.space.s2,
      children: <Widget>[
        for (final MapEntry<String, String> entry in queueDispositions.entries)
          UiChip(
            key: ValueKey<String>('disposition-${entry.key}'),
            label: entry.value,
            variant: UiChipVariant.filter,
            selected: controller.disposition == entry.key,
            // Choosing the chosen one again is not a clear: "All" is where
            // this filter goes when it is cleared, and it is one of the six.
            onPressed: controller.disposition == entry.key
                ? () {}
                : () => unawaited(controller.selectDisposition(entry.key)),
          ),
      ],
    );
  }
}

/// The control that opens the filter sheet, with the active count beside it.
///
/// The count lives on the badge rather than in the button's label, so the
/// button keeps one name at every state and a reader hears the count once.
class _FiltersControl extends StatelessWidget {
  const _FiltersControl({required this.count, required this.onPressed});

  final int count;
  final VoidCallback onPressed;

  /// The button's one label.
  static const String label = 'Filters';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          UiButton(
            label: label,
            variant: UiButtonVariant.secondary,
            leading: UiIcons.filter,
            onPressed: onPressed,
          ),
          if (count > 0) ...<Widget>[
            SizedBox(width: ui.space.s2),
            UiBadge(count, semanticsLabel: activeLabel(count)),
          ],
        ],
      ),
    );
  }

  /// What the badge reads as. Counted, because one filter is not two.
  static String activeLabel(int count) =>
      count == 1 ? '1 filter active' : '$count filters active';
}

/// One removable chip per active filter, so a filter is never invisible once
/// the sheet closes (audit, pass criterion 6.4).
class _ActiveFilterChips extends StatelessWidget {
  const _ActiveFilterChips({required this.controller});

  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Map<String, String> filters = controller.filters;
    // Adding and removing a filter changes the height of the row above the
    // list, so the chips arrive and leave through the shared reveal rather
    // than snapping the rows down (motion catalog, rows 10 and 23).
    return MotionReveal(
      visible: filters.isNotEmpty,
      child: filters.isEmpty
          ? const SizedBox(width: double.infinity)
          : Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s2),
              child: Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: ui.space.s2,
                runSpacing: ui.space.s1,
                children: <Widget>[
                  for (final MapEntry<String, String> entry in filters.entries)
                    UiChip(
                      key: ValueKey<String>('filter-chip-${entry.key}'),
                      label: '${searchFieldLabel(entry.key)}: ${entry.value}',
                      variant: UiChipVariant.input,
                      onRemove: () =>
                          unawaited(controller.removeFilter(entry.key)),
                      removeSemanticsLabel:
                          'Remove the ${searchFieldLabel(entry.key)} filter',
                    ),
                  UiButton(
                    label: 'Clear all',
                    variant: UiButtonVariant.ghost,
                    onPressed: () => unawaited(controller.clearFilters()),
                  ),
                ],
              ),
            ),
    );
  }
}

/// The load more control (motion catalog, row 27).
///
/// The label swaps for the present participle and the button takes its
/// loading ring, so the control keeps its footprint while the request is out.
/// The appended rows have no entrance animation: they arrive below the fold,
/// and animating something nobody can see is decoration.
class _LoadMoreButton extends StatelessWidget {
  const _LoadMoreButton({required this.controller});

  final WorkspaceController controller;

  /// The label, fixed so the copy and the tests cannot drift.
  static const String label = 'Load more records';

  @override
  Widget build(BuildContext context) {
    final bool busy = controller.loadingMore;
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: UiButton(
        label: busy ? 'Loading more…' : label,
        variant: UiButtonVariant.secondary,
        loading: busy,
        onPressed: busy || controller.loading
            ? null
            : () => unawaited(controller.loadMore()),
      ),
    );
  }
}

/// Pull down at the top of the list to ask the server again.
///
/// Built here rather than taken from the design system because the system has
/// no refresh control yet, and `RefreshIndicator` is a Material component this
/// screen may not import. The gesture, the threshold and the ring are the
/// parts that carry the behaviour; everything else is deliberately absent.
//
// TODO(specimen_ui): a UiRefreshControl, so the two lists that pull to refresh
// share one gesture and one indicator. Not a slot's to build until it has an
// entry in 10 section 4, which 10 section 10 asks for before a new component
// exists.
class _PullToRefresh extends StatefulWidget {
  const _PullToRefresh({required this.onRefresh, required this.child});

  /// What a completed pull asks for.
  final Future<void> Function() onRefresh;

  /// The scrollable this wraps.
  final Widget child;

  @override
  State<_PullToRefresh> createState() => _PullToRefreshState();
}

class _PullToRefreshState extends State<_PullToRefresh> {
  /// How far past the top the reviewer has pulled, in logical pixels.
  double _pull = 0;

  /// True from the moment the gesture commits until the answer lands.
  bool _refreshing = false;

  /// How far a pull has to reach before it asks.
  static const double _threshold = 72;

  /// How much of the pull the indicator travels through, so the ring settles
  /// well before the finger runs out of screen.
  static const double _travel = 56;

  bool _onNotification(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    if (_refreshing) return false;
    if (notification is OverscrollNotification &&
        notification.overscroll < 0 &&
        notification.metrics.extentBefore == 0) {
      setState(() => _pull = (_pull - notification.overscroll).clamp(0, 200));
    } else if (notification is ScrollUpdateNotification &&
        _pull > 0 &&
        notification.metrics.extentBefore > 0) {
      setState(() => _pull = 0);
    } else if (notification is ScrollEndNotification) {
      if (_pull >= _threshold) {
        unawaited(_run());
      } else if (_pull > 0) {
        setState(() => _pull = 0);
      }
    }
    return false;
  }

  Future<void> _run() async {
    setState(() {
      _refreshing = true;
      _pull = _travel;
    });
    try {
      await widget.onRefresh();
    } finally {
      if (mounted) {
        setState(() {
          _refreshing = false;
          _pull = 0;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double progress = (_pull / _threshold).clamp(0, 1);
    return NotificationListener<ScrollNotification>(
      onNotification: _onNotification,
      child: Stack(
        children: <Widget>[
          Positioned.fill(child: widget.child),
          if (_pull > 0)
            PositionedDirectional(
              top: (_pull.clamp(0, _travel) - _travel) + ui.space.s4,
              start: 0,
              end: 0,
              child: Align(
                child: Opacity(
                  opacity: progress,
                  child: UiProgress.ring(
                    semanticsLabel: 'Reloading the queue',
                    value: _refreshing ? null : progress,
                  ),
                ),
              ),
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

class _ClearSelectionIntent extends Intent {
  const _ClearSelectionIntent();
}
