// The typed thread, part one (UI.md T2.1): the envelope, the regions, the
// readings and their comparison, read from the thread response S5 serves
// (docs/execution/golive/DATA_CONTRACT.md section 8).
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

    test('malformed values are absent, never coerced', () {
      final SpecimenThread thread = SpecimenThread.fromJson(<String, dynamic>{
        'specimen_id': 'odd',
        'revision': '7',
        'image': <String, dynamic>{'asset_id': 'a', 'width': 'wide'},
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
      expect(thread.regions.single.comparisons.single.ratio, isNull);
      expect(thread.regions.single.comparisons.single.editDistance, isNull);
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
}
