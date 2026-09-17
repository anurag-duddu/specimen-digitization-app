/// A notifier a page writes to while the frame above it is being built.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart' show SchedulerBinding, SchedulerPhase;

/// Announces a change now, or after the frame when one is being built.
///
/// A page publishes what it wants from the frame while it is being laid out,
/// which is the one moment the frame above it cannot be rebuilt. Every channel
/// a page publishes to and a frame reads, the scaffold's slots and exclusion
/// and the modal scope, defers to the end of the frame when it is written
/// during one and announces immediately otherwise. One mixin, so the three
/// cannot drift.
///
/// Not exported: it is how the package's own ambients are built, not a thing
/// the application composes with.
mixin FrameSafeNotifier on ChangeNotifier {
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  /// Notifies listeners, after the frame when one is being built.
  void announce() {
    final SchedulerPhase phase = SchedulerBinding.instance.schedulerPhase;
    if (phase == SchedulerPhase.persistentCallbacks ||
        phase == SchedulerPhase.midFrameMicrotasks) {
      SchedulerBinding.instance.addPostFrameCallback((Duration _) {
        if (!_disposed) notifyListeners();
      });
      return;
    }
    notifyListeners();
  }
}
