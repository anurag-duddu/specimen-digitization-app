import 'dart:js_interop';

import 'app_reload.dart';

@JS('window.history.replaceState')
external void _replaceState(JSAny? state, String title, String url);

@JS('window.history.state')
external JSAny? get _historyState;

@JS('window.location.reload')
external void _reload();

AppReload createAppReload() => const WebAppReload();

/// Rebuilds this document using only public browser APIs, keeping Firebase's
/// persisted session and the other tabs untouched. It never handles tokens.
class WebAppReload implements AppReload {
  const WebAppReload();

  @override
  Future<void> reload(String location) async {
    _replaceState(_historyState, '', appReloadUrl(Uri.base, location));
    _reload();
  }
}
