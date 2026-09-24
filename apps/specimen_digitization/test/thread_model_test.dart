// The typed thread (UI.md T2.1), read from the thread response S5 serves
// (docs/execution/golive/DATA_CONTRACT.md section 8): part one's envelope,
// regions, readings and comparison, and part two's first pass, handoffs,
// harness calls, fields and queue decision.
//
// Two things matter more than the happy path: an absent part stays absent,
// never a value (an unmeasured ratio is null, a measured zero is zero), and
// a value the client does not know stays what the server said, never a
// guess.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/thread/thread.dart';

Json fixture() =>
    jsonDecode(
          File('test/fixtures/thread-two-label-slide.json').readAsStringSync(),
        )
        as Json;

void main() {
  group('the two-label fixture', () {
    final SpecimenThread thread = SpecimenThread.fromJson(fixture());

    test('names the specimen, the run and where it stands', () {
      expect(thread.specimenId, 'fixture-thread-001');
      expect(thread.revision, 7);
      expect(thread.run.runId, 'run-fixture-1');
      expect(thread.run.status, 'completed');
      expect(thread.run.stage, 'finalized');
      expect(thread.run.blocker, isNull);
      expect(thread.run.profileKey, 'zoology_insects_slides');
      expect(thread.run.profileVersion, '1.0.0');
    });

    test('carries the trace, the image and the segmentation provenance', () {
      expect(thread.trace.traceId, '11111111111111111111111111111112');
      expect(
        thread.trace.url,
        Uri.parse(
          'https://logfire.example.test/trace/11111111111111111111111111111112',
        ),
      );
      expect(thread.image?.width, 4000);
      expect(thread.image?.height, 3000);
      expect(thread.image?.pixelBasis, 'original_pixel_edges');
      expect(thread.segmentation?.modelRevision, 'sam3-fixture-revision');
      expect(thread.segmentation?.settings['concept_prompt'], 'label');
    });

    test('carries the automatic coverage check (G15)', () {
      final ThreadCoverageCheck? check = thread.coverageCheck;
      expect(check?.status, 'passed');
      expect(check?.checks.map((ThreadCheck c) => c.name), <String>[
        'region_count',
        'full_image',
      ]);
      expect(check?.checks.every((ThreadCheck c) => c.passed == true), isTrue);
      expect(check?.evidenceId, 'evidence-coverage-1');
    });

    test('holds two regions, in the order the labels were numbered', () {
      expect(thread.regions.map((ThreadRegion r) => r.regionId), <String>[
        'region-left',
        'region-right',
      ]);
      final ThreadRegion right = thread.regions[1];
      expect(right.ordinal, 1);
      expect(right.geometry?.x, 2480);
      expect(right.geometry?.width, 1360);
      expect(right.rotationQuarterTurns, 0);
    });

    test('names each reader: route, model, provider and prompt version', () {
      final ThreadReading reading = thread.regions[0].readings.first;
      expect(reading.observationId, 'obs-left-qwen');
      expect(reading.routeId, 'handwriting-qwen');
      expect(reading.model, 'Qwen/Qwen2.5-VL-72B-Instruct');
      expect(reading.provider, 'hf-inference-fixture');
      expect(reading.promptVersion, 'literal-transcription-v3');
      expect(reading.literalText, '12.v.1978 leg. R. Ortiz');
      expect(reading.unreadableSpans, isEmpty);
      expect(reading.rawResponse?.assetId, 'raw-left-qwen');
    });

    test('keeps a measured zero as zero, beside its components', () {
      final ThreadComparison same = thread.regions[0].comparisons.single;
      expect(same.ratio, 0.0);
      expect(same.editDistance, 0);
      expect(same.lengthBasis, 23);
      expect(same.calibration, 'uncalibrated review priority');
      final ThreadComparison differ = thread.regions[1].comparisons.single;
      expect(differ.ratio, closeTo(0.0303, 0.0001));
      expect(differ.editDistance, 1);
      expect(differ.status, 'disagreement');
    });

    test('records how each transcript was decided', () {
      final ThreadFirstPass identical = thread.regions[0].firstPass!;
      expect(identical.kind, ThreadDecisionKind.identicalReadings);
      expect(identical.rationale, isNull);
      expect(identical.modelCall, isNull);

      final ThreadFirstPass decided = thread.regions[1].firstPass!;
      expect(decided.kind, ThreadDecisionKind.firstPass);
      expect(decided.selectedObservationId, 'obs-right-muse');
      expect(decided.decidedText, 'GUATEMALA Zacapa Sa. de las Minas');
      expect(decided.unresolved, isFalse);
      expect(decided.rationale, startsWith('The fourth word reads las'));
      expect(decided.modelCall?.model, 'first-pass-fixture-model');
      expect(
        decided.modelCall?.promptVersion,
        'transcription-disagreement-adjudication-v1',
      );
      expect(decided.modelCall?.rawResponse?.assetId, 'raw-right-first-pass');
    });

    test('records what each reader handed to the harness', () {
      final List<ThreadHandoff> handoffs =
          thread.regions[1].firstPass!.handoffs;
      expect(
        handoffs.map((ThreadHandoff h) => (h.observationId, h.source)),
        <(String?, ThreadInputSource?)>[
          ('obs-right-muse', ThreadInputSource.decidedTranscript),
          ('obs-right-qwen', ThreadInputSource.rawReading),
        ],
      );
      expect(handoffs[1].handedText, 'GUATEMALA Zacapa Sa. de los Minas');
      expect(handoffs[1].note, startsWith('Kept for the raw check'));
    });

    test('lists the lookups in the order they ran, retries included', () {
      expect(thread.toolCalls.map((ThreadToolCall c) => c.callKey), <String>[
        'call-1',
        'call-2',
        'call-3',
        'call-4',
      ]);
      final ThreadToolCall timedOut = thread.toolCalls[1];
      expect(timedOut.source, 'google-maps-geocoding');
      expect(timedOut.fieldKeys, <String>[
        'country',
        'province_state',
        'county',
        'city',
      ]);
      expect(timedOut.attempt, 1);
      expect(timedOut.outcome, 'timeout');
      expect(timedOut.error, 'The service did not answer within 30 seconds.');
      expect(timedOut.retryAfter, '2026-09-23T14:31:45Z');
      expect(thread.toolCalls[2].attempt, 2);
      final ThreadToolCall onRaw = thread.toolCalls[3];
      expect(onRaw.inputSource, ThreadInputSource.rawReading);
      expect(onRaw.observationId, 'obs-left-muse');
      expect(onRaw.outcome, 'no_match');
    });

    test('groups the fields as the profile does (G16)', () {
      expect(
        thread.mandatoryFields.map((ThreadField f) => f.fieldKey),
        <String>[
          'country',
          'province_state',
          'collectors',
          'date_visited_from',
          'habitat',
        ],
      );
      expect(thread.optionalFields.map((ThreadField f) => f.fieldKey), <String>[
        'identified_by_irn',
      ]);
      expect(thread.ungroupedFields, isEmpty);
      final ThreadField country = thread.mandatoryFields.first;
      expect(country.state, 'supported');
      final ThreadVerbatim written = country.verbatim.single;
      expect(written.text, 'GUATEMALA');
      expect(written.inputSource, ThreadInputSource.decidedTranscript);
      expect(written.regionId, 'region-right');
      expect(written.observationId, isNull);
      expect(country.parsed, 'Guatemala');
      expect(country.normalized, isNull, reason: 'G26: no Google names');
      expect(country.authorityId, 'fixture-place-id-zacapa');
      final ThreadEvidence geo = country.evidence.single;
      expect(geo.evidenceId, 'evidence-geo-1');
      expect(geo.relation, 'supports');
      expect(geo.source, 'google-maps-geocoding');
      expect(geo.locator, 'place/fixture-place-id-zacapa');
      expect(geo.outcome, 'success');
    });

    test('carries the queue decision and its reasons', () {
      expect(thread.decision?.disposition, 'needs_human_review');
      expect(thread.decision?.policyVersion, 'slide-pilot-policy-1');
      expect(thread.decision?.reasonCodes, <String>[
        'mandatory_field_not_supported',
      ]);
      expect(thread.decision?.summary, contains('habitat'));
      final ThreadFinding finding = thread.decision!.findings.single;
      expect(finding.ruleId, 'mandatory-fields-supported');
      expect(finding.severity, 'hard');
      expect(finding.fieldKey, 'habitat');
      expect(finding.reasonCode, 'mandatory_field_not_supported');
    });

    test('finds a reading and a region by id', () {
      expect(
        thread.readingOf('obs-right-muse')?.literalText,
        'GUATEMALA Zacapa Sa. de las Minas',
      );
      expect(thread.readingOf('obs-missing'), isNull);
      expect(thread.readingOf(null), isNull);
      expect(thread.regionOf('region-left')?.ordinal, 0);
    });
  });

  group('absence stays absence', () {
    test('an unmeasured ratio is null, never zero', () {
      final ThreadComparison comparison = ThreadComparison.fromJson(
        <String, dynamic>{
          'algorithm': 'bounded-levenshtein-fraction-v1',
          'ratio': null,
          'status': 'policy_blocked',
          'reasons': <String>['pilot_risk_unmeasured'],
        },
      );
      expect(comparison.ratio, isNull);
      expect(comparison.editDistance, isNull);
      expect(comparison.lengthBasis, isNull);
      expect(comparison.reasons, <String>['pilot_risk_unmeasured']);
    });

    test('a response with nothing in it is a thread with nothing in it', () {
      final SpecimenThread thread = SpecimenThread.fromJson(<String, dynamic>{
        'specimen_id': 'bare',
      });
      expect(thread.specimenId, 'bare');
      expect(thread.revision, isNull);
      expect(thread.run.status, isNull);
      expect(thread.trace.traceId, isNull);
      expect(thread.trace.url, isNull);
      expect(thread.image, isNull);
      expect(thread.segmentation, isNull);
      expect(thread.coverageCheck, isNull);
      expect(thread.regions, isEmpty);
      expect(thread.toolCalls, isEmpty);
      expect(thread.fields, isEmpty);
      expect(thread.decision, isNull);
    });

    test('a reading is kept verbatim, an empty one included', () {
      final ThreadReading empty = ThreadReading.fromJson(<String, dynamic>{
        'observation_id': 'o1',
        'literal_text': '',
      });
      expect(empty.literalText, '');
      final ThreadReading spaced = ThreadReading.fromJson(<String, dynamic>{
        'observation_id': 'o2',
        'literal_text': ' Chicago  1912 ',
      });
      expect(spaced.literalText, ' Chicago  1912 ');
      expect(
        ThreadReading.fromJson(<String, dynamic>{
          'observation_id': 'o3',
        }).literalText,
        isNull,
      );
    });

    test('a region with no recorded decision has no first pass', () {
      final ThreadRegion region = ThreadRegion.fromJson(<String, dynamic>{
        'region_id': 'r1',
        'ordinal': 0,
        'first_pass': null,
      });
      expect(region.firstPass, isNull);
      expect(region.geometry, isNull);
    });

    test('malformed values are absent, never coerced', () {
      final SpecimenThread thread = SpecimenThread.fromJson(<String, dynamic>{
        'specimen_id': 'odd',
        'revision': '7',
        'image': <String, dynamic>{'asset_id': 'a', 'width': 'wide'},
        'tool_calls': <Json>[
          <String, dynamic>{
            'call_key': 'c',
            'attempt': 1.5,
            'field_keys': <Object?>['country', 7, null],
          },
        ],
        'regions': <Json>[
          <String, dynamic>{
            'region_id': 'r1',
            'comparisons': <Json>[
              <String, dynamic>{'ratio': 'NaN', 'edit_distance': '1'},
            ],
          },
        ],
      });
      expect(thread.revision, isNull);
      expect(thread.image?.width, isNull);
      expect(thread.toolCalls.single.attempt, isNull);
      expect(thread.toolCalls.single.fieldKeys, <String>['country']);
      expect(thread.regions.single.comparisons.single.ratio, isNull);
      expect(thread.regions.single.comparisons.single.editDistance, isNull);
    });
  });

  group('the unknown stays what the server said', () {
    test('an unknown decision kind keeps its word and has no kind', () {
      final ThreadFirstPass pass = ThreadFirstPass.fromJson(<String, dynamic>{
        'decision_kind': 'oracle',
      });
      expect(pass.kind, isNull);
      expect(pass.kindName, 'oracle');
    });

    test('an unknown input source keeps its word and has no source', () {
      final ThreadHandoff handoff = ThreadHandoff.fromJson(<String, dynamic>{
        'observation_id': 'o1',
        'role': 'rumour',
      });
      expect(handoff.source, isNull);
      expect(handoff.roleName, 'rumour');
    });

    test('a field with no known group is kept apart from both groups', () {
      final SpecimenThread thread = SpecimenThread.fromJson(<String, dynamic>{
        'specimen_id': 's',
        'fields': <Json>[
          <String, dynamic>{'field_key': 'a', 'group': 'mandatory'},
          <String, dynamic>{'field_key': 'b'},
          <String, dynamic>{'field_key': 'c', 'group': 'sometimes'},
        ],
      });
      expect(
        thread.mandatoryFields.map((ThreadField f) => f.fieldKey),
        <String>['a'],
      );
      expect(thread.optionalFields, isEmpty);
      expect(
        thread.ungroupedFields.map((ThreadField f) => f.fieldKey),
        <String>['b', 'c'],
      );
      expect(thread.ungroupedFields.last.groupName, 'sometimes');
    });
  });

  // G27 and G28: a place or taxon field keeps what was written and what was
  // settled; when the first pass chose no reading, each reader's text is
  // kept, attributed to its reader.
  group('two values per field (G27, G28)', () {
    test('each reader keeps its own reading when none was chosen', () {
      final ThreadField field = ThreadField.fromJson(<String, dynamic>{
        'field_key': 'province_state',
        'verbatim': <Json>[
          <String, dynamic>{
            'text': 'Chimaltenago',
            'input_source': 'raw_reading',
            'region_id': 'r1',
            'observation_id': 'o-a',
          },
          <String, dynamic>{
            'text': 'Chimaltenango',
            'input_source': 'raw_reading',
            'region_id': 'r1',
            'observation_id': 'o-b',
          },
        ],
        'authority_id': 'fixture-place-id',
      });
      expect(field.verbatim.map((ThreadVerbatim v) => v.text), <String>[
        'Chimaltenago',
        'Chimaltenango',
      ]);
      expect(
        field.verbatim.map((ThreadVerbatim v) => v.observationId),
        <String>['o-a', 'o-b'],
      );
      expect(
        field.verbatim.every(
          (ThreadVerbatim v) => v.inputSource == ThreadInputSource.rawReading,
        ),
        isTrue,
      );
    });

    test('a written text is kept exactly, spaces and all', () {
      final ThreadField field = ThreadField.fromJson(<String, dynamic>{
        'field_key': 'taxon',
        'verbatim': <Json>[
          <String, dynamic>{'text': ' Tachinidae  sp.'},
        ],
      });
      expect(field.verbatim.single.text, ' Tachinidae  sp.');
    });

    test('evidence says whether a source decides, supports or contradicts', () {
      final ThreadField field = ThreadField.fromJson(<String, dynamic>{
        'field_key': 'taxon',
        'normalized': 'Tachinidae',
        'evidence': <Json>[
          <String, dynamic>{
            'evidence_id': 'e1',
            'relation': 'decides',
            'source': 'gbif',
          },
          <String, dynamic>{
            'evidence_id': 'e2',
            'relation': 'contradicts',
            'source': 'col',
          },
        ],
      });
      expect(
        field.normalized,
        'Tachinidae',
        reason: 'G28: GBIF names can be shown',
      );
      expect(field.evidence.map((ThreadEvidence e) => e.relation), <String>[
        'decides',
        'contradicts',
      ]);
    });
  });

  // G24, as S5 pins it for the thread: the parsed text stays a string and
  // the precision and the century rule are its siblings.
  group('dates (G24)', () {
    test('carry their precision and, for two digits, the century rule', () {
      final ThreadField field = ThreadField.fromJson(<String, dynamic>{
        'field_key': 'date_visited_from',
        'literal': '12.v.78',
        'parsed': '1978-05-12',
        'precision': 'day',
        'century_rule': 'date-rules-v1:two_digit_year_century=1900',
      });
      expect(field.parsed, '1978-05-12');
      expect(field.precision, 'day');
      expect(field.centuryRule, 'date-rules-v1:two_digit_year_century=1900');
    });

    test('a four-digit year has a precision and no century rule', () {
      final ThreadField field = SpecimenThread.fromJson(fixture())
          .mandatoryFields
          .firstWhere((ThreadField f) => f.fieldKey == 'date_visited_from');
      expect(field.precision, 'day');
      expect(field.centuryRule, isNull);
    });

    test('a non-date has neither', () {
      final ThreadField field = SpecimenThread.fromJson(
        fixture(),
      ).mandatoryFields.first;
      expect(field.precision, isNull);
      expect(field.centuryRule, isNull);
    });

    test('the stored object form is read too, never lost', () {
      final ThreadField field = ThreadField.fromJson(<String, dynamic>{
        'field_key': 'date_visited_from',
        'parsed': <String, dynamic>{
          'value': '1978-05',
          'precision': 'month',
          'century_rule': null,
        },
      });
      expect(field.parsed, '1978-05');
      expect(field.precision, 'month');
    });
  });

  group('regions', () {
    test('are ordered by their number, unnumbered last', () {
      final SpecimenThread thread = SpecimenThread.fromJson(<String, dynamic>{
        'specimen_id': 's',
        'regions': <Json>[
          <String, dynamic>{'region_id': 'none'},
          <String, dynamic>{'region_id': 'second', 'ordinal': 1},
          <String, dynamic>{'region_id': 'first', 'ordinal': 0},
        ],
      });
      expect(thread.regions.map((ThreadRegion r) => r.regionId), <String>[
        'first',
        'second',
        'none',
      ]);
    });
  });

  group('the trace link', () {
    ThreadTrace trace(Object? url) =>
        ThreadTrace.fromJson(<String, dynamic>{'trace_id': 't', 'url': url});

    test('is kept when it is an absolute https URL', () {
      expect(
        trace('https://logfire.example.test/t/1').url?.host,
        'logfire.example.test',
      );
    });

    test('is dropped for any other scheme or a relative path', () {
      for (final Object? url in <Object?>[
        'javascript:alert(1)',
        'http://logfire.example.test/t/1',
        '/trace/1',
        'https://',
        42,
        null,
      ]) {
        expect(trace(url).url, isNull, reason: '$url');
      }
    });
  });

  group('the readings that settled a value (G20, G32)', () {
    test('are listed in verbatim order', () {
      final ThreadField field = ThreadField.fromJson(<String, dynamic>{
        'field_key': 'country',
        'settled_observation_ids': <String>['obs-left-qwen', 'obs-right-muse'],
      });
      expect(field.settledObservationIds, <String>[
        'obs-left-qwen',
        'obs-right-muse',
      ]);
    });

    test('are none when absent or malformed, never a guess', () {
      expect(
        ThreadField.fromJson(<String, dynamic>{}).settledObservationIds,
        isEmpty,
      );
      expect(
        ThreadField.fromJson(<String, dynamic>{
          'settled_observation_ids': 'obs-left-qwen',
        }).settledObservationIds,
        isEmpty,
      );
    });
  });

  group("the program's model allowance (G30)", () {
    test('is read in micro-dollars from the run', () {
      final ThreadRun run = ThreadRun.fromJson(<String, dynamic>{
        'run_id': 'r',
        'blocker': 'program_allowance_exhausted',
        'allowance': <String, dynamic>{
          'allowance_micros': 5000000,
          'reserved_total_micros': 250000,
          'remaining_micros': 0,
          'at': '2026-09-23T14:40:00Z',
        },
      });
      expect(run.allowanceMicros, 5000000);
    });

    test('is absent when the run does not carry it, never zero', () {
      expect(ThreadRun.fromJson(<String, dynamic>{}).allowanceMicros, isNull);
      expect(
        ThreadRun.fromJson(<String, dynamic>{
          'allowance': <String, dynamic>{'allowance_micros': '5000000'},
        }).allowanceMicros,
        isNull,
        reason: 'a malformed value is absent, never coerced',
      );
    });
  });
}
