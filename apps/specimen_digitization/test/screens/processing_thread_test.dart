// The Processing disclosure's run and trace (UI.md T2.5).

import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/thread/thread.dart';
import 'package:url_launcher/link.dart';

import '../ui_finders.dart';
import '../widgets/harness.dart';

Json fixtureJson() =>
    jsonDecode(
          File('test/fixtures/thread-two-label-slide.json').readAsStringSync(),
        )
        as Json;

const String traceId = '11111111111111111111111111111112';
const String traceUrl = 'https://logfire.example.test/trace/$traceId';

/// The record the workspace serves, with its run's [blocker].
Specimen record({String? blocker}) => Specimen(<String, dynamic>{
  'specimen_id': 'fixture-thread-001',
  'revision': 7,
  'run': <String, dynamic>{
    'run_id': 'run-fixture-1',
    'stage': 'finalized',
    'blocker': ?blocker,
  },
});

Future<void> pumpDetail(
  WidgetTester tester,
  Specimen specimen, {
  SpecimenThread? thread,
  ThreadGap? threadGap,
}) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: ProcessingDetail(
      specimen: specimen,
      thread: thread,
      threadGap: threadGap,
      canOperate: false,
      busy: false,
      onAction: (_) async {},
    ),
  ),
  size: const Size(900, 2000),
);

