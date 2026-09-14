/// The collection workspace: the state every collection screen reads, and the
/// shell the router renders it inside (screen blueprints, sections 1 and 3).
///
/// The controller lives above the router so a redirect can ask which
/// collections this account has before a screen is built, and so the queue
/// keeps its records, its scroll offset and its poll across a route change.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'app/shell.dart';
import 'auth.dart';
import 'models.dart';
import 'screens/queue/queue_screen.dart';
import 'widgets/widgets.dart';

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

  List<Specimen> _items = <Specimen>[];
  Specimen? _selected;
  String? _selectedId;
  String? _nextCursor;
  final Set<String> _seenCursors = <String>{};
  DateTime? _updatedAt;

  String _query = '';
  String _disposition = '';
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
    if (_started || _disposed) return;
    _started = true;
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
      final String? openId = _selectedId;
      final Specimen? selected = openId == null
          ? null
          : await repository.specimen(scope, openId);
      if (_disposed || generation != _listGeneration) return;
      // The open record is the record load's to own. A refresh only carries
      // it along when nothing opened or closed a record meanwhile.
      final bool ownsRecord = openRecord == _recordGeneration;
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
      if (ownsRecord) _selected = selected;
      _loading = false;
      // A quiet poll is a background process. It may not clear a message the
      // reviewer has not read: that is what the banner's own Dismiss is for
      // (pass criterion 9.5). A refresh the reviewer asked for does clear it,
      // because they are watching the result.
      if (!quiet) _error = null;
      _notify();
    } catch (error) {
      if (_disposed || generation != _listGeneration) return;
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
    _disposition = '';
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
    if (_selectedId == id && _selected != null) return;
    _selectedId = id;
    _selected = null;
    _recordLoading = true;
    _error = null;
    _notify();
    final int generation = ++_recordGeneration;
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
  Future<void> mutate(Json? change, String? retryReason) async {
    final Specimen? current = _selected;
    final CollectionScope? scope = _scope;
    if (current == null || scope == null || _mutating) return;
    final int generation = _recordGeneration;
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
      if (_disposed || generation != _recordGeneration) return;
      _selected = result;
      _mutationKeys.remove(payload);
    } catch (error) {
      if (_disposed || generation != _recordGeneration) return;
      _recordFailure(error);
    } finally {
      if (!_disposed) {
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
  Future<int> mutateBatch(List<Json> changes, String reason) async {
    final Specimen? current = _selected;
    final CollectionScope? scope = _scope;
    if (current == null || scope == null || _mutating || changes.isEmpty) {
      return 0;
    }
    final int generation = _recordGeneration;
    final String payload =
        '${current.id}:${current.revision}:batch:${changes.length}:$reason';
    final String prefix = _mutationKeys.putIfAbsent(
      payload,
      () => 'review-batch-${DateTime.now().microsecondsSinceEpoch}',
    );
    _mutating = true;
    _error = null;
    _notify();
    try {
      final Specimen result = await repository.reviewBatch(
        scope,
        current,
        changes,
        reason,
        prefix,
      );
      if (_disposed || generation != _recordGeneration) return changes.length;
      _selected = result;
      _mutationKeys.remove(payload);
      return changes.length;
    } on ReviewBatchFailure catch (failure) {
      if (_disposed || generation != _recordGeneration) return failure.saved;
      // What landed, landed. The screen shows the record the server has now
      // rather than the one the reviewer opened, and the caller reports the
      // corrections that are still outstanding.
      if (failure.saved > 0) _selected = failure.specimen;
      _recordFailure(failure.cause);
      return failure.saved;
    } catch (error) {
      if (_disposed || generation != _recordGeneration) return 0;
      _recordFailure(error);
      return 0;
    } finally {
      if (!_disposed) {
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
    required this.child,
  });

  /// The collection the location names, still encoded.
  final String routeKey;

  /// Which navigation destination the current route belongs to.
  final WorkspaceDestination destination;

  /// The routed screen.
  final Widget child;

  @override
  State<CollectionWorkspace> createState() => _CollectionWorkspaceState();
}

class _CollectionWorkspaceState extends State<CollectionWorkspace> {
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

  /// Opens the collection the location names, after the frame the router is
  /// building, so selecting one never notifies during a navigation.
  void _sync() {
    if (widget.routeKey.isEmpty) return;
    scheduleMicrotask(() {
      if (mounted) WorkspaceScope.read(context).selectRouteKey(widget.routeKey);
    });
  }

  @override
  Widget build(BuildContext context) {
    final bool listDetail =
        widget.destination == WorkspaceDestination.queue &&
        WindowClass.of(context).isAtLeast(WindowClass.large);

    return AppShell(
      destination: widget.destination,
      child: listDetail
          ? Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const SizedBox(width: queueListPaneWidth, child: QueuePane()),
                const VerticalDivider(width: 1),
                Expanded(child: widget.child),
              ],
            )
          : widget.child,
    );
  }
}
