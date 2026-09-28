/// The queue (07 section 3).
///
/// A header that states what is loaded, one row per record with the facts a
/// reviewer chooses between rows on, and a list that never moves under a
/// reviewer because a poll answered.
library;

import 'dart:async';
import 'dart:math' as math;

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

/// True where the queue's search row sticks under the header rather than
/// scrolling with the page (13 sections 2.3, 3.5 and 4.2).
///
/// At medium only, and the arithmetic decides it. A stuck row is pinned
/// chrome, and a row holding a text control is 48 dp at default type and
/// 69.75 at 200 percent. At 390 by 844 the frame already pins 172 dp at
/// default type and 185.75 at 200 percent (top bar, one line band, pill) of
/// the 236.3 the phone's 28 percent allows, so the row fits at default type
/// and not at 200 percent, and 13 section 2.3 says a screen over the budget
/// gives a region up rather than shrinking it: the row a reviewer uses once
/// scrolls on a phone (slot A3's decision). At 768 by 1024 the frame pins 124
/// dp at default type and 137.75 at 200 percent (top bar, full band, no pill)
/// of the 245.76 that 24 percent allows, so the row fits at every size:
/// 172 and 207.5, 0.168 and 0.203. From `expanded` up the budget is 20
/// percent of a landscape window: at 1180 by 820 the frame pins 116 dp at
/// default type and 129.75 at 200 percent of 164, and the row at 200 percent
/// is 61.75, which is 191.5 and 0.234; at 1440 by 900 it is 191 of 180 and
/// 0.212. A variant is chosen per class and not per text size, so those two
/// classes scroll the row.
bool searchRowSticks(WindowClass window) => window == WindowClass.medium;

/// How many placeholder rows stand in for the first page.
const int queueSkeletonRows = 5;

