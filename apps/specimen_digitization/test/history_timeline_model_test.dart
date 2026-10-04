import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/history_timeline.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test('snapshot prefixes dedupe by event ID and keep event order', () {
    final timeline = HistoryTimeline(
      const Specimen({
        'specimen_id': 's',
        'revision': 10,
        'audit_offset': 2,
        'audit_events': [
          {
            'id': 'third',
            'sequence': 3,
            'resulting_revision': 8,
            'action': 'workflow_step',
          },
        ],
      }),
    );
    timeline.add(
      const Specimen({
        'specimen_id': 's',
        'revision': 8,
        'audit_offset': 0,
        'audit_events': [
          {'id': 'first', 'sequence': 1, 'action': 'ingest'},
          {'id': 'second', 'sequence': 2, 'action': 'review_field'},
          {
            'id': 'third',
            'sequence': 3,
            'resulting_revision': 8,
            'action': 'workflow_step',
          },
        ],
      }),
    );
    timeline.add(const Specimen({'specimen_id': 's', 'revision': 7}));
    expect(timeline.newestFirst.map((entry) => entry.event['id']), [
      'third',
      'second',
      'first',
    ]);
    expect(timeline.newestFirst.first.retainedRevision, 10);
    expect(timeline.missingArchivedEvents, 0);
    expect(timeline.throughRevision, 10);
  });

  test(
    'legacy identical occurrences stay distinct across repeated prefixes',
    () {
      final timeline = HistoryTimeline(
        const Specimen({
          'specimen_id': 's',
          'revision': 3,
          'audit_events': [
            {'action': 'legacy', 'reason': 'Recorded reason'},
            {'action': 'legacy', 'reason': 'Recorded reason'},
          ],
        }),
      );
      timeline.add(
        const Specimen({
          'specimen_id': 's',
          'revision': 2,
          'audit_events': [
            {'reason': 'Recorded reason', 'action': 'legacy'},
            {'reason': 'Recorded reason', 'action': 'legacy'},
          ],
        }),
      );
      expect(timeline.newestFirst, hasLength(2));
      expect(timeline.hasLegacyEvents, isTrue);
      expect(timeline.newestFirst.first.event.containsKey('actor'), isFalse);
      expect(
        timeline.newestFirst.first.event.containsKey('created_at'),
        isFalse,
      );
      expect(timeline.newestFirst.first.resultingRevision, isNull);
    },
  );

  test(
    'future or different specimen snapshots cannot enter a pinned timeline',
    () {
      final timeline = HistoryTimeline(
        const Specimen({'specimen_id': 's', 'revision': 3}),
      );
      expect(
        () => timeline.add(
          const Specimen({'specimen_id': 'other', 'revision': 2}),
        ),
        throwsA(isA<ApiFailure>()),
      );
      expect(
        () => timeline.add(const Specimen({'specimen_id': 's', 'revision': 4})),
        throwsA(isA<ApiFailure>()),
      );
      expect(timeline.newestFirst, isEmpty);
    },
  );

  test(
    'archive pointers must be earlier and require recorded offloaded events',
    () {
      expect(
        historyArchiveRevision(
          const Specimen({
            'specimen_id': 's',
            'revision': 9,
            'audit_offset': 2,
            'history_through_revision': 7,
          }),
        ),
        7,
      );
      for (final boundary in [0, 9, 10, null]) {
        expect(
          historyArchiveRevision(
            Specimen({
              'specimen_id': 's',
              'revision': 9,
              'audit_offset': 2,
              'history_through_revision': boundary,
            }),
          ),
          isNull,
        );
      }
      expect(
        historyArchiveRevision(
          const Specimen({
            'specimen_id': 's',
            'revision': 9,
            'audit_offset': 0,
            'history_through_revision': 7,
          }),
        ),
        isNull,
      );
    },
  );
}
