/// The collection workspace: the state every collection screen reads, and the
/// shell the router renders it inside (screen blueprints, sections 1 and 3).
///
/// The controller lives above the router so a redirect can ask which
/// collections this account has before a screen is built, and so the queue
/// keeps its records, its scroll offset and its poll across a route change.
library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';

import 'app/shell.dart';
import 'auth.dart';
import 'models.dart';
import 'widgets/editing_safe_shortcut.dart';
import 'screens/queue/queue_screen.dart';
import 'screens/intake/intake_transfer_session.dart';

/// How often the queue asks the server for the current page.
const Duration queuePollInterval = Duration(seconds: 20);

/// How long the search field waits after the last keystroke.
const Duration searchDebounce = Duration(milliseconds: 350);

/// The two collection destinations.
enum WorkspaceDestination {
  /// The review queue.
  queue,

  /// Photograph intake.
  intake,
}

/// A screen level failure: what happened, and the one action that recovers it
/// (screen blueprints, section 11).
@immutable
class WorkspaceError {
  const WorkspaceError({
    required this.message,
    required this.actionLabel,
    required this.action,
    this.clearsAccess = false,
  });

  /// The sentence the banner carries.
  final String message;

  /// The verb phrase on the banner's single action.
  final String actionLabel;

  /// What the action does.
  final Future<void> Function() action;

  /// True when this failure removed collection access, so the banner is the
  /// only thing left on screen.
  final bool clearsAccess;
}

/// The disposition segments over the queue (screen blueprints, section 3).
///
/// The key is the wire value; the empty key is every record. A key the search
/// API treats as an operational state rather than a disposition is sent as
/// `state`, which is the split `specimenPage` already expects.
const Map<String, String> queueDispositions = <String, String>{
  '': 'All',
  'needs_human_review': 'Needs review',
  'cleared': 'Cleared',
  'deferred': 'Deferred',
  'processing_blocked': 'Blocked',
  'running': 'Processing',
};

/// The disposition values the API filters as `disposition`. Everything else in
/// [queueDispositions] is an operational `state`.
const Set<String> queueDispositionValues = <String>{
  'cleared',
  'needs_human_review',
  'deferred',
};

/// Everything the collection screens read and act on.
///
/// A `ChangeNotifier` rather than screen state, because the router's redirect,
/// the shell and the queue all read the same collection list, and because the
/// queue has to survive a push to a specimen and back.
class WorkspaceController extends ChangeNotifier {
  WorkspaceController({
    required this.repository,
    required this.session,
    this.pollInterval = queuePollInterval,
  });

  /// The open editor may retain a local correction that has not been saved.
  Future<bool> Function()? reviewExitGuard;

  /// The mounted record route that owns the selected detail. A disposed route
  /// may finish after its replacement mounts; it must not close that detail.
  Object? recordRouteOwner;

  /// All explicit workspace navigation asks the active editor before leaving.
  Future<bool> mayLeaveReview() async {
    // Losing authorization must clear the workspace even during an old save.
    if (!session.signedIn || _scope == null) return true;
    if (mutating) return false;
    return await reviewExitGuard?.call() ?? true;
  }

  /// The collection API.
  final SpecimenRepository repository;

  /// The signed in account.
  final SessionAccess session;

  /// How often the queue quietly refreshes.
  final Duration pollInterval;

  /// The scroll offset of the queue list, kept here so a push to a specimen
  /// and back returns the reviewer to the row they left.
  final ScrollController queueScroll = ScrollController();

  List<CollectionScope> _scopes = <CollectionScope>[];
  CollectionScope? _scope;
  bool _scopesLoaded = false;
  bool _scopesVerified = false;
  bool _started = false;
  String? _startedUserId;
  int _mutationEpoch = 0;

  List<Specimen> _items = <Specimen>[];
  Specimen? _selected;
  String? _selectedId;
  String? _nextCursor;
  final Set<String> _seenCursors = <String>{};
  DateTime? _updatedAt;

  String _query = '';
  String _disposition = 'needs_human_review';
  Map<String, String> _filters = <String, String>{};

  bool _loading = true;
  bool _recordLoading = false;
  bool _loadingMore = false;
  bool _mutating = false;
  WorkspaceError? _error;

  /// Counts the list loads: `refresh`, `loadMore`, `search` and a change of
  /// collection. Separate from [_recordGeneration] because the two are
  /// independent requests and one must never cancel the other.
  ///
  /// One counter for both is finding V-5: a deep link mounted the workbench,
  /// `openSpecimen` bumped the shared counter while `refresh` was still
  /// awaiting its page, and `refresh` then threw away the page it had already
  /// been given. The list pane told the reviewer the collection was empty.
  int _listGeneration = 0;

  /// Counts the record loads: `openSpecimen` and the save that follows one.
  int _recordGeneration = 0;
  int _holds = 0;
  SpecimenPage? _deferredPage;

  StreamSubscription<ApiFailure>? _accessSubscription;
  Timer? _poll;
  AppLifecycleListener? _lifecycle;
  bool _foreground = true;
  Timer? _search;
  bool _disposed = false;

  final Map<String, String> _mutationKeys = <String, String>{};

  /// The collections this account may open.
  List<CollectionScope> get scopes =>
      List<CollectionScope>.unmodifiable(_scopes);

  /// The open collection, if one is resolved.
  CollectionScope? get scope => _scope;

  /// True once the collection list has been answered, either way.
  bool get scopesLoaded => _scopesLoaded;

  /// True when the server confirmed the collection list. False after a denial,
  /// which is not the same as an account with no collections.
  bool get scopesVerified => _scopesVerified;

