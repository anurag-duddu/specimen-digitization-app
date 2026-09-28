// The harness's calls on one label's text, as a timeline (UI.md T2.7).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/harness_lookups.dart';
import 'package:specimen_digitization/src/thread/thread.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'harness.dart';

/// One call as the thread sends it.
ThreadToolCall call({
  required String phase,
  required String tool,
  String? source,
  required String outcome,
  String input = 'raw_reading',
  String? reading,
  int attempt = 1,
  List<String> fields = const <String>[],
  List<String>? placeIds,
}) => ThreadToolCall.fromJson(<String, dynamic>{
  'phase': phase,
  'tool': tool,
  'source': source,
  'outcome': outcome,
  'input_source': input,
  'region_id': 'region-2',
  'observation_id': reading,
  'attempt': attempt,
  'field_keys': fields,
  'result': placeIds == null
      ? <String, dynamic>{}
      : <String, dynamic>{'place_ids': placeIds},
});

const Map<String, String> readers = <String, String>{
  'obs-a': 'Reader A',
  'obs-b': 'Reader B',
};

const Map<String, String> names = <String, String>{
  'city': 'City',
  'county': 'County',
  'country': 'Country',
  'fmnh_ins_number': 'FMNH number',
  'verbatim_dts': 'Verbatim date',
};

Future<void> pumpLookups(WidgetTester tester, List<ThreadToolCall> calls) =>
    pumpComponent(
      tester,
      SingleChildScrollView(
        child: HarnessLookups(
          calls: calls,
          readerName: (String? id) => readers[id] ?? 'A reader',
          fieldName: (String key) => names[key] ?? key,
        ),
      ),
      size: const Size(900, 1400),
    );

void main() {
  testWidgets('each call is one entry: what ran, how it ended, on what', (
    WidgetTester tester,
  ) async {
    await pumpLookups(tester, <ThreadToolCall>[
      call(
        phase: 'validate',
        tool: 'catalog_number_validator',
        outcome: 'success',
        input: 'decided_transcript',
        fields: <String>['fmnh_ins_number'],
      ),
      call(
        phase: 'validate',
        tool: 'date_parser',
        outcome: 'success',
        reading: 'obs-a',
        fields: <String>['verbatim_dts'],
      ),
      call(
        phase: 'lookup',
        tool: 'geography_lookup',
        source: 'google-maps-geocoding',
        outcome: 'ambiguous',
        reading: 'obs-b',
        fields: <String>['city', 'county', 'country'],
        placeIds: <String>[],
      ),
      call(
        phase: 'lookup',
        tool: 'geocode',
        source: 'google-maps-geocoding',
        outcome: 'success',
        input: 'decided_transcript',
        attempt: 2,
        fields: <String>['city'],
        placeIds: <String>['place-1'],
      ),
    ]);

    expect(tester.takeException(), isNull);
    expect(find.byType(UiTimeline), findsOneWidget);
    for (final String text in <String>[
      HarnessLookups.title,
      // US spelling, the coordinator's ruling at 20:05Z on 2026-09-28.
      'Catalog number check',
      'Decided transcript · For FMNH number',
      'Date parse',
      "Reader A's reading · For Verbatim date",
      'Google Maps lookup',
      'Several places match',
      "Reader B's reading · For City, County and Country",
      'Found',
      // G26: a found Google place is its place ID, never a name.
      'Decided transcript · Attempt 2 · For City · place ID place-1',
    ]) {
      expect(find.text(text), findsWidgets, reason: text);
    }
    // A check that found its answer reads as a lookup that found its record.
    expect(find.text('Found'), findsNWidgets(3));
    expect(find.text('Passed'), findsNothing);
    expect(find.textContaining('geography_lookup'), findsNothing);
    expect(find.textContaining('catalog_number_validator'), findsNothing);
  });

  testWidgets('an operational failure and an unknown tool keep their meaning', (
    WidgetTester tester,
  ) async {
    await pumpLookups(tester, <ThreadToolCall>[
      call(
        phase: 'lookup',
        tool: 'gbif',
        source: 'gbif',
        outcome: 'rate_limited',
        reading: 'obs-a',
      ),
      call(
        phase: 'validate',
        tool: 'new_checker',
        outcome: 'strange_state',
        reading: 'obs-b',
      ),
      call(
        phase: 'lookup',
        tool: 'gbif',
        source: 'gbif',
        outcome: 'ambiguous',
        reading: 'obs-b',
      ),
      call(
        phase: 'lookup',
        tool: 'gbif',
        source: 'gbif',
        outcome: 'empty_response',
        reading: 'obs-a',
      ),
    ]);

    expect(tester.takeException(), isNull);
    expect(find.text('GBIF lookup'), findsNWidgets(3));
    expect(find.text('Could not complete'), findsOneWidget);
    expect(find.text('New checker'), findsOneWidget);
    expect(find.text('Strange state'), findsOneWidget);
    // "Places" is Google's answer; another source's ambiguous answer, and an
    // empty one, keep the server's word.
    expect(find.text('Several places match'), findsNothing);
    expect(find.text('Ambiguous'), findsOneWidget);
    expect(find.text('Empty response'), findsOneWidget);
  });

  testWidgets('a label with no calls draws nothing', (
    WidgetTester tester,
  ) async {
    await pumpLookups(tester, const <ThreadToolCall>[]);
    expect(find.text(HarnessLookups.title), findsNothing);
    expect(find.byType(UiTimeline), findsNothing);
  });
}
