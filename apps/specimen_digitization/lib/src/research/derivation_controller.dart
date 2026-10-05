import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../models.dart' show ApiFailure, CollectionScope, Specimen;
import 'derivation_models.dart';
import 'derivation_repository.dart';
import 'research_repository.dart' show ResearchFailure, ResearchFailureKind;

enum DerivationNetworkState { idle, loading, ready, submitting, error, denied }

/// Manages only the explicit capability, saved request and retained result.
/// It never writes a field value or guesses worker progress.
class ResearchDerivationController extends ChangeNotifier {
  ResearchDerivationController({
    required ResearchDerivationRepository repository,
    required CollectionScope collection,
    required Specimen specimen,
    bool readOnly = false,
    Stream<ApiFailure>? accessFailures,
  }) : _repository = repository,
       _collection = collection,
       _specimen = specimen,
       _readOnly = readOnly {
    if (specimen.revision < 0) {
      throw ArgumentError('Record revision must be zero or greater.');
    }
    _accessSubscription = accessFailures?.listen((failure) {
      if (failure.status == 401 || failure.status == 403) {
        _deny(
          failure.status == 401
              ? ResearchFailureKind.unauthenticated
              : ResearchFailureKind.forbidden,
        );
      }
    });
  }

  final ResearchDerivationRepository _repository;
  CollectionScope _collection;
  Specimen _specimen;
  bool _readOnly;
  bool _disposed = false;
  bool _accessDenied = false;
  int _epoch = 0;
  StreamSubscription<ApiFailure>? _accessSubscription;
  ResearchDerivationCapability? _capability;
  ResearchDerivationAccepted? _accepted;
  ResearchDerivationResult? _result;
  DerivationNetworkState _state = DerivationNetworkState.idle;
  String? _message;

  CollectionScope get collection => _collection;
  Specimen get specimen => _specimen;
  ResearchDerivationCapability? get capability => _capability;
  ResearchDerivationAccepted? get accepted => _accepted;
  ResearchDerivationResult? get result => _result;
  DerivationNetworkState get state => _state;
  String? get message => _message;

  bool get canRequest =>
      !_disposed &&
      !_accessDenied &&
      !_readOnly &&
      _state == DerivationNetworkState.ready &&
      (_capability?.appliesTo(_specimen.revision) ?? false) &&
      (_result == null ||
          (!_result!.stale &&
              (_result!.status == 'completed' ||
                  _result!.status == 'blocked')));

  bool _current(int epoch) => !_disposed && !_accessDenied && epoch == _epoch;

  void bind({
    required CollectionScope collection,
    required Specimen specimen,
    bool readOnly = false,
  }) {
    if (_disposed) return;
    final sameRecord =
        _collection.key == collection.key && _specimen.id == specimen.id;
    if (sameRecord &&
        _specimen.revision == specimen.revision &&
        _specimen.recordVersionId == specimen.recordVersionId &&
        _readOnly == readOnly) {
      return;
    }
    _epoch++;
    _collection = collection;
    _specimen = specimen;
    _readOnly = readOnly;
    _capability = null;
    _message = null;
    if (!sameRecord) {
      _accepted = null;
      _result = null;
    }
    _state = _accessDenied
        ? DerivationNetworkState.denied
        : sameRecord && _accepted != null && _result != null
        ? DerivationNetworkState.ready
        : DerivationNetworkState.idle;
    notifyListeners();
  }

  Future<void> loadCapability() async {
    if (_disposed ||
        _accessDenied ||
        _state == DerivationNetworkState.loading ||
        _state == DerivationNetworkState.submitting) {
      return;
    }
    final epoch = ++_epoch;
    final collection = _collection;
    final specimen = _specimen;
    _capability = null;
    _message = null;
    _state = DerivationNetworkState.loading;
    notifyListeners();
    try {
      final capability = await _repository.capability(collection, specimen);
      if (!_current(epoch)) return;
      if (capability.canonicalRevision != specimen.revision) {
        throw const ResearchFailure(ResearchFailureKind.conflict);
      }
      _capability = capability;
      _state = DerivationNetworkState.ready;
      notifyListeners();
    } catch (error) {
      if (_current(epoch)) _fail(_safe(error));
    }
  }

