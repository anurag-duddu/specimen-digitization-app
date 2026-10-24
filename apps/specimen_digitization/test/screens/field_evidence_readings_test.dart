// Synthetic evidence shapes test presentation only. No repository or model IO.
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import 'field_review_test.dart' show expandField, showFields;

Specimen evidenceRecord({
  Map<String, String> readings = const {},
  List<Json> observations = const [],
  List<Json> summaries = const [],
  List<Json> regions = const [
    {'region_id': 'label-one'},
    {'region_id': 'label-two'},
  ],
  Map<String, String> inputSources = const {},
  List<String>? evidenceIds,
  String? sourceRegion,
  String literalValue = 'Unresolved place',
}) => Specimen({
  'specimen_id': 'synthetic-evidence-readings',
  'revision': 9,
  'regions': regions,
  'observations': observations,
  'evidence': summaries,
  'fields': [
    {
      'field_key': 'city',
      'display_name': 'City',
      'state': 'unresolved',
      'required': true,
      'literal_value': literalValue,
      'verbatim_by_observation': readings,
      'input_source_by_observation': inputSources,
      'evidence_ids':
          evidenceIds ??
          summaries.map((item) => item['evidence_id'] ?? item['id']).toList(),
      'source_region_id': ?sourceRegion,
      'source_observation_id': null,
    },
  ],
});

Finder readingBlock(String id) =>
    find.byKey(ValueKey('field-reading:city:$id'));

Finder sourceBlock(String id) => find.byKey(ValueKey('field-source:city:$id'));

Future<void> openEvidence(
  WidgetTester tester,
  Specimen record, {
  double scale = 1,
}) async {
  await showFields(
    tester,
    record: record,
    size: const Size(390, 844),
    textScale: scale,
    onPendingChanged: (_) => fail('Reading evidence must not edit the field'),
  );
  await expandField(tester, 'City');
}

Future<void> expectReachable(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  expect(finder.hitTestable(), findsOneWidget);
  expect(tester.takeException(), isNull);
}

