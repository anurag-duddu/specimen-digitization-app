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
import '../../app/shell.dart';
import '../../models.dart';
import '../../reason_codes.dart';
import '../../selection.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import '../../workspace.dart';

/// The width of the list pane in the list detail layout (05 section 3.2).
const double queueListPaneWidth = 320;

/// How many placeholder rows stand in for the first page.
const int queueSkeletonRows = 5;

/// The first specific issue that distinguishes this record in its queue.
/// Shared review state and unavailable telemetry do not add an action.
String queueReason(Specimen specimen) {
  final Json data = specimen.data;
  const sharedStates = <String>{
    'human_approval_required',
    'human_review_required',
    'needs_human_review',
    'deferred',
    'running',
    'processing_blocked',
    'cleared',
    'unmeasured',
    'uncalibrated',
    'not_measured',
    'not_calibrated',
    'risk_unmeasured',
    'risk_uncalibrated',
    'risk_not_measured',
    'risk_not_calibrated',
  };
  for (final Object? value in <Object?>[
    for (final Json finding in specimen.findings) finding['message'],
    data['blocker'],
    ...data['reason_codes'] as List? ?? const <Object?>[],
  ]) {
    if (value is! String || value.trim().isEmpty) continue;
    final String normalized = value.trim().toLowerCase().replaceAll(' ', '_');
    if (sharedStates.contains(normalized)) {
      continue;
    }
    return vocabularyLabel(value.trim());
  }
  return '';
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
  Widget build(BuildContext context) {
    final shell = AppSidebarScope.maybeOf(context);
    return shell?.mobileSpecimens ?? const _NoRecordSelected();
  }
}

class _NoRecordSelected extends StatelessWidget {
  const _NoRecordSelected();

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: context.ui.color.ground,
    child: const Center(
      child: UiEmptyState(
        icon: UiIcons.record,
        title: 'No record open',
        body: 'Choose a specimen to review.',
      ),
    ),
  );
}

/// Commands routed from the common workspace shortcut scope to the queue.
class QueueKeyboardController extends ChangeNotifier {
  _QueuePaneState? _owner;
  bool _notificationScheduled = false;
  bool _disposed = false;

  bool get canBrowse => _owner?._listening?.scope != null;
  bool get canSelect => _owner?._listening?.items.isNotEmpty ?? false;
  bool get selecting => _owner?._selection.active ?? false;

  void showView(String value) =>
      unawaited(_owner?._listening?.selectDisposition(value));

  void move(int delta) => _owner?._move(delta);
  void open() => _owner?._openSelected();
  void clear() => _owner?._selection.clear();
  void toggleSelection() {
    final selection = _owner?._selection;
    if (selection == null) return;
    selection.active ? selection.clear() : selection.begin();
  }

  // The queue may mount or reconcile during layout. Publish the header
  // affordance after that frame so its sibling never rebuilds during build.
  void _notifyChanged() {
    if (_disposed || _notificationScheduled) return;
    _notificationScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _notificationScheduled = false;
      if (!_disposed) notifyListeners();
    });
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

/// Ends an active selection beside the collection switcher.
class QueueListActions extends StatelessWidget {
  const QueueListActions({required this.controller, super.key});
  final QueueKeyboardController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: controller,
    builder: (context, child) => controller.selecting
        ? UiIconButton(
            key: const ValueKey<String>('queue-select-records'),
            icon: UiIcons.check,
            semanticsLabel: 'Done selecting',
            tooltip: 'Done selecting',
            onPressed: controller.toggleSelection,
          )
        : const SizedBox.shrink(),
  );
}

/// The queue itself: search, review views and selectable records.
class QueuePane extends StatefulWidget {
  const QueuePane({
    this.searchFocusNode,
    this.controller,
    this.onDismiss,
    super.key,
  });

  /// An optional caller-owned node for search shortcuts above both panes.
  final FocusNode? searchFocusNode;
  final QueueKeyboardController? controller;