  /// The records on screen.
  List<Specimen> get items => List<Specimen>.unmodifiable(_items);

  /// The record the workbench has open.
  Specimen? get selected => _selected;

  /// The identifier the workbench route asked for.
  String? get selectedId => _selectedId;

  /// A cursor for the next page, or null at the end of the results.
  String? get nextCursor => _nextCursor;

  /// When the records on screen were last answered by the server.
  DateTime? get updatedAt => _updatedAt;

  /// The exact match search text.
  String get query => _query;

  /// The selected disposition segment.
  String get disposition => _disposition;

  /// The filter sheet's values, in the wire format the repository expects.
  Map<String, String> get filters => Map<String, String>.unmodifiable(_filters);

  /// True while a request that replaces the list is in flight.
  bool get loading => _loading;

  /// True while the record a workbench route named is being fetched.
  ///
  /// Separate from [loading], which belongs to the list: a deep link loads
  /// both at once and neither may report the other's state (finding V-5).
  bool get recordLoading => _recordLoading;

  /// True once the server has answered the list at least once.
  ///
  /// Until it has, the queue shows placeholders rather than a claim about
  /// what the collection contains.
  bool get listAnswered => _updatedAt != null;

  /// True while another page is being appended.
  bool get loadingMore => _loadingMore;

  /// True while a decision is being saved.
  bool get mutating => _mutating;

  /// The screen level failure, if any.
  WorkspaceError? get error => _error;

  /// The environment name the banner states.
  String get environment =>
      session is LocalFixtureSession ? 'synthetic' : repository.mode;

  /// How many records need a person, of those loaded.
  int get needsReview => _items
      .where((Specimen s) => s.disposition == 'needs_human_review')
      .length;

  /// How many loaded records are blocked.
  int get blocked => _items
      .where(
        (Specimen s) => s.state == 'processing_blocked' || s.state == 'blocked',
      )
      .length;

  /// True when no search, segment or filter is narrowing the list.
  bool get unfiltered =>
      _query.isEmpty && _disposition.isEmpty && _filters.isEmpty;

  /// How many filters the Filters button reports.
  int get activeFilterCount => _filters.length;

  /// Counts the result sets this controller has produced.
  ///
  /// The queue keys its cross-fade on this, so a search, a filter or a
  /// segment change swaps the rows and a poll that answered with the same
  /// records does not (motion catalog, rows 14 and 24).
  int get listGeneration => _listGeneration;

  /// The filters as the repository wants them. Unchanged from before the
  /// redesign: same keys, same string values.
  Map<String, String> get activeFilters => <String, String>{
    ..._filters,
    if (_query.trim().isNotEmpty) 'specimen_id': _query.trim(),
    if (_disposition.isNotEmpty)
      (queueDispositionValues.contains(_disposition) ? 'disposition' : 'state'):
          _disposition,
  };

  /// Starts collection loading once, after the session is signed in and
  /// verified. Called by the app, never by a screen, so an unverified account
  /// never reaches the collection API.
  void start() {
    if (_disposed || (_started && _startedUserId == session.userId)) return;
    if (_started) resetSession();
    _started = true;
    _startedUserId = session.userId;
    final SpecimenRepository source = repository;
    if (source is AccessFailureSource) {
      _accessSubscription = (source as AccessFailureSource).accessFailures
          .listen((ApiFailure failure) {
            if (_disposed) return;
            _loading = false;
            _loadingMore = false;
            _recordFailure(failure);
            notifyListeners();
          });
    }
    unawaited(checkAccess());
    // A poll that runs while nobody is looking is a request the collection
    // pays for and no one reads. The listener is created here rather than in
    // the constructor so a controller that was never started never installs
    // one.
    final lifecycleState = WidgetsBinding.instance.lifecycleState;
    _foreground =
        lifecycleState == null || lifecycleState == AppLifecycleState.resumed;
    _lifecycle = AppLifecycleListener(
      onStateChange: (AppLifecycleState state) =>
          _foreground = state == AppLifecycleState.resumed,
    );
    _poll = Timer.periodic(pollInterval, (_) {
      if (_foreground &&
          !_mutating &&
          !_loading &&
          !_loadingMore &&
          _scope != null &&
          _seenCursors.isEmpty) {
        unawaited(refresh(quiet: true));
      }
    });
  }

  /// Invalidates requests, timers and cached permissions when an account
  /// leaves. A later verified session must load its own collection access.
  void resetSession() {
    final previousUser = _startedUserId;
    if (previousUser != null) forgetIntakeTransfers(repository, previousUser);
    reviewExitGuard = null;
    recordRouteOwner = null;
    _listGeneration++;
    _recordGeneration++;
    _mutationEpoch++;
    _started = false;
    _startedUserId = null;
    _accessSubscription?.cancel();
    _accessSubscription = null;
    _lifecycle?.dispose();
    _lifecycle = null;
    _poll?.cancel();
    _poll = null;
    _search?.cancel();
    _search = null;
    _scopes = <CollectionScope>[];
    _scope = null;
    _scopesLoaded = false;
    _scopesVerified = false;
    _items = <Specimen>[];
    _selected = null;
    _selectedId = null;
    _nextCursor = null;
    _seenCursors.clear();
    _updatedAt = null;
    _query = '';
    _disposition = 'needs_human_review';
    _filters = <String, String>{};
    _holds = 0;
    _deferredPage = null;
    _mutationKeys.clear();
    _loading = true;
    _loadingMore = false;
    _mutating = false;
    _error = null;
    if (queueScroll.hasClients) queueScroll.jumpTo(0);
    _notify();
  }

  /// True while the window is the one the operating system is showing.
  ///
  /// The poll is the only thing that reads it. Everything else in the client
  /// happens because a reviewer asked for it.
  bool get foreground => _foreground;

