/// Removes an acknowledged callback without overwriting a newer navigation.
///
/// Hash routing may change the fragment before acknowledgment. Only that route
/// change is allowed; a new origin, path or query belongs to a different URL.
String? emailLinkCleanupLocation(Uri initialUri, Uri currentUri) {
  final initialDocument = initialUri.removeFragment();
  final currentDocument = currentUri.removeFragment();
  if (initialDocument != currentDocument) return null;

  final changedFragment = currentUri.fragment != initialUri.fragment;
  if (changedFragment &&
      currentUri.fragment.isNotEmpty &&
      !currentUri.fragment.startsWith('/')) {
    // A newer non-route fragment may itself be an unrelated callback.
    return null;
  }

  // Work with encoded URI text: malformed query UTF-8 must still be removable.
  final document = currentDocument.toString();
  final queryStart = document.indexOf('?');
  final cleanDocument = queryStart < 0
      ? document
      : document.substring(0, queryStart);
  if (!changedFragment || !currentUri.hasFragment) return cleanDocument;

  // Preserve the router's current fragment exactly, including its own query.
  final current = currentUri.toString();
  return '$cleanDocument${current.substring(current.indexOf('#'))}';
}
