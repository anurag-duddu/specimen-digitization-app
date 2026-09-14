/// The stored "Reduce motion" setting and the scope that carries it
/// (motion and microinteractions, section 6.2 and 6.2b).
///
/// Three of the four reduced-motion sources belong to a platform. This is the
/// fourth: an explicit preference the reviewer sets inside the app. It is the
/// only route available to a reviewer on a managed desktop who cannot change
/// an operating system accessibility setting, and it is the only route at all
/// on a build where the browser bridge reports nothing.
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'reduced_motion_platform.dart';

/// Where the preference is stored. Versioned, so a later change of meaning
/// gets a new key rather than a surprising value under the old one.
const String reduceMotionPreferenceKey = 'reduce-motion-v1';

/// Reads and writes the stored preference.
///
/// Injected so a test, and the fixture build, can run without touching the
/// platform store.
abstract interface class MotionPreferenceStore {
  /// The stored preference, or null when the reviewer has not set one.
  Future<bool?> read();

  /// Stores [value].
  Future<void> write(bool value);
}

/// The default store, backed by `shared_preferences`.
class SharedMotionPreferenceStore implements MotionPreferenceStore {
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

/// An in-memory store, for tests and for the local fixture build.
class MemoryMotionPreferenceStore implements MotionPreferenceStore {
  MemoryMotionPreferenceStore([this.value]);

  /// The stored value.
  bool? value;

  @override
  Future<bool?> read() async => value;

  @override
  Future<void> write(bool input) async => value = input;
}

/// The live preference, as a listenable.
class MotionPreferenceController extends ChangeNotifier {
  MotionPreferenceController({
    MotionPreferenceStore store = const SharedMotionPreferenceStore(),
    bool initial = false,
  }) : _store = store,
       _forced = initial;

  final MotionPreferenceStore _store;
  bool _forced;

  /// True when the reviewer has asked for reduced motion inside the app.
  bool get forceReducedMotion => _forced;

  /// Loads the stored value. Safe to call more than once.
  Future<void> load() async {
    final bool? stored = await _store.read();
    if (stored != null && stored != _forced) {
      _forced = stored;
      notifyListeners();
    }
  }

  /// Sets the preference and stores it.
  Future<void> set(bool value) async {
    if (value == _forced) return;
    _forced = value;
    notifyListeners();
    await _store.write(value);
  }
}

/// Carries the preference down the tree.
///
/// `MotionTokens.prefersReducedMotion` reads this, so every widget that asks
/// for a duration rebuilds when the reviewer changes the setting.
class MotionPreference extends InheritedNotifier<MotionPreferenceController> {
  const MotionPreference({
    super.key,
    required MotionPreferenceController controller,
    required super.child,
  }) : super(notifier: controller);

  /// The controller above [context], or null where no scope was installed.
  ///
  /// A component test pumps a bare `MaterialApp`, so the absence of a scope is
  /// normal and means "no in-app override", never an error.
  static MotionPreferenceController? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<MotionPreference>()?.notifier;

  /// True when the reviewer asked for reduced motion inside the app.
  static bool forcedOf(BuildContext context) =>
      maybeOf(context)?.forceReducedMotion ?? false;
}

/// Keeps the app rebuilding when a reduced-motion source changes.
///
/// `AccessibilityFeatures` is not an inherited widget, so an iPad reviewer
/// turning Reduce Motion on mid-session would otherwise change nothing until
/// the next unrelated rebuild. The web bridge has the same problem, and the
/// browser reports its change through an event listener rather than through
/// the framework at all.
class MotionScope extends StatefulWidget {
  const MotionScope({super.key, required this.controller, required this.child});

  /// The in-app preference.
  final MotionPreferenceController controller;

  /// The application beneath the scope.
  final Widget child;

  @override
  State<MotionScope> createState() => _MotionScopeState();
}

class _MotionScopeState extends State<MotionScope> with WidgetsBindingObserver {
  void Function()? _cancelPlatformListener;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _cancelPlatformListener = listenToPlatformReducedMotion(_platformChanged);
  }

  @override
  void dispose() {
    _cancelPlatformListener?.call();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _platformChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAccessibilityFeatures() => _platformChanged();

  @override
  Widget build(BuildContext context) =>
      MotionPreference(controller: widget.controller, child: widget.child);
}