  Future<void> request({
    required List<String> fields,
    required String reason,
    required Future<void> Function() refreshRecord,
  }) async {
    if (!canRequest) return;
    final capability = _capability!;
    final collection = _collection;
    final specimen = _specimen;
    final epoch = ++_epoch;
    _accepted = null;
    _result = null;
    _message = null;
    _state = DerivationNetworkState.submitting;
    notifyListeners();
    if (!_current(epoch) ||
        _readOnly ||
        !capability.appliesTo(specimen.revision) ||
        !capability.eligibleFields.toSet().containsAll(fields)) {
      return;
    }
    try {
      final accepted = await _repository.enqueue(
        collection,
        specimen,
        capability: capability,
        requestedFields: List.unmodifiable(fields),
        reason: reason,
        idempotencyKey: _newIdempotencyKey(),
      );
      if (!_current(epoch)) return;
      if (accepted.sourceRevision != specimen.revision ||
          accepted.queuedRevision != specimen.revision + 1) {
        throw const ResearchFailure(ResearchFailureKind.invalidResponse);
      }
      _accepted = accepted;
      _state = DerivationNetworkState.loading;
      _message = 'Request saved. Checking its progress.';
      notifyListeners();
      await _readResult(epoch, collection, specimen, accepted.requestId);
      if (!_current(epoch)) return;
      await refreshRecord();
    } catch (error) {
      if (_current(epoch)) _fail(_safe(error));
    }
  }

  Future<void> refreshResult({
    required Future<void> Function() refreshRecord,
  }) async {
    final accepted = _accepted;
    if (_disposed ||
        _accessDenied ||
        accepted == null ||
        _state == DerivationNetworkState.submitting ||
        _state == DerivationNetworkState.loading) {
      return;
    }
    final epoch = ++_epoch;
    final collection = _collection;
    final specimen = _specimen;
    _state = DerivationNetworkState.loading;
    _message = null;
    notifyListeners();
    await _readResult(epoch, collection, specimen, accepted.requestId);
    if (!_current(epoch)) return;
    if (_result?.stale == true) {
      _message =
          'The record changed. Refresh this record before reviewing suggestions.';
      notifyListeners();
      await refreshRecord();
    }
  }

  Future<void> _readResult(
    int epoch,
    CollectionScope collection,
    Specimen specimen,
    String requestId,
  ) async {
    try {
      final result = await _repository.result(collection, specimen, requestId);
      if (!_current(epoch)) return;
      if (result.stale && result.proposals.isNotEmpty) {
        throw const ResearchFailure(ResearchFailureKind.invalidResponse);
      }
      _result = result;
      _state = DerivationNetworkState.ready;
      _message = result.stale
          ? 'The record changed. Refresh this record before reviewing suggestions.'
          : null;
      notifyListeners();
    } catch (error) {
      if (_current(epoch)) _fail(_safe(error));
    }
  }

  ResearchFailure _safe(Object error) => error is ResearchFailure
      ? error
      : const ResearchFailure(ResearchFailureKind.unavailable);

  void _fail(ResearchFailure failure) {
    if (failure.kind == ResearchFailureKind.unauthenticated ||
        failure.kind == ResearchFailureKind.forbidden) {
      _deny(failure.kind);
      return;
    }
    _capability = null;
    _state = DerivationNetworkState.error;
    _message = failure.message;
    notifyListeners();
  }

  void _deny(ResearchFailureKind kind) {
    if (_disposed) return;
    _epoch++;
    _accessDenied = true;
    _capability = null;
    _accepted = null;
    _result = null;
    _state = DerivationNetworkState.denied;
    _message = ResearchFailure(kind).message;
    notifyListeners();
  }

  static String _newIdempotencyKey() {
    final random = Random.secure();
    final bytes = List<int>.generate(24, (_) => random.nextInt(256));
    return 'research-derivation-${bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join()}';
  }

  @override
  void dispose() {
    _disposed = true;
    _epoch++;
    _capability = null;
    _accepted = null;
    _result = null;
    unawaited(_accessSubscription?.cancel() ?? Future<void>.value());
    super.dispose();
  }
}
