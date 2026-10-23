/// Owns draft metadata, file-backed transfers, and submission reconciliation.
library;

import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../models.dart';
import 'bulk_intake_repository.dart';
import 'draft_file_store.dart';
import 'intake_timing.dart';

String intakeClientId() => List.generate(
  16,
  (_) => Random.secure().nextInt(256),
).map((value) => value.toRadixString(16).padLeft(2, '0')).join();

typedef _PreparedPhoto = ({
  XFile file,
  int size,
  String? hash,
  Json? previous,
  Object? failure,
});

typedef _UncertainPhoto = ({Json row, XFile retained, String? previousPath});

class _DraftPersistenceUncertain extends StateError {
  _DraftPersistenceUncertain()
    : super('Could not confirm whether draft metadata was saved');
}

class BulkIntakeController extends ChangeNotifier {
  BulkIntakeController({
    required this.repository,
    required this.scope,
    required this.userId,
  });
  final BulkIntakeRepository repository;
  final CollectionScope scope;
  final String userId;
  IntakeDraft? draft;
  List<IntakeDraftItem> items = [];
  List<IntakeSubmission> submissions = [];
  List<Json> drafts = [];
  List<Json> get savedDrafts {
    final localBatches = <String, int>{};
    for (final row in _local.values) {
      if (row['draft_id'] == null &&
          row['removed'] != true &&
          row['saved'] != true) {
        final id = row['batch_client_id'] as String;
        localBatches.update(id, (count) => count + 1, ifAbsent: () => 1);
      }
    }
    return [
      ...drafts,
      for (final entry in localBatches.entries)
        {
          'local_client_id': entry.key,
          'state': 'draft',
          'name': 'draft on this device (${entry.value} photos)',
        },
    ];
  }

  Json capabilities = {};
  String? error;
  bool loading = true, submitting = false;
  bool _disposed = false, _viewActive = true, _pollAgain = false;
  bool preparingFiles = false, addingSources = false;
  bool _sourceBulkRoutesMissing = false;
  int preparationCompleted = 0, preparationTotal = 0;
  int sourceAddCompleted = 0, sourceAddTotal = 0;
  String get preparationLabel =>
      'Preparing $preparationCompleted of $preparationTotal photos';
  String get sourceAddLabel =>
      'Adding $sourceAddCompleted of $sourceAddTotal photos';
  int _viewGeneration = 0, _readRevision = 0, _progressPages = 1;
  String? _progressId;
  final Map<String, IntakeSubmissionProgress> _progress = {};
  final Map<String, int> _progressGenerations = {};
  final Map<String, String> _progressErrors = {};
  Future<void>? _pollTask;
  String? _draftClientId;
  String get sourceContextKey {
    if (_draftClientId != null) return 'local:$_draftClientId';
    if (draft != null) return 'draft:${draft!.id}';
    return 'local:${_draftClientId ??= intakeClientId()}';
  }

  final Set<String> selected = {};
  List<String> lastRemoved = [];
  final Map<String, XFile> _files = {};
  final Map<String, Json> _local = {};
  final Map<String, _UncertainPhoto> _uncertainPhotos = {};
  final Map<String, Json> _pendingSources = {};
  final Map<String, String> _sourceIdentityIndex = {};
  String? _sourceIndexDraft;
  int _sourceRevision = 0, _sourceIndexRevision = -1;
  final Set<String> _queuedTransfers = {};
  final LinkedHashMap<String, Future<Uint8List>> _previews = LinkedHashMap();
  Future<void> _admissions = Future.value();
  Future<void> _mutations = Future.value();
  Future<void> _transfers = Future.value();
  Future<void> _previewTail = Future.value();
  Future<void> _persistence = Future.value();
  Timer? _timer;
  String get _owner => '$userId:${scope.key}';
  String get _key => 'bulk-intake-v1:${sha256.convert(utf8.encode(_owner))}';
  List<IntakeDraftItem> get visible {
    final replacing = _local.values
        .where((r) => r['replaces_id'] != null && r['removed'] != true)
        .map((r) => r['replaces_id'])
        .toSet();
    return items
        .where((item) => !item.removed && !replacing.contains(item.id))
        .toList();
  }

  int get readyCount => visible
      .where((item) => item.canSubmit && !item.id.startsWith('local:'))
      .length;
  int get savedCount => visible.where((item) => item.saved).length;
  bool get hasUnsaved => visible.any((item) => !item.saved);
  bool get hasPendingLocalTransfers => _local.values.any(
    (row) => row['saved'] != true && row['removed'] != true,
  );
  bool get needsOpenWorkspace =>
      !hasDurableLocalFiles && hasPendingLocalTransfers;
  bool get needsReselection => _local.values.any(
    (row) =>
        row['saved'] != true &&
        row['removed'] != true &&
        visible.any(
          (i) => i.id == row['item_id'] || i.id == 'local:${row['client_id']}',
        ) &&
        !_files.containsKey(row['client_id']),
  );
  String get saveLabel => visible.isEmpty
      ? 'Private draft'
      : savedCount == visible.length
      ? 'Saved'
      : needsReselection
      ? 'Choose original files to resume'
      : error != null
      ? 'Needs connection'
      : 'Saving $savedCount of ${visible.length}';

  void changed() {
    if (!_disposed) {
      setDraftLeaveWarning(!hasDurableLocalFiles && hasPendingLocalTransfers);
    }
    if (!_disposed) {
      if (_pollTask == null) _schedulePoll();
      notifyListeners();
    }
  }

  String message(Object e) => e is ApiFailure
      ? e.message
      : 'Could not save this change. Retry when your connection is available.';
  void _invalidateReads() {
    _readRevision++;
    if (_pollTask != null) _pollAgain = true;
  }

