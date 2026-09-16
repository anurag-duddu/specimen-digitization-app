/// The platform reduced-motion signal that Flutter 3.38.5 does not carry
/// (motion and microinteractions, section 6.2b).
///
/// The web engine's `computeAccessibilityFeatures` sets `highContrast` and
/// returns, so `prefers-reduced-motion` never reaches the framework. This
/// conditional export is the bridge, in the same shape the repository already
/// uses for `email_link_browser.dart`.
///
/// TODO(flutter-3.44): delete this bridge and its two implementations when the
/// app moves to Flutter 3.44 or later, where the engine reports the media
/// query itself. The `dependency_overrides` block in `pubspec.yaml` tracks the
/// same upgrade.
library;

export 'reduced_motion_platform_stub.dart'
    if (dart.library.js_interop) 'reduced_motion_platform_web.dart';