  /// Dismisses a summoned queue on Escape. An ordinary queue clears selection.
  final VoidCallback? onDismiss;

  @override
  State<QueuePane> createState() => _QueuePaneState();
}

class _QueuePaneState extends State<QueuePane> {
  final TextEditingController _search = TextEditingController();
  final FocusNode _ownedSearchFocus = FocusNode(debugLabel: 'Queue search');
  FocusNode get _searchFocus => widget.searchFocusNode ?? _ownedSearchFocus;
  int? _cursor;

  /// The records this reviewer has picked out of the loaded page.
  ///
  /// Shared with every other list a reviewer picks from, so the browse screen
  /// over a data source gets the same reach, the same keyboard behaviour and
  /// the same honesty about what a select all could not see.
  final PagedSelection<Specimen> _selection = PagedSelection<Specimen>(
    identify: (Specimen specimen) => specimen.id,
    limit: bulkDecisionLimit,
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

  BulkSelectionEligibility? _eligibility;
  int _eligibilityGeneration = 0;
  String _eligibilityKey = '';
  bool _checkingDecision = false;

  /// This reviewer's own recent reasons, offered as chips in the
  /// confirmation exactly as the workbench offers them.
  List<String> _recentReasons = <String>[];
  RecentReasonStore _reasonStore = const RecentReasonStore('');

  @override
  void initState() {
    super.initState();
    widget.controller?._owner = this;
    widget.controller?._notifyChanged();
    _selection.addListener(_onSelectionChanged);
  }

  @override
  void didUpdateWidget(QueuePane oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      if (oldWidget.controller?._owner == this) {
        oldWidget.controller?._owner = null;
        oldWidget.controller?._notifyChanged();
      }
      widget.controller?._owner = this;
      widget.controller?._notifyChanged();
    }
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
    if (widget.controller?._owner == this) {
      widget.controller?._owner = null;
      widget.controller?._notifyChanged();
    }
    _listening?.removeListener(_syncSelection);
    _selection.removeListener(_onSelectionChanged);
    if (_holdingForSelection) _listening?.releaseList();
    _selection.dispose();
    _search.dispose();
    _ownedSearchFocus.dispose();
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
    _refreshEligibility();
    widget.controller?._notifyChanged();
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
    _refreshEligibility();
    widget.controller?._notifyChanged();
    if (mounted) setState(() {});
  }

  void _refreshEligibility({bool force = false}) {
    final chosen = _selection.items;
    final key =
        '${_controller.scope?.key}:${chosen.map((s) => '${s.id}@${s.recordVersionId}').join(',')}';
    if (!force && key == _eligibilityKey) return;
    _eligibilityKey = key;
    final generation = ++_eligibilityGeneration;
    _eligibility = null;
    if (chosen.isEmpty) return;
    unawaited(
      _controller.inspectSelection(chosen).then((evidence) {
        if (mounted && generation == _eligibilityGeneration) {
          setState(() => _eligibility = evidence);
        }
      }),
    );
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
    final scope = controller.scope;
    if (chosen.isEmpty || controller.mutating) return;
    if (_checkingDecision) return;
    setState(() => _checkingDecision = true);
    final evidence = await controller.inspectSelection(chosen);
    if (!mounted) return;
    if (!identical(scope, controller.scope) ||
        !_selection.ids.containsAll(chosen.map((s) => s.id))) {
      setState(() => _checkingDecision = false);
      return;
    }
    setState(() {
      _checkingDecision = false;
      _eligibility = evidence;
    });
    final eligible = evidence.eligibleFor(kind);
    if (eligible.isEmpty) return;
    final Map<String, String> names = {
      for (final specimen in chosen) specimen.id: specimen.title,
    };
    final int count = eligible.length;
    final int excluded = chosen.length - count;
    controller.holdList();
    final String? reason;
    try {
      reason = await showReasonSheet(
        context,
        title: kind.title(count),
        action: kind.action(count),
        consequence:
            '${kind.consequence(count)}${excluded == 0 ? '' : ' $excluded of ${chosen.length} selected records are not eligible and will remain selected.'}',
        retained: kind.retained,
        recentReasons: _recentReasons,
      );
    } finally {
      controller.releaseList();
    }
    if (reason == null ||
        !mounted ||
        !identical(scope, controller.scope) ||
        !_selection.ids.containsAll(chosen.map((s) => s.id))) {
      return;
    }
    final BulkDecisionReport? result = await controller.reviewSelection(
      eligible,
      kind,
      reason,
    );
    if (!mounted) return;
    // A call that did not complete leaves the selection alone: the reviewer's
    // work is still on screen, and the controller's banner says what happened.
    if (result == null) return;
    final eligibleIds = eligible.map((s) => s.id).toSet();
    final report = BulkDecisionReport([
      ...result.results,
      for (final specimen in chosen)
        if (!eligibleIds.contains(specimen.id))
          BulkDecisionResult(
            specimenId: specimen.id,
            outcome: BulkOutcome.skipped,
            message:
                evidence.reasonFor(specimen.id, kind) ??
                'Not included in this confirmation.',
          ),
    ]);
    unawaited(_rememberReason(reason));
    _selection.removeIds(
      report.results.where((row) => row.changed).map((row) => row.specimenId),
    );
    if (_selection.isEmpty) {
      await controller.refresh();
    } else {
      _refreshEligibility(force: true);
    }
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
    unawaited(_open(items[cursor.clamp(0, items.length - 1)]));
  }

