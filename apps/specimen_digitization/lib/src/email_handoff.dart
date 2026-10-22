import 'package:url_launcher/url_launcher.dart';

/// Opens the inbox from an explicit user action without authenticating anyone.
abstract interface class EmailInboxLauncher {
  Future<bool> openInbox();
}

typedef EmailInboxLaunch =
    Future<bool> Function(
      Uri url, {
      required LaunchMode mode,
      required String webOnlyWindowName,
    });

/// Opens Gmail's website externally, without an email address or sign-in token.
class UrlEmailInboxLauncher implements EmailInboxLauncher {
  const UrlEmailInboxLauncher({EmailInboxLaunch launch = launchUrl})
    : _launch = launch;

  static final Uri _inbox = Uri.parse('https://mail.google.com/mail/');
  final EmailInboxLaunch _launch;

  @override
  Future<bool> openInbox() async {
    try {
      // Dispatch before the first await so a web click keeps its user gesture.
      return await _launch(
        _inbox,
        mode: LaunchMode.externalApplication,
        webOnlyWindowName: '_blank',
      );
    } catch (_) {
      // The caller supplies recovery text; platform errors may contain details.
      return false;
    }
  }
}