  /// Tells the controller the window went to the background, for a test that
  /// has no operating system to hear it from.
  @visibleForTesting
  void setForeground(bool value) => _foreground = value;

  @override
  void dispose() {
    _disposed = true;
    final previousUser = _startedUserId;
    if (previousUser != null) forgetIntakeTransfers(repository, previousUser);
    _accessSubscription?.cancel();
    _lifecycle?.dispose();
    _poll?.cancel();
    _search?.cancel();
    queueScroll.dispose();
    super.dispose();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  /// Holds the list still while a row has focus or a sheet is open, so a quiet
  /// poll never moves what the reviewer is looking at (blueprints, section 3).
  void holdList() => _holds++;

  /// Releases one hold and applies whatever the poll answered meanwhile.
  void releaseList() {
    if (_holds > 0) _holds--;
    final SpecimenPage? deferred = _deferredPage;
    if (_holds == 0 && deferred != null) {
      _deferredPage = null;
      _applyPage(deferred);
      _notify();
    }
  }

  /// True while the list is held.
  bool get listHeld => _holds > 0;

  /// Loads the collection list, or reloads it after a denial.
  Future<void> checkAccess() async {
    _loading = true;
    _error = null;
    _scopesVerified = false;
    _scopes = <CollectionScope>[];
    _scope = null;
    _items = <Specimen>[];
    _selected = null;
    _listGeneration++;
    _recordGeneration++;
    _notify();
    final int generation = _listGeneration;
    try {
      final List<CollectionScope> scopes = await repository.scopes();
      if (_disposed || generation != _listGeneration) return;
      _scopesVerified = true;
      _scopesLoaded = true;
      _scopes = scopes;
      _scope = scopes.isEmpty ? null : scopes.first;
      _loading = false;
      _notify();
      if (_scope != null) await refresh();
    } catch (error) {
      if (_disposed || generation != _listGeneration) return;
      _scopesLoaded = true;
      _loading = false;
      _recordFailure(error);
      _notify();
    }
  }

  /// Opens the collection whose route key matches, if it is not already open.
  ///
  /// Returns false when the key names no collection this account holds, which
  /// is the router's signal to send the window to a collection that exists.
  bool selectRouteKey(String routeKey) {
    if (!_scopesLoaded || _scopes.isEmpty) return true;
    final String key = decodeCollectionKey(routeKey);
    CollectionScope? match;
    for (final CollectionScope scope in _scopes) {
      if (scope.key == key) match = scope;
    }
    if (match == null) return false;
    if (identical(match, _scope) || match.key == _scope?.key) return true;
    _scope = match;
    reviewExitGuard = null;
    recordRouteOwner = null;
    _items = <Specimen>[];
    _selected = null;
    _selectedId = null;
    _nextCursor = null;
    _seenCursors.clear();
    _updatedAt = null;
    _loading = true;
    _recordLoading = false;
    _recordGeneration++;
    _error = null;
    scheduleMicrotask(() => unawaited(refresh()));
    return true;
  }

  /// The route key for the collection a window should open by default.
  String? get defaultRouteKey {
    final CollectionScope? scope =
        _scope ?? (_scopes.isEmpty ? null : _scopes.first);
    return scope == null ? null : encodeCollectionKey(scope.key);
  }

  /// Replaces the list with the current filters.
  Future<void> refresh({bool quiet = false}) async {
    final CollectionScope? scope = _scope;
    if (scope == null) return;
    final int generation = ++_listGeneration;
    final int openRecord = _recordGeneration;
    final String? openId = _selectedId;
    final Specimen? recordAtStart = _selected;
    final bool refreshOpenRecord = !_recordLoading;
    _nextCursor = null;
    _seenCursors.clear();
    _loadingMore = false;
    if (!quiet) {
      _loading = true;
      _error = null;
      _notify();
    }
    try {
      final SpecimenPage page = await repository.specimenPage(
        scope,
        filters: activeFilters,
      );
      if (_disposed ||
          generation != _listGeneration ||
          !identical(scope, _scope)) {
        return;
      }
      // A route opened while the list was loading owns its own detail request.
      // Check that ownership before dispatch, rather than fetching and merely
      // rejecting the duplicate response afterwards.
      final Specimen? selected =
          openId == null ||
              !refreshOpenRecord ||
              openRecord != _recordGeneration ||
              !identical(recordAtStart, _selected)
          ? null
          : await repository.specimen(scope, openId);
      if (_disposed ||
          generation != _listGeneration ||
          !identical(scope, _scope)) {
        return;
      }
      // The open record is the record load's to own. A refresh only carries
      // it along when nothing opened or closed a record meanwhile.
      // An acknowledged save (including a partial batch) replaces the record
      // object without navigating. A response started before that replacement
      // no longer owns the selected detail, even if the route is unchanged.
      final bool ownsRecord =
          openRecord == _recordGeneration &&
          identical(recordAtStart, _selected);
      if (quiet && _holds > 0) {
        // A row has focus or a sheet is open. Keep the answer until it does
        // not, rather than moving the list under the reviewer.
        _deferredPage = page;
        if (ownsRecord) _selected = selected ?? _selected;
        _loading = false;
        _notify();
        return;
      }
      _applyPage(page);
      if (ownsRecord && selected != null) _selected = selected;
      _loading = false;
      // A quiet poll is a background process. It may not clear a message the
      // reviewer has not read: that is what the banner's own Dismiss is for
      // (pass criterion 9.5). A refresh the reviewer asked for does clear it,
      // because they are watching the result.
      if (!quiet) _error = null;
      _notify();
    } catch (error) {
      if (_disposed ||
          generation != _listGeneration ||
          !identical(scope, _scope)) {
        return;
      }
      _loading = false;
      _recordFailure(error);
      _notify();
    }
  }

  void _applyPage(SpecimenPage page) {
    _items = page.items;
    _nextCursor = page.nextCursor;
    _updatedAt = DateTime.now();
  }

  /// Appends the next page.
  Future<void> loadMore() async {
    final CollectionScope? scope = _scope;
    final String? cursor = _nextCursor;
    if (scope == null || cursor == null || _loadingMore || _loading) return;
    final int generation = _listGeneration;
    _loadingMore = true;
    _error = null;
    _notify();
    try {
      final SpecimenPage page = await repository.specimenPage(
        scope,
        filters: activeFilters,
        cursor: cursor,
      );
      if (_disposed || generation != _listGeneration) return;
      if (_seenCursors.contains(cursor) ||
          page.nextCursor == cursor ||
          (page.nextCursor != null && _seenCursors.contains(page.nextCursor))) {
        throw const ApiFailure(
          'Page cursor repeated. Refresh the queue.',
          code: 'pagination',
        );
      }
      final Set<String> ids = _items.map((Specimen s) => s.id).toSet();
      if (page.items.any((Specimen s) => !ids.add(s.id))) {
        throw const ApiFailure(
          'Records changed across pages. Refresh the queue.',
          code: 'pagination',
        );
      }
      _items = <Specimen>[..._items, ...page.items];
      _seenCursors.add(cursor);
      _nextCursor = page.nextCursor;
      _updatedAt = DateTime.now();
    } catch (error) {
      if (_disposed || generation != _listGeneration) return;
      _nextCursor = null;
      _recordFailure(error);
    } finally {
      if (!_disposed && generation == _listGeneration) {
        _loadingMore = false;
        _notify();
      }
    }
  }

  /// Sets the exact match search and reloads after the debounce.
  void search(String value) {
    _query = value;
    _listGeneration++;
    _nextCursor = null;
    _loadingMore = false;
    _notify();
    _search?.cancel();
    _search = Timer(searchDebounce, () => unawaited(refresh()));
  }

  /// Selects a disposition segment and reloads.
  Future<void> selectDisposition(String value) {
    _disposition = value;
    _notify();
    return refresh();
  }

  /// Applies the filter sheet's result.
  Future<void> applyFilters(Map<String, String> values) {
    _filters = Map<String, String>.from(values)
      ..removeWhere((String key, String value) => value.isEmpty);
    _notify();
    return refresh();
  }

  /// Removes one active filter, from its chip.
  Future<void> removeFilter(String key) {
    final Map<String, String> next = Map<String, String>.from(_filters)
      ..remove(key);
    return applyFilters(next);
  }

  /// Clears the search, the segment and every filter.
  Future<void> clearFilters() {
    _query = '';
    _disposition = 'needs_human_review';
    _filters = <String, String>{};
    _notify();
    return refresh();
  }

  /// Asks for the list once, when a deep link opened a record before the
  /// queue was ever shown.
  ///
  /// Silent when the list is already loaded or already in flight, so the
  /// ordinary path from the queue to a record adds no request
  /// (`test/app/request_budget_test.dart`).
  void ensureListLoaded() {
    if (_scope == null || _loading || _updatedAt != null) return;
    scheduleMicrotask(() => unawaited(refresh()));
  }

  /// Loads the record the workbench route names.
  ///
  /// Takes the record counter, never the list counter: a deep link opens a
  /// record while the queue is still loading, and cancelling the queue load
  /// is what left the list pane claiming an empty collection (finding V-5).
  Future<void> openSpecimen(String id) async {
    final CollectionScope? scope = _scope;
    if (scope == null) return;
    // A dependency notification can ask for the same route while its detail
    // request is pending. Restarting it invalidates the first response and
    // schedules another notification, so a slow request would never finish.
    if (_selectedId == id && (_selected != null || _recordLoading)) return;
    _selectedId = id;
    _selected = null;
    _recordLoading = true;
    _error = null;
    final int generation = ++_recordGeneration;
    _notify();
    try {
      final Specimen item = await repository.specimen(scope, id);
      if (_disposed || generation != _recordGeneration) return;
      _selected = item;
      _recordLoading = false;
      _notify();
    } catch (error) {
      if (_disposed || generation != _recordGeneration) return;
      _recordLoading = false;
      _recordFailure(error);
      _notify();
    }
  }

  /// Forgets the open record when the workbench route is left.
  void closeSpecimen() {
    if (_selectedId == null && _selected == null) return;
    _selectedId = null;
    _selected = null;
    _recordLoading = false;
    _recordGeneration++;
    _notify();
  }

  /// Where the open record sits in the loaded list, one based, or null when
  /// the list does not carry it.
  ///
  /// The decision bar says "3 of 38" from this, and the next and previous
  /// controls are derived from it (pass criterion 6.5).
  int? get selectedPosition {
    final String? id = _selectedId;
    if (id == null) return null;
    for (int i = 0; i < _items.length; i++) {
      if (_items[i].id == id) return i + 1;
    }
    return null;
  }

  /// The record after the open one in the loaded list, or null at the end.
  ///
  /// Null at the ends rather than wrapping: a queue that loops has no end,
  /// and a reviewer working it cannot tell when they are finished.
  Specimen? get nextSpecimen {
    final int? position = selectedPosition;
    if (position == null || position >= _items.length) return null;
    return _items[position];
  }

  /// The record before the open one, or null at the start of the list.
  Specimen? get previousSpecimen {
    final int? position = selectedPosition;
    if (position == null || position <= 1) return null;
    return _items[position - 2];
  }

  /// Saves a review decision, or a retry, against the open record.
  ///
  /// A mutation key is retained for an uncertain response, so an identical
  /// retry reconciles on the server rather than recording twice.
  Future<bool> mutate(Json? change, String? retryReason) async {
    final Specimen? current = _selected;
    final CollectionScope? scope = _scope;
    if (current == null || scope == null || _mutating) return false;
    final int generation = _recordGeneration;
    final int mutationEpoch = _mutationEpoch;
    final String payload =
        '${current.id}:${current.revision}:${change ?? retryReason}';
    final String key = _mutationKeys.putIfAbsent(
      payload,
      () => 'review-${DateTime.now().microsecondsSinceEpoch}',
    );
    _mutating = true;
    _error = null;
    _notify();
    try {
      final Specimen result = change != null
          ? await repository.review(scope, current, change, key)
          : await repository.retry(scope, current, retryReason!, key);
      if (_disposed || generation != _recordGeneration) return false;
      if (result.id != current.id ||
          (change != null && result.revision <= current.revision)) {
        throw const ApiFailure(
          'The server has not confirmed this save with a newer record version.',
          code: 'unconfirmed_save',
        );
      }
      _selected = result;
      _mutationKeys.remove(payload);
      return true;
    } catch (error) {
      if (_disposed || generation != _recordGeneration) return false;
      _recordFailure(error);
      return false;
    } finally {
      if (!_disposed && mutationEpoch == _mutationEpoch) {
        _mutating = false;
        _notify();
      }
    }
  }

  /// Restores a retained version as a new, independently audited revision.
  Future<void> restoreVersion(
    int sourceRevision,
    bool resetToInitial,
    String reason,
  ) async {
    final current = _selected;
    final scope = _scope;
    final history = repository;
    if (current == null ||
        scope == null ||
        _mutating ||
        history is! SpecimenHistoryRepository) {
      throw const ApiFailure(
        'Version restoration is unavailable.',
        code: 'unavailable',
      );
    }
    if (!scope.permissions.any(
          (role) => const ['reviewer', 'manager', 'admin'].contains(role),
        ) ||
        !(current.data['available_actions'] as List? ?? const []).contains(
          'restore_version',
        )) {
      throw const ApiFailure(
        'Restoring this version requires reviewer access and an available restore action.',
        code: 'forbidden',
        status: 403,
      );
    }
    final generation = _recordGeneration;
    final mutationEpoch = _mutationEpoch;
    final payload =
        'restore:${current.id}:${current.revision}:$sourceRevision:$resetToInitial:$reason';
    final key = _mutationKeys.putIfAbsent(
      payload,
      () => 'restore-${DateTime.now().microsecondsSinceEpoch}',
    );
    _mutating = true;
    _error = null;
    _notify();
    try {
      final result = await (history as SpecimenHistoryRepository)
          .restoreVersion(
            scope,
            current,
            sourceRevision: sourceRevision,
            resetToInitial: resetToInitial,
            reason: reason,
            idempotencyKey: key,
          );
      if (_disposed || generation != _recordGeneration) return;
      if (result.id != current.id || result.revision <= current.revision) {
        throw const ApiFailure(
          'The server has not confirmed a new restored version.',
          code: 'unconfirmed_save',
        );
      }
      // A poll or manual refresh may have started before this save. Its
      // older response (including a held page) must not replace the new version.
      _recordGeneration++;
      _listGeneration++;
      _deferredPage = null;
      _loading = false;
      _loadingMore = false;
      _selected = result;
      final index = _items.indexWhere((item) => item.id == result.id);
      if (index >= 0) _items[index] = result;
      _mutationKeys.remove(payload);
    } catch (error) {
      if (!_disposed && generation == _recordGeneration) _recordFailure(error);
      rethrow;
    } finally {
      if (!_disposed && mutationEpoch == _mutationEpoch) {
        _mutating = false;
        _notify();
      }
    }
  }

  /// Saves several corrections as one reviewer action under one reason.
  ///
  /// Pass criterion 7.2. The wire takes one decision per call, so this is
  /// still several calls; what it is not is several screen updates. The
  /// record is replaced once, from the last result, so a reviewer saving
  /// five corrections sees the version move once instead of five times, and
  /// the whole batch shares one idempotency key prefix.
  ///
  /// Returns how many of [changes] the server accepted.
  Future<int> mutateBatch(
    List<Json> changes,
    String reason, {
    bool Function(Specimen current, Json change)? stillApplies,
  }) async {
    final Specimen? current = _selected;
    final CollectionScope? scope = _scope;
    if (current == null || scope == null || _mutating || changes.isEmpty) {
      return 0;
    }
    final int generation = _recordGeneration;
    final int mutationEpoch = _mutationEpoch;
    final String prefix =
        'review-batch-${DateTime.now().microsecondsSinceEpoch}';
    // One key per decision, memoised on the record version it was sent
    // against, exactly as `mutate` does for a single decision: a call retried
    // after an uncertain answer carries the key it carried the first time, so
    // the server reconciles rather than recording twice. The prefix names the
    // batch, the key identifies the decision, and the two jobs stay separate.
    final List<String> payloads = <String>[];
    String keyFor(Specimen atVersion, Json body, int index) {
      final String payload = '${atVersion.id}:${atVersion.revision}:$body';
      payloads.add(payload);
      return _mutationKeys.putIfAbsent(payload, () => '$prefix-$index');
    }

    _mutating = true;
    _error = null;
    _notify();
    try {
      final ReviewBatchResult result = await repository.reviewBatch(
        scope,
        current,
        changes,
        reason,
        prefix,
        stillApplies: stillApplies,
        keyFor: keyFor,
      );
      if (_disposed || generation != _recordGeneration) return result.saved;
      if (result.saved > 0) _selected = result.specimen;
      for (final String payload in payloads.take(result.saved)) {
        _mutationKeys.remove(payload);
      }
      return result.saved;
    } on ReviewBatchFailure catch (failure) {
      if (_disposed || generation != _recordGeneration) return failure.saved;
      // What landed, landed. The screen shows the record the server has now
      // rather than the one the reviewer opened, and the caller reports the
      // corrections that are still outstanding.
      if (failure.saved > 0) _selected = failure.specimen;
      // The key of the call that failed is deliberately retained: its answer
      // is uncertain, so a retry has to reconcile rather than record twice.
      for (final String payload in payloads.take(failure.saved)) {
        _mutationKeys.remove(payload);
      }
      _recordFailure(failure.cause);
      return failure.saved;
    } catch (error) {
      if (_disposed || generation != _recordGeneration) return 0;
      _recordFailure(error);
      return 0;
    } finally {
      if (!_disposed && mutationEpoch == _mutationEpoch) {
        _mutating = false;
        _notify();
      }
    }
  }

  /// Fetches current scoped detail before exposing a bulk decision.
  Future<BulkSelectionEligibility> inspectSelection(
    List<Specimen> specimens,
  ) async {
    final scope = _scope;
    final epoch = _mutationEpoch;
    final userId = session.userId;
    final records = <String, Specimen>{};
    final unavailable = <String, String>{};
    String? blocked;
    if (scope == null || !_scopesVerified) {
      blocked = 'Collection access could not be verified.';
    } else if (!scope.permissions.any(
      ['reviewer', 'manager', 'admin'].contains,
    )) {
      blocked = 'Your role on this collection does not include reviewing.';
    } else if (specimens.length > bulkDecisionLimit) {
      blocked = 'Select at most $bulkDecisionLimit records for one decision.';
    }
    bool current() =>
        !_disposed &&
        identical(scope, _scope) &&
        epoch == _mutationEpoch &&
        userId == session.userId &&
        _scopesVerified;
    if (blocked == null) {
      // Bound parallel reads; a selection must not fan out 100 requests at once.
      for (int offset = 0; offset < specimens.length; offset += 6) {
        if (!current()) break;
        await Future.wait(
          specimens.skip(offset).take(6).map((specimen) async {
            try {
              final detail = await repository.specimen(scope!, specimen.id);
              if (detail.id != specimen.id) {
                unavailable[specimen.id] =
                    'The requested record could not be verified.';
              } else {
                records[specimen.id] = detail;
              }
            } catch (error) {
              unavailable[specimen.id] =
                  'Current permission could not be verified. Check the connection and try again.';
              if (current() &&
                  error is ApiFailure &&
                  (error.status == 401 || error.status == 403)) {
                _recordFailure(error);
                _notify();
              }
            }
          }),
        );
      }
      if (!current()) {
        blocked = 'Collection access changed. Check access before reviewing.';
      }
    }
    if (blocked != null) {
      records.clear();
      for (final specimen in specimens) {
        unavailable[specimen.id] = blocked;
      }
    }
    return BulkSelectionEligibility(
      requested: List.unmodifiable(specimens),
      records: Map.unmodifiable(records),
      unavailable: Map.unmodifiable(unavailable),
    );
  }

  /// Rechecks permission and the confirmed versions immediately before writing.
  /// Every requested ID receives an outcome, including records not sent.
  Future<BulkDecisionReport?> reviewSelection(
    List<Specimen> specimens,
    BulkDecisionKind kind,
    String reason,
  ) async {
    final CollectionScope? scope = _scope;
    if (scope == null || specimens.isEmpty || _mutating) return null;
    final int mutationEpoch = _mutationEpoch;
    _mutating = true;
    _error = null;
    _notify();
    try {
      final evidence = await inspectSelection(specimens);
      if (_disposed ||
          mutationEpoch != _mutationEpoch ||
          !identical(scope, _scope)) {
        return null;
      }
      final eligible = <Specimen>[];
      final outcomes = <String, BulkDecisionResult>{};
      for (final specimen in specimens) {
        final detail = evidence.records[specimen.id];
        String? blocked = evidence.reasonFor(specimen.id, kind);
        String code = 'not_permitted';
        if (blocked == null &&
            (detail!.revision != specimen.revision ||
                detail.recordVersionId != specimen.recordVersionId)) {
          blocked =
              'This record changed after confirmation. Review the current version before trying again.';
          code = 'version_changed';
        }
        if (blocked != null) {
          outcomes[specimen.id] = BulkDecisionResult(
            specimenId: specimen.id,
            outcome: BulkOutcome.skipped,
            code: code,
            message: blocked,
          );
        } else {
          eligible.add(detail!);
        }
      }
      if (eligible.isNotEmpty) {
        final String payload =
            '${scope.key}:${kind.wire}:$reason:'
            '${eligible.map((s) => '${s.id}@${s.recordVersionId}').join(',')}';
        final key = _mutationKeys.putIfAbsent(
          payload,
          () => 'review-many-${DateTime.now().microsecondsSinceEpoch}',
        );
        final response = await repository.reviewMany(
          scope,
          eligible,
          kind,
          reason,
          key,
        );
        if (_disposed ||
            mutationEpoch != _mutationEpoch ||
            !identical(scope, _scope)) {
          return null;
        }
        for (final specimen in eligible) {
          final matches = response.results
              .where((row) => row.specimenId == specimen.id)
              .toList();
          outcomes[specimen.id] = matches.length == 1
              ? matches.single
              : BulkDecisionResult(
                  specimenId: specimen.id,
                  outcome: BulkOutcome.skipped,
                  code: 'outcome_unconfirmed',
                  message:
                      'The result was not confirmed. Check the current record before trying again.',
                );
        }
        if (eligible.every((s) => outcomes[s.id]!.changed)) {
          _mutationKeys.remove(payload);
        }
      }
      return BulkDecisionReport([
        for (final specimen in specimens) outcomes[specimen.id]!,
      ]);
    } catch (error) {
      if (_disposed ||
          mutationEpoch != _mutationEpoch ||
          !identical(scope, _scope)) {
        return null;
      }
      _recordFailure(error);
      return null;
    } finally {
      if (!_disposed && mutationEpoch == _mutationEpoch) {
        _mutating = false;
        _notify();
      }
    }
  }

  /// Ends the session.
  Future<void> signOut() async {
    try {
      await session.signOut();
    } catch (_) {
      _error = WorkspaceError(
        message: 'Sign-out did not complete. Try again.',
        actionLabel: 'Try again',
        action: signOut,
      );
      _notify();
    }
  }

  /// Drops the banner once the reviewer has acted on it.
  void clearError() {
    if (_error == null) return;
    _error = null;
    _notify();
  }

  void _recordFailure(Object error) {
    final ApiFailure? failure = error is ApiFailure ? error : null;
    final bool denied =
        failure != null && (failure.status == 401 || failure.status == 403);
    if (denied) {
      // Do not retain an editable workspace after current access is denied.
      _scopesVerified = false;
      _scopes = <CollectionScope>[];
      _scope = null;
      _items = <Specimen>[];
      _selected = null;
      _selectedId = null;
      _nextCursor = null;
      _seenCursors.clear();
      _listGeneration++;
      _recordGeneration++;
    }
    _error = _failureFor(error, denied: denied);
  }

  WorkspaceError _failureFor(Object error, {required bool denied}) {
    final ApiFailure? failure = error is ApiFailure ? error : null;
    if (denied) {
      return WorkspaceError(
        message: session is LocalFixtureSession
            ? 'The local server did not authorize this request. Your collection '
                  'access is unverified, so sign out and sign in with the '
                  'current fixture token.'
            : '${failure!.message} Your collection access could not be verified.',
        actionLabel: 'Check access again',
        action: checkAccess,
        clearsAccess: true,
      );
    }
    if (failure != null && failure.conflict) {
      return WorkspaceError(
        message:
            'Another reviewer saved a new version while you were working. '
            'Your decision was not saved.',
        actionLabel: 'Refresh and compare',
        action: refresh,
      );
    }
    if (failure != null && failure.code == 'pagination') {
      return WorkspaceError(
        message: '${failure.message} Refresh the queue to restart this search.',
        actionLabel: 'Refresh the queue',
        action: refresh,
      );
    }
    final bool unreachable =
        failure == null ||
        <String>['network', 'timeout', 'unavailable'].contains(failure.code) ||
        (failure.status ?? 0) >= 500;
    if (unreachable) {
      final String base = session is LocalFixtureSession && failure != null
          ? 'The test server is unavailable and collection permissions were '
                'not checked. Reconnect the demo server, then refresh.'
          : failure?.message ??
                'The service could not be reached. Check your connection and retry.';
      return WorkspaceError(
        message: '$base ${lastSyncSentence()}',
        actionLabel: 'Retry',
        action: () => refresh(),
      );
    }
    return WorkspaceError(
      message: failure.message,
      actionLabel: 'Retry',
      action: () => refresh(),
    );
  }

  /// Names the last answer from the server, so an unreachable banner says what
  /// the records on screen still are (blueprints, section 11).
  String lastSyncSentence() {
    final DateTime? moment = _updatedAt;
    if (moment == null) return 'No records have been loaded yet.';
    return 'These records were last loaded ${_secondsSince(moment)} ago.';
  }

  static String _secondsSince(DateTime moment) {
    final Duration age = DateTime.now().difference(moment);
    if (age.inMinutes < 1) return '${age.inSeconds.clamp(0, 59)} s';
    if (age.inHours < 1) return '${age.inMinutes} min';
    return '${age.inHours} h';
  }
}

/// A collection key inside a URL path segment.
///
/// A scope key is `organization/collection`, so it carries a slash that a path
/// segment cannot. One encode, one decode, both named, so no call site invents
/// a second spelling.
String encodeCollectionKey(String key) => Uri.encodeComponent(key);

/// The inverse of [encodeCollectionKey], tolerant of an already decoded value.
String decodeCollectionKey(String routeKey) {
  try {
    return Uri.decodeComponent(routeKey);
  } on ArgumentError {
    return routeKey;
  }
}

/// Publishes the [WorkspaceController] to everything under the router.
class WorkspaceScope extends InheritedNotifier<WorkspaceController> {
  const WorkspaceScope({
    super.key,
    required WorkspaceController controller,
    required super.child,
  }) : super(notifier: controller);

