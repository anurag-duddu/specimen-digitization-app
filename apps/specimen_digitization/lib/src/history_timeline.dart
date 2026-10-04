/// Audit events recovered from snapshots, pinned to one specimen and version.
library;

import 'dart:convert';

import 'models.dart';

/// One recorded event, with the snapshot that retained it.
class HistoryTimelineEvent {
  const HistoryTimelineEvent({
    required this.key,
    required this.event,
    required this.retainedRevision,
    required this.index,
    required this.legacyIdentity,
    this.sequence,
  });

  final String key;
  final Json event;
  final int retainedRevision;
  final int index;
  final int? sequence;
  final bool legacyIdentity;

  /// Only a server-recorded resulting version attributes an event to a save.
  int? get resultingRevision => event['resulting_revision'] is int
      ? event['resulting_revision'] as int
      : null;
}

int historyAuditOffset(Specimen record) {
  final offset = record.data['audit_offset'];
  return offset is int && offset > 0 ? offset : 0;
}

/// Compaction points to an older immutable snapshot, never a future version.
int? historyArchiveRevision(Specimen record) {
  if (historyAuditOffset(record) == 0) return null;
  final revision = record.data['history_through_revision'];
  return revision is int && revision > 0 && revision < record.revision
      ? revision
      : null;
}

/// Merges retained audit arrays without turning snapshot rows into actions.
class HistoryTimeline {
  HistoryTimeline(Specimen current)
    : specimenId = current.id,
      throughRevision = current.revision,
      archivedEventCount = historyAuditOffset(current),
      expectedEventCount = historyAuditOffset(current) + current.audit.length {
    add(current);
  }

  final String specimenId;
  final int throughRevision;
  final int archivedEventCount;
  final int expectedEventCount;
  final Map<String, HistoryTimelineEvent> _events = {};

  List<HistoryTimelineEvent> get newestFirst {
    final entries = _events.values.toList();
    entries.sort((a, b) {
      if (a.sequence != null && b.sequence != null) {
        final order = b.sequence!.compareTo(a.sequence!);
        if (order != 0) return order;
      } else if (a.sequence != null || b.sequence != null) {
        return a.sequence != null ? -1 : 1;
      }
      final revisionOrder = (b.resultingRevision ?? b.retainedRevision)
          .compareTo(a.resultingRevision ?? a.retainedRevision);
      if (revisionOrder != 0) return revisionOrder;
      final indexOrder = b.index.compareTo(a.index);
      return indexOrder == 0 ? a.key.compareTo(b.key) : indexOrder;
    });
    return entries;
  }

  bool get hasLegacyEvents => _events.values.any(
    (entry) => entry.legacyIdentity || entry.resultingRevision == null,
  );

  /// An offset records how many events were moved out of the current snapshot.
  /// Unknown sequence information cannot establish that those events recovered.
  int get missingArchivedEvents {
    if (archivedEventCount == 0) return 0;
    final known = _events.values
        .map((entry) => entry.sequence)
        .whereType<int>()
        .where((sequence) => sequence > 0 && sequence <= expectedEventCount)
        .toSet()
        .length;
    final missing = expectedEventCount - known;
    return missing > 0 ? missing : 0;
  }

  void add(Specimen record) {
    if (record.id != specimenId || record.revision > throughRevision) {
      throw const ApiFailure(
        'The requested history snapshot could not be verified.',
      );
    }
    final offset = record.data['audit_offset'];
    final occurrences = <String, int>{};
    final audit = record.audit;
    for (var index = 0; index < audit.length; index++) {
      final event = audit[index];
      final rawId = event['id'] ?? event['event_id'];
      final id = rawId is String && rawId.isNotEmpty ? rawId : null;
      final rawSequence = event['sequence'];
      final sequence = rawSequence is int && rawSequence > 0
          ? rawSequence
          : offset is int && offset >= 0
          ? offset + index + 1
          : null;
      final fingerprint = jsonEncode(_canonical(event));
      final occurrence = occurrences.update(
        fingerprint,
        (n) => n + 1,
        ifAbsent: () => 0,
      );
      // Legacy arrays have no stable identity. Keep equal occurrences within
      // one array distinct, while merging the same retained prefix safely.
      final key = id != null
          ? 'id:$id'
          : sequence != null
          ? 'sequence:$sequence'
          : 'legacy:$fingerprint:$occurrence';
      _events.putIfAbsent(
        key,
        () => HistoryTimelineEvent(
          key: key,
          event: Map<String, dynamic>.unmodifiable(event),
          retainedRevision: record.revision,
          index: index,
          sequence: sequence,
          legacyIdentity: id == null,
        ),
      );
    }
  }

  static Object? _canonical(Object? value) {
    if (value is Map) {
      final keys = value.keys.map((key) => key.toString()).toList()..sort();
      return {for (final key in keys) key: _canonical(value[key])};
    }
    if (value is List) return value.map(_canonical).toList();
    return value;
  }
}
