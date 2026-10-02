import 'dart:js_interop';
import 'email_link_cleanup.dart';
import 'magic_link.dart';

@JS('window.history.replaceState')
external void _replaceState(JSAny? state, String title, String url);

@JS('window.history.state')
external JSAny? get _historyState;

EmailLinkBrowser createEmailLinkBrowser() => _WebEmailLinkBrowser();

class _WebEmailLinkBrowser implements EmailLinkBrowser {
  // Capture before Flutter's initial route can change the address bar.
  @override
  final Uri initialUri = Uri.base;

  @override
  void clearLink() {
    final location = emailLinkCleanupLocation(initialUri, Uri.base);
    if (location != null) _replaceState(_historyState, '', location);
  }
}
