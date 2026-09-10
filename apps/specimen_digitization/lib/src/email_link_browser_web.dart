import 'dart:js_interop';
import 'magic_link.dart';

@JS('window.history.replaceState')
external void _replaceState(JSAny? state, String title, String url);

EmailLinkBrowser createEmailLinkBrowser() => _WebEmailLinkBrowser();

class _WebEmailLinkBrowser implements EmailLinkBrowser {
  // Capture before Flutter's initial route can change the address bar.
  @override
  final Uri initialUri = Uri.base;

  @override
  void clearLink() {
    // A late completion may outlive its widget. Do not replace a newer URL.
    if (Uri.base == initialUri) _replaceState(null, '', '/');
  }
}
