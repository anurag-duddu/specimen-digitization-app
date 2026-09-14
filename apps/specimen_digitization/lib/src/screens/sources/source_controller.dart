/// Paging one inventory snapshot, and adding a selection out of it.
///
/// The snapshot is the unit of consistency here, not the page. Rows are bound
/// to a storage generation captured at one moment, a cursor is bound to the
/// snapshot that issued it, and an import declares a generation back so the
/// server can refuse an object that moved. So this controller carries the
/// snapshot's identity beside the rows and treats a new one as a different
/// list rather than as more of the same list.
library;

import 'package:flutter/foundation.dart';

import '../../models.dart';
import '../../sources.dart';

/// Whether the reviewer is looking at everything, or only at what is or is not
/// already a record.
enum SourceFilter {
  /// Every object in the snapshot.
  all,

  /// Only objects that are not records yet.
  notInQueue,

  /// Only objects that already are.
  inQueue;

  /// The `imported` query value, or null when the filter does not set one.
  String? get imported => switch (this) {
    SourceFilter.all => null,
    SourceFilter.notInQueue => 'false',
    SourceFilter.inQueue => 'true',
  };

  /// The words on the segmented control.
  String get label => switch (this) {
    SourceFilter.all => 'All',
    SourceFilter.notInQueue => 'Not in queue',
    SourceFilter.inQueue => 'In queue',
  };
}

/// Browses one registered source.
class SourceBrowseController extends ChangeNotifier {
  SourceBrowseController({
    required this.repository,
    required this.scope,
    required this.sourceId,
  });

  final SourceRepository repository;
  final CollectionScope scope;
  final String sourceId;

  final List<SourceObject> _items = <SourceObject>[];
  final Map<String, String> _importKeys = <String, String>{};

  SourceFilter _filter = SourceFilter.all;
  String? _mediaType;
  String? _cursor;
  String _inventoryId = '';
  DateTime? _capturedAt;
  int _objectCount = 0;
  int? _matchingCount;
  bool _loading = false;
  bool _loadingMore = false;
  bool _loaded = false;
  bool _refreshed = false;
  ApiFailure? _error;
  int _epoch = 0;
  bool _disposed = false;

  /// The rows loaded so far, in snapshot order.
  List<SourceObject> get items => List<SourceObject>.unmodifiable(_items);

  SourceFilter get filter => _filter;

  /// The media type the listing is narrowed to, or null for every type the
  /// source admits.
  String? get mediaType => _mediaType;

  /// True while the first page of a listing is out.
  bool get loading => _loading;

  /// True while a later page is out.
  bool get loadingMore => _loadingMore;

  /// True once a listing has answered, which is what tells an empty list apart
  /// from one that has not loaded.
  bool get loaded => _loaded;

  /// True when the server has another page.
  bool get moreToLoad => _cursor != null;

  /// The snapshot these rows came from.
  String get inventoryId => _inventoryId;

  DateTime? get capturedAt => _capturedAt;

  /// How many objects the whole snapshot holds.
  int get objectCount => _objectCount;

  /// How many objects the active filter covers, or null when the server did
  /// not count.
  ///
  /// Null is not zero. A select all that reaches past the loaded page may only
  /// be offered when this is a number, because that is the only case where the
  /// count stated before loading is one the server actually made.
  int? get matchingCount => _matchingCount;

  /// True when the source was recaptured under the reviewer while they were
  /// paging, and the list was reloaded from the start.
  ///
  /// The reviewer is told once and the flag is cleared, because a snapshot
  /// change is a moment rather than a state.
  bool get refreshed => _refreshed;

  ApiFailure? get error => _error;

  /// True when every object in this filter is loaded, so a select all reaches
  /// all of them without another request.
  bool get allLoaded => _loaded && !moreToLoad;

  /// How many objects a select all over the whole filter would cover, or null
  /// when that cannot be stated.
  ///
  /// Once everything is loaded the loaded count is the exact answer whatever
  /// the server counted, which is what makes the control available under the
  /// `imported` filter too, but only after paging.
  int? get reachableCount => allLoaded ? _items.length : _matchingCount;

  Map<String, String> get _query => <String, String>{
    'imported': ?_filter.imported,
    'media_type': ?_mediaType,
  };

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  /// Loads the first page, discarding anything loaded before.
  Future<void> load() async {
    final int epoch = ++_epoch;
    _loading = true;
    _error = null;
    _notify();
    try {
      final SourceObjectPage page = await repository.sourceObjectPage(
        scope,
        sourceId,
        filters: _query,
      );
      if (_disposed || epoch != _epoch) return;
      _items
        ..clear()
        ..addAll(page.items);
      _adopt(page);
      _loaded = true;
    } on ApiFailure catch (failure) {
      if (_disposed || epoch != _epoch) return;
      _error = failure;
    } finally {
      if (!_disposed && epoch == _epoch) {
        _loading = false;
        _notify();
      }
    }
  }