  Future<Json> call(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
  }) async {
    if (_disposed) throw StateError('Intake account changed');
    Future<Json> send() =>
        repository.intakeRequest(scope, method, path, body: body, query: query);
    // Admission, edits and Submit share a draft CAS. File transfers may keep
    // moving, but this controller never sends competing manifest mutations.
    final Future<Json> request;
    if (method == 'GET') {
      request = send();
    } else {
      request = _mutations.then((_) {
        if (_disposed) throw StateError('Intake account changed');
        _invalidateReads();
        return send().whenComplete(_invalidateReads);
      });
      _mutations = request.then<void>((_) {}, onError: (Object _) {});
    }
    final result = await request;
    if (_disposed) throw StateError('Intake account changed');
    return result;
  }

  Future<void> initialize() async {
    String? restoredId;
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(_key);
      if (saved != null) {
        final state = jsonDecode(saved) as Map;
        _draftClientId = state['client_id'] as String?;
        restoredId = state['active_draft_id'] as String?;
        for (final row in objects(state['sources'])) {
          _pendingSources[row['client_id'] as String] = row;
        }
        _sourceRevision++;
        for (final raw in (state['files'] as List? ?? [])) {
          final row = Map<String, dynamic>.from(raw as Map);
          _local[row['client_id'] as String] = row;
          final file = await restoreDraftFile(row['path'] as String);
          if (file != null) _files[row['client_id'] as String] = file;
          if (row['saved'] != true &&
              (restoredId != null
                  ? row['draft_id'] == restoredId
                  : row['batch_client_id'] == _draftClientId)) {
            items.add(
              IntakeDraftItem({
                ...row,
                'id': row['item_id'] ?? 'local:${row['client_id']}',
                'state': file == null ? 'needs_attention' : 'waiting',
                if (file == null)
                  'error': {
                    'message': 'Choose the original file again to resume.',
                  },
              }),
            );
          }
        }
      }
      capabilities = await call('GET', '/capabilities');
      await refreshLists();
      final open = drafts.where((d) => d['state'] == 'draft').toList()
        ..sort((a, b) => '${b['created_at']}'.compareTo('${a['created_at']}'));
      if (open.isNotEmpty && (restoredId != null || items.isEmpty)) {
        draft = IntakeDraft(
          open.where((d) => d['id'] == restoredId).firstOrNull ?? open.first,
        );
        await refreshDraft();
      }
      for (final row in _local.values.toList()) {
        if (_files.containsKey(row['client_id']) && row['saved'] != true) {
          _queueTransfer(row);
        }
      }
    } catch (e) {
      error = message(e);
    } finally {
      loading = false;
      changed();
      _schedulePoll();
    }
  }

  Future<void> _persist({Json? retainedFile}) {
    final write = _persistence.then((_) async {
      if (_disposed) {
        if (retainedFile != null) throw StateError('Intake account changed');
        return;
      }
      if (_uncertainPhotos.isNotEmpty &&
          !_uncertainPhotos.values.any(
            (photo) =>
                photo.row['client_id'] == retainedFile?['client_id'] &&
                photo.row['path'] == retainedFile?['path'],
          )) {
        throw StateError('Confirm the previous photo save before continuing');
      }
      final prefs = await SharedPreferences.getInstance();
      final files = {..._local};
      if (retainedFile != null) {
        files[retainedFile['client_id'] as String] = retainedFile;
      }
      final snapshot = jsonEncode({
        'client_id': _draftClientId,
        'active_draft_id': draft?.id,
        'files': files.values.toList(),
        'sources': _pendingSources.values.toList(),
      });
      Object? failure;
      StackTrace? failureStack;
      try {
        if (!await prefs.setString(_key, snapshot)) {
          failure = StateError('Draft metadata was not saved');
        }
      } catch (error, stack) {
        failure = error;
        failureStack = stack;
      }
      if (failure != null) {
        // A host may commit the value, then lose its acknowledgement. Reload
        // the host state rather than trusting the optimistic legacy cache.
        try {
          await prefs.reload();
        } catch (_) {
          // The outcome is unknown. Keep retained bytes for a later retry or
          // restart; deleting them could strand a committed metadata row.
          throw _DraftPersistenceUncertain();
        }
        if (prefs.getString(_key) != snapshot) {
          if (failureStack != null) {
            Error.throwWithStackTrace(failure, failureStack);
          }
          throw failure;
        }
      }
      // Publish a new file only after the metadata write has been accepted.
      // Commit within this queue so later snapshots include the new identity.
      if (retainedFile != null && !_disposed) {
        _local[retainedFile['client_id'] as String] = retainedFile;
      }
    });
    _persistence = write.catchError((Object _) {});
    return write;
  }

  Future<void> refreshLists({bool Function()? isCurrent}) async {
    final revision = _readRevision, generation = _viewGeneration;
    bool current() =>
        !_disposed &&
        revision == _readRevision &&
        generation == _viewGeneration &&
        isCurrent?.call() != false;
    final nextDrafts = await _pages('/drafts', isCurrent: current);
    if (!current()) return;
    final nextSubmissions =
        (await _pages(
          '/submissions',
          isCurrent: current,
        )).map(IntakeSubmission.new).toList()..sort(
          (a, b) =>
              '${b.data['created_at']}'.compareTo('${a.data['created_at']}'),
        );
    if (!current()) return;
    drafts = nextDrafts;
    submissions = nextSubmissions;
    if (nextDrafts.map(_pruneSourceReceipts).fold(false, (a, b) => a || b)) {
      await _persist();
    }
  }

  Future<List<Json>> _pages(String path, {bool Function()? isCurrent}) async {
    final rows = <Json>[];
    String? after;
    do {
      final page = await call(
        'GET',
        path,
        query: {'after': ?after, 'limit': '100'},
      );
      rows.addAll(objects(page['items']));
      after = page['next_cursor']?.toString();
    } while (after != null && !_disposed && isCurrent?.call() != false);
    return rows;
  }

  Future<void> refreshDraft({bool Function()? isCurrent}) async {
    final id = draft?.id;
    if (id == null) return;
    final revision = _readRevision, generation = _viewGeneration;
    bool current() =>
        !_disposed &&
        draft?.id == id &&
        revision == _readRevision &&
        generation == _viewGeneration &&
        isCurrent?.call() != false;
    final nextDraft = IntakeDraft(await call('GET', '/drafts/$id'));
    if (!current()) return;
    final rows = (await _pages(
      '/drafts/$id/items',
      isCurrent: current,
    )).map(IntakeDraftItem.new).toList();
    if (!current()) return;
    draft = nextDraft;
    var receiptsChanged = false;
    for (final item in rows) {
      final receipt = _pendingSources[item.data['client_id']];
      if (receipt != null &&
          (receipt['draft_id'] == id ||
              receipt['draft_id'] == item.data['draft_id']) &&
          receipt['item_id'] != item.id) {
        receipt['item_id'] = item.id;
        receipt['confirmed'] = true;
        receiptsChanged = true;
      }
    }
    items = [
      ...rows,
      for (final row in _local.values)
        if (row['saved'] != true &&
            row['removed'] != true &&
            (row['draft_id'] == id ||
                (row['draft_id'] == null &&
                    row['batch_client_id'] == _draftClientId)) &&
            !rows.any((i) => i.id == row['item_id']))
          IntakeDraftItem({
            ...row,
            'id': row['item_id'] ?? 'local:${row['client_id']}',
            'state': 'waiting',
          }),
    ];
    for (final row in _local.values.where(
      (r) => r['saved'] != true && !_files.containsKey(r['client_id']),
    )) {
      final index = items.indexWhere((item) => item.id == row['item_id']);
      if (index >= 0 && !items[index].saved) {
        items[index] = IntakeDraftItem({
          ...items[index].data,
          'state': 'needs_attention',
          'error': {'message': 'Choose the original file again to resume.'},
        });
      }
    }
    selected.removeWhere((id) => !visible.any((item) => item.id == id));
    if (receiptsChanged) await _persist();
    changed();
  }

  bool get _needsDraftPoll =>
      draft != null &&
      visible.any(
        (item) =>
            !item.id.startsWith('local:') &&
            const ['waiting', 'transferring', 'checking'].contains(item.state),
      );
  bool get _needsPoll => _progressId != null
      ? (_progress[_progressId]?.batch.active ?? true)
      : _needsDraftPoll;

  void setViewActive(bool active) {
    if (_viewActive == active || _disposed) return;
    _viewActive = active;
    _viewGeneration++;
    _timer?.cancel();
    if (active) {
      if (_pollTask != null) {
        _pollAgain = true;
      } else {
        unawaited(poll(force: true));
      }
    }
  }

  void _schedulePoll() {
    _timer?.cancel();
    if (_disposed || !_viewActive || loading || !_needsPoll) return;
    _timer = Timer(intakePollInterval, () => unawaited(poll()));
  }

  IntakeSubmissionProgress? progressFor(String id) => _progress[id];
  String? progressErrorFor(String id) => _progressErrors[id];

  Future<void> observeSubmission(String id) {
    if (_progressId != id) {
      _progressId = id;
      _progressPages = 1;
    }
    return _refreshCurrentView();
  }

  Future<void> _refreshCurrentView() {
    _viewGeneration++;
    final previous = _pollTask;
    if (previous == null) return poll(force: true);
    _pollAgain = true;
    return previous.then((_) => poll(force: true));
  }

  void stopObservingSubmission(String id) {
    if (_progressId != id) return;
    _progressId = null;
    _viewGeneration++;
    _schedulePoll();
  }

  Future<void> loadMoreProgress(String id) {
    if (_progressId != id || _progress[id]?.hasMore != true) {
      return Future.value();
    }
    _progressPages++;
    return _refreshCurrentView();
  }

  Future<List<IntakeSubmissionItem>> progressItemsForAction(String id) async {
    if (_disposed || _progressId != id || !_viewActive) {
      throw StateError('Intake view changed');
    }
    final visiblePages = _progressPages;
    // Repair is an explicit action on the entire submission, including rows
    // beyond the current page. Ordinary polling keeps its current page bound.
    _progressPages = 5;
    try {
      await _refreshCurrentView();
      if (_disposed ||
          _progressId != id ||
          !_viewActive ||
          _progressErrors[id] != null ||
          _progressGenerations[id] != _viewGeneration ||
          _progress[id]?.hasMore != false) {
        throw const ApiFailure('Refresh this submission before retrying.');
      }
      return List.of(_progress[id]?.items ?? const []);
    } finally {
      if (_progressId == id) _progressPages = visiblePages;
    }
  }

  Future<void> poll({bool force = false}) {
    if (_disposed || !_viewActive || loading) return Future.value();
    if (_pollTask != null) return _pollTask!;
    if (!force && !_needsPoll) return Future.value();
    _timer?.cancel();
    _pollAgain = false;
    final generation = _viewGeneration, revision = _readRevision;
    bool current() =>
        !_disposed &&
        _viewActive &&
        generation == _viewGeneration &&
        revision == _readRevision;
    final task = _reconcileView(current, force: force);
    _pollTask = task;
    return task.whenComplete(() {
      _pollTask = null;
      if (_pollAgain && _viewActive && !_disposed) {
        _pollAgain = false;
        unawaited(poll(force: true));
      } else {
        _schedulePoll();
      }
    });
  }

  Future<void> _reconcileView(
    bool Function() current, {
    required bool force,
  }) async {
    final id = _progressId;
    try {
      if (id != null) {
        final batch = IntakeSubmission(await call('GET', '/submissions/$id'));
        if (!current()) return;
        final rows = <IntakeSubmissionItem>[];
        String? after;
        for (var pageIndex = 0; pageIndex < _progressPages; pageIndex++) {
          final page = await call(
            'GET',
            '/submissions/$id/items',
            query: {'limit': '100', 'after': ?after},
          );
          if (!current()) return;
          rows.addAll(objects(page['items']).map(IntakeSubmissionItem.new));
          after = page['next_cursor']?.toString();
          if (after == null) break;
        }
        await reconcileFinishedTransfers(rows);
        if (!current()) return;
        _progress[id] = IntakeSubmissionProgress(
          batch: batch,
          items: rows,
          hasMore: after != null,
        );
        _progressGenerations[id] = _viewGeneration;
        _progressErrors.remove(id);
        final index = submissions.indexWhere((row) => row.id == id);
        if (index >= 0) submissions[index] = batch;
      } else {
        if (draft != null && (force || _needsDraftPoll)) {
          await refreshDraft(isCurrent: current);
        }
        if (force && current()) await refreshLists(isCurrent: current);
      }
      if (current()) changed();
    } catch (failure) {
      // Keep the last confirmed queue; polling never invents a failure/success.
      if (id != null && current()) {
        _progressErrors[id] = message(failure);
        changed();
      }
    }
  }

  Future<void> ensureDraft() async {
    if (draft?.editable == true) return;
    _draftClientId ??= intakeClientId();
    await _persist();
    draft = IntakeDraft(
      await call('POST', '/drafts', body: {'client_id': _draftClientId}),
    );
    _rememberDraft(draft!);
  }

  void _rememberDraft(IntakeDraft value) {
    drafts.removeWhere((row) => row['id'] == value.id);
    drafts.add(value.data);
  }

  Future<void> addFiles(
    List<XFile> files, {
    bool camera = false,
    bool sensitive = false,
    String? replacesId,
  }) {
    final admission = _admissions.then((_) async {
      if (_disposed || files.isEmpty) return;
      _draftClientId ??= intakeClientId();
      preparingFiles = true;
      preparationCompleted = 0;
      preparationTotal = files.length;
      changed();
      final matched = <String>{};
      Future<_PreparedPhoto> prepare(XFile file) async {
        try {
          final size = await file.length();
          if (size == 0 || size > 25000000) {
            throw const ApiFailure(
              'Photos must be non-empty and 25 MB or smaller.',
              code: 'image_size',
            );
          }
          final hash = (await sha256.bind(file.openRead()).first).toString();
          final previous = camera || replacesId != null
              ? null
              : _local.values
                    .where(
                      (row) =>
                          row['sha256'] == hash &&
                          row['saved'] != true &&
                          row['removed'] != true &&
                          !_files.containsKey(row['client_id']) &&
                          !matched.contains(row['client_id']) &&
                          (draft != null
                              ? row['draft_id'] == draft!.id
                              : row['batch_client_id'] == _draftClientId),
                    )
                    .firstOrNull;
          if (previous != null) matched.add(previous['client_id'] as String);
          return (
            file: file,
            size: size,
            hash: hash,
            previous: previous,
            failure: null,
          );
        } catch (failure) {
          return (
            file: file,
            size: 0,
            hash: null,
            previous: null,
            failure: failure,
          );
        }
      }

      Future<void> publish(_PreparedPhoto photo) async {
        if (_disposed) return;
        final file = photo.file, id = intakeClientId();
        XFile? retained;
        late Json row;
        String? previousPath;
        var committed = false;
        try {
          if (photo.failure != null) throw photo.failure!;
          final previous = photo.previous;
          final uncertain = _uncertainPhotos[file.path];
          final clientId =
              uncertain?.row['client_id'] as String? ??
              previous?['client_id'] as String? ??
              id;
          if (uncertain != null) {
            retained = uncertain.retained;
            row = uncertain.row;
            previousPath = uncertain.previousPath;
          } else {
            // A reselection may reuse the previous client identity. Keep its
            // earlier bytes intact until replacement metadata is durable.
            retained = await retainDraftFile(
              file,
              _owner,
              previous == null ? clientId : '$clientId-${intakeClientId()}',
            );
            previousPath = previous?['path'] as String?;
            row = <String, dynamic>{
              ...?previous,
              'client_id': clientId,
              'batch_client_id': previous?['batch_client_id'] ?? _draftClientId,
              if (draft != null) 'draft_id': draft!.id,
              'path': retained.path,
              'filename': file.name,
              'size_bytes': photo.size,
              'sha256': photo.hash,
              'media_type': _mediaType(file),
              'photo_sensitive': previous?['photo_sensitive'] ?? sensitive,
              'replaces_id': ?replacesId,
              'source':
                  previous?['source'] ??
                  {'provider': camera ? 'camera' : 'files'},
              'saved': false,
            };
          }
          await _persist(retainedFile: row);
          committed = true;
          _uncertainPhotos.remove(file.path);
          if (_disposed) return;
          _files[clientId] = retained;
          if (!items.any(
            (item) => item.id == row['item_id'] || item.id == 'local:$clientId',
          )) {
            items.add(
              IntakeDraftItem({
                ...row,
                'id': 'local:$clientId',
                'state': 'waiting',
              }),
            );
          }
          changed();
          _queueTransfer(row);
          if (previousPath != null && previousPath != retained.path) {
            try {
              await releaseDraftFile(previousPath);
            } catch (_) {
              // The newly acknowledged path remains the recovery source.
            }
          }
        } catch (failure) {
          if (!committed && retained != null) {
            if (failure is _DraftPersistenceUncertain) {
              _uncertainPhotos[file.path] = (
                row: row,
                retained: retained,
                previousPath: previousPath,
              );
            } else {
              _uncertainPhotos.remove(file.path);
              try {
                await releaseDraftFile(retained.path);
              } catch (_) {
                // A failed cleanup must not hide the failed admission.
              }
            }
          }
          if (camera) rethrow;
          if (retained != null && !committed) {
            // The file is still selectable; a synthetic failed item would
            // become a duplicate when the user retries this same original.
            error = message(failure);
          } else {
            items.add(
              IntakeDraftItem({
                'id': 'local:$id',
                'filename': file.name,
                'state': 'needs_attention',
                'error': {'message': message(failure)},
              }),
            );
          }
        }
        preparationCompleted++;
        changed();
        // Give the first prepared photo and progress a frame before hashing
        // another original, including when file/persistence futures are fast.
        await Future<void>.delayed(Duration.zero);
      }

      try {
        // Only an ambiguous near-capacity reselection needs all hashes first.
        // Ordinary batches publish their first retained file immediately.
        if (visible.length + files.length - (replacesId == null ? 0 : 1) >
            500) {
          final prepared = <_PreparedPhoto>[];
          for (final file in files) {
            if (_disposed) return;
            prepared.add(await prepare(file));
          }
          final additions = prepared
              .where((photo) => photo.previous == null)
              .length;
          if (visible.length + additions - (replacesId == null ? 0 : 1) > 500) {
            error =
                'A batch holds up to 500 photos. Choose fewer files or start another batch.';
            if (camera) throw ApiFailure(error!, code: 'batch_limit');
            return;
          }
          for (final photo in prepared) {
            await publish(photo);
          }
        } else {
          for (final file in files) {
            if (_disposed) return;
            await publish(await prepare(file));
          }
        }
      } finally {
        preparingFiles = false;
        changed();
      }
    });
    // A failed capture must reach its caller without poisoning later retries.
    _admissions = admission.catchError((Object _) {});
    return admission;
  }

  String _mediaType(XFile file) {
    if (file.mimeType?.startsWith('image/') == true) return file.mimeType!;
    return switch (file.name.toLowerCase().split('.').last) {
      'jpg' || 'jpeg' => 'image/jpeg',
      'png' => 'image/png',
      'tif' || 'tiff' => 'image/tiff',
      'heic' || 'heif' => 'image/heic',
      'dng' => 'image/dng',
      _ => 'application/octet-stream',
    };
  }

  void _queueTransfer(Json row) {
    final clientId = row['client_id'] as String;
    if (!_queuedTransfers.add(clientId)) return;
    _transfers = _transfers.then((_) async {
      try {
        if (_disposed || row['removed'] == true) return;
        await _transfer(row);
        error = null;
      } catch (e) {
        error = message(e);
      } finally {
        _queuedTransfers.remove(clientId);
      }
      changed();
    });
  }

  Future<void> _transfer(Json row) async {
    if (_disposed || row['removed'] == true) return;
    final file = _files[row['client_id']];
    if (file == null) {
      throw const ApiFailure(
        'Choose the original file again to resume this photo.',
        code: 'reselect',
      );
    }
    Json item;
    if (row['item_id'] == null) {
      if (row['draft_id'] == null) {
        final batch = IntakeDraft(
          await call(
            'POST',
            '/drafts',
            body: {'client_id': row['batch_client_id'] ?? _draftClientId},
          ),
        );
        row['draft_id'] = batch.id;
        _rememberDraft(batch);
        if (row['batch_client_id'] == _draftClientId) draft = batch;
        await _persist();
      }
      row['registration'] ??= {
        for (final key in [
          'client_id',
          'filename',
          'media_type',
          'size_bytes',
          'sha256',
          'photo_sensitive',
          'source',
          if (row['replaces_id'] != null) 'replaces_id',
        ])
          key: row[key],
      };
      await _persist();
      try {
        item = await call(
          'POST',
          '/drafts/${row['draft_id']}/items',
          body: Map<String, dynamic>.from(row['registration'] as Map),
        );
      } on ApiFailure catch (failure) {
        if (!failure.conflict) rethrow;
        final old = await call('GET', '/drafts/${row['draft_id']}');
        if (old['state'] != 'submitted') rethrow;
        final next = old['remaining_draft_id'] as String?;
        final batch = next != null
            ? await call('GET', '/drafts/$next')
            : await call(
                'POST',
                '/drafts',
                body: {'client_id': 'pending-${row['draft_id']}'},
              );
        row['draft_id'] = batch['id'];
        _rememberDraft(IntakeDraft(batch));
        if (items.any((i) => i.id == 'local:${row['client_id']}')) {
          draft = IntakeDraft(batch);
        }
        await _persist();
        return _transfer(row);
      }
      row['item_id'] = item['id'];
      await _persist();
      items.removeWhere((i) => i.id == 'local:${row['client_id']}');
      if (draft?.id == row['draft_id']) {
        items.add(
          IntakeDraftItem({
            ...item,
            'photo_sensitive': row['photo_sensitive'],
            'included': true,
            'removed': row['removed'] == true,
          }),
        );
      }
      changed();
      if (row['removed'] == true) {
        final latest = await call('GET', '/drafts/${row['draft_id']}');
        await call(
          'POST',
          '/drafts/${row['draft_id']}/edit',
          body: {
            'expected_revision': latest['revision'],
            'item_ids': [item['id']],
            'action': 'remove',
          },
        );
        return;
      }
    } else {
      item = await call('GET', '/items/${row['item_id']}');
    }
    await _syncLocalEdits(row);
    if (item['state'] != 'ready') {
      var offset = (item['offset'] as num).toInt();
      final size = (row['size_bytes'] as num).toInt();
      while (offset < size) {
        if (_disposed || row['removed'] == true) return;
        final end = min(offset + 1024 * 1024, size);
        final builder = BytesBuilder(copy: false);
        await for (final bytes in file.openRead(offset, end)) {
          builder.add(bytes);
        }
        if (_disposed || row['removed'] == true) return;
        _invalidateReads();
        try {
          item = await repository.intakeRequest(
            scope,
            'PUT',
            '/items/${row['item_id']}/content',
            offset: offset,
            bytes: builder.takeBytes(),
          );
        } finally {
          _invalidateReads();
        }
        final next = (item['offset'] as num).toInt();
        if (next <= offset || next > size) {
          throw const ApiFailure(
            'Refresh to reconcile the saved upload position.',
            code: 'upload_offset',
          );
        }
        offset = next;
        _replaceItem(item);
      }
      item = await call('POST', '/items/${row['item_id']}/save');
    }
    row['saved'] = true;
    await _persist();
    _replaceItem(item);
    // The server has acknowledged every byte. Local retention is no longer
    // needed for recovery, even if validation is still queued there.
    _files.remove(row['client_id']);
    await releaseDraftFile(row['path'] as String);
  }

  Future<void> _syncLocalEdits(Json row) async {
    var current = await call('GET', '/drafts/${row['draft_id']}');
    if (current['state'] != 'draft') return;
    final entry = objects(
      current['entries'],
    ).where((e) => e['id'] == row['item_id']).firstOrNull;
    if (entry == null) return;
    for (final field in ['included', 'photo_sensitive']) {
      final desired = row[field] ?? (field == 'included');
      if (entry[field] == desired) continue;
      current = await call(
        'POST',
        '/drafts/${row['draft_id']}/edit',
        body: {
          'expected_revision': current['revision'],
          'item_ids': [row['item_id']],
          'action': field == 'included'
              ? (desired == true ? 'include' : 'exclude')
              : 'sensitive',
          if (field == 'photo_sensitive') 'value': desired,
        },
      );
    }
  }

  void _replaceItem(Json data) {
    final index = items.indexWhere((item) => item.id == data['id']);
    if (index >= 0) {
      items[index] = IntakeDraftItem({...items[index].data, ...data});
    }
    changed();
  }

  Future<void> retrySaving() async {
    error = null;
    try {
      capabilities = await call('GET', '/capabilities');
      for (final item in visible.where(
        (i) => i.state == 'needs_attention' && !i.id.startsWith('local:'),
      )) {
        await call('POST', '/items/${item.id}/retry');
      }
      for (final row in _local.values.where((row) => row['saved'] != true)) {
        _queueTransfer(row);
      }
      await _transfers;
      await refreshDraft();
      await refreshLists();
    } catch (e) {
      error = message(e);
    }
    changed();
  }

  String _sourceIdentity(Json input, {bool includeClientId = true}) {
    Object? canonical(Object? value) {
      if (value is Map) {
        final keys = value.keys.map((key) => key as String).toList()..sort();
        return {for (final key in keys) key: canonical(value[key])};
      }
      if (value is List) return value.map(canonical).toList();
      return value;
    }

    return jsonEncode(
      canonical({
        for (final entry in input.entries)
          if (includeClientId || entry.key != 'client_id')
            entry.key: entry.value,
      }),
    );
  }

  String? retainedSourceClientId(Json input) {
    final id = draft?.id;
    if (id == null) return null;
    if (_sourceIndexDraft != id || _sourceIndexRevision != _sourceRevision) {
      _sourceIdentityIndex.clear();
      for (final row in _pendingSources.values) {
        if (row['draft_id'] != id) continue;
        _sourceIdentityIndex[_sourceIdentity(
              Map<String, dynamic>.from(row['body'] as Map),
              includeClientId: false,
            )] =
            row['client_id'] as String;
      }
      _sourceIndexDraft = id;
      _sourceIndexRevision = _sourceRevision;
    }
    final retained =
        _sourceIdentityIndex[_sourceIdentity(input, includeClientId: false)];
    return retained != null && !sourceClientIdRemoved(retained)
        ? retained
        : null;
  }

  bool sourceClientIdRemoved(String id) =>
      items.any((item) => item.data['client_id'] == id && item.removed);

  bool _pruneSourceReceipts(Json value) {
    if (!const ['submitted', 'discarded'].contains(value['state'])) {
      return false;
    }
    final terminalIds = {
      for (final entry in objects(value['submitted_entries'])) entry['id'],
      for (final entry in objects(value['entries']))
        if (value['state'] == 'discarded' || entry['removed'] == true)
          entry['id'],
    };
    final before = _pendingSources.length;
    _pendingSources.removeWhere(
      (_, row) =>
          terminalIds.contains(row['item_id']) ||
          (row['draft_id'] == value['id'] && value['state'] == 'discarded'),
    );
    if (_pendingSources.length == before) return false;
    _sourceRevision++;
    return true;
  }

  Future<Json> _sourceResponse(
    String draftId,
    List<Json> inputs, {
    required bool reconcile,
  }) async {
    if (capabilities['bulk_source_admission'] == true &&
        !_sourceBulkRoutesMissing) {
      try {
        return await call(
          'POST',
          '/drafts/$draftId/items/${reconcile ? 'reconcile' : 'bulk'}',
          body: {'items': inputs},
        );
      } on ApiFailure catch (failure) {
        if (!const [404, 405].contains(failure.status)) rethrow;
        _sourceBulkRoutesMissing = true;
      }
    }
    // An older runtime still supports exact idempotent item registration.
    // Advance one photo at a time so each acknowledged identity is persisted.
    final item = await call(
      'POST',
      '/drafts/$draftId/items',
      body: inputs.first,
    );
    final manifest = await call('GET', '/drafts/$draftId');
    final entry = objects(
      manifest['entries'],
    ).where((row) => row['id'] == item['id']).firstOrNull;
    if (entry == null) {
      throw const ApiFailure(
        'Refresh to reconcile the photo already added.',
        code: 'admission_reconciliation',
      );
    }
    return {
      'items': [
        {...item, ...entry, 'id': item['id']},
      ],
      'pending_client_ids': [
        for (final input in inputs.skip(1)) input['client_id'],
      ],
      'draft_revision': manifest['revision'],
    };
  }

  Future<void> addSource(List<Json> photos) {
    final admission = _admissions.then((_) async {
      if (_disposed || photos.isEmpty) return;
      addingSources = true;
      sourceAddCompleted = 0;
      sourceAddTotal = photos.length;
      error = null;
      changed();
      String? draftId;
      try {
        for (final photo in photos) {
          if (photo['client_id'] case final String id) {
            if (sourceClientIdRemoved(id)) photo.remove('client_id');
          }
          final retained = retainedSourceClientId(photo);
          if (!_pendingSources.containsKey(photo['client_id']) &&
              retained != null) {
            photo['client_id'] = retained;
          }
          photo['client_id'] ??= intakeClientId();
        }
        final ids = photos.map((photo) => photo['client_id']).toSet();
        if (ids.length != photos.length) {
          throw const ApiFailure(
            'Choose each photo once for this batch.',
            code: 'duplicate_client_id',
          );
        }
        final admitted = items.map((item) => item.data['client_id']).toSet();
        if (visible.length + ids.where((id) => !admitted.contains(id)).length >
            500) {
          throw ApiFailure(
            'Choose up to ${500 - visible.length} more photos for this batch.',
            code: 'batch_limit',
          );
        }
        await ensureDraft();
        draftId = draft!.id;
        final inputs = photos
            .map(
              (photo) => Map<String, dynamic>.from(
                jsonDecode(jsonEncode(photo)) as Map,
              ),
            )
            .toList();
        for (final input in inputs) {
          final id = input['client_id'] as String;
          final previous = _pendingSources[id];
          if (previous != null &&
              (previous['draft_id'] != draftId ||
                  _sourceIdentity(
                        Map<String, dynamic>.from(previous['body'] as Map),
                      ) !=
                      _sourceIdentity(input))) {
            throw const ApiFailure(
              'This photo selection changed. Choose it again before adding.',
              code: 'source_changed',
            );
          }
          _pendingSources[id] = {
            ...?previous,
            'client_id': id,
            'draft_id': draftId,
            'body': input,
            'attempted': previous?['attempted'] == true,
          };
        }
        _sourceRevision++;
        // Persist the exact original request, not a regenerated source identity.
        await _persist();
        final confirmed = <String>{};
        for (var start = 0; start < inputs.length; start += 50) {
          var pending = inputs.sublist(start, min(start + 50, inputs.length));
          final reconcileFirst = pending.any(
            (input) =>
                admitted.contains(input['client_id']) ||
                _pendingSources[input['client_id']]?['attempted'] == true,
          );
          var reconcile = reconcileFirst;
          while (pending.isNotEmpty) {
            if (_disposed) return;
            for (final input in pending) {
              _pendingSources[input['client_id']]?['attempted'] = true;
            }
            await _persist();
            Json response;
            Object? interrupted;
            try {
              response = await _sourceResponse(
                draftId,
                pending,
                reconcile: reconcile,
              );
            } catch (failure) {
              if (reconcile) rethrow;
              interrupted = failure;
              response = await _sourceResponse(
                draftId,
                pending,
                reconcile: true,
              );
            }
            final wanted = {
              for (final input in pending) input['client_id'] as String: input,
            };
            final returned = objects(response['items']);
            final remaining = (response['pending_client_ids'] as List?)
                ?.cast<String>();
            final found = returned.map((item) => item['client_id']).toList();
            if (remaining == null ||
                found.any((id) => !wanted.containsKey(id)) ||
                found.toSet().length != found.length ||
                remaining.toSet().length != remaining.length ||
                remaining.any(
                  (id) => !wanted.containsKey(id) || found.contains(id),
                ) ||
                found.length + remaining.length != wanted.length ||
                returned.any((item) => item['id'] is! String)) {
              throw const ApiFailure(
                'Refresh to reconcile the photos already added.',
                code: 'admission_reconciliation',
              );
            }
            for (final item in returned) {
              final clientId = item['client_id'] as String;
              confirmed.add(clientId);
              _pendingSources[clientId]?['confirmed'] = true;
              _pendingSources[clientId]?['item_id'] = item['id'];
              final value = IntakeDraftItem({
                ...item,
                'photo_sensitive': item['photo_sensitive'] ?? item['sensitive'],
                'included': item['included'] ?? true,
              });
              final index = items.indexWhere(
                (existing) => existing.id == value.id,
              );
              if (index < 0) {
                items.add(value);
              } else {
                items[index] = value;
              }
            }
            sourceAddCompleted = confirmed.length;
            await _persist();
            changed();
            if (remaining.isNotEmpty && interrupted != null) throw interrupted;
            if (remaining.isNotEmpty && returned.isEmpty && !reconcile) {
              throw const ApiFailure(
                'Adding paused before the next photo. Retry to continue.',
                code: 'admission_paused',
              );
            }
            pending = [for (final id in remaining) wanted[id]!];
            reconcile = false;
          }
        }
      } catch (failure) {
        error = message(failure);
      } finally {
        if (draftId != null && draft?.id == draftId && !_disposed) {
          try {
            await refreshDraft();
          } catch (failure) {
            error ??= message(failure);
          }
        }
        addingSources = false;
        changed();
      }
    });
    _admissions = admission.catchError((Object _) {});
    return admission;
  }

  void select(String id, bool value) {
    value ? selected.add(id) : selected.remove(id);
    changed();
  }

  Future<void> edit(String action, {bool? value, List<String>? ids}) async {
    final chosen = ids ?? selected.toList();
    final remote = <String>[];
    for (final id in chosen) {
      final row = _local.values
          .where((r) => r['item_id'] == id || 'local:${r['client_id']}' == id)
          .firstOrNull;
      final field = switch (action) {
        'remove' || 'restore' => 'removed',
        'include' || 'exclude' => 'included',
        _ => 'photo_sensitive',
      };
      final changedValue = switch (action) {
        'remove' || 'include' => true,
        'restore' || 'exclude' => false,
        _ => value,
      };
      if (row != null) {
        row[field] = changedValue;
        final index = items.indexWhere(
          (i) => i.id == id || i.id == row['item_id'],
        );
        if (index >= 0) {
          items[index] = IntakeDraftItem({
            ...items[index].data,
            field: changedValue,
          });
        }
        if (row['item_id'] != null) remote.add(row['item_id'] as String);
        if (action == 'restore' && row['saved'] != true) _queueTransfer(row);
      } else if (!id.startsWith('local:')) {
        remote.add(id);
      } else if (action == 'remove') {
        items.removeWhere((i) => i.id == id);
      }
    }
    if (action == 'remove') lastRemoved = chosen;
    if (action == 'restore') lastRemoved = [];
    await _persist();
    if (remote.isEmpty || draft == null) {
      selected.clear();
      changed();
      return;
    }
    try {
      draft = IntakeDraft(await call('GET', '/drafts/${draft!.id}'));
      draft = IntakeDraft(
        await call(
          'POST',
          '/drafts/${draft!.id}/edit',
          body: {
            'expected_revision': draft!.revision,
            'item_ids': remote,
            'action': action,
            'value': ?value,
          },
        ),
      );
      selected.clear();
      await refreshDraft();
    } catch (e) {
      error = message(e);
      changed();
    }
  }

  Future<IntakeSubmission?> submit() async {
    if (submitting ||
        preparingFiles ||
        addingSources ||
        draft == null ||
        readyCount == 0) {
      return null;
    }
    submitting = true;
    error = null;
    changed();
    try {
      final reviewed = {
        for (final item in visible.where(
          (item) => item.canSubmit && !item.id.startsWith('local:'),
        ))
          item.id: item.sensitive,
      };
      final chosen = reviewed.keys.toList();
      final current = await call('GET', '/drafts/${draft!.id}');
      final latestEntries = {
        for (final entry in objects(current['entries'])) entry['id']: entry,
      };
      if (reviewed.entries.any((photo) {
        final entry = latestEntries[photo.key];
        return entry == null ||
            entry['included'] != true ||
            entry['removed'] != false ||
            entry['photo_sensitive'] != photo.value;
      })) {
        await refreshDraft();
        throw const ApiFailure(
          'This batch changed. Review the updated photos before submitting.',
          code: 'draft_changed',
        );
      }
      final result = await call(
        'POST',
        '/drafts/${draft!.id}/submit',
        body: {'expected_revision': current['revision'], 'item_ids': chosen},
      );
      _pruneSourceReceipts({
        ...current,
        'state': 'submitted',
        'submitted_entries': [
          for (final entry in objects(current['entries']))
            if (chosen.contains(entry['id'])) entry,
        ],
      });
      final remaining = result['remaining_draft_id'] as String?;
      _local.removeWhere(
        (_, row) => chosen.contains(row['item_id']) && row['saved'] == true,
      );
      items = items.where((i) => i.id.startsWith('local:')).toList();
      selected.clear();
      draft = null;
      _draftClientId = null;
      if (remaining != null) {
        draft = IntakeDraft(await call('GET', '/drafts/$remaining'));
        await refreshDraft();
      }
      await _persist();
      await refreshLists();
      return IntakeSubmission(result);
    } catch (e) {
      error = message(e);
      return null;
    } finally {
      submitting = false;
      changed();
    }
  }

  Future<void> openDraft(Json value) => _changeDraft(() async {
    _viewGeneration++;
    final localId = value['local_client_id'] as String?;
    if (localId != null) {
      draft = null;
      _draftClientId = localId;
      items = [
        for (final row in _local.values)
          if (row['batch_client_id'] == localId && row['removed'] != true)
            IntakeDraftItem({
              ...row,
              'id': row['item_id'] ?? 'local:${row['client_id']}',
              'state': _files.containsKey(row['client_id'])
                  ? 'waiting'
                  : 'needs_attention',
              if (!_files.containsKey(row['client_id']))
                'error': {
                  'message': 'Choose the original file again to resume.',
                },
            }),
      ];
      selected.clear();
      await _persist();
      changed();
      return;
    }
    draft = IntakeDraft(value);
    _draftClientId = null;
    items = [];
    selected.clear();
    await refreshDraft();
    await _persist();
    changed();
  });

  Future<void> reselectSubmission(
    String submissionId,
    List<XFile> files,
  ) async {
    // Reconcile any already-running upload before replacing its local handle.
    await _transfers;
    final candidates = await _pages('/submissions/$submissionId/items');
    final matched = <String>{};
    var unmatched = 0;
    error = null;
    for (final file in files) {
      final size = await file.length();
      if (size == 0 || size > 25000000) {
        unmatched++;
        continue;
      }
      final hash = (await sha256.bind(file.openRead()).first).toString();
      final target = candidates
          .where(
            (row) =>
                row['needs_original'] == true &&
                row['sha256'] == hash &&
                row['size_bytes'] == size &&
                !matched.contains(row['item_id']),
          )
          .firstOrNull;
      if (target == null) {
        unmatched++;
        continue;
      }
      final item = await call('GET', '/items/${target['item_id']}');
      final clientId = item['client_id'] as String;
      final retained = await retainDraftFile(file, _owner, clientId);
      final row = <String, dynamic>{
        ...item,
        'item_id': item['id'],
        'path': retained.path,
        'saved': false,
        'photo_sensitive': item['sensitive'],
        'submission_id': submissionId,
      };
      _local[clientId] = row;
      _files[clientId] = retained;
      matched.add(item['id'] as String);
      await _persist();
      changed();
      // The immutable submitted item is resumed directly: no draft admission,
      // metadata edit, or new specimen identity is created by reselection.
      _queueTransfer(row);
    }
    await _transfers;
    if (unmatched > 0) {
      error =
          '$unmatched files did not match unfinished photos in this submission. Choose their original files.';
    }
    await refreshLists();
    changed();
  }

  Future<void> reconcileFinishedTransfers(
    List<IntakeSubmissionItem> results,
  ) async {
    final finished = results
        .where(
          (row) =>
              ['sent', 'duplicate', 'held', 'cancelled'].contains(row.state),
        )
        .map((row) => row.itemId)
        .toSet();
    final removed = _local.keys
        .where((id) => finished.contains(_local[id]!['item_id']))
        .toList();
    for (final id in removed) {
      final row = _local.remove(id)!;
      row['removed'] = true;
      _files.remove(id);
      await releaseDraftFile(row['path'] as String);
    }
    if (removed.isNotEmpty) {
      await _persist();
      changed();
    }
  }

  Future<void> _changeDraft(Future<void> Function() change) {
    final update = _admissions.then((_) async {
      if (_disposed) return;
      await change();
    });
    _admissions = update.catchError((Object _) {});
    return update;
  }

  Future<void> newDraft() => _changeDraft(_newDraft);

  Future<void> _newDraft() async {
    await _persist();
    _viewGeneration++;
    draft = null;
    _draftClientId = intakeClientId();
    items = [];
    selected.clear();
    lastRemoved = [];
    await _persist();
    changed();
  }

  Future<void> discardDraft() => _changeDraft(() async {
    final current = draft;
    if (current != null) {
      final latest = await call('GET', '/drafts/${current.id}');
      await call(
        'POST',
        '/drafts/${current.id}/discard',
        body: {'expected_revision': latest['revision']},
      );
      _pruneSourceReceipts({...latest, 'state': 'discarded'});
    }
    final localIds = _local.entries
        .where(
          (e) => current == null
              ? e.value['batch_client_id'] == _draftClientId
              : e.value['draft_id'] == current.id,
        )
        .map((e) => e.key)
        .toList();
    for (final id in localIds) {
      final row = _local.remove(id)!;
      row['removed'] = true;
      _files.remove(id);
      await releaseDraftFile(row['path'] as String);
    }
    await _newDraft();
    await refreshLists();
  });

  void invalidatePreview(IntakeDraftItem item, {bool full = false}) {
    _previews.remove(
      '${item.id}:${item.data['state']}:${item.data['revision']}:$full',
    );
  }

  Future<Uint8List> preview(IntakeDraftItem item, {bool full = false}) {
    final key =
        '${item.id}:${item.data['state']}:${item.data['revision']}:$full';
    final cached = _previews.remove(key);
    if (cached != null) {
      _previews[key] = cached;
      return cached;
    }
    final future = () async {
      if (item.saved) {
        return repository.intakePreview(scope, item.id, full: full);
      }
      final row = _local.values
          .where(
            (row) =>
                row['item_id'] == item.id ||
                'local:${row['client_id']}' == item.id,
          )
          .firstOrNull;
      final file = row == null ? null : _files[row['client_id']];
      if (file == null) throw const IntakePreviewPending();
      // Only one original is decoded at a time, even when many tiles mount.
      final previous = _previewTail;
      final gate = Completer<void>();
      _previewTail = gate.future;
      await previous;
      try {
        if (_disposed) throw StateError('Intake closed');
        final bytes = await file.readAsBytes();
        final descriptorBuffer = await ui.ImmutableBuffer.fromUint8List(bytes);
        final descriptor = await ui.ImageDescriptor.encoded(descriptorBuffer);
        final longest = full ? 1600 : 400;
        final scale = min(
          1.0,
          longest / max(descriptor.width, descriptor.height),
        );
        final width = max(1, (descriptor.width * scale).round());
        final height = max(1, (descriptor.height * scale).round());
        descriptor.dispose();
        descriptorBuffer.dispose();
        final codec = await ui.instantiateImageCodec(
          bytes,
          targetWidth: width,
          targetHeight: height,
          allowUpscaling: false,
        );
        try {
          final frame = await codec.getNextFrame();
          try {
            return (await frame.image.toByteData(
              format: ui.ImageByteFormat.png,
            ))!.buffer.asUint8List();
          } finally {
            frame.image.dispose();
          }
        } finally {
          codec.dispose();
        }
      } finally {
        gate.complete();
      }
    }();
    _previews[key] = future;
    while (_previews.length > 32) {
      _previews.remove(_previews.keys.first);
    }
    return future;
  }

  Future<XFile> originalForEdit(IntakeDraftItem item) async {
    final row = _local.values
        .where(
          (r) =>
              r['item_id'] == item.id || 'local:${r['client_id']}' == item.id,
        )
        .firstOrNull;
    final file = row == null ? null : _files[row['client_id']];
    if (file != null) return file;
    return XFile.fromData(
      await repository.intakePreview(scope, item.id, full: true),
      name: '${item.name}-view.png',
      mimeType: 'image/png',
    );
  }

  @override
  void dispose() {
    _disposed = true;
    setDraftLeaveWarning(!hasDurableLocalFiles && hasPendingLocalTransfers);
    _timer?.cancel();
    _previews.clear();
    _files.clear();
    super.dispose();
  }
}
