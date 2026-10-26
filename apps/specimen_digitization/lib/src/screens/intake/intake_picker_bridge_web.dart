import 'dart:js_interop';
import 'package:web/web.dart' as web;

/// Hosts the API-origin page without moving provider credentials into the app.
class IntakePickerBridge {
  IntakePickerBridge({
    required String url,
    required String pickerId,
    required void Function(String action) onEvent,
  }) {
    final uri = Uri.parse(url);
    final loopback = const ['127.0.0.1', 'localhost', '::1'].contains(uri.host);
    if (!uri.hasAuthority ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        (uri.scheme != 'https' && !(uri.scheme == 'http' && loopback)) ||
        pickerId.isEmpty) {
      throw ArgumentError('Drive selection page is unavailable');
    }
    frame = web.HTMLIFrameElement()
      ..title = 'Choose Google Drive photos'
      ..src = url
      ..referrerPolicy = 'strict-origin'
      ..setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms');
    frame.style
      ..width = '100%'
      ..height = '100%'
      ..border = '0';
    _listener = ((web.MessageEvent event) {
      final source = event.source, expected = frame.contentWindow;
      if (_disposed ||
          expected == null ||
          source == null ||
          event.origin != uri.origin ||
          source.strictNotEquals(expected).toDart) {
        return;
      }
      final Object? data;
      try {
        data = event.data.dartify();
      } catch (_) {
        return;
      }
      if (data is! Map ||
          data.length != 3 ||
          data['type'] != 'specimen-intake-picker' ||
          data['picker_id'] != pickerId ||
          !const [
            'ready',
            'selected',
            'cancelled',
            'error',
          ].contains(data['action'])) {
        return;
      }
      onEvent(data['action'] as String);
    }).toJS;
    web.window.addEventListener('message', _listener);
  }

  late final web.HTMLIFrameElement frame;
  late final JSFunction _listener;
  bool _disposed = false;

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    web.window.removeEventListener('message', _listener);
    frame.src = 'about:blank';
    frame.remove();
  }
}