  /// The controller, rebuilding the caller when it changes.
  static WorkspaceController of(BuildContext context) {
    final WorkspaceScope? scope = context
        .dependOnInheritedWidgetOfExactType<WorkspaceScope>();
    assert(scope != null, 'no WorkspaceScope above this widget');
    return scope!.notifier!;
  }

  /// The controller without subscribing to its changes, for a callback that
  /// acts on it rather than drawing it.
  static WorkspaceController read(BuildContext context) {
    final WorkspaceScope? scope = context
        .getInheritedWidgetOfExactType<WorkspaceScope>();
    assert(scope != null, 'no WorkspaceScope above this widget');
    return scope!.notifier!;
  }
}

/// Activity and collection ownership of one retained navigation branch.
/// A branch can remain mounted while another tab is visible.
class WorkspaceBranchScope extends InheritedWidget {
  const WorkspaceBranchScope({
    super.key,
    required this.active,
    required this.collectionKey,
    required super.child,
  });

  final bool active;
  final String collectionKey;

  static WorkspaceBranchScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<WorkspaceBranchScope>();

  @override
  bool updateShouldNotify(WorkspaceBranchScope oldWidget) =>
      active != oldWidget.active || collectionKey != oldWidget.collectionKey;
}

/// Retains each tab's navigator while removing hidden branches from focus,
/// semantics and animation. Activity is explicit because a hidden navigator's
/// top route still reports `ModalRoute.isCurrent`.
class WorkspaceBranchStack extends StatelessWidget {
  const WorkspaceBranchStack({
    super.key,
    required this.activeIndex,
    required this.collectionKey,
    required this.children,
  });

