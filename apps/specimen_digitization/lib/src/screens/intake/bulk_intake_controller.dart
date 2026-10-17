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

String intakeClientId() => List.generate(
  16,
  (_) => Random.secure().nextInt(256),
).map((value) => value.toRadixString(16).padLeft(2, '0')).join();

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
  bool _disposed = false, _polling = false;
  String? _draftClientId;
  final Set<String> selected = {};
  List<String> lastRemoved = [];
  final Map<String, XFile> _files = {};
  final Map<String, Json> _local = {};
  final LinkedHashMap<String, Future<Uint8List>> _previews = LinkedHashMap();
  Future<void> _admissions = Future.value();
  Future<void> _transfers = Future.value();
  Future<void> _previewTail = Future.value();
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
    if (!_disposed) setDraftLeaveWarning(!hasDurableLocalFiles && hasUnsaved);
    if (!_disposed) notifyListeners();
  }

  String message(Object e) => e is ApiFailure
      ? e.message
      : 'Could not save this change. Retry when your connection is available.';
  Future<Json> call(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
  }) async {
    if (_disposed) throw StateError('Intake account changed');
    final result = await repository.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
    );
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
      if (!_disposed) {
        _timer = Timer.periodic(const Duration(seconds: 3), (_) => poll());
      }
    }
  }

  Future<void> _persist() async {
    if (_disposed) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _key,
      jsonEncode({
        'client_id': _draftClientId,
        'active_draft_id': draft?.id,
        'files': _local.values.toList(),
      }),
    );
  }

  Future<void> refreshLists() async {
    drafts = await _pages('/drafts');
    submissions =
        (await _pages('/submissions')).map(IntakeSubmission.new).toList()..sort(
          (a, b) =>
              '${b.data['created_at']}'.compareTo('${a.data['created_at']}'),
        );
  }

  Future<List<Json>> _pages(String path) async {
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
    } while (after != null && !_disposed);
    return rows;
  }

  Future<void> refreshDraft() async {
    final id = draft?.id;
    if (id == null) return;
    final current = IntakeDraft(await call('GET', '/drafts/$id'));
    final rows = (await _pages(
      '/drafts/$id/items',
    )).map(IntakeDraftItem.new).toList();
    if (_disposed || draft?.id != id) return;
    draft = current;
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
    changed();
  }

  Future<void> poll() async {
    if (_polling || _disposed || loading) return;
    _polling = true;
    try {
      if (hasUnsaved && draft != null) await refreshDraft();
      if (submissions.any((s) => s.active)) await refreshLists();
      changed();
    } catch (_) {
      // Keep the last confirmed queue; polling never invents a failure/success.
    } finally {
      _polling = false;
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
      _draftClientId ??= intakeClientId();
      final matched = <String>{};
      final prepared =
          <
            ({
              XFile file,
              int size,
              String? hash,
              Json? previous,
              Object? failure,
            })
          >[];
      for (final file in files) {
        if (_disposed) return;
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
          prepared.add((
            file: file,
            size: size,
            hash: hash,
            previous: previous,
            failure: null,
          ));
        } catch (e) {
          prepared.add((
            file: file,
            size: 0,
            hash: null,
            previous: null,
            failure: e,
          ));
        }
      }
      final additions = prepared.where((row) => row.previous == null).length;
      if (visible.length + additions - (replacesId == null ? 0 : 1) > 500) {
        error =
            'A batch holds up to 500 photos. Choose fewer files or start another batch.';
        changed();
        if (camera) throw ApiFailure(error!, code: 'batch_limit');
        return;
      }
      for (final photo in prepared) {
        if (_disposed) return;
        final file = photo.file;
        final id = intakeClientId();
        try {
          if (photo.failure != null) throw photo.failure!;
          final size = photo.size, hash = photo.hash!;
          final previous = photo.previous;
          final clientId = previous?['client_id'] as String? ?? id;
          final retained = await retainDraftFile(file, _owner, clientId);
          final row = <String, dynamic>{
            ...?(previous),
            'client_id': clientId,
            'batch_client_id': previous?['batch_client_id'] ?? _draftClientId,
            if (draft != null) 'draft_id': draft!.id,
            'path': retained.path,
            'filename': file.name,
            'size_bytes': size,
            'sha256': hash,
            'media_type': _mediaType(file),
            'photo_sensitive': previous?['photo_sensitive'] ?? sensitive,
            'replaces_id': ?replacesId,
            'source':
                previous?['source'] ??
                {'provider': camera ? 'camera' : 'files'},
            'saved': false,
          };
          _local[clientId] = row;
          _files[clientId] = retained;
          if (!items.any(
            (i) => i.id == row['item_id'] || i.id == 'local:$clientId',
          )) {
            items.add(
              IntakeDraftItem({
                ...row,
                'id': 'local:$clientId',
                'state': 'waiting',
              }),
            );
          }
          await _persist();
          changed();
          _queueTransfer(row);
        } catch (e) {
          if (camera) rethrow;
          items.add(
            IntakeDraftItem({
              'id': 'local:$id',
              'filename': file.name,
              'state': 'needs_attention',
              'error': {'message': message(e)},
            }),
          );
          changed();
        }
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
    _transfers = _transfers.then((_) async {
      if (_disposed || row['removed'] == true) return;
      try {
        await _transfer(row);
        error = null;
      } catch (e) {
        error = message(e);
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
        item = await repository.intakeRequest(
          scope,
          'PUT',
          '/items/${row['item_id']}/content',
          offset: offset,
          bytes: builder.takeBytes(),
        );
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

  Future<void> addSource(List<Json> photos) async {
    for (final photo in photos) {
      photo['client_id'] ??= intakeClientId();
    }
    final admitted = items.map((item) => item.data['client_id']).toSet();
    final additions = photos
        .where((photo) => !admitted.contains(photo['client_id']))
        .length;
    if (visible.length + additions > 500) {
      error =
          'Choose up to ${500 - visible.length} more photos for this batch.';
      changed();
      return;
    }
    try {
      error = null;
      await ensureDraft();
      for (final photo in photos) {
        final item = await call(
          'POST',
          '/drafts/${draft!.id}/items',
          body: photo,
        );
        if (!items.any((existing) => existing.id == item['id'])) {
          items.add(
            IntakeDraftItem({
              ...item,
              'photo_sensitive': item['sensitive'],
              'included': true,
            }),
          );
          changed();
        }
      }
    } catch (e) {
      error = message(e);
    } finally {
      // Reconcile a lost acknowledgement once, including partial success.
      try {
        await refreshDraft();
      } catch (e) {
        error ??= message(e);
      }
      changed();
    }
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
    if (submitting || draft == null || readyCount == 0) return null;
    submitting = true;
    error = null;
    changed();
    try {
      final chosen = visible
          .where((item) => item.canSubmit && !item.id.startsWith('local:'))
          .map((i) => i.id)
          .toList();
      final current = await call('GET', '/drafts/${draft!.id}');
      final result = await call(
        'POST',
        '/drafts/${draft!.id}/submit',
        body: {'expected_revision': current['revision'], 'item_ids': chosen},
      );
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

  Future<void> openDraft(Json value) async {
    await _admissions;
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
  }

  Future<void> newDraft() async {
    await _admissions;
    await _persist();
    draft = null;
    _draftClientId = intakeClientId();
    items = [];
    selected.clear();
    lastRemoved = [];
    await _persist();
    changed();
  }

  Future<void> discardDraft() async {
    final current = draft;
    if (current != null) {
      final latest = await call('GET', '/drafts/${current.id}');
      await call(
        'POST',
        '/drafts/${current.id}/discard',
        body: {'expected_revision': latest['revision']},
      );
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
    await newDraft();
    await refreshLists();
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
      if (file == null) throw StateError('Preview awaits saved content');
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
    setDraftLeaveWarning(false);
    _timer?.cancel();
    _previews.clear();
    _files.clear();
    super.dispose();
  }
}
