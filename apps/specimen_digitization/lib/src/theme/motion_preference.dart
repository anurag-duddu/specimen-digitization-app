/// The stored "Reduce motion" setting (04 sections 6.2 and 6.2b).
///
/// Three of the four reduced-motion sources belong to a platform. This is the
/// fourth: an explicit preference the reviewer sets inside the application. It
/// is the only route available to a reviewer on a managed desktop who cannot
/// change an operating system accessibility setting, and the only route at all
/// on a build where the browser bridge reports nothing.
///
/// The controller, the scope and the store interface live in
/// `package:specimen_ui`, because every component in the package asks for a
/// duration and a duration has to know about this. What stays here is the one
/// piece that needs a platform: the `shared_preferences` implementation. The
/// package carries no storage dependency of its own.
library;

import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';

export 'package:specimen_ui/specimen_ui.dart'
    show
        MemoryMotionPreferenceStore,
        MotionPreference,
        MotionPreferenceController,
        MotionPreferenceStore,
        MotionScope;

/// Where the preference is stored. Versioned, so a later change of meaning
/// gets a new key rather than a surprising value under the old one.
const String reduceMotionPreferenceKey = 'reduce-motion-v1';

/// The default store, backed by `shared_preferences`.
class SharedMotionPreferenceStore implements MotionPreferenceStore {
  /// The store the application runs on.
  const SharedMotionPreferenceStore();

  @override
  Future<bool?> read() async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      return prefs.getBool(reduceMotionPreferenceKey);
    } catch (_) {
      // A platform with no preference store is a platform with no stored
      // preference, not a startup failure.
      return null;
    }
  }

  @override
  Future<void> write(bool value) async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setBool(reduceMotionPreferenceKey, value);
    } catch (_) {
      // The setting still applies to this session; it just will not survive a
      // restart. Failing the toggle would be worse.
    }
  }
}