void main() {
  for (final scale in [1.0, 2.0]) {
    for (var readingCount = 0; readingCount <= 2; readingCount++) {
      for (var summaryCount = 0; summaryCount <= 2; summaryCount++) {
        testWidgets(
          '$readingCount readings and $summaryCount summaries at 390 text $scale',
          (tester) async {
            final record = evidenceRecord(
              readings: {
                for (var i = 1; i <= readingCount; i++)
                  'observation-$i': 'Exact wording from reading $i',
              },
              observations: [
                for (var i = 1; i <= readingCount; i++)
                  {
                    'id': 'observation-$i',
                    'region_id': i == 1 ? 'label-one' : 'label-two',
                    'model_id': 'synthetic-model-$i',
                  },
              ],
              inputSources: {
                for (var i = 1; i <= readingCount; i++)
                  'observation-$i': 'raw_reading',
              },
              summaries: [
                for (var i = 1; i <= summaryCount; i++)
                  {
                    'evidence_id': 'evidence-$i',
                    'region_id': i == 1 ? 'label-one' : 'label-two',
                    'excerpt': 'Exact source summary $i',
                  },
              ],
            );
            final original = jsonDecode(jsonEncode(record.data));
            await openEvidence(tester, record, scale: scale);
            expect(
              find.text('Evidence for City'),
              readingCount + summaryCount == 0 ? findsNothing : findsOneWidget,
            );
            expect(
              uiDisclosure('Label readings'),
              readingCount > 1 ? findsOneWidget : findsNothing,
            );
            for (var i = 1; i <= readingCount; i++) {
              expect(
                find.text('Exact wording from reading $i'),
                readingCount == 1 ? findsOneWidget : findsNothing,
              );
            }
            final summariesDisclosed =
                summaryCount > 0 && (readingCount > 0 || summaryCount > 1);
            expect(
              uiDisclosure('Evidence details'),
              summariesDisclosed ? findsOneWidget : findsNothing,
            );
            if (summariesDisclosed) {
              expect(
                tester
                    .widget<UiDisclosure>(uiDisclosure('Evidence details'))
                    .summary,
                '$summaryCount source '
                '${summaryCount == 1 ? 'summary' : 'summaries'}',
              );
            }
            for (var i = 1; i <= summaryCount; i++) {
              expect(
                find.text('Exact source summary $i'),
                summariesDisclosed ? findsNothing : findsOneWidget,
              );
            }
            if (readingCount > 1) {
              expect(find.text('2 readings'), findsOneWidget);
              expect(
                tester
                    .widget<UiDisclosure>(uiDisclosure('Label readings'))
                    .semanticsLabel,
                'Label readings for City, 2 readings',
              );
              await expandField(tester, 'Label readings');
            }
            for (var i = 1; i <= readingCount; i++) {
              final block = readingBlock('observation-$i');
              expect(block, findsOneWidget);
              expect(
                find.descendant(
                  of: block,
                  matching: find.text('synthetic-model-$i'),
                ),
                findsOneWidget,
              );
              await expectReachable(
                tester,
                find.text('Exact wording from reading $i'),
              );
            }
            if (summariesDisclosed) {
              await expandField(tester, 'Evidence details');
            }
            for (var i = 1; i <= summaryCount; i++) {
              await expectReachable(
                tester,
                find.text('Exact source summary $i'),
              );
              if (summariesDisclosed) {
                expect(find.text('Label $i · Source summary'), findsOneWidget);
              }
            }
            if (readingCount > 1) {
              await expandField(tester, 'Label readings');
              expect(readingBlock('observation-1'), findsNothing);
              expect(readingBlock('observation-2'), findsNothing);
            }
            expect(record.data, original);
            expect(tester.takeException(), isNull);
            await tester.pumpWidget(const SizedBox.shrink());
          },
        );
      }
    }

    for (final wording in [
      ('equal', 'E. slope Mt. McKinley', 'E. slope Mt. McKinley'),
      ('near', 'E. slope Mt. McKinley', 'E.slope Mt. McKinley'),
      ('conflicting', 'Eastern slope', 'Western slope'),
    ]) {
      testWidgets('${wording.$1} wording retains both provenances at $scale', (
        tester,
      ) async {
        final semantics = tester.ensureSemantics();
        final record = evidenceRecord(
          readings: {'observation-a': wording.$2, 'observation-b': wording.$3},
          observations: [
            {
              'id': 'observation-a',
              'region_id': 'label-two',
              'model_id': 'same-model',
            },
            {
              'id': 'observation-b',
              'region_id': 'label-two',
              'model_id': 'same-model',
            },
          ],
        );
        final original = jsonDecode(jsonEncode(record.data));
        await openEvidence(tester, record, scale: scale);
        expect(find.text(wording.$2), findsNothing);
        expect(find.text(wording.$3), findsNothing);
        expect(find.text('2 readings'), findsOneWidget);
        await expandField(tester, 'Label readings');
        for (final item in [
          ('observation-a', wording.$2, 'Reading 1 · Label 2'),
          ('observation-b', wording.$3, 'Reading 2 · Label 2'),
        ]) {
          final block = readingBlock(item.$1);
          expect(
            find.descendant(of: block, matching: find.text(item.$3)),
            findsOneWidget,
          );
          expect(
            find.descendant(of: block, matching: find.text('same-model')),
            findsOneWidget,
          );
          final exact = find.descendant(
            of: block,
            matching: find.text(item.$2),
          );
          await expectReachable(tester, exact);
          expect(find.bySemanticsLabel(RegExp(item.$3)), findsOneWidget);
          expect(find.bySemanticsLabel(RegExp(item.$1)), findsNothing);
        }
        expect(record.data, original);
        expect(tester.takeException(), isNull);
        semantics.dispose();
      });
    }

    testWidgets(
      'literal retained excerpts without verbatim readings disclose exact readers at $scale',
      (tester) async {
        final semantics = tester.ensureSemantics();
        // Sanitized reproduction of the retained-source shape: both excerpts
        // refer to the same label, with separate exact observation references.
        final record = evidenceRecord(
          literalValue: 'Mt. McKinley',
          observations: [
            {
              'id': 'synthetic-observation-a',
              'region_id': 'label-two',
              'provider': 'synthetic-provider-a',
              'model_id': 'synthetic-reader-a',
              'route_id': 'synthetic-route-a',
              'reading_metadata': <String, Object?>{},
            },
            {
              'id': 'synthetic-observation-b',
              'region_id': 'label-two',
              'provider': 'synthetic-provider-b',
              'model_id': 'synthetic-reader-b',
              'route_id': 'synthetic-route-b',
              'reading_metadata': <String, Object?>{},
            },
          ],
          summaries: [
            {
              'evidence_id': 'synthetic-evidence-a',
              'kind': 'literal',
              'source': 'bounded_extraction_v1',
              'region_id': 'label-two',
              'observation_ids': ['synthetic-observation-a'],
              'excerpt': 'E. slope Mt. McKinley',
              'locator':
                  'reading:2A:synthetic-observation-a#quote=11-32;literal=20-32',
            },
            {
              'evidence_id': 'synthetic-evidence-b',
              'kind': 'literal',
              'source': 'bounded_extraction_v1',
              'region_id': 'label-two',
              'observation_ids': ['synthetic-observation-b'],
              'excerpt': 'E.slope Mt. McKinley',
              'locator':
                  'reading:2B:synthetic-observation-b#quote=11-32;literal=20-32',
            },
          ],
        );
        final original = jsonDecode(jsonEncode(record.data));
        await openEvidence(tester, record, scale: scale);
        expect(uiDisclosure('Label readings'), findsNothing);
        expect(find.text('E. slope Mt. McKinley'), findsNothing);
        expect(find.text('E.slope Mt. McKinley'), findsNothing);
        expect(find.text('Source reader: synthetic-reader-a'), findsNothing);
        expect(find.text('Source reader: synthetic-reader-b'), findsNothing);
        expect(find.text('2 source summaries'), findsOneWidget);
        await expandField(tester, 'Evidence details');
        for (final item in [
          ('a', 'E. slope Mt. McKinley'),
          ('b', 'E.slope Mt. McKinley'),
        ]) {
          final block = sourceBlock('synthetic-evidence-${item.$1}');
          expect(
            find.descendant(
              of: block,
              matching: find.text('Label 2 · Source summary'),
            ),
            findsOneWidget,
          );
          final reader = find.descendant(
            of: block,
            matching: find.text('Source reader: synthetic-reader-${item.$1}'),
          );
          await expectReachable(tester, reader);
          final excerpt = find.descendant(
            of: block,
            matching: find.text(item.$2),
          );
          await expectReachable(tester, excerpt);
          expect(
            find.bySemanticsLabel(RegExp('synthetic-observation-${item.$1}')),
            findsNothing,
          );
        }
        await expandField(tester, 'Evidence details');
        expect(find.text('E. slope Mt. McKinley'), findsNothing);
        expect(find.text('E.slope Mt. McKinley'), findsNothing);
        expect(record.data, original);
        expect(tester.takeException(), isNull);
        semantics.dispose();
      },
    );
  }

  testWidgets(
    'summary readers use only unambiguous explicit observation references',
    (tester) async {
      final record = evidenceRecord(
        observations: [
          {
            'id': 'current',
            'observation_id': 'legacy',
            'region_id': 'label-one',
            'model_id': 'Exact reader',
          },
          {
            'id': 'ambiguous',
            'region_id': 'label-two',
            'model_id': 'Do not borrow first',
          },
          {
            'id': 'other',
            'observation_id': 'ambiguous',
            'model_id': 'Do not borrow second',
          },
        ],
        summaries: [
          for (final id in ['legacy', 'missing', 'ambiguous', ''])
            {
              'evidence_id': 'evidence-$id',
              'region_id': 'label-one',
              'observation_ids': [id],
              'excerpt': 'Evidence with reference: $id',
              'locator': 'reading:1A:current',
            },
          {
            'evidence_id': 'no-reference',
            'region_id': 'label-one',
            'excerpt': 'Evidence without explicit observation references',
            'locator': 'reading:1A:current',
          },
        ],
        sourceRegion: 'label-one',
      );
      final original = jsonDecode(jsonEncode(record.data));
      await openEvidence(tester, record, scale: 2);
      await expandField(tester, 'Evidence details');
      await expectReachable(tester, find.text('Source reader: Exact reader'));
      for (final id in ['missing', 'ambiguous', '']) {
        final fallback = find.descendant(
          of: sourceBlock('evidence-$id'),
          matching: find.text('Source reader: Reader metadata unavailable'),
        );
        await expectReachable(tester, fallback);
      }
      expect(
        find.descendant(
          of: sourceBlock('no-reference'),
          matching: find.textContaining('Source reader'),
        ),
        findsNothing,
      );
      expect(find.textContaining('Do not borrow'), findsNothing);
      expect(record.data, original);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('multiple source observations retain separate reader metadata', (
    tester,
  ) async {
    final record = evidenceRecord(
      observations: [
        {'id': 'first', 'model_id': 'Same producer'},
        {'id': 'second', 'model_id': 'Same producer'},
      ],
      summaries: [
        {
          'evidence_id': 'first-summary',
          'excerpt': 'Retained summary with two independent observations',
          'observation_ids': ['first', 'second'],
        },
        {'evidence_id': 'second-summary', 'excerpt': 'Another source'},
      ],
    );
    final original = jsonDecode(jsonEncode(record.data));
    await openEvidence(tester, record, scale: 2);
    await expandField(tester, 'Evidence details');
    for (final ordinal in [1, 2]) {
      await expectReachable(
        tester,
        find.descendant(
          of: sourceBlock('first-summary'),
          matching: find.text('Source reader $ordinal: Same producer'),
        ),
      );
    }
    expect(record.data, original);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'exact legacy observation IDs and mixed input sources stay attributed',
    (tester) async {
      final record = evidenceRecord(
        readings: {
          'legacy-a': '  Decided wording remains exact.\n',
          'current-b': 'Raw wording remains exact.',
        },
        observations: [
          {
            'id': 'new-a',
            'observation_id': 'legacy-a',
            'region_id': 'label-one',
            'model_id': 'same-model',
            'route_id': 'route-a',
          },
          {
            'id': 'current-b',
            'region_id': 'label-two',
            'model_id': 'same-model',
            'route_id': 'route-b',
          },
        ],
        inputSources: {
          'legacy-a': 'decided_transcript',
          'current-b': 'raw_reading',
        },
      );
      await openEvidence(tester, record, scale: 2);
      await expandField(tester, 'Label readings');
      final decided = readingBlock('legacy-a');
      final raw = readingBlock('current-b');
      expect(
        find.descendant(
          of: decided,
          matching: find.text('Reading 1 · Label 1'),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(of: decided, matching: find.text('Decided transcript')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: decided,
          matching: find.text('Source reader: same-model · route-a'),
        ),
        findsOneWidget,
      );
      await expectReachable(
        tester,
        find.text('  Decided wording remains exact.\n'),
      );
      expect(
        find.descendant(of: raw, matching: find.text('Reading 2 · Label 2')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: raw, matching: find.text('Raw reading')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: raw, matching: find.text('same-model · route-b')),
        findsOneWidget,
      );
      await expectReachable(tester, find.text('Raw wording remains exact.'));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'missing and ambiguous observation metadata never borrow another source',
    (tester) async {
      final record = evidenceRecord(
        readings: {
          'missing': 'Missing metadata wording',
          'ambiguous': 'Ambiguous metadata wording',
          '': 'Blank observation identifier wording',
        },
        observations: [
          {
            'id': 'ambiguous',
            'region_id': 'label-one',
            'model_id': 'First reader',
          },
          {
            'id': 'other',
            'observation_id': 'ambiguous',
            'region_id': 'label-two',
            'model_id': 'Second reader',
          },
          {
            'id': '',
            'region_id': 'label-one',
            'model_id': 'Invalid observation reader',
          },
        ],
        sourceRegion: 'label-one',
      );
      await openEvidence(tester, record, scale: 2);
      await expandField(tester, 'Label readings');
      for (final id in ['missing', 'ambiguous', '']) {
        final block = readingBlock(id);
        expect(
          find.descendant(
            of: block,
            matching: find.text('Reader metadata unavailable'),
          ),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: block,
            matching: find.textContaining('Label not recorded'),
          ),
          findsOneWidget,
        );
        expect(
          find.descendant(of: block, matching: find.textContaining('Label 1')),
          findsNothing,
        );
        expect(
          find.descendant(of: block, matching: find.textContaining('Label 2')),
          findsNothing,
        );
      }
      expect(find.text('First reader'), findsNothing);
      expect(find.text('Second reader'), findsNothing);
      expect(find.text('Invalid observation reader'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  for (final region in [null, '', 'stale-label']) {
    testWidgets('unavailable region $region never invents a label', (
      tester,
    ) async {
      final record = evidenceRecord(
        readings: {'observation': 'Exact retained wording'},
        observations: [
          {'id': 'observation', 'region_id': region},
        ],
        regions: [
          {'region_id': null},
          {'region_id': ''},
          {'region_id': 'label-one'},
        ],
        sourceRegion: 'label-one',
      );
      await openEvidence(tester, record);
      final block = readingBlock('observation');
      expect(
        find.descendant(
          of: block,
          matching: find.text(
            region == 'stale-label'
                ? 'Label unavailable'
                : 'Label not recorded',
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(of: block, matching: find.text('Model not recorded')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: block, matching: find.textContaining('Label 1')),
        findsNothing,
      );
      expect(
        find.descendant(of: block, matching: find.textContaining('Label 2')),
        findsNothing,
      );
      expect(
        find.descendant(of: block, matching: find.textContaining('Label 3')),
        findsNothing,
      );
      expect(find.text('Exact retained wording'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets(
    'unmatched evidence references do not display uncited summaries',
    (tester) async {
      final record = evidenceRecord(
        summaries: [
          {'id': 'uncited', 'excerpt': 'Unrelated retained evidence'},
        ],
        evidenceIds: ['stale-reference'],
      );
      await openEvidence(tester, record);
      expect(find.text('Evidence for City'), findsNothing);
      expect(find.text('Unrelated retained evidence'), findsNothing);
      expect(uiDisclosure('Evidence details'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'equal summaries from distinct labels retain both source blocks',
    (tester) async {
      final record = evidenceRecord(
        summaries: [
          {
            'id': 'first',
            'region_id': 'label-one',
            'excerpt': 'Same source wording',
          },
          {
            'id': 'second',
            'region_id': 'label-two',
            'excerpt': 'Same source wording',
          },
        ],
      );
      final original = jsonDecode(jsonEncode(record.data));
      await openEvidence(tester, record, scale: 2);
      expect(find.text('Same source wording'), findsNothing);
      await expandField(tester, 'Evidence details');
      expect(find.text('Same source wording'), findsNWidgets(2));
      for (final label in [
        'Label 1 · Source summary',
        'Label 2 · Source summary',
      ]) {
        await expectReachable(tester, find.text(label));
      }
      expect(record.data, original);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('a lone structured source keeps its exact response available', (
    tester,
  ) async {
    const response =
        '{"label":"Retained candidate","source_id":"synthetic-source"}';
    final record = evidenceRecord(
      observations: [
        {'id': 'source-observation', 'model_id': 'Source producer'},
      ],
      summaries: [
        {
          'id': 'source',
          'region_id': 'label-one',
          'excerpt': response,
          'observation_ids': ['source-observation'],
        },
      ],
    );
    await openEvidence(tester, record, scale: 2);
    expect(uiDisclosure('Label readings'), findsNothing);
    expect(find.text(response), findsNothing);
    expect(find.text('1 source response'), findsOneWidget);
    await expandField(tester, 'Evidence details');
    expect(find.text('Label 1 · Source response'), findsOneWidget);
    await expectReachable(tester, find.text('Source reader: Source producer'));
    await expectReachable(tester, find.text(response));
    expect(tester.takeException(), isNull);
  });

  testWidgets('mixed source details count summaries and responses separately', (
    tester,
  ) async {
    const response = '{"label":"Structured candidate"}';
    final record = evidenceRecord(
      observations: [
        {'id': 'source-observation', 'model_id': 'Source producer'},
      ],
      summaries: [
        {
          'id': 'structured',
          'region_id': 'label-one',
          'excerpt': response,
          'observation_ids': ['source-observation'],
        },
        {
          'id': 'plain',
          'region_id': 'label-two',
          'excerpt': 'Plain source summary',
        },
      ],
    );
    final original = jsonDecode(jsonEncode(record.data));
    await openEvidence(tester, record, scale: 2);
    expect(find.text('2 source summaries · 1 source response'), findsOneWidget);
    await expandField(tester, 'Evidence details');
    expect(find.text('Label 1 · Source summary'), findsOneWidget);
    expect(find.text('Label 1 · Source response'), findsOneWidget);
    // Summary and response belong to one retained source; reader metadata is
    // presented once for that source without losing the exact raw response.
    expect(find.text('Source reader: Source producer'), findsOneWidget);
    await expectReachable(tester, find.text(response));
    await expectReachable(tester, find.text('Plain source summary'));
    expect(record.data, original);
    expect(tester.takeException(), isNull);
  });
}
