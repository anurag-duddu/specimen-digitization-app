import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/readings_panel.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widgets/harness.dart';

Json _transcription(
  String region,
  List<String> alternatives, {
  bool resolved = false,
}) => <String, dynamic>{
  'region_id': region,
  'resolved': resolved,
  'text': resolved ? 'Accepted correction' : '',
  'alternatives': alternatives,
};

Specimen _record({
  List<Json> transcriptions = const <Json>[],
  List<Json> disagreements = const <Json>[],
  List<Json> observations = const <Json>[],
  List<Json> findings = const <Json>[],
  List<String> reasons = const <String>[],
}) => Specimen(<String, dynamic>{
  'specimen_id': 'synthetic-recovery-comparison',
  'revision': 1,
  'regions': <Json>[
    <String, dynamic>{'region_id': 'r1'},
    <String, dynamic>{'region_id': 'r2'},
  ],
  'transcriptions': transcriptions,
  'disagreements': disagreements,
  'observations': observations,
  'validation_findings': findings,
  'reason_codes': reasons,
});

Future<void> _pumpReadings(WidgetTester tester, Specimen specimen) async {
  String? selected = 'r1';
  final RegionAnchors anchors = <String, GlobalKey>{
    'r1': GlobalKey(),
    'r2': GlobalKey(),
  };
  await pumpComponent(
    tester,
    StatefulBuilder(
      builder: (BuildContext context, StateSetter setState) =>
          SingleChildScrollView(
            child: WorkbenchReadings(
              specimen: specimen,
              anchors: anchors,
              selectedRegionId: selected,
              onSelectRegion: (String? value) =>
                  setState(() => selected = value),
              onChange: (_) async => fail('Viewing evidence must not save'),
              transcriptionBlockedReason: null,
              declarationsBlocked: true,
            ),
          ),
    ),
    size: const Size(1000, 1600),
    reduceMotion: true,
  );
}

Future<void> _openComparison(WidgetTester tester) async {
  final Finder disclosure = find.text(WorkbenchReadings.differencesHeading);
  await tester.ensureVisible(disclosure);
  await tester.tap(disclosure);
  await tester.pumpAndSettle();
}