  final int activeIndex;
  final String collectionKey;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => IndexedStack(
    index: activeIndex,
    children: [
      for (var i = 0; i < children.length; i++)
        WorkspaceBranchScope(
          active: i == activeIndex,
          collectionKey: collectionKey,
          child: Offstage(
            offstage: i != activeIndex,
            child: TickerMode(
              enabled: i == activeIndex,
              child: ExcludeFocus(
                excluding: i != activeIndex,
                child: ExcludeSemantics(
                  excluding: i != activeIndex,
                  child: children[i],
                ),
              ),
            ),
          ),
        ),
    ],
  );
}

/// The collection shell: navigation, the environment band, the error banner
/// and the routed screen inside them.
///
/// Constructed only on a collection route, so a session that is not signed in,
/// not verified, or not connected to an API never builds one.
class CollectionWorkspace extends StatefulWidget {
  const CollectionWorkspace({
    super.key,
    required this.routeKey,
    required this.destination,
    this.navigationShell,
    required this.child,
  });

  /// The collection the location names, still encoded.
  final String routeKey;

  /// Which navigation destination the current route belongs to.
  final WorkspaceDestination destination;

  /// The two retained tab navigators, absent only while scope access loads.
  final StatefulNavigationShell? navigationShell;

  /// The routed screen.
  final Widget child;

