import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models.dart' show ApiFailure;
import 'research_models.dart';
import 'research_repository.dart';

/// Network state independent of the server's scientific work phase.
enum ResearchNetworkState { idle, loading, ready, submitting, error, denied }

/// Lazy research state bound to the host's record and complete locator.
///
/// The host replaces this controller after a verified access recheck. No auth,
/// discovery, specimen mutation or approval is performed here.
class ResearchController extends ChangeNotifier {
  ResearchController({
    required ResearchRepository repository,
    required ResearchScope scope,
    required int recordRevision,
    bool readOnly = false,
    Stream<ApiFailure>? accessFailures,
  }) : _repository = repository,
       _scope = scope,
       _recordRevision = recordRevision,
       _readOnly = readOnly {
    if (recordRevision < 0) {
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

  final ResearchRepository _repository;
  ResearchScope _scope;
  int _recordRevision;
  bool _readOnly;
  int _epoch = 0;
  bool _disposed = false;
  bool _accessDenied = false;
  StreamSubscription<ApiFailure>? _accessSubscription;
  ResearchThread? _thread;
  ResearchRetryAck? _ack;
  String? _message;
  String? _retryFieldKey;
  ResearchNetworkState _networkState = ResearchNetworkState.idle;

  ResearchScope get scope => _scope;
  int get recordRevision => _recordRevision;
  bool get readOnly => _readOnly;
  ResearchThread? get thread => _thread;
  ResearchRetryAck? get queuedAck => _ack;
  String? get message => _message;
  String? get retryFieldKey => _retryFieldKey;
  ResearchNetworkState get networkState => _networkState;

  /// Whether a fresh field capability is available without an active exchange.
  bool canRetry(String fieldKey) =>
      !_disposed &&
      !_accessDenied &&
      !_readOnly &&
      _networkState == ResearchNetworkState.ready &&
      _retryFieldKey == null &&
      (_thread?.scope.matches(_scope) ?? false) &&
      (_thread?.canRetry(fieldKey) ?? false);

  /// Clears state when the host changes record, scope, generation or view mode.
  ///
  /// An unchanged specimen revision does not prevent an explicit fresh read.
  void bind({
    required ResearchScope scope,
    required int recordRevision,
    bool readOnly = false,
  }) {
    if (_disposed) return;
    if (recordRevision < 0) {
      throw ArgumentError('Record revision must be zero or greater.');
    }
    if (_scope.matches(scope) &&
        _recordRevision == recordRevision &&
        _readOnly == readOnly) {
      return;
    }
    _epoch++;
    _scope = scope;
    _recordRevision = recordRevision;
    _readOnly = readOnly;
    _thread = null;
    _ack = null;
    _retryFieldKey = null;
    _message = null;
    // Scope changes cannot silently recover an already revoked session.
    _networkState = _accessDenied
        ? ResearchNetworkState.denied
        : ResearchNetworkState.idle;
    notifyListeners();
  }

  /// Loads once when the host reveals the field's collapsed disclosure.
  Future<void> ensureLoaded() async {
    if (_networkState != ResearchNetworkState.idle) return;
    await refresh();
  }

  /// Reads authoritative state without submitting another action.
  Future<void> refresh({bool quiet = false}) async {
    if (_disposed ||
        _accessDenied ||
        _retryFieldKey != null ||
        (quiet && _networkState == ResearchNetworkState.loading)) {
      return;
    }
    final epoch = ++_epoch;
    final scope = _scope;
    if (!quiet) {
      _thread = null;
      _ack = null;
    }
    _message = null;
    _networkState = ResearchNetworkState.loading;
    notifyListeners();
    await _read(epoch, scope);
  }

  bool _current(int epoch, ResearchScope scope) =>
      !_disposed && !_accessDenied && epoch == _epoch && _scope.matches(scope);

  ResearchFailure _safe(Object error) => error is ResearchFailure
      ? error
      : const ResearchFailure(ResearchFailureKind.unavailable);

  void _deny(ResearchFailureKind kind) {
    if (_disposed) return;
    _epoch++;
    _accessDenied = true;
    _thread = null;
    _ack = null;
    _retryFieldKey = null;
    _message = ResearchFailure(kind).message;
    _networkState = ResearchNetworkState.denied;
    notifyListeners();
  }

  void _fail(ResearchFailure failure) {
    if (failure.kind == ResearchFailureKind.unauthenticated ||
        failure.kind == ResearchFailureKind.forbidden) {
      _deny(failure.kind);
      return;
    }
    _thread = null;
    _retryFieldKey = null;
    _message = failure.message;
    _networkState = ResearchNetworkState.error;
    notifyListeners();
  }

  Future<void> _read(int epoch, ResearchScope scope, {String? notice}) async {
    // A synchronous listener may rebind or revoke access during notification.
    if (!_current(epoch, scope)) return;
    try {
      final thread = await _repository.read(scope);
      if (!_current(epoch, scope)) return;
      if (!thread.scope.matches(scope)) {
        throw const ResearchFailure(ResearchFailureKind.invalidResponse);
      }
      _thread = thread;
      _message = notice;
      _networkState = ResearchNetworkState.ready;
      notifyListeners();
    } catch (error) {
      if (_current(epoch, scope)) _fail(_safe(error));
    }
  }

  bool _canDispatchRetry(
    int epoch,
    ResearchScope scope,
    String fieldKey,
    int checkpointRevision,
  ) =>
      _current(epoch, scope) &&
      !_readOnly &&
      _networkState == ResearchNetworkState.submitting &&
      _retryFieldKey == fieldKey &&
      (_thread?.scope.matches(scope) ?? false) &&
      (_thread?.canRetry(fieldKey) ?? false) &&
      _thread?.field(fieldKey)?.checkpoint?.revision == checkpointRevision;

  /// Queues one advertised field and rereads after its verified acknowledgment.
  ///
  /// A conflict triggers one fresh GET. It never resubmits against a new revision.
  Future<void> retryField(String fieldKey) async {
    if (!canRetry(fieldKey)) return;
    final scope = _scope;
    final checkpoint = _thread!.field(fieldKey)!.checkpoint!;
    final revision = checkpoint.revision;
    final epoch = ++_epoch;
    _retryFieldKey = fieldKey;
    _ack = null;
    _message = null;
    _networkState = ResearchNetworkState.submitting;
    notifyListeners();
    if (!_canDispatchRetry(epoch, scope, fieldKey, revision)) return;
    try {
      final ack = await _repository.retry(
        scope,
        fieldKey,
        expectedCheckpointRevision: revision,
      );
      if (!_current(epoch, scope)) return;
      if (!ack.scope.matches(scope) ||
          ack.fieldKey != fieldKey ||
          ack.checkpointRevision != revision) {
        throw const ResearchFailure(ResearchFailureKind.invalidResponse);
      }
      _ack = ack;
      _thread = null;
      _retryFieldKey = null;
      _networkState = ResearchNetworkState.loading;
      _message = 'Retry queued. Refreshing research.';
      notifyListeners();
      await _read(epoch, scope, notice: 'Retry queued.');
    } catch (error) {
      if (!_current(epoch, scope)) return;
      final failure = _safe(error);
      _ack = null;
      if (failure.kind == ResearchFailureKind.conflict) {
        _thread = null;
        _retryFieldKey = null;
        _networkState = ResearchNetworkState.loading;
        _message = failure.message;
        notifyListeners();
        await _read(epoch, scope, notice: failure.message);
      } else {
        _fail(failure);
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _epoch++;
    _thread = null;
    _ack = null;
    _retryFieldKey = null;
    _message = null;
    unawaited(_accessSubscription?.cancel() ?? Future<void>.value());
    super.dispose();
  }
}