  Future<void> _open(Specimen specimen) async {
    final WorkspaceController controller = _controller;
    final CollectionScope? scope = controller.scope;
    if (scope == null) return;
    if (!await controller.mayLeaveReview() || !mounted) return;
    QueueWorkspaceScope.maybeOf(context)?.hideQueue();
    context.go(
      AppRoutes.specimenOf(encodeCollectionKey(scope.key), specimen.id),
    );
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
        SingleActivator(LogicalKeyboardKey.keyS, shift: true):
            _ToggleFocusedRowIntent(),
        SingleActivator(LogicalKeyboardKey.slash): _FocusSearchIntent(),
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
          _ToggleFocusedRowIntent: CallbackAction<_ToggleFocusedRowIntent>(
            onInvoke: (_) {
              if (controller.mutating || _checkingDecision) return null;
              final focused = controller.items
                  .where((item) => _rowFocus[item.id]?.hasFocus ?? false)
                  .firstOrNull;
              if (focused != null) _selection.toggle(focused);
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
          // Escape dismisses a summoned queue or clears an ordinary queue's
          // selection, including while search owns the caret. Descendant
          // menus and dialogs retain their own Escape handling first.
          _ClearSelectionIntent: CallbackAction<_ClearSelectionIntent>(
            onInvoke: (_) {
              final dismiss = widget.onDismiss;
              if (dismiss != null) {
                dismiss();
              } else {
                _selection.clear();
              }
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
              child: ColoredBox(
                color: context.ui.color.paper,
                child: Column(
                  children: [
                    Expanded(flex: 3, child: _body(context, controller)),
                    if (_selection.isNotEmpty)
                      Flexible(
                        flex: 2,
                        fit: FlexFit.loose,
                        child: SingleChildScrollView(
                          child: _QueueSelectionBar(
                            selection: _selection,
                            eligibility: _eligibility,
                            checking: _checkingDecision,
                            onRetry: () => setState(
                              () => _refreshEligibility(force: true),
                            ),
                            onDecide: (kind) =>
                                unawaited(_decideOnSelection(kind)),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, WorkspaceController controller) =>
      LayoutBuilder(
        builder: (context, constraints) => _list(
          context,
          controller,
          UiLayoutMetrics.fromConstraints(
            constraints,
            textScaler: MediaQuery.textScalerOf(context),
          ),
        ),
      );

  Widget _list(
    BuildContext context,
    WorkspaceController controller,
    UiLayoutMetrics layout,
  ) {
    final UiThemeData ui = context.ui;
    final List<Specimen> items = controller.items;
    // Placeholders until the server has answered at least once, never a claim
    // about the collection. A deep link used to cancel the queue load and
    // leave this pane saying "No specimens yet" about a collection with
    // records (finding V-5); a list that has never been answered says only
    // that it is loading.
    final bool first = items.isEmpty && !controller.listAnswered;
    final double gutter = layout.gutter;
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
            ui.space.s2,
            gutter,
            ui.space.s2,
          ),
          sliver: SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                _SearchRow(
                  controller: _search,
                  focusNode: _searchFocus,
                  onChanged: controller.search,
                  onEscape: widget.onDismiss,
                ),
                SizedBox(height: ui.space.s2),
                _StatusControls(controller: controller),
              ],
            ),
          ),
        ),
        SliverPadding(
          padding: EdgeInsetsDirectional.zero,
          sliver: first
              ? _skeleton(ui, controller, sides)
              : items.isEmpty
              ? SliverPadding(
                  padding: sides,
                  sliver: SliverToBoxAdapter(
                    child: _empty(context, controller),
                  ),
                )
              : _rows(context, controller, items, sides, layout),
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

  /// The search field's one label, so the control, its hint and the tests
  /// cannot word it three ways.
  static const String searchLabel = 'Search by full specimen ID';

  /// Search matches the exact specimen identifier the API accepts.
  static const String searchHint = 'Specimen ID';

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

  Widget _empty(BuildContext context, WorkspaceController controller) {
    if (controller.unfiltered) {
      return UiEmptyState(
        icon: UiIcons.queue,
        title: 'No specimens yet',
        body: 'Add specimens to this collection.',
        action: UiButton(
          label: 'Add specimens',
          onPressed: () {
            final CollectionScope? scope = controller.scope;
            if (scope == null) return;
            context.go(AppRoutes.intakeOf(encodeCollectionKey(scope.key)));
          },
        ),
      );
    }
    if (controller.query.trim().isEmpty && controller.activeFilterCount == 0) {
      return Padding(
        padding: EdgeInsets.symmetric(vertical: context.ui.space.s4),
        child: Text(
          switch (controller.disposition) {
            'needs_human_review' => 'No specimens need a human',
            'deferred' => 'No deferred specimens',
            'cleared' => 'No cleared specimens',
            _ => 'No specimens in this view',
          },
          style: context.ui.type.bodySmall.copyWith(
            color: context.ui.color.inkSecondary,
          ),
        ),
      );
    }
    return UiEmptyState(
      icon: UiIcons.noResults,
      title: 'No matching records',
      body: 'Try another specimen ID.',
      action: UiButton(
        label: 'Reset search',
        onPressed: () => unawaited(controller.clearFilters()),
      ),
    );
  }

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
    UiLayoutMetrics layout,
  ) {
    // A window wide enough for a checkbox column keeps one open, so a
    // reviewer on a pointer never has to discover a gesture. A narrow one
    // reveals it on a long press and hides it again when the selection
    // empties (07 section 3, "Multi-select"). The window decides, never the
    // platform.
    final bool column = _selection.active;
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
                disabledReason: controller.mutating || _checkingDecision
                    ? 'Wait for the current selection check or decision to finish.'
                    : _selection.atLimit && !_selection.isSelected(items[index])
                    ? 'Select at most $bulkDecisionLimit records for one decision.'
                    : null,
                showCheckbox: column,
                cursor: items[index].id == controller.selectedId,
                focusNode: _rowFocusNode(items[index].id),
                onToggle: () => _selection.toggle(items[index]),
                onExtend: () => _selection.selectRange(items[index]),
                onLongPress: column
                    ? null
                    : () => _selection.select(items[index]),
                onOpen: () {
                  setState(() => _cursor = index);
                  unawaited(_open(items[index]));
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
    required this.disabledReason,
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
  final String? disabledReason;
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
    enabled: disabledReason == null,
    disabledReason: disabledReason,
    label: specimen.displayReference,
    showCheckbox: showCheckbox,
    onToggle: onToggle,
    onExtend: onExtend,
    onLongPress: onLongPress,
    child: QueueRow(
      id: specimen.id,
      title: specimen.displayReference,
      concise: true,
      showStatus: false,
      reason: queueReason(specimen),
      status: SpecimenStatus.ofRecord(
        disposition: specimen.disposition,
        state: specimen.state,
      ),
      riskComposite: specimen.data['risk'] is num
          ? specimen.data['risk'] as num
          : null,
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

/// Bulk actions belong to the visible queue, including in list-detail layouts.
class _QueueSelectionBar extends StatelessWidget {
  const _QueueSelectionBar({
    required this.selection,
    required this.eligibility,
    required this.checking,
    required this.onDecide,
    required this.onRetry,
  });
  final PagedSelection<Specimen> selection;
  final BulkSelectionEligibility? eligibility;
  final bool checking;
  final void Function(BulkDecisionKind kind) onDecide;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final controller = WorkspaceScope.of(context);
    final ui = context.ui;
    final pending = eligibility == null || checking;
    final counts = {
      for (final kind in BulkDecisionKind.values)
        kind: eligibility?.eligibleFor(kind).length ?? 0,
    };
    return DecoratedBox(
      decoration: BoxDecoration(
        color: ui.color.paper,
        border: Border(top: BorderSide(color: ui.color.hairline)),
      ),
      child: Padding(
        padding: EdgeInsets.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              pending
                  ? 'Checking current permissions...'
                  : '${counts[BulkDecisionKind.approve]} eligible for approval, ${counts[BulkDecisionKind.confirmCoverage]} for coverage.',
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
            SizedBox(height: ui.space.s2),
            SelectionBar(
              pane: false,
              count: selection.count,
              loadedCount: selection.loadedCount,
              moreToLoad: selection.moreToLoad,
              allLoadedSelected: selection.allLoadedSelected,
              selectionLimit: bulkDecisionLimit,
              onSelectAllLoaded: selection.selectAllLoaded,
              onClear: selection.clear,
              busy: controller.mutating || checking,
              actionReasons: {
                for (final kind in BulkDecisionKind.values)
                  kind.label: pending
                      ? 'Wait for current permissions to be checked.'
                      : 'None of the selected records currently permit this action. Check permissions again or review each record.',
              },
              actions: [
                for (final kind in BulkDecisionKind.values)
                  (
                    label: kind.label,
                    icon: kind.icon,
                    onPressed: pending || counts[kind] == 0
                        ? null
                        : () => onDecide(kind),
                  ),
              ],
            ),
            if (selection.atLimit)
              Text(
                'Limit of $bulkDecisionLimit records reached. Clear some selections to choose others.',
                style: ui.type.bodySmall,
              ),
            if (!pending &&
                counts.values.any((count) => count < selection.count))
              UiButton(
                label: 'Check permissions again',
                variant: UiButtonVariant.ghost,
                onPressed: controller.mutating ? null : onRetry,
              ),
          ],
        ),
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

/// Three review views, with the active name and an icon for each view.
class _StatusControls extends StatefulWidget {
  const _StatusControls({required this.controller});
  final WorkspaceController controller;

  @override
  State<_StatusControls> createState() => _StatusControlsState();
}

class _StatusControlsState extends State<_StatusControls> {
  static const views = <({String value, String label, IconSpec icon})>[
    (
      value: 'needs_human_review',
      label: 'Needs a human',
      icon: UiIcons.needsReview,
    ),
    (value: 'deferred', label: 'Deferred', icon: UiIcons.deferred),
    (value: 'cleared', label: 'Cleared', icon: UiIcons.cleared),
  ];
  final _focusNodes = <FocusNode>[
    for (final view in views) FocusNode(debugLabel: view.label),
  ];

  @override
  void dispose() {
    for (final node in _focusNodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _select(int index) {
    _focusNodes[index].requestFocus();
    unawaited(widget.controller.selectDisposition(views[index].value));
  }

  KeyEventResult _handleKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final index = _focusNodes.indexWhere((node) => node.hasFocus);
    if (index < 0) return KeyEventResult.ignored;
    final key = event.logicalKey;
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final int next;
    if (key == LogicalKeyboardKey.arrowRight) {
      next = (index + (rtl ? -1 : 1)) % views.length;
    } else if (key == LogicalKeyboardKey.arrowLeft) {
      next = (index + (rtl ? 1 : -1)) % views.length;
    } else if (key == LogicalKeyboardKey.arrowDown) {
      next = (index + 1) % views.length;
    } else if (key == LogicalKeyboardKey.arrowUp) {
      next = (index - 1) % views.length;
    } else if (key == LogicalKeyboardKey.home) {
      next = 0;
    } else if (key == LogicalKeyboardKey.end) {
      next = views.length - 1;
    } else {
      return KeyEventResult.ignored;
    }
    _select(next);
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final active = views.indexWhere(
      (view) => view.value == widget.controller.disposition,
    );
    return Focus(
      canRequestFocus: false,
      skipTraversal: true,
      onKeyEvent: _handleKey,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (active < 0) ...[
            Expanded(
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: UiDensity.hitBox),
                child: Align(
                  alignment: AlignmentDirectional.centerStart,
                  heightFactor: 1,
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      widget.controller.disposition.isEmpty
                          ? 'All specimens'
                          : queueDispositions[widget.controller.disposition] ??
                                'Specimens',
                      style: ui.type.label,
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(width: ui.space.s2),
          ],
          for (var index = 0; index < views.length; index++) ...[
            if (index > 0) SizedBox(width: ui.space.s2),
            if (active == index)
              Expanded(child: _filter(context, index))
            else
              SizedBox(width: UiDensity.hitBox, child: _filter(context, index)),
          ],
        ],
      ),
    );
  }

  Widget _filter(BuildContext context, int index) {
    final ui = context.ui;
    final view = views[index];
    final selected = view.value == widget.controller.disposition;
    return UiTooltip(
      message: view.label,
      child: Pressable(
        key: ValueKey<String>('queue-filter-${view.value}'),
        semanticsLabel: view.label,
        role: PressableRole.radio,
        selected: selected,
        focusNode: _focusNodes[index],
        onPressed: () => _select(index),
        builder: (context, states) => DecoratedBox(
          decoration: ShapeDecoration(
            shape: Squircle.border(ui.shape.inner),
            color: selected
                ? ui.color.ground
                : ui.color.paper.withValues(alpha: 0),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: UiDensity.hitBox),
            child: Padding(
              padding: EdgeInsets.all(ui.space.s2),
              child: Row(
                mainAxisAlignment: selected
                    ? MainAxisAlignment.start
                    : MainAxisAlignment.center,
                children: [
                  UiIcon(view.icon, size: UiIconSize.inline),
                  if (selected) ...[
                    SizedBox(width: ui.space.s2),
                    Expanded(child: Text(view.label, style: ui.type.label)),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Exact specimen-ID search, with no secondary filter workflow.
class _SearchRow extends StatelessWidget {
  const _SearchRow({
    required this.controller,
    required this.focusNode,
    required this.onChanged,
    this.onEscape,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onChanged;
  final VoidCallback? onEscape;

  @override
  Widget build(BuildContext context) => UiSearchField(
    label: _QueuePaneState.searchLabel,
    hintText: _QueuePaneState.searchHint,
    clearLabel: 'Clear the search',
    controller: controller,
    focusNode: focusNode,
    onChanged: onChanged,
    onEscape: onEscape,
  );
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

class _ToggleFocusedRowIntent extends Intent {
  const _ToggleFocusedRowIntent();
}

class _FocusSearchIntent extends Intent {
  const _FocusSearchIntent();
}

class _ClearSelectionIntent extends Intent {
  const _ClearSelectionIntent();
}
