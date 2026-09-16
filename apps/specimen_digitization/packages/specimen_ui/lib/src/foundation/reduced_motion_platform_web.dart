/// The web half of the reduced-motion bridge
/// (motion and microinteractions, section 6.2b).
///
/// `EnginePlatformDispatcher.computeAccessibilityFeatures()` on Flutter
/// 3.38.5 reports `highContrast` and nothing else, so a browser that answers
/// `(prefers-reduced-motion: reduce)` is invisible to `MediaQuery` and to
/// `AccessibilityFeatures`. This reads the media query directly, through the
/// same hand-written `dart:js_interop` binding style the email link browser
/// uses, so no new package enters the dependency graph for four lines of
/// interop.
library;

import 'dart:js_interop';

/// The query the CSS Accessibility specification defines for the setting.
const String _reduceQuery = '(prefers-reduced-motion: reduce)';

@JS('window.matchMedia')
external _MediaQueryList _matchMedia(String query);

extension type _MediaQueryList._(JSObject _) implements JSObject {
  external bool get matches;
  external void addEventListener(String type, JSFunction listener);
  external void removeEventListener(String type, JSFunction listener);
}

/// True when the browser reports the reduced-motion preference.
bool platformPrefersReducedMotion() {
  try {
    return _matchMedia(_reduceQuery).matches;
  } catch (_) {
    // A host page without `matchMedia` is not a reason to fail a build.
    return false;
  }
}

/// Calls [onChange] whenever the browser preference changes, so a tab that is
/// already open follows the setting. Returns the canceller.
void Function() listenToPlatformReducedMotion(void Function() onChange) {
  try {
    final _MediaQueryList list = _matchMedia(_reduceQuery);
    final JSFunction listener = ((JSAny _) => onChange()).toJS;
    list.addEventListener('change', listener);
    return () => list.removeEventListener('change', listener);
  } catch (_) {
    return () {};
  }
}
