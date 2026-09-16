/// Motion, as names over `package:specimen_ui`.
///
/// `MotionTokens` and the reduced-motion plumbing live in the design system
/// package now, because a duration is a token and every component in the
/// package needs one. This file re-exports them so no screen changed, and
/// keeps the product's haptics, which are behaviour rather than a token.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
export 'package:specimen_ui/specimen_ui.dart'
    show
        MemoryMotionPreferenceStore,
        MotionPreference,
        MotionPreferenceController,
        MotionPreferenceStore,
        MotionScope,
        MotionTokens;

/// The app's entire haptic surface (motion and microinteractions, 4.7).
///
/// Two delight moments are approved, and only two: the disposition settling
/// after a save the reviewer committed (catalog row 50), and a whole upload
/// batch finishing while the operator is at a copy stand rather than looking
/// at the screen (row 67). The per-item version of row 67 is banned outright,
/// because a two hundred image batch would produce two hundred buzzes, which
/// is noise rather than feedback. The selection tick the catalog attaches to
/// choosing a region and a segment is the only other call, and it is the one
/// Flutter documents as the lightest of the five.
///
/// `HapticFeedback` is already a no-op on web and desktop, but every call is
/// gated here anyway, so the platform rule is a line of code a reviewer can
/// read rather than a property of a plugin.
abstract final class SpecimenHaptics {
  /// True on the two platforms whose system haptics these calls reach.
  static bool get available =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.android);

  /// Delight moment 1: a decision the reviewer committed has landed.
  ///
  /// The reviewer is looking at the screen, so this is redundancy beside the
  /// chip change and the spoken announcement, never the only channel.
  static void decisionLanded() {
    if (available) unawaited(HapticFeedback.mediumImpact());
  }

  /// Delight moment 2: one upload batch reached its final states.
  ///
  /// Fired once per batch, never once per item.
  static void batchComplete() {
    if (available) unawaited(HapticFeedback.lightImpact());
  }

  /// The selection tick for choosing a region (catalog rows 36 and 37) and
  /// for the segment that changes which panel a reviewer is reading (row 41).
  static void selectionChanged() {
    if (available) unawaited(HapticFeedback.selectionClick());
  }
}
