/// The status vocabulary the shared components render
/// (design system, sections 3.4, 3.5 and 6.2; UX writing, sections 4.13 and
/// 4.16).
///
/// One enum covers both the queue dispositions and states the server reports
/// for a record and the per-field states it reports for a value. A call site
/// names a status; it never names a color, an icon or a label separately, so
/// the three cannot drift apart.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';

/// Everything a chip needs to draw one status, resolved against the theme.
///
/// There is deliberately no public constructor that takes a bare color: a
/// presentation is produced by an enum, so the color, the glyph and the word
/// always travel together (design system, section 8.2).
@immutable
class StatusPresentation {
  const StatusPresentation({
    required this.content,
    required this.fill,
    required this.onFill,
    required this.icon,
    required this.fill01,
    required this.label,
    required this.semanticsLabel,
    this.progress,
  });

  /// Text, glyph and border color on a plain surface.
  final Color content;

  /// The container behind the chip.
  final Color fill;

  /// Text and glyph color on [fill].
  final Color onFill;

  /// The glyph. Status is never color alone.
  final IconData icon;

  /// The Material Symbols fill axis: 1 for a settled disposition, 0 otherwise.
  final double fill01;

  /// The visible word, sentence case, 2 to 20 characters.
  final String label;

  /// A complete phrase that stands alone out of context.
  final String semanticsLabel;

  /// A determinate progress fraction to draw in place of [icon], if any.
  /// Progress is information, so it keeps its motion under reduced motion.
  final double? progress;
}

/// The dispositions, operational states and field states this client renders.
///
/// The first six values are record-level; the last seven are the field states
/// the server publishes in `knownFieldStates`.
enum SpecimenStatus {
  /// A reviewer affirmed the record.
  cleared('disposition.cleared'),

  /// The record is waiting on a person.
  needsReview('disposition.needsReview'),

  /// Shelved by a reviewer, not judged.
  deferred('disposition.deferred'),

  /// Work is running. Never a final queue.
  processing('state.processing'),

  /// Processing stopped. Operational, not evidentiary, and never error red.
  blocked('state.blocked'),

  /// The server reported something this client has no treatment for.
  unknown('state.unknown'),

  /// The field value is supported by the evidence on the record.
  supported('disposition.cleared'),

  /// The field state named `unknown` on the wire. Distinct from [unknown],
  /// which is this client failing to recognize a value at all.
  unknownValue('evidence.model'),

  /// The pixels could not be read.
  unreadable('evidence.model'),

  /// The label does not carry this field.
  notPresent('evidence.model'),

  /// The field does not apply to this specimen.
  notApplicable('disposition.deferred'),

  /// More than one reading is defensible.
  ambiguous('disposition.needsReview'),

  /// A conflict that no rule settles.
  unresolved('disposition.needsReview');

  const SpecimenStatus(this.tokenKey);

  /// The product token triple this status draws from.
  final String tokenKey;

  /// True for the six record-level values.
  bool get isRecordStatus => index <= SpecimenStatus.unknown.index;

  /// The server strings this client maps, by status.
  ///
  /// The record-level strings are the ones the API already emits
  /// (`cleared`, `needs_human_review`, `deferred`, `running`,
  /// `processing_blocked`); the field-level strings are `knownFieldStates`
  /// in `models.dart`.
  static const Map<String, SpecimenStatus> wireValues =
      <String, SpecimenStatus>{
        'cleared': SpecimenStatus.cleared,
        'needs_human_review': SpecimenStatus.needsReview,
        'deferred': SpecimenStatus.deferred,
        'running': SpecimenStatus.processing,
        'processing_blocked': SpecimenStatus.blocked,
        'supported': SpecimenStatus.supported,
        'unknown': SpecimenStatus.unknownValue,
        'unreadable': SpecimenStatus.unreadable,
        'not_present': SpecimenStatus.notPresent,
        'not_applicable': SpecimenStatus.notApplicable,
        'ambiguous': SpecimenStatus.ambiguous,
        'unresolved': SpecimenStatus.unresolved,
      };

  /// Maps a server string to a status.
  ///
  /// Anything absent, empty or unrecognized becomes [unknown], which renders
  /// as a visible "State unknown" chip rather than as a blank. An unmapped
  /// server value is a fact about the record, so it is shown, not swallowed.
  static SpecimenStatus fromWire(String? wire) {
    if (wire == null) return SpecimenStatus.unknown;
    return wireValues[wire.trim()] ?? SpecimenStatus.unknown;
  }

  /// The visible chip word.
  String get label => switch (this) {
    SpecimenStatus.cleared => 'Cleared',
    SpecimenStatus.needsReview => 'Needs human review',
    SpecimenStatus.deferred => 'Deferred',
    SpecimenStatus.processing => 'Processing',
    SpecimenStatus.blocked => 'Processing blocked',
    SpecimenStatus.unknown => 'State unknown',
    SpecimenStatus.supported => 'Supported',
    SpecimenStatus.unknownValue => 'Unknown',
    SpecimenStatus.unreadable => 'Unreadable',
    SpecimenStatus.notPresent => 'Not present',
    SpecimenStatus.notApplicable => 'Not applicable',
    SpecimenStatus.ambiguous => 'Ambiguous',
    SpecimenStatus.unresolved => 'Unresolved',
  };

  /// The glyph.
  ///
  /// The record-level values reuse `SpecimenIconography`. The field states
  /// are not in that set yet, so their glyphs are named here, next to the
  /// words they belong to, rather than being chosen at a call site.
  IconData get icon => switch (this) {
    SpecimenStatus.cleared => SpecimenIconography.cleared,
    SpecimenStatus.needsReview => SpecimenIconography.needsReview,
    SpecimenStatus.deferred => SpecimenIconography.deferred,
    SpecimenStatus.processing => SpecimenIconography.processing,
    SpecimenStatus.blocked => SpecimenIconography.blocked,
    SpecimenStatus.unknown => SpecimenIconography.unknownState,
    SpecimenStatus.supported => SpecimenIconography.cleared,
    SpecimenStatus.unknownValue => Symbols.help,
    SpecimenStatus.unreadable => Symbols.visibility_off,
    SpecimenStatus.notPresent => Symbols.horizontal_rule,
    SpecimenStatus.notApplicable => Symbols.hide_source,
    SpecimenStatus.ambiguous => Symbols.alt_route,
    SpecimenStatus.unresolved => Symbols.pending,
  };

  /// A complete phrase for assistive technology, 100 characters or fewer.
  ///
  /// Where a chip carries meaning through color, the label carries it through
  /// words, and it names which vocabulary the word came from, so "Unknown"
  /// spoken on a field is not mistaken for a queue state (UX writing, 4.16).
  String get semanticsLabel =>
      '${isRecordStatus ? 'Queue' : 'Field'}: ${label.toLowerCase()}';

  /// Resolves the color triple from the theme and pairs it with the glyph and
  /// the word.
  StatusPresentation presentation(BuildContext context) {
    final DispositionStyle style = context.dispositionStyle(tokenKey);
    return StatusPresentation(
      content: style.content,
      fill: style.fill,
      onFill: style.onFill,
      icon: icon,
      fill01: style.fill01,
      label: label,
      semanticsLabel: semanticsLabel,
    );
  }
}
