/// The non-web half of the reduced-motion bridge.
///
/// Android and iOS both reach the framework through `AccessibilityFeatures`,
/// so there is nothing for this half to read.
library;

/// False everywhere but the web.
bool platformPrefersReducedMotion() => false;

/// No listener to install off the web. Returns a no-op canceller.
void Function() listenToPlatformReducedMotion(void Function() onChange) =>
    () {};
