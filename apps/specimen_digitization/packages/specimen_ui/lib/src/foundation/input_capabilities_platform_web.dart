/// Touch and hover capability of the browser, including hybrid computers.
library;

import 'dart:js_interop';

@JS('window.matchMedia')
external _MediaQueryList _matchMedia(String query);

@JS('navigator.maxTouchPoints')
external int get _maxTouchPoints;

extension type _MediaQueryList._(JSObject _) implements JSObject {
  external bool get matches;
  external void addEventListener(String type, JSFunction listener);
  external void removeEventListener(String type, JSFunction listener);
}

/// Any touch input keeps destination names visible, even with a mouse attached.
bool? platformSupportsTouch() {
  try {
    return _maxTouchPoints > 0 || _matchMedia('(any-pointer: coarse)').matches;
  } catch (_) {
    return null;
  }
}

/// Whether any attached pointer can expose hover explanations.
bool? platformSupportsHover() {
  try {
    return _matchMedia('(any-hover: hover)').matches;
  } catch (_) {
    return null;
  }
}

/// Rechecks capabilities when an attached pointer changes.
void Function() listenToPlatformInputCapabilities(void Function() onChange) {
  final cancellations = <void Function()>[];
  try {
    final listener = ((JSAny _) => onChange()).toJS;
    for (final query in ['(any-pointer: coarse)', '(any-hover: hover)']) {
      final list = _matchMedia(query);
      list.addEventListener('change', listener);
      cancellations.add(() => list.removeEventListener('change', listener));
    }
  } catch (_) {
    // Unknown browser capabilities retain visible labels conservatively.
  }
  return () {
    for (final cancel in cancellations) {
      cancel();
    }
  };
}
