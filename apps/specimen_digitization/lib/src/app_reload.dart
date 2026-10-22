import 'app/routes.dart';

/// A host action, injected separately from authentication and App Check.
abstract interface class AppReload {
  Future<void> reload(String location);
}

/// Keeps reload navigation on a registered internal route. The router still
/// performs the ordinary authenticated collection-membership checks afterward.
String appReloadLocation(String? value) {
  if (value == null ||
      !value.startsWith('/') ||
      value.startsWith('//') ||
      value.contains('\\')) {
    return AppRoutes.setup;
  }
  try {
    final parsed = Uri.tryParse(value);
    if (parsed == null ||
        parsed.hasScheme ||
        parsed.hasAuthority ||
        parsed.hasFragment) {
      return AppRoutes.setup;
    }
    final uri = AppRoutes.restoreWebHistory(parsed) ?? parsed;
    final segments = uri.pathSegments;
    final entry = AppRoutes.isEntryLocation(uri.path) || uri.path == '/';
    final global = uri.path == AppRoutes.help;
    final collection =
        AppRoutes.collectionKeyIn(uri) != null &&
        segments.length >= 3 &&
        segments[1].isNotEmpty &&
        ((segments[2] == 'queue' &&
                (segments.length == 3 ||
                    (segments.length == 4 && segments.last.isNotEmpty))) ||
            (segments[2] == 'intake' &&
                (segments.length == 3 ||
                    (segments[3] == 'sources' &&
                        (segments.length == 4 ||
                            (segments.length == 5 &&
                                segments.last.isNotEmpty))))));
    if (!entry && !global && !collection) return AppRoutes.setup;
    // Action links are never reload destinations or a persistence mechanism.
    if (uri.queryParametersAll.keys.any(
      (key) => const {'oobCode', 'mode', 'apiKey', 'link'}.contains(key),
    )) {
      return AppRoutes.setup;
    }
    return uri.toString();
  } on FormatException {
    return AppRoutes.setup;
  }
}

/// Rewrites only this document's hash route and removes any action query.
/// No session state, credential or other tab is read or modified.
String appReloadUrl(Uri current, String location) {
  final route = appReloadLocation(location);
  final document = current.removeFragment().toString();
  final query = document.indexOf('?');
  final cleanDocument = query < 0 ? document : document.substring(0, query);
  return '$cleanDocument#$route';
}