  @override
  State<CollectionWorkspace> createState() => _CollectionWorkspaceState();
}

/// Specimen sidebar controls shared with the active record route.
class QueueWorkspaceScope extends InheritedWidget {
  const QueueWorkspaceScope({
    super.key,
    required this.showQueue,
    required this.hideQueue,
    this.expanded = false,
    required super.child,
  });
  final VoidCallback? showQueue;
  final VoidCallback hideQueue;
  final bool expanded;
  static QueueWorkspaceScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<QueueWorkspaceScope>();
  @override
  bool updateShouldNotify(QueueWorkspaceScope oldWidget) =>
      showQueue != oldWidget.showQueue || expanded != oldWidget.expanded;
}

class _CollectionWorkspaceState extends State<CollectionWorkspace> {
  final GlobalKey _queueKey = GlobalKey(debugLabel: 'persistent-specimens');
  final FocusNode _queueSearch = FocusNode(debugLabel: 'Specimen search');
  final QueueKeyboardController _queueKeyboard = QueueKeyboardController();

  @override
  void dispose() {
    _queueSearch.dispose();
    _queueKeyboard.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(CollectionWorkspace oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.routeKey != widget.routeKey) _sync();
  }

  void _sync() {
    if (widget.routeKey.isEmpty) return;
    scheduleMicrotask(() {
      if (mounted) WorkspaceScope.read(context).selectRouteKey(widget.routeKey);
    });
  }

