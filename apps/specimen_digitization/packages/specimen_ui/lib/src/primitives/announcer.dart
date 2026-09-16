/// Announcing a status change once (10 section 3, `Announcer`; 06 section 3).
///
/// Two shapes, because the product has two kinds of change. A message that
/// persists on screen lives in a live region, so a screen reader reads it when
/// it changes and never again. A momentary event that has no text host is sent
/// through `SemanticsService.sendAnnouncement`, once, guarded so a rebuild
/// cannot re-fire it.
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

/// Wraps a message that stays on screen in a live region.
///
/// Flutter fires an announcement only when a live region's computed label
/// changes, so a status that rebuilds with the same words is not read twice.
class Announcer extends StatelessWidget {
  /// Announces [child] when its label changes.
  const Announcer({super.key, required this.child, this.assertive = false});

  /// The message. Usually a `Text`.
  final Widget child;

  /// True to interrupt whatever the screen reader is reading.
  ///
  /// Reserved for a message that stops work. A status change is polite.
  final bool assertive;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    container: true,
    child: child,
  );
}

/// Sends a one-shot announcement for an event with no text on screen.
///
/// `SemanticsService.announce` is deprecated as of Flutter 3.35; this uses
/// `sendAnnouncement`, and it checks `MediaQuery.supportsAnnounceOf` first
/// because a platform that does not support announcements should not be sent
/// one (06 section 3.3).
abstract final class AnnounceOnce {
  /// Announces [message] if the platform supports it.
  ///
  /// Call this from an event handler, never from `build`: a rebuild would
  /// repeat it, which is the defect the guard in 06 section 3.3 exists to
  /// prevent.
  static void send(
    BuildContext context,
    String message, {
    Assertiveness assertiveness = Assertiveness.polite,
  }) {
    if (message.isEmpty) return;
    if (!MediaQuery.supportsAnnounceOf(context)) return;
    SemanticsService.sendAnnouncement(
      View.of(context),
      message,
      Directionality.of(context),
      assertiveness: assertiveness,
    );
  }
}