  /// Appends the next page.
  ///
  /// A cursor is bound to the snapshot that issued it, so a recapture between
  /// two pages is refused rather than silently straddling two lists. That is
  /// recovered by reloading from the start, which is the only honest answer:
  /// the rows the reviewer was choosing from no longer exist.
  Future<void> loadMore() async {
    final String? cursor = _cursor;
    if (cursor == null || _loadingMore || _loading) return;
    final int epoch = _epoch;
    _loadingMore = true;
    _notify();
    try {
      final SourceObjectPage page = await repository.sourceObjectPage(
        scope,
        sourceId,
        filters: _query,
        cursor: cursor,
      );
      if (_disposed || epoch != _epoch) return;
      if (page.inventoryId != _inventoryId) {
        // A new snapshot is a different list. Start it again rather than
        // mixing two.
        _loadingMore = false;
        _refreshed = true;
        await load();
        return;
      }
      _items.addAll(page.items);
      _adopt(page);
    } on ApiFailure catch (failure) {
      if (_disposed || epoch != _epoch) return;
      if (_isStaleCursor(failure)) {
        _loadingMore = false;
        _refreshed = true;
        await load();
        return;
      }
      _error = failure;
    } finally {
      if (!_disposed && epoch == _epoch) {
        _loadingMore = false;
        _notify();
      }
    }
  }

  /// Loads every remaining page of this filter.
  ///
  /// This is what a select all over more than one page costs, and it is paid
  /// before anything is selected rather than after. An object cannot be
  /// imported without the generation its listing row carries, so a selection
  /// the client has not loaded is a selection it could not send.
  Future<void> loadAll() async {
    while (moreToLoad && _error == null && !_disposed) {
      final int before = _items.length;
      await loadMore();
      // A page that added nothing and left a cursor would spin forever.
      if (_items.length == before && moreToLoad) break;
    }
  }

  /// Clears the "this source was refreshed" flag once the reviewer has been
  /// told.
  void acknowledgeRefresh() {
    if (!_refreshed) return;
    _refreshed = false;
    _notify();
  }

  /// Narrows the listing and reloads from the first page.
  Future<void> applyFilter({SourceFilter? filter, String? mediaType}) {
    // A filter is part of a cursor's binding, so changing one invalidates
    // every page already loaded.
    _filter = filter ?? _filter;
    _mediaType = mediaType;
    return load();
  }

  void _adopt(SourceObjectPage page) {
    _cursor = page.nextCursor;
    _inventoryId = page.inventoryId;
    _capturedAt = page.capturedAt;
    _objectCount = page.objectCount;
    _matchingCount = page.matchingCount;
  }

  /// True for the failure a cursor issued against an older snapshot produces.
  static bool _isStaleCursor(ApiFailure failure) =>
      failure.code == 'pagination' ||
      failure.code == 'source_inventory_changed' ||
      (failure.status == 422 && failure.code == 'invalid_input');

  /// Adds [selection] to the queue, in as many requests as the server's bound
  /// takes.
  ///
  /// Reports progress through [onProgress] after every request, so a selection
  /// of a thousand is visibly moving rather than a spinner over twenty calls.
  ///
  /// An object the source refuses is reported against that object and never
  /// fails the rest, which is the server's own rule. Only an integrity failure
  /// stops the run, and when it does the photographs already added are named
  /// rather than concealed.
  Future<SourceImportProgress> importSelection(
    List<SourceObject> selection, {
    void Function(SourceImportProgress progress)? onProgress,
  }) async {
    SourceImportProgress progress = SourceImportProgress(
      requested: selection.length,
    );
    for (int start = 0; start < selection.length; start += sourceImportBatchSize) {
      final List<SourceObject> chunk = selection.sublist(
        start,
        (start + sourceImportBatchSize).clamp(0, selection.length),
      );
      // Memoised on the photographs at the generations they were picked at, so
      // a retry after an uncertain answer carries the key it carried the
      // first time and the server reconciles rather than importing twice.
      final String payload = chunk
          .map((SourceObject o) => '${o.objectName}@${o.generation}')
          .join(',');
      final String key = _importKeys.putIfAbsent(
        payload,
        () => 'from-source-${DateTime.now().microsecondsSinceEpoch}-$start',
      );
      try {
        progress = progress.add(
          await repository.importFromSource(scope, sourceId, chunk, key),
        );
      } on ApiFailure catch (failure) {
        return progress.stoppedBy(_stopReason(failure));
      }
      onProgress?.call(progress);
      if (_disposed) return progress;
    }
    return progress;
  }

  /// One sentence saying why a run stopped, and what to do.
  static String _stopReason(ApiFailure failure) =>
      failure.code == 'source_object_changed'
      ? 'This source changed while the photographs were being added. Reload '
            'the source and add the rest.'
      : failure.message;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