  @override
  Widget build(BuildContext context) {
    final queueDestination = widget.destination == WorkspaceDestination.queue;
    final record = AppShell.insideRecord(GoRouterState.of(context).uri);
    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        if (queueDestination && !record) ...<ShortcutActivator, VoidCallback>{
          const EditingSafeActivator(LogicalKeyboardKey.slash):
              _queueSearch.requestFocus,
          const EditingSafeActivator(LogicalKeyboardKey.arrowDown): () =>
              _queueKeyboard.move(1),
          const EditingSafeActivator(LogicalKeyboardKey.keyJ): () =>
              _queueKeyboard.move(1),
          const EditingSafeActivator(LogicalKeyboardKey.arrowUp): () =>
              _queueKeyboard.move(-1),
          const EditingSafeActivator(LogicalKeyboardKey.keyK): () =>
              _queueKeyboard.move(-1),
          const EditingSafeActivator(LogicalKeyboardKey.enter):
              _queueKeyboard.open,
          const EditingSafeActivator(LogicalKeyboardKey.escape):
              _queueKeyboard.clear,
        },
      },
      child: AppShell(
        destination: widget.destination,
        onSelectDestination: widget.navigationShell == null
            ? null
            : (next) => widget.navigationShell!.goBranch(
                next.index,
                initialLocation: next == widget.destination,
              ),
        specimensFocus: _queueSearch,
        specimensActions: QueueListActions(controller: _queueKeyboard),
        specimens: Builder(
          builder: (context) => QueuePane(
            key: _queueKey,
            searchFocusNode: _queueSearch,
            controller: _queueKeyboard,
            onDismiss:
                (record || !queueDestination) &&
                    !(AppSidebarScope.maybeOf(context)?.mobileNavigation ??
                        false)
                ? AppSidebarScope.maybeOf(context)?.close
                : null,
          ),
        ),
        child: widget.child,
      ),
    );
  }
}
