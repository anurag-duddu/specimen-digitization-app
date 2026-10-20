import 'dart:async';
import 'dart:isolate';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// Runner used by [intakeRunOffUi]. Product default is [Isolate.run].
typedef IntakeComputeRunner =
    Future<T> Function<T>(FutureOr<T> Function() action);

/// Runs [action] off the UI isolate in product builds.
///
/// [Isolate.run] is the right production choice: SHA-256 and RGBA quality
/// measurement can stall the UI isolate on large photographs. Under
/// [TestWidgetsFlutterBinding], isolate completion is delivered on the real
/// event loop and never advances the binding's fake async clock, so `pump` /
/// `pumpAndSettle` leave admission unfinished and the manifest empty unless
/// every caller wraps work in `tester.runAsync`. Same-isolate execution keeps
/// identical results and lets existing widget tests stay deterministic.
///
/// Detection uses the binding's runtime type (no `flutter_test` import in
/// `lib/`). [debugIntakeComputeOverride] remains available for explicit
/// harness pinning. Web stays on the current isolate — the same fallback
/// Flutter's `compute` uses there.
Future<T> intakeRunOffUi<T>(T Function() action) {
  final IntakeComputeRunner? override = kDebugMode
      ? debugIntakeComputeOverride
      : null;
  if (override != null) {
    return override(action);
  }
  if (kIsWeb || _intakeSameIsolateCompute) {
    // Already-complete future so FakeAsync does not need a real event-loop
    // turn the way an `async` body / Isolate.run completion would.
    return SynchronousFuture<T>(action());
  }
  return Isolate.run(action);
}

/// When set (debug builds only), [intakeRunOffUi] uses this instead of
/// [Isolate.run]. Prefer the automatic test-binding detection; this exists
/// for harnesses that pin before a binding exists.
@visibleForTesting
IntakeComputeRunner? debugIntakeComputeOverride;

/// In-process runner for widget tests. Same results as product; no isolate.
@visibleForTesting
Future<T> intakeComputeInProcess<T>(FutureOr<T> Function() action) {
  return SynchronousFuture<T>(action() as T);
}

bool get _intakeSameIsolateCompute {
  // AutomatedTestWidgetsFlutterBinding / LiveTestWidgetsFlutterBinding both
  // contain this substring. Avoid importing flutter_test from lib/.
  try {
    return WidgetsBinding.instance.runtimeType.toString().contains(
      'TestWidgetsFlutterBinding',
    );
  } on TypeError {
    // Binding not yet initialized (rare outside widgets); stay on Isolate.run.
    return false;
  }
}
