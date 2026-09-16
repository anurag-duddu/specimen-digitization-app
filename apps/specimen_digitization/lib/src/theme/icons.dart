/// The icon, word and color triple for every state the product can show
/// (design system, sections 3.5, 6.1, 6.2 and 8.2).
///
/// Status is never color alone. A call site asks for a status key and gets the
/// icon, the label and the colors together, so it cannot pair the color of one
/// status with the label of another, and cannot pass a bare color to something
/// that displays state.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'semantic_colors.dart';
import 'spacing.dart';
import 'typography.dart';

/// Everything a status chip needs. `fill01` is the Material Symbols fill axis:
/// 1 only for a settled disposition, 0 everywhere else.
typedef DispositionStyle = ({
  Color content,
  Color fill,
  Color onFill,
  IconData icon,
  double fill01,
  String label,
});

/// An abstention: a value that is absent, rendered in the slot the value
/// would have occupied.
typedef AbstentionStyle = ({IconData icon, String label});

/// The status keys this product knows about. A key that is not in this list
/// has no visual treatment, which is deliberate: adding a status is a design
/// decision, not a call-site decision.
///
/// These still return `Symbols.` glyphs. The registry that replaces them is
/// `UiIcons`, on Phosphor; the screens that draw these move to it in waves 2
/// and 3, and `icons_unique` carries the backlog until they do.
abstract final class SpecimenIconography {
  static const IconData cleared = Symbols.check_circle;
  static const IconData needsReview = Symbols.flag;
  static const IconData deferred = Symbols.pause_circle;
  static const IconData processing = Symbols.autorenew;
  static const IconData blocked = Symbols.block;
  static const IconData unknownState = Symbols.help;
  static const IconData modelReading = Symbols.memory;
  static const IconData humanDecision = Symbols.person;
  static const IconData authorityMatch = Symbols.menu_book;
  static const IconData riskLow = Symbols.signal_cellular_alt_1_bar;
  static const IconData riskMedium = Symbols.signal_cellular_alt_2_bar;
  static const IconData riskHigh = Symbols.signal_cellular_alt;
  static const IconData syntheticEnvironment = Symbols.science;

  /// The four abstentions (design system, section 3.5).
  static const Map<String, AbstentionStyle> abstentions =
      <String, AbstentionStyle>{
        'unknown': (icon: Symbols.help, label: 'Unknown'),
        'unreadable': (icon: Symbols.visibility_off, label: 'Unreadable'),
        'notPresent': (icon: Symbols.horizontal_rule, label: 'Not present'),
        'unmeasured': (icon: Symbols.hide_source, label: 'Unmeasured'),
      };
}

/// Reads the token layer from a `BuildContext`.
extension SpecimenTokensX on BuildContext {
  /// The product color tokens.
  SpecimenColors get tokens => Theme.of(this).extension<SpecimenColors>()!;

  /// The 4px spacing grid.
  SpecimenSpacing get space => Theme.of(this).extension<SpecimenSpacing>()!;

  /// Icon sizes, hit boxes, row heights.
  SpecimenSizing get sizes => Theme.of(this).extension<SpecimenSizing>()!;

  /// Corner radii and stroke widths.
  SpecimenShape get shape => Theme.of(this).extension<SpecimenShape>()!;

  /// The monospace roles.
  SpecimenTypography get mono =>
      Theme.of(this).extension<SpecimenTypography>()!;

  /// Durations and curves, with the live reduced-motion state folded in.
  MotionTokens get motion => MotionTokens.of(this);

  /// The letterbox behind a photograph (09 section 3.1).
  ///
  /// The photograph itself is never re-toned; the matte is what changes. It
  /// is a role of its own now, so this no longer reads `brightness` to pick a
  /// surface: `UiColor` already carries the right value for the mode.
  Color get sourceMatte => UiTheme.of(this).color.matte;

  /// The icon, word and colors for a status key.
  DispositionStyle dispositionStyle(String key) {
    final SpecimenColors t = tokens;
    return switch (key) {
      'disposition.cleared' => (
        content: t.clearedContent,
        fill: t.clearedFill,
        onFill: t.clearedOnFill,
        icon: SpecimenIconography.cleared,
        fill01: 1,
        label: 'Cleared',
      ),
      'disposition.needsReview' => (
        content: t.needsReviewContent,
        fill: t.needsReviewFill,
        onFill: t.needsReviewOnFill,
        icon: SpecimenIconography.needsReview,
        fill01: 1,
        label: 'Needs human review',
      ),
      'disposition.deferred' => (
        content: t.deferredContent,
        fill: t.deferredFill,
        onFill: t.deferredOnFill,
        icon: SpecimenIconography.deferred,
        fill01: 1,
        label: 'Deferred',
      ),
      'state.processing' => (
        content: t.processingContent,
        fill: t.processingFill,
        onFill: t.processingOnFill,
        icon: SpecimenIconography.processing,
        fill01: 0,
        label: 'Processing',
      ),
      'state.blocked' => (
        content: t.blockedContent,
        fill: t.blockedFill,
        onFill: t.blockedOnFill,
        icon: SpecimenIconography.blocked,
        fill01: 0,
        label: 'Processing blocked',
      ),
      'evidence.model' => (
        content: t.evidenceModelContent,
        fill: t.evidenceModelFill,
        onFill: t.evidenceModelOnFill,
        icon: SpecimenIconography.modelReading,
        fill01: 0,
        label: 'Model reading',
      ),
      'evidence.human' => (
        content: t.evidenceHumanContent,
        fill: t.evidenceHumanFill,
        onFill: t.evidenceHumanOnFill,
        icon: SpecimenIconography.humanDecision,
        fill01: 1,
        label: 'Reviewer',
      ),
      'evidence.authority' => (
        content: t.evidenceAuthorityContent,
        fill: t.evidenceAuthorityFill,
        onFill: t.evidenceAuthorityOnFill,
        icon: SpecimenIconography.authorityMatch,
        fill01: 0,
        label: 'Authority',
      ),
      _ => (
        content: t.evidenceModelContent,
        fill: t.evidenceModelFill,
        onFill: t.evidenceModelOnFill,
        icon: SpecimenIconography.unknownState,
        fill01: 0,
        label: 'State unknown',
      ),
    };
  }
}
