/// Native hosts use their platform defaults and observed pointer events.
library;

/// Null when the host has no browser capability API.
bool? platformSupportsTouch() => null;

/// Null when the host has no browser capability API.
bool? platformSupportsHover() => null;

/// Native pointer capability changes arrive through Flutter pointer events.
void Function() listenToPlatformInputCapabilities(void Function() onChange) =>
    () {};