/// What the disposition filter is called where it is named rather than drawn
/// as its six options: in the filter sheet, and on the chip that keeps it
/// visible once the sheet closes.
///
/// The same word the sheet's own first group carries, so one filter is not
/// two names.
const String queueDispositionLabel = 'Status';

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

  /// The frame's slots, so the bulk bar goes where 13 section 2.3 puts a
  /// screen's decisions: the scaffold's action bar, above the navigation.
  UiScaffoldSlots? _slots;

  /// The bulk bar itself, built once.
  ///
  /// One instance, published and withdrawn rather than rebuilt: the slot
  /// compares what it is given, and a fresh widget every build would tell the
  /// frame its action bar had changed on every frame the frame itself caused.
  /// The bar listens to the selection and to the collection, so it keeps
  /// itself in step without being republished.
  late final Widget _bulkBar = _QueueSelectionBar(
    selection: _selection,
    onDecide: (BulkDecisionKind kind) => unawaited(_decideOnSelection(kind)),
  );

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
    _slots = UiScaffoldSlots.of(context);
    _publishBulkBar();
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
    _slots?.release(this);
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
    _publishBulkBar();
    if (mounted) setState(() {});
  }

  /// Puts the bulk bar in the frame's action bar while there is a selection,
  /// and gives the slot back when there is not.
  ///
  /// The record is a route pushed over this one, so this pane stays mounted
  /// beneath it; [_current] keeps a selection's bar from following the
  /// reviewer into a record that has its own decision to take.
  void _publishBulkBar() => _slots?.setActionBar(
    _selection.isEmpty || !_current ? null : _bulkBar,
    owner: this,
  );

  /// True while this pane is the route on top.
  ///
  /// `ModalRoute.of` depends on the scope that carries `isCurrent`, so the
  /// pane is rebuilt when a route is pushed over it or popped back off.
  bool _current = true;

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
    // On a phone the six dispositions are not a row of chips above the list,
    // so the sheet is where they are chosen and this is what carries them
    // there and back.
    final bool compact = WindowClass.of(context).isCompact;
    controller.holdList();
    try {
      String? chosen;
      final Map<String, String>? values = await SearchFilters.show(
        context,
        initial: controller.filters,
        configuration: scope?.configuration ?? const <String, dynamic>{},
        savedFilters: scope == null ? null : SavedFilterStore(scope.key),
        dispositions: compact ? queueDispositions : null,
        dispositionLabel: queueDispositionLabel,
        disposition: controller.disposition,
        onDisposition: (String value) => chosen = value,
      );
      if (values == null || !mounted) return;
      // One request per thing that actually changed. Applying a sheet that
      // moved nothing used to ask the server again; a sheet that moved both
      // the disposition and a filter asks twice, which is the honest cost of
      // two controller fields that each reload
      // (`test/app/request_budget_test.dart` holds the ordinary path).
      final bool moved = !mapEquals(values, controller.filters);
      if (chosen != null && chosen != controller.disposition) {
        await controller.selectDisposition(chosen!);
        if (!moved || !mounted) return;
      }
      if (moved) await controller.applyFilters(values);
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
    final bool current = ModalRoute.of(context)?.isCurrent ?? true;
    if (current != _current) {
      _current = current;
      _publishBulkBar();
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
    final bool compact = WindowClass.of(context).isCompact;
    final double gutter = compact ? ui.space.s4 : ui.space.s6;
    final EdgeInsetsGeometry sides = EdgeInsetsDirectional.symmetric(
      horizontal: gutter,
    );

    // One scroll, and the rows are a lazy sliver inside it (13 section 2.1).
    // The page used to be a `ListView(children:)` whose rows were all built at
    // once: a thousand records laid out a thousand rows at every window, which
    // is the defect the client readiness slot measured.
    final Widget list = CustomScrollView(
      // The offset survives a push to a record and back, on a window too
      // narrow to keep the list mounted beside it (pass criterion 6.5).
      key: const PageStorageKey<String>('queue-list'),
      controller: controller.queueScroll,
      slivers: <Widget>[
        SliverPadding(
          padding: EdgeInsetsDirectional.fromSTEB(
            gutter,
            ui.space.s4,
            gutter,
            ui.space.s4,
          ),
          sliver: SliverToBoxAdapter(
            child: _QueueHeader(controller: controller),
          ),
        ),
        _searchBar(context, controller, sides, compact: compact),
        // Six dispositions one tap away wherever there is room for them. On a
        // phone they are in the filter sheet instead, with the chosen one on
        // an active filter chip: 13 section 4.2 gives the queue at compact a
        // header, a search row and the rows, and two controls that both filter
        // the queue are two regions doing one job (13 section 2.4).
        if (!compact)
          SliverPadding(
            padding: EdgeInsetsDirectional.fromSTEB(
              gutter,
              ui.space.s4,
              gutter,
              0,
            ),
            sliver: SliverToBoxAdapter(
              child: _DispositionChips(controller: controller),
            ),
          ),
        SliverPadding(
          padding: sides,
          sliver: SliverToBoxAdapter(
            child: _ActiveFilterChips(
              controller: controller,
              // The disposition is only a chip where it is not already a row
              // of chips above: a filter must never be invisible once the
              // sheet closes (audit, pass criterion 6.4).
              withDisposition: compact,
            ),
          ),
        ),
        SliverPadding(
          padding: EdgeInsetsDirectional.only(top: ui.space.s4),
          sliver: first
              ? _skeleton(ui, controller, sides)
              : items.isEmpty
              ? SliverPadding(
                  padding: sides,
                  sliver: SliverToBoxAdapter(
                    child: _empty(context, controller),
                  ),
                )
              : _rows(context, controller, items, sides),
        ),
        if (controller.nextCursor != null)
          SliverPadding(
            padding: EdgeInsetsDirectional.fromSTEB(
              gutter,
              ui.space.s4,
              gutter,
              0,
            ),
            sliver: SliverToBoxAdapter(
              child: _LoadMoreButton(controller: controller),
            ),
          ),
        // The last row scrolls clear of the floating navigation and of the
        // selection bar above it on a phone: the scaffold says how much
        // clearance the chrome it floats takes (verification report v2, V2-3).
        SliverToBoxAdapter(
          child: SizedBox(
            height: ui.space.s4 + UiScaffold.of(context).bottomInset,
          ),
        ),
      ],
    );

    // Pull to refresh is a touch gesture, and on the web it fights the
    // browser's own pull to refresh, so it is offered on the two touch
    // platforms only (motion catalog, row 21). The list is never cleared
    // while the refresh is out: the rows that are there stay there.
    return _pullToRefresh
        ? _PullToRefresh(onRefresh: controller.refresh, child: list)
        : list;
  }

  /// The search row, stuck under the header where the chrome budget holds it
  /// (13 sections 3.5 and 4.2).
  ///
  /// `UiStickyBar` pins the row once the page has scrolled it up to the
  /// header, and it is pinned chrome while it is stuck, so [searchRowSticks]
  /// weighs the window class. It sticks only while this pane is the route on
  /// top: the record is pushed over the queue and the queue stays mounted
  /// beneath it, and a region a covered screen pins is height the reader
  /// never sees and height the record's own budget would be charged for, the
  /// same reason [_current] keeps a selection's bar out of the record. The
  /// bar's extent is the row's own height and nothing around it: the field is
  /// the taller of its two controls, and its box is `UiInputStyle`'s at the
  /// live text scale, floored at the hit box a pointer density field keeps
  /// (11 section 2.2). The gutter is inside the bar, so the ground it draws
  /// reaches the window's edges.
  Widget _searchBar(
    BuildContext context,
    WorkspaceController controller,
    EdgeInsetsGeometry sides, {
    required bool compact,
  }) {
    final UiThemeData ui = context.ui;
    final Widget row = Padding(
      padding: sides,
      child: _SearchRow(
        controller: _search,
        focusNode: _searchFocus,
        onChanged: controller.search,
        filterCount: _activeFilterCount(controller, compact: compact),
        onFilters: () => unawaited(_openFilters()),
      ),
    );
    if (!_current || !searchRowSticks(WindowClass.of(context))) {
      return SliverToBoxAdapter(child: row);
    }
    return UiStickyBar(
      extent: math.max(
        UiDensity.hitBox,
        UiInputStyle.resolve(
          ui,
          UiFieldShape.capsule,
          textScaler: MediaQuery.textScalerOf(context),
        ).minHeight,
      ),
      child: row,
    );
  }

  /// What the filter control's badge counts.
  ///
  /// The sheet's own filters, and the disposition as well on the window where
  /// the disposition is only in the sheet.
  int _activeFilterCount(
    WorkspaceController controller, {
    required bool compact,
  }) =>
      controller.activeFilterCount +
      (compact && controller.disposition.isNotEmpty ? 1 : 0);

  /// The search field's one label, so the control, its hint and the tests
  /// cannot word it three ways.
  static const String searchLabel = 'Search by specimen ID';

  /// What the field matches, as the placeholder and as the semantics hint.
  ///
  /// It used to be a drawn footer saying "Exact match. Use Filters for
  /// anything else." The filter control now sits beside the field, which says
  /// the second half better than a sentence does (13 section 2.4), and a
  /// footer that wraps to three lines at 200 percent text is a third of a
  /// phone spent on a hint.
  static const String searchHint = 'Specimen ID, exact match';

  /// True on the two platforms whose pull gesture is the app's to own.
  bool get _pullToRefresh =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.android);

  Widget _skeleton(
    UiThemeData ui,
    WorkspaceController controller,
    EdgeInsetsGeometry sides,
  ) => SliverPadding(
    padding: sides,
    sliver: SliverToBoxAdapter(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          // Keyed on the collection, so switching collections while the first
          // load is still out builds a new announcer and says "Loading queue"
          // again. The body's own key is the same string in both loads, so
          // without this the element was reused and the second collection
          // loaded in silence: the placeholders are hidden from the semantics
          // tree and there is nothing else on the screen to hear.
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
      ),
    ),
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
  /// A lazy `SliverList`: the list builds the rows its viewport holds and no
  /// others, so a collection of a thousand records lays out the dozen on
  /// screen. The rows themselves never animate in: they existed before the
  /// rebuild, and an entrance animation on an existing row is on the
  /// blocklist.
  Widget _rows(
    BuildContext context,
    WorkspaceController controller,
    List<Specimen> items,
    EdgeInsetsGeometry sides,
  ) {
    // A window wide enough for a checkbox column keeps one open, so a
    // reviewer on a pointer never has to discover a gesture. A narrow one
    // reveals it on a long press and hides it again when the selection
    // empties (07 section 3, "Multi-select"). The window decides, never the
    // platform.
    final bool column =
        WindowClass.of(context).isAtLeast(WindowClass.medium) ||
        _selection.active;
    return SliverPadding(
      padding: sides,
      // One node around the whole list, which holds the poll still while a
      // row has keyboard focus. A sliver cannot carry it, so the focus node
      // is the list's own sliver wrapper rather than a box around the rows.
      sliver: SliverMainAxisGroup(
        slivers: <Widget>[
          SliverList.builder(
            itemCount: items.length,
            findChildIndexCallback: (Key key) {
              final int index = items.indexWhere(
                (Specimen item) =>
                    key == ValueKey<String>('queue-row-${item.id}'),
              );
              return index < 0 ? null : index;
            },
            itemBuilder: (BuildContext context, int index) => KeyedSubtree(
              key: ValueKey<String>('queue-row-${items[index].id}'),
              child: _QueueListRow(
                specimen: items[index],
                selected: _selection.isSelected(items[index]),
                showCheckbox: column,
                cursor:
                    index == _cursor ||
                    items[index].id == controller.selectedId,
                focusNode: _rowFocusNode(items[index].id),
                onToggle: () => _selection.toggle(items[index]),
                onExtend: () => _selection.selectRange(items[index]),
                onLongPress: column
                    ? null
                    : () => _selection.select(items[index]),
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

/// One record in the queue, with the selection affordance beside it.
///
/// Its own widget so the sliver list builds one row per visible record rather
/// than a closure over the whole page.
class _QueueListRow extends StatelessWidget {
  const _QueueListRow({
    required this.specimen,
    required this.selected,
    required this.showCheckbox,
    required this.cursor,
    required this.focusNode,
    required this.onToggle,
    required this.onExtend,
    required this.onLongPress,
    required this.onOpen,
  });

  final Specimen specimen;
  final bool selected;
  final bool showCheckbox;
  final bool cursor;
  final FocusNode focusNode;
  final VoidCallback onToggle;
  final VoidCallback onExtend;
  final VoidCallback? onLongPress;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) => SelectableRow(
    selected: selected,
    label: specimen.title,
    showCheckbox: showCheckbox,
    onToggle: onToggle,
    onExtend: onExtend,
    onLongPress: onLongPress,
    child: QueueRow(
      id: specimen.id,
      title: specimen.title,
      reason: queueReason(specimen),
      status: SpecimenStatus.fromWire(specimen.disposition ?? specimen.state),
      riskComposite: specimen.data['risk'] as num?,
      // The search endpoint answers a bare composite and leaves the
      // contributing signals on the record. The compact meter never draws
      // them, so the row says nothing rather than naming a signal the list
      // response did not carry.
      riskComponents: const <String>[],
      riskCalibrated: specimen.data['risk_calibrated'] == true,
      updatedAt: queueUpdatedAt(specimen),
      focusNode: focusNode,
      selected: cursor,
      onOpen: onOpen,
    ),
  );
}

/// The bulk bar, in the frame's action bar (13 sections 2.3 and 3.3).
///
/// It used to float over the list on a pane of its own, which is a second
/// frosted pane on a phone where the budget is one and a bar the list's own
/// column had to leave room for. The scaffold floats one thing, and this is
/// what a list screen gives it while there is a selection to act on.
///
/// It reads the selection and the collection itself rather than being handed
/// their values, so the pane it is published into stays in step without the
/// screen republishing it every frame.
class _QueueSelectionBar extends StatelessWidget {
  const _QueueSelectionBar({required this.selection, required this.onDecide});

  /// What the reviewer has picked out of the loaded page.
  final PagedSelection<Specimen> selection;

  /// Takes one bulk decision across the whole selection.
  final void Function(BulkDecisionKind kind) onDecide;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: selection,
    builder: (BuildContext context, Widget? child) {
      final WorkspaceController controller = WorkspaceScope.of(context);
      return SelectionBar(
        // The scaffold's action bar is already the pane, and a pane inside a
        // pane is the depth 13 section 2.2 counts.
        pane: false,
        count: selection.count,
        loadedCount: selection.loadedCount,
        moreToLoad: selection.moreToLoad,
        allLoadedSelected: selection.allLoadedSelected,
        onSelectAllLoaded: selection.selectAllLoaded,
        onClear: selection.clear,
        busy: controller.mutating,
        actions: <SelectionAction>[
          for (final BulkDecisionKind kind in BulkDecisionKind.values)
            (
              label: kind.label,
              icon: kind.icon,
              onPressed: () => onDecide(kind),
            ),
        ],
      );
    },
  );
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
    return '$loaded. ${_breakdown()}';
  }

  /// What the loaded page is made of, as the line under the numeral.
  String _breakdown() {
    final WorkspaceController controller = widget.controller;
    // One record needs review; two need it. The count is read aloud as part
    // of a live region, so the verb has to agree with it.
    final int review = controller.needsReview;
    final String needs = review == 1 ? '1 needs review' : '$review need review';
    return '$needs, ${controller.blocked} blocked.';
  }

  /// The unit beside the numeral (09 section 4.2, the `unit` role).
  String _unit() => widget.controller.items.length == 1 ? 'RECORD' : 'RECORDS';

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
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: <Widget>[
            Expanded(
              child: Semantics(
                // Its own node, so the screen's name is not read as one
                // phrase with the count beside it.
                container: true,
                header: true,
                child: Text(
                  'Queue',
                  style: ui.type.headline.copyWith(color: ui.color.ink),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
            SizedBox(width: ui.space.s2),
            // The count as a numeral with its unit (13 section 4.2). 09
            // section 4.2 names `display.medium` for exactly this number and
            // `unit` for the upper case word beside it. The whole sentence
            // stays on the live region below, so a reader hears what is
            // loaded and what it is made of rather than a bare numeral.
            _CountNumeral(count: widget.controller.items.length, unit: _unit()),
          ],
        ),
        SizedBox(height: ui.space.s1),
        Announcer(
          child: Semantics(
            label: _summary(),
            excludeSemantics: true,
            child: Text(
              _breakdown(),
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
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

/// The loaded count, as a numeral with its unit (09 section 4.2).
///
/// Tabular figures, so a digit that changes is visible by position, and the
/// pair is one semantics node under the header's own live region rather than
/// two fragments a reader hears as "four" and then "records".
class _CountNumeral extends StatelessWidget {
  const _CountNumeral({required this.count, required this.unit});

  final int count;
  final String unit;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return ExcludeSemantics(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: <Widget>[
          Text(
            '$count',
            style: ui.type.displayMedium.copyWith(color: ui.color.ink),
            maxLines: 1,
          ),
          SizedBox(width: ui.space.s2),
          Text(
            unit,
            style: ui.type.unit.copyWith(color: ui.color.inkTertiary),
            maxLines: 1,
          ),
        ],
      ),
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

/// The search field with the filter control beside it (13 section 4.2).
///
/// One region, one job: narrow the list. It scrolls with the header rather
/// than sticking under the top bar, which is what 13 section 4.2 asks for and
/// what 13 section 2.3 refuses: at 390 by 844 and 200 percent text the queue
/// already pins 185.75 dp of top bar, band and navigation against a budget of
/// 236.3, and a row holding a text control is 69.75 dp of the 50.6 that
/// leaves. Section 2.3 says a screen over the budget gives a region up rather
/// than shrinking one below its density height, and the row a reviewer uses
/// once is the one to give up. The finding is recorded against 13 section 4.2
/// rather than worked around.
class _SearchRow extends StatelessWidget {
  const _SearchRow({
    required this.controller,
    required this.focusNode,
    required this.onChanged,
    required this.filterCount,
    required this.onFilters,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onChanged;
  final int filterCount;
  final VoidCallback onFilters;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        Expanded(
          child: UiSearchField(
            label: _QueuePaneState.searchLabel,
            hintText: _QueuePaneState.searchHint,
            clearLabel: 'Clear the search',
            controller: controller,
            focusNode: focusNode,
            onChanged: onChanged,
          ),
        ),
        SizedBox(width: ui.space.s2),
        _FiltersControl(count: filterCount, onPressed: onFilters),
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
    return Row(
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
    );
  }

  /// What the badge reads as. Counted, because one filter is not two.
  static String activeLabel(int count) =>
      count == 1 ? '1 filter active' : '$count filters active';
}

/// One removable chip per active filter, so a filter is never invisible once
/// the sheet closes (audit, pass criterion 6.4).
class _ActiveFilterChips extends StatelessWidget {
  const _ActiveFilterChips({
    required this.controller,
    this.withDisposition = false,
  });

  final WorkspaceController controller;

  /// True where the disposition is only in the sheet, so this row is the one
  /// place it is visible once the sheet closes.
  final bool withDisposition;

  /// What the chosen disposition is called, or null where every record shows.
  String? get _disposition {
    if (!withDisposition) return null;
    final String chosen = controller.disposition;
    if (chosen.isEmpty) return null;
    return queueDispositions[chosen];
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Map<String, String> filters = controller.filters;
    final String? disposition = _disposition;
    final bool any = filters.isNotEmpty || disposition != null;
    // Adding and removing a filter changes the height of the row above the
    // list, so the chips arrive and leave through the shared reveal rather
    // than snapping the rows down (motion catalog, rows 10 and 23).
    return MotionReveal(
      visible: any,
      child: !any
          ? const SizedBox(width: double.infinity)
          : Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s2),
              child: Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: ui.space.s2,
                runSpacing: ui.space.s1,
                children: <Widget>[
                  if (disposition != null)
                    UiChip(
                      key: const ValueKey<String>('filter-chip-disposition'),
                      label: '$queueDispositionLabel: $disposition',
                      variant: UiChipVariant.input,
                      onRemove: () =>
                          unawaited(controller.selectDisposition('')),
                      removeSemanticsLabel: 'Remove the disposition filter',
                    ),
                  for (final MapEntry<String, String> entry in filters.entries)
                    UiChip(
                      key: ValueKey<String>('filter-chip-${entry.key}'),
                      label:
                          '${searchFieldLabel(entry.key)}: '
                          '${searchValueLabel(entry.key, entry.value)}',
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