void main() {
  // A thread the record screen asked for and could not draw is said where
  // the run's provenance would be (UI.md T2.6).
  for (final (ThreadGap gap, String label, String why)
      in <(ThreadGap, String, String)>[
        (
          ThreadGap.tooLarge,
          "The run's details are too large to show.",
          "The server sends a run's details whole or not at all. The readings "
              'and fields shown come from the record.',
        ),
        (
          ThreadGap.unreadable,
          "The run's details could not be read.",
          'The readings and fields shown come from the record. The next '
              'refresh tries again.',
        ),
      ]) {
    testWidgets('a thread not drawn is said where the run would be '
        '(${gap.name})', (WidgetTester tester) async {
      await pumpDetail(tester, record(), threadGap: gap);

      expect(find.text(label), findsOneWidget);
      expect(find.text('Run'), findsNothing);

      await tester.tap(find.text('Why'));
      await tester.pumpAndSettle();

      expect(find.text(why), findsOneWidget);
    });
  }

  testWidgets('a call with no region is listed in Processing (UI.md T2.7)', (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    (json['tool_calls'] as List<dynamic>).add(<String, dynamic>{
      'phase': 'lookup',
      'tool': 'geography_lookup',
      'source': 'google-maps-geocoding',
      'outcome': 'no_match',
      'input_source': 'review',
      'region_id': null,
      'observation_id': null,
      'review_decision_id': 'decision-1',
      'attempt': 1,
      'field_keys': <String>['city'],
      'result': <String, dynamic>{'place_ids': <String>[]},
    });
    await pumpDetail(tester, record(), thread: SpecimenThread.fromJson(json));

    expect(find.text('Harness lookups'), findsOneWidget);
    expect(find.text('Google Maps lookup'), findsOneWidget);
    expect(find.text('No match'), findsOneWidget);
    expect(find.textContaining("Reviewer's text"), findsOneWidget);
  });

  testWidgets('a thread that has loaded says nothing of a gap', (
    WidgetTester tester,
  ) async {
    await pumpDetail(
      tester,
      record(),
      thread: SpecimenThread.fromJson(fixtureJson()),
      threadGap: ThreadGap.unreadable,
    );

    expect(find.text("The run's details could not be read."), findsNothing);
    expect(find.text('Run'), findsOneWidget);
  });

  testWidgets('the run, its profile and the policy are named', (
    WidgetTester tester,
  ) async {
    await pumpDetail(
      tester,
      record(),
      thread: SpecimenThread.fromJson(fixtureJson()),
    );
    for (final String text in <String>[
      'Run',
      'run-fixture-1',
      'Profile',
      'zoology insects slides 1.0.0',
      'Policy',
      'slide-pilot-policy-1',
    ]) {
      expect(find.text(text), findsOneWidget);
    }
  });

  testWidgets("'Open trace' links to the run's trace", (
    WidgetTester tester,
  ) async {
    await pumpDetail(
      tester,
      record(),
      thread: SpecimenThread.fromJson(fixtureJson()),
    );
    final Link link = tester.widget<Link>(find.byType(Link));
    expect(link.uri, Uri.parse(traceUrl));
    expect(link.target, LinkTarget.blank);
    expect(
      find.descendant(of: find.byType(Link), matching: find.text('Open trace')),
      findsOneWidget,
    );
  });

  testWidgets('the trace id is named and can be copied', (
    WidgetTester tester,
  ) async {
    final List<MethodCall> calls = <MethodCall>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (MethodCall call) async {
        if (call.method == 'Clipboard.setData') calls.add(call);
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
    await pumpDetail(
      tester,
      record(),
      thread: SpecimenThread.fromJson(fixtureJson()),
    );
    expect(find.text(traceId), findsOneWidget);
    await tester.tap(uiIconButton('Copy the trace ID'));
    await tester.pumpAndSettle();
    expect(calls, hasLength(1));
    expect((calls.single.arguments as Map<Object?, Object?>)['text'], traceId);
  });

  testWidgets('a trace id without an address is still named', (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    (json['trace'] as Json)['url'] = 'http://logfire.example.test/insecure';
    await pumpDetail(tester, record(), thread: SpecimenThread.fromJson(json));
    expect(find.byType(Link), findsNothing, reason: 'only https opens');
    expect(find.text(traceId), findsOneWidget);
  });

  testWidgets('a run with no trace says so', (WidgetTester tester) async {
    final Json json = fixtureJson()..['trace'] = null;
    await pumpDetail(tester, record(), thread: SpecimenThread.fromJson(json));
    expect(find.text('No trace recorded'), findsOneWidget);
    expect(find.byType(Link), findsNothing);
  });

  testWidgets('a spent allowance says so, with the amount the thread holds', (
    WidgetTester tester,
  ) async {
    final Json json = fixtureJson();
    (json['run'] as Json)
      ..['status'] = 'processing_blocked'
      ..['blocker'] = 'program_allowance_exhausted'
      ..['allowance'] = <String, dynamic>{
        'allowance_micros': 5000000,
        'reserved_total_micros': 0,
        'remaining_micros': 0,
        'at': '2026-09-23T14:40:00Z',
      };
    await pumpDetail(
      tester,
      record(blocker: 'program_allowance_exhausted'),
      thread: SpecimenThread.fromJson(json),
    );
    expect(
      find.text(
        'The USD 5.00 model allowance for this program is spent. '
        'Processing resumes when the owner raises it.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('without the thread the allowance sentence names no amount', (
    WidgetTester tester,
  ) async {
    await pumpDetail(tester, record(blocker: 'program_allowance_exhausted'));
    expect(
      find.text(
        'The model allowance for this program is spent. '
        'Processing resumes when the owner raises it.',
      ),
      findsOneWidget,
    );
    expect(find.textContaining('USD'), findsNothing);
  });

  testWidgets('without a thread nothing is said of a trace', (
    WidgetTester tester,
  ) async {
    await pumpDetail(tester, record());
    expect(find.byType(Link), findsNothing);
    expect(find.text('No trace recorded'), findsNothing);
    expect(find.text('Policy'), findsNothing);
  });

  testWidgets('a sensitive record says it is not processed (UI.md T3.1)', (
    WidgetTester tester,
  ) async {
    await pumpDetail(tester, record(blocker: 'sensitive_record_not_processed'));
    expect(
      find.text('Blocked: sensitive record not processed'),
      findsOneWidget,
    );
    expect(
      find.text(
        'This record was uploaded as sensitive, so it is not processed. To '
        'have it processed, upload the photograph again as not sensitive.',
      ),
      findsOneWidget,
    );
    expect(find.textContaining('wait'), findsNothing);
  });
}