Future<void> _selectSecondLabel(WidgetTester tester) async {
  final Finder selector = find.byWidgetPredicate(
    (Widget widget) =>
        widget is UiSelect<String> &&
        widget.semanticsLabel == 'Label to review',
  );
  await tester.ensureVisible(selector);
  await tester.tap(selector);
  await tester.pumpAndSettle();
  final Finder option = find.byWidgetPredicate(
    (Widget widget) => widget is UiListRow && widget.title == 'Label 2',
  );
  await tester.ensureVisible(option);
  await tester.tap(option);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('selected label has one comparison behind its disclosure', (
    WidgetTester tester,
  ) async {
    final Json first = _transcription('r1', <String>['Chicago', 'Chicago']);
    final Json second = _transcription('r2', <String>['Museum', 'MUSEUM']);
    await _pumpReadings(
      tester,
      _record(
        transcriptions: <Json>[first, second],
        disagreements: <Json>[
          // An older redundant entry must not contradict the transcription.
          _transcription('r1', <String>['Chicago', 'Stale alternative']),
          second,
        ],
      ),
    );
    expect(find.text('Label 1: unresolved'), findsNothing);
    await _openComparison(tester);
    expect(find.text('Label 1: unresolved'), findsOneWidget);
    expect(find.text('Label 1: the readings differ'), findsNothing);
    expect(find.text('Label 2: the readings differ'), findsNothing);
    expect(find.textContaining('Stale alternative'), findsNothing);

    await _selectSecondLabel(tester);
    await _openComparison(tester);
    expect(find.text('Label 2: the readings differ'), findsOneWidget);
    expect(find.text('Label 2: unresolved'), findsNothing);
    expect(find.text('Label 1: unresolved'), findsNothing);
    expect(find.text('Museum · MUSEUM'), findsOneWidget);
  });

  for (final List<String> alternatives in <List<String>>[
    <String>['Chicago', 'chicago'],
    <String>['Chicago 1912', 'Chicago  1912'],
    <String>['Chicago 1912', 'Chicago 1912 '],
  ]) {
    testWidgets('comparison preserves exact text ${alternatives.toString()}', (
      WidgetTester tester,
    ) async {
      await _pumpReadings(
        tester,
        _record(transcriptions: <Json>[_transcription('r1', alternatives)]),
      );
      await _openComparison(tester);
      expect(find.text('Label 1: the readings differ'), findsOneWidget);
      expect(find.text(alternatives.join(' · ')), findsOneWidget);
    });
  }

  for (final bool malformed in <bool>[false, true]) {
    testWidgets('regional fallback when alternatives are '
        '${malformed ? 'malformed' : 'missing'}', (WidgetTester tester) async {
      await _pumpReadings(
        tester,
        _record(
          transcriptions: <Json>[
            <String, dynamic>{
              'region_id': 'r1',
              'resolved': false,
              if (malformed) 'alternatives': 'not a list',
            },
          ],
          observations: <Json>[
            <String, dynamic>{
              'id': 'r1-a',
              'model_id': 'reader-a',
              'region_id': 'r1',
              'literal_text': 'Chicago',
            },
            <String, dynamic>{
              'id': 'r1-b',
              'model_id': 'reader-b',
              'region_id': 'r1',
              'verbatim_text': 'CHICAGO',
            },
            <String, dynamic>{
              'id': 'r2-a',
              'model_id': 'reader-a',
              'region_id': 'r2',
              'literal_text': 'Other label',
            },
          ],
        ),
      );
      await _openComparison(tester);
      expect(find.text('Label 1: the readings differ'), findsOneWidget);
      expect(find.text('Chicago · CHICAGO'), findsOneWidget);
      expect(find.textContaining('Other label'), findsNothing);
    });
  }

  testWidgets('resolved comparison keeps the original alternatives once', (
    WidgetTester tester,
  ) async {
    final Json resolved = _transcription('r1', <String>[
      'Chicago 1912',
      'Chicago 1917',
    ], resolved: true);
    await _pumpReadings(
      tester,
      _record(
        transcriptions: <Json>[resolved],
        disagreements: <Json>[resolved],
      ),
    );
    await _openComparison(tester);
    expect(find.text('Label 1: resolved'), findsOneWidget);
    expect(find.text('Label 1: the readings differ'), findsNothing);
    expect(
      find.descendant(
        of: find.byWidgetPredicate(
          (Widget widget) =>
              widget is UiDisclosure &&
              widget.title == WorkbenchReadings.differencesHeading,
        ),
        matching: find.text('Accepted correction'),
      ),
      findsOneWidget,
    );
    expect(
      find.text('Readings: Chicago 1912 · Chicago 1917', findRichText: true),
      findsOneWidget,
    );
  });

  for (final bool differ in <bool>[false, true]) {
    testWidgets('legacy comparison without a transcription: differ=$differ', (
      WidgetTester tester,
    ) async {
      await _pumpReadings(
        tester,
        _record(
          disagreements: <Json>[
            _transcription('r1', <String>[
              'Chicago',
              differ ? 'CHICAGO' : 'Chicago',
            ]),
          ],
        ),
      );
      await _openComparison(tester);
      expect(
        find.text('Label 1: ${differ ? 'the readings differ' : 'unresolved'}'),
        findsOneWidget,
      );
      expect(
        find.text('Label 1: ${differ ? 'unresolved' : 'the readings differ'}'),
        findsNothing,
      );
    });
  }

  test(
    'blockers count distinct texts and keep identical readings unresolved',
    () {
      final List<ClearanceBlocker> blockers = blockersFor(
        _record(
          transcriptions: <Json>[
            _transcription('r1', <String>['A', 'A', 'a', 'a ']),
            _transcription('r2', <String>['Same', 'Same']),
          ],
        ),
      );
      expect(blockers.map((ClearanceBlocker b) => b.message), <String>[
        'Three readings differ for Label 1',
        'Transcription not resolved for Label 2',
      ]);
      expect(blockers.map((ClearanceBlocker b) => b.regionId), <String>[
        'r1',
        'r2',
      ]);
    },
  );

  test(
    'blockers retain field findings without generic or repeated reasons',
    () {
      final List<ClearanceBlocker> blockers = blockersFor(
        _record(
          transcriptions: <Json>[
            _transcription('r1', <String>['A', 'B'], resolved: true),
          ],
          findings: <Json>[
            <String, dynamic>{
              'field_key': 'locality',
              'reason_code': 'source_conflict',
              'message': 'Locality needs review',
            },
            <String, dynamic>{
              'field_key': 'collector',
              'reason_code': 'source_conflict',
              'message': 'Collector needs review',
            },
          ],
          reasons: <String>[
            'source_conflict',
            'human_approval_required',
            'coverage_unconfirmed',
            'coverage_unconfirmed',
          ],
        ),
      );
      expect(blockers, hasLength(3));
      expect(blockers[0].fieldKey, 'locality');
      expect(blockers[1].fieldKey, 'collector');
      expect(blockers[2].fieldKey, isNull);
      expect(
        blockers.every((ClearanceBlocker b) => b.regionId == null),
        isTrue,
      );
    },
  );
}
