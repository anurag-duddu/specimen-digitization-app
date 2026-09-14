/// Corrections a reviewer has made but not yet sent
/// (screen blueprints, 6.4; audit pass criterion 7.2).
///
/// A reviewer corrects five fields and saves once, with one reason. The
/// pending set is the local half of that: it holds what was typed, what the
/// server said at the time it was typed, and enough to say in plain words
/// what will change.
library;

import 'package:flutter/foundation.dart';

import '../../models.dart';

/// One field correction waiting to be sent.
@immutable
class PendingFieldChange {
  const PendingFieldChange({
    required this.fieldKey,
    required this.displayName,
    required this.state,
    this.literal,
    this.parsed,
    this.normalized,
    this.authorityId,
    this.evidenceIds = const <String>[],
    this.regionId,
    this.baseLiteral,
  });

  /// The field's key on the wire.
  final String fieldKey;

  /// The field's name, as the reviewer reads it.
  final String displayName;

  /// The evidence state the reviewer chose.
  final String state;

  /// The verbatim value. Null for every state except `supported`.
  final String? literal;

  /// The interpretation.
  final String? parsed;

  /// The standardized value.
  final String? normalized;

  /// The authority identifier backing the standardized value.
  final String? authorityId;

  /// The record's own evidence identifiers that support this value. Picked
  /// from the record, never typed (audit finding H6.1).
  final List<String> evidenceIds;

  /// The region the field was read from, so the source pane can jump to it.
  final String? regionId;

  /// What the server said the verbatim value was when this edit was made.
  /// Used to tell a stale pending change from one that is still safe to
  /// re-apply after the record moves under the reviewer (blueprint 6.7).
  final String? baseLiteral;

  /// One line naming what this change does, for the reason sheet and the
  /// pending list.
  String get summary => state == 'supported'
      ? '$displayName becomes "${literal ?? ''}"'
      : '$displayName is recorded as ${state.replaceAll('_', ' ')}';

  /// The payload the repository's `review` accepts for one field decision.
  ///
  /// The wire takes one decision per call, so a batch is this map once per
  /// change, sent in sequence under one reason.
  Json toChange(String reason) => <String, dynamic>{
    'kind': 'field_correction',
    'target_id': fieldKey,
    'value': state == 'supported' ? literal : null,
    'state': state,
    'parsed': state == 'supported' && (parsed?.isNotEmpty ?? false)
        ? parsed
        : null,
    'normalized': state == 'supported' && (normalized?.isNotEmpty ?? false)
        ? normalized
        : null,
    'authority_id': state == 'supported' && (authorityId?.isNotEmpty ?? false)
        ? authorityId
        : null,
    'reason': reason,
    'evidence_ids': evidenceIds,
  };

  @override
  bool operator ==(Object other) =>
      other is PendingFieldChange &&
      other.fieldKey == fieldKey &&
      other.state == state &&
      other.literal == literal &&
      other.parsed == parsed &&
      other.normalized == normalized &&
      other.authorityId == authorityId &&
      listEquals(other.evidenceIds, evidenceIds);

  @override
  int get hashCode =>
      Object.hash(fieldKey, state, literal, parsed, normalized, authorityId);
}

/// The chip's word for a count of pending changes.
///
/// Singular and plural are spelled out rather than assembled, so neither
/// reads as a template (UX writing, section 4).
String pendingChangesLabel(int count) =>
    count == 1 ? '1 pending change' : '$count pending changes';

/// Drops pending changes whose field moved under the reviewer.
///
/// A change is kept when the field's verbatim value on the new version is the
/// same one the reviewer was looking at when they typed. Anything else is
/// returned in [stale] so the reviewer is told rather than silently
/// overwriting someone else's work (blueprint 6.7).
({List<PendingFieldChange> keep, List<PendingFieldChange> stale}) reapply(
  List<PendingFieldChange> pending,
  Specimen specimen,
) {
  final List<PendingFieldChange> keep = <PendingFieldChange>[];
  final List<PendingFieldChange> stale = <PendingFieldChange>[];
  for (final PendingFieldChange change in pending) {
    final Json? field = specimen.fields
        .where((Json f) => f['field_key'] == change.fieldKey)
        .firstOrNull;
    if (field == null) {
      stale.add(change);
      continue;
    }
    final String? now = field['literal_value'] as String?;
    if (change.baseLiteral == now) {
      keep.add(change);
    } else {
      stale.add(change);
    }
  }
  return (keep: keep, stale: stale);
}
