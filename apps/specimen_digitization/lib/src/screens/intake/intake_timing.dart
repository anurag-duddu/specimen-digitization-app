/// Network reconciliation policies, independent of visual motion and text size.
library;

/// Bounds status latency without polling on every repaint or photo selection.
const Duration intakePollInterval = Duration(seconds: 3);

/// Allows the user to sign in and complete provider consent in another window.
const Duration intakeAuthorizationTimeout = Duration(minutes: 10);
