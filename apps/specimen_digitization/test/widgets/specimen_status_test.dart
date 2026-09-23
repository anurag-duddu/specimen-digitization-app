// The status vocabulary: the wire mapping, the words and the phrases.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'harness.dart';

void main() {
  group('fromWire', () {
    test('maps every record level string the server emits', () {
      expect(SpecimenStatus.fromWire('cleared'), SpecimenStatus.cleared);
      expect(
        SpecimenStatus.fromWire('needs_human_review'),
        SpecimenStatus.needsReview,
      );
      expect(SpecimenStatus.fromWire('deferred'), SpecimenStatus.deferred);
      expect(SpecimenStatus.fromWire('running'), SpecimenStatus.processing);
      expect(
        SpecimenStatus.fromWire('processing_blocked'),
        SpecimenStatus.blocked,
      );
    });

    test('maps every field state in knownFieldStates', () {
      for (final String state in knownFieldStates) {
        final SpecimenStatus mapped = SpecimenStatus.fromWire(state);
        expect(
          mapped,
          isNot(SpecimenStatus.unknown),
          reason: '$state has no treatment',
        );
        expect(mapped.isRecordStatus, isFalse, reason: '$state is a field');
      }
    });

    test('an absent, empty or unrecognized value is state unknown', () {
      expect(SpecimenStatus.fromWire(null), SpecimenStatus.unknown);
      expect(SpecimenStatus.fromWire(''), SpecimenStatus.unknown);
      expect(SpecimenStatus.fromWire('gone_fishing'), SpecimenStatus.unknown);
    });

    test('trims the value before mapping', () {
      expect(SpecimenStatus.fromWire(' cleared '), SpecimenStatus.cleared);
    });

    test('the wire unknown is the field state, not the fallback', () {
      expect(SpecimenStatus.fromWire('unknown'), SpecimenStatus.unknownValue);
    });

    // PRD 10.1: "Any processing stage may enter Retry scheduled, Paused,
    // Cancelled, or Processing blocked." The summary sends each as `status`.
    test('maps every operational state the summary sends', () {
      expect(
        SpecimenStatus.fromWire('retry_scheduled'),
        SpecimenStatus.retryScheduled,
      );
      expect(SpecimenStatus.fromWire('paused'), SpecimenStatus.paused);
      expect(SpecimenStatus.fromWire('cancelled'), SpecimenStatus.cancelled);
      for (final SpecimenStatus status in <SpecimenStatus>[
        SpecimenStatus.retryScheduled,
        SpecimenStatus.paused,
        SpecimenStatus.cancelled,
      ]) {
        expect(status.isRecordStatus, isTrue, reason: status.name);
      }
    });
  });

  group('operational states', () {
    test('say the word PRD 10.1 uses for each', () {
      expect(SpecimenStatus.retryScheduled.label, 'Retry scheduled');
      expect(SpecimenStatus.paused.label, 'Paused');
      expect(SpecimenStatus.cancelled.label, 'Cancelled');
    });

    test('draw the operational triple, never a queue colour', () {
      for (final SpecimenStatus status in <SpecimenStatus>[
        SpecimenStatus.retryScheduled,
        SpecimenStatus.paused,
        SpecimenStatus.cancelled,
      ]) {
        expect(status.tokenKey, 'state.blocked', reason: status.name);
      }
    });

    test('draw the registry glyph whose meaning matches', () {
      expect(SpecimenStatus.retryScheduled.iconSpec, UiIcons.time);
      expect(SpecimenStatus.paused.iconSpec, UiIcons.blocked);
      expect(SpecimenStatus.cancelled.iconSpec, UiIcons.stop);
    });
  });

  group('ofRecord', () {
    test('the disposition is the queue, whatever the run state says', () {
      expect(
        SpecimenStatus.ofRecord(disposition: 'cleared', state: 'completed'),
        SpecimenStatus.cleared,
      );
      expect(
        SpecimenStatus.ofRecord(
          disposition: 'needs_human_review',
          state: 'processing_blocked',
        ),
        SpecimenStatus.needsReview,
      );
    });

    test('with no disposition the run state is shown', () {
      expect(
        SpecimenStatus.ofRecord(state: 'processing_blocked'),
        SpecimenStatus.blocked,
      );
      expect(
        SpecimenStatus.ofRecord(state: 'running'),
        SpecimenStatus.processing,
      );
      expect(
        SpecimenStatus.ofRecord(state: 'retry_scheduled'),
        SpecimenStatus.retryScheduled,
      );
    });

    test('a completed run with no disposition has no queue to show', () {
      expect(
        SpecimenStatus.ofRecord(state: 'completed'),
        SpecimenStatus.unknown,
      );
    });

    test('a field state is never drawn as a record state', () {
      expect(SpecimenStatus.ofRecord(state: 'unknown'), SpecimenStatus.unknown);
      expect(
        SpecimenStatus.ofRecord(state: 'supported'),
        SpecimenStatus.unknown,
      );
      expect(
        SpecimenStatus.ofRecord(disposition: 'unresolved'),
        SpecimenStatus.unknown,
      );
    });

    test('nothing sent is state unknown', () {
      expect(SpecimenStatus.ofRecord(), SpecimenStatus.unknown);
    });

    // An unmapped value is shown, not swallowed: a disposition the client
    // cannot name is never hidden behind the run state.
    test('an unrecognised disposition is state unknown, not the run', () {
      expect(
        SpecimenStatus.ofRecord(disposition: 'escalated', state: 'running'),
        SpecimenStatus.unknown,
      );
      expect(
        SpecimenStatus.ofRecord(disposition: 'running', state: 'running'),
        SpecimenStatus.unknown,
        reason: 'a run state is not a queue, even in the disposition slot',
      );
    });

    test('a blank disposition is no disposition', () {
      expect(
        SpecimenStatus.ofRecord(disposition: '  ', state: 'running'),
        SpecimenStatus.processing,
      );
    });
  });

  group('words', () {
    test('every label fits the chip budget of 2 to 20 characters', () {
      for (final SpecimenStatus status in SpecimenStatus.values) {
        expect(
          status.label.length,
          inInclusiveRange(2, 20),
          reason: '${status.name} label "${status.label}"',
        );
      }
    });

    test('every label is sentence case with no terminal period', () {
      for (final SpecimenStatus status in SpecimenStatus.values) {
        expect(status.label, isNot(endsWith('.')));
        expect(status.label, isNot(equals(status.label.toUpperCase())));
      }
    });

    test('the semantics phrase names the vocabulary it came from', () {
      expect(SpecimenStatus.cleared.semanticsLabel, 'Queue: cleared');
      expect(SpecimenStatus.unknownValue.semanticsLabel, 'Field: unknown');
      expect(SpecimenStatus.unknown.semanticsLabel, 'Queue: state unknown');
    });

    // PRD 10.1: the operational states are "not final data-quality queues",
    // so a screen reader hears them as the run's state.
    test('an operational state is heard as the run, never a queue', () {
      expect(SpecimenStatus.processing.semanticsLabel, 'Run: processing');
      expect(SpecimenStatus.blocked.semanticsLabel, 'Run: processing blocked');
      expect(
        SpecimenStatus.retryScheduled.semanticsLabel,
        'Run: retry scheduled',
      );
      expect(SpecimenStatus.paused.semanticsLabel, 'Run: paused');
      expect(SpecimenStatus.cancelled.semanticsLabel, 'Run: cancelled');
    });

    test('every semantics phrase is 100 characters or fewer', () {
      for (final SpecimenStatus status in SpecimenStatus.values) {
        expect(status.semanticsLabel.length, lessThanOrEqualTo(100));
      }
    });
  });

  testWidgets('every status resolves a full presentation in both themes', (
    WidgetTester tester,
  ) async {
    for (final MapEntry<String, ThemeData> entry in productThemes.entries) {
      for (final SpecimenStatus status in SpecimenStatus.values) {
        late StatusPresentation seen;
        await pumpComponent(
          tester,
          Builder(
            builder: (BuildContext context) {
              seen = status.presentation(context);
              return const SizedBox.shrink();
            },
          ),
          theme: entry.value,
        );
        expect(seen.label, status.label, reason: entry.key);
        expect(seen.icon, status.icon, reason: entry.key);
        expect(seen.semanticsLabel, status.semanticsLabel);
        expect(seen.content, isNot(seen.fill), reason: 'no invisible chip');
      }
    }
  });
}
