import 'dart:async';

/// One delivery whose object identity is its acknowledgment token.
///
/// Equal URIs in separate deliveries do not represent the same pending event.
final class EmailLinkDelivery {
  EmailLinkDelivery(this.uri);

  final Uri uri;
}

/// Buffered link delivery, independent of platform and authentication policy.
abstract interface class EmailLinkSource {
  /// The latest delivery not yet acknowledged, including before subscription.
  EmailLinkDelivery? get pending;

  /// New deliveries after subscription. Read [pending] for earlier delivery.
  Stream<EmailLinkDelivery> get links;

  /// Consumes only this exact delivery if it is still pending.
  void acknowledge(EmailLinkDelivery delivery);

  /// Stops input and output, drops the pending URI and may be called again.
  Future<void> close();
}

/// Combines a platform's initial link and subsequent link notifications.
///
/// The warm subscription starts before the initial read. Any warm link takes
/// precedence over a later initial result, even after acknowledgment. Transport
/// errors carry no public payload or log: validation and recovery policy belong
/// to the caller, and an error may contain private link details.
final class BufferedEmailLinkSource implements EmailLinkSource {
  BufferedEmailLinkSource({
    required Future<Uri?> Function() initialLink,
    required Stream<Uri> incomingLinks,
  }) {
    try {
      _input = incomingLinks.listen(
        _receiveWarm,
        onError: (Object _) {
          // Platform errors may contain private links. Keep the input alive.
        },
      );
    } catch (_) {
      // A failed subscription must not expose platform exception details.
    }
    unawaited(_readInitial(initialLink));
  }

  final StreamController<EmailLinkDelivery> _events =
      StreamController<EmailLinkDelivery>.broadcast();
  StreamSubscription<Uri>? _input;
  EmailLinkDelivery? _pending;
  bool _receivedWarm = false;
  bool _closed = false;
  Future<void>? _closing;

  @override
  EmailLinkDelivery? get pending => _pending;

  @override
  // Filtering at delivery time also suppresses events queued before close.
  Stream<EmailLinkDelivery> get links =>
      _events.stream.where((EmailLinkDelivery _) => !_closed);

  Future<void> _readInitial(Future<Uri?> Function() initialLink) async {
    try {
      final Uri? uri = await initialLink();
      if (_closed || _receivedWarm || uri == null) return;
      _receive(uri);
    } catch (_) {
      // No raw platform error, URI or authentication code leaves this source.
    }
  }

  void _receiveWarm(Uri uri) {
    if (_closed) return;
    _receivedWarm = true;
    _receive(uri);
  }

  void _receive(Uri uri) {
    if (_closed || _pending?.uri == uri) return;
    final EmailLinkDelivery delivery = EmailLinkDelivery(uri);
    _pending = delivery;
    _events.add(delivery);
  }

  @override
  void acknowledge(EmailLinkDelivery delivery) {
    if (identical(_pending, delivery)) _pending = null;
  }

  @override
  Future<void> close() {
    final Future<void>? closing = _closing;
    if (closing != null) return closing;
    final Completer<void> completion = Completer<void>();
    _closing = completion.future;
    _closed = true;
    _pending = null;
    unawaited(_finishClose(completion));
    return completion.future;
  }

  Future<void> _finishClose(Completer<void> completion) async {
    try {
      await _input?.cancel();
    } catch (_) {
      // Closing stays private and idempotent even if a platform cancel fails.
    }
    await _events.close();
    completion.complete();
  }
}
