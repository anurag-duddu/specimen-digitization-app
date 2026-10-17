import 'dart:async';
import 'package:app_links/app_links.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../models.dart';

/// The application must still prove its initiating session at completion.
class IntakeAuthSession {
  String? get returnOrigin => null;
  final Completer<Uri> _result = Completer<Uri>();
  StreamSubscription<Uri>? _links;

  Future<void> openPicker(String url) async {
    if (!await launchUrl(
      Uri.parse(url),
      mode: LaunchMode.externalApplication,
    )) {
      throw const ApiFailure(
        'The file picker browser could not open.',
        code: 'browser_unavailable',
      );
    }
  }

  Future<Json> authenticate(String authorizationUrl) async {
    final expected = Uri.parse(authorizationUrl).queryParameters['state'];
    _links = AppLinks().uriLinkStream.listen((uri) {
      if (uri.scheme != 'specimenintake' ||
          uri.host != 'oauth' ||
          uri.path != '/callback') {
        return;
      }
      final fields = Uri.splitQueryString(uri.fragment);
      if (fields['state'] == expected && !_result.isCompleted) {
        _result.complete(uri);
      }
    });
    try {
      if (!await launchUrl(
        Uri.parse(authorizationUrl),
        mode: LaunchMode.externalApplication,
      )) {
        throw const ApiFailure(
          'The sign-in browser could not open. Try again.',
          code: 'browser_unavailable',
        );
      }
      final uri = await _result.future.timeout(const Duration(minutes: 10));
      return Map<String, dynamic>.from(Uri.splitQueryString(uri.fragment));
    } finally {
      await _links?.cancel();
    }
  }

  void close() {
    unawaited(_links?.cancel());
  }
}
