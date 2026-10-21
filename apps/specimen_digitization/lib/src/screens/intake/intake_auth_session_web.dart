import 'intake_timing.dart';
import 'dart:async';
import 'dart:js_interop';
import 'package:web/web.dart' as web;
import '../../models.dart';

/// Reserve the popup synchronously during the user's click. Only messages from
/// this exact window, from the configured API callback origin, are accepted.
class IntakeAuthSession {
  IntakeAuthSession()
    : _popup = web.window.open(
        'about:blank',
        '_blank',
        'popup,width=620,height=760',
      );
  final web.Window? _popup;
  String get returnOrigin => web.window.location.origin;
  JSFunction? _listener;
  Timer? _closed;
  Future<void> openPicker(String url) async {
    if (_popup == null || _popup.closed) {
      throw const ApiFailure(
        'Allow pop-ups to choose Drive files.',
        code: 'popup',
      );
    }
    _popup.location.href = url;
  }

  Future<Json> authenticate(
    String authorizationUrl, {
    bool keepOpen = false,
  }) async {
    final popup = _popup;
    if (popup == null) {
      throw const ApiFailure(
        'Allow pop-ups and try connecting again.',
        code: 'popup',
      );
    }
    final auth = Uri.parse(authorizationUrl);
    final expectedState = auth.queryParameters['state'];
    final callbackOrigin = Uri.parse(
      auth.queryParameters['redirect_uri']!,
    ).origin;
    final result = Completer<Json>();
    final listener = ((web.MessageEvent event) {
      // Dart equality can probe runtime properties on a cross-origin Window.
      // JavaScript identity checks the WindowProxy without crossing that boundary.
      if (event.origin != callbackOrigin ||
          event.source.strictNotEquals(popup).toDart) {
        return;
      }
      final data = event.data.dartify();
      if (data is Map &&
          data['state'] == expectedState &&
          !result.isCompleted) {
        result.complete(Map<String, dynamic>.from(data));
      }
    }).toJS;
    _listener = listener;
    web.window.addEventListener('message', listener);
    popup.location.href = authorizationUrl;
    _closed = Timer.periodic(const Duration(seconds: 1), (_) {
      if (popup.closed && !result.isCompleted) {
        result.completeError(
          const ApiFailure(
            'Connection window closed. Connect again when ready.',
            code: 'cancelled',
          ),
        );
      }
    });
    var completed = false;
    try {
      final response = await result.future.timeout(intakeAuthorizationTimeout);
      completed = true;
      return response;
    } finally {
      _stopListening();
      if (!keepOpen || !completed) _popup?.close();
    }
  }

  void _stopListening() {
    _closed?.cancel();
    final listener = _listener;
    if (listener != null) web.window.removeEventListener('message', listener);
    _listener = null;
  }

  void close() {
    _stopListening();
    _popup?.close();
  }
}
