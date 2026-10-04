import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import 'research_fixture.dart';

/// The thread the server's own reader produced for four fields that wait for a
/// person (tests/research_harness/test_thread_review.py writes and checks it):
/// country with three GEOLocate possibilities, province_state with a GEOLocate
/// no_match, habitat the label lacks, collection_method waiting for a rule.
Map<String, dynamic> unresolvedJson() => researchFixture('unresolved-thread');

ResearchScope unresolvedScope(Map<String, dynamic> json) =>
    ResearchScope.fromJson(json['scope']);

ResearchThread unresolvedThread([Map<String, dynamic>? json]) {
  final body = json ?? unresolvedJson();
  return ResearchThread.fromJson(body, expectedScope: unresolvedScope(body));
}

Map<String, dynamic> reviewOf(Map<String, dynamic> json, String key) =>
    fixtureField(json, key)['review'] as Map<String, dynamic>;

ResearchThreadCard cardFor(
  ResearchThread thread,
  String key, {
  String label = 'Field',
}) => ResearchThreadCard(
  scope: thread.scope,
  recordRevision: 100,
  fieldKey: key,
  fieldLabel: label,
  field: thread.field(key),
  networkState: ResearchNetworkState.ready,
  onRefresh: () {},
);

ResearchThreadCard unresolvedCard(Map<String, dynamic> json, String key) =>
    cardFor(unresolvedThread(json), key);

Future<void> pumpCard(
  WidgetTester tester,
  Widget card, {
  double width = 640,
  double scale = 1,
  bool dark = false,
  bool reducedMotion = true,
}) async {
  tester.view.physicalSize = Size(width, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: dark ? AppTheme.dark() : AppTheme.light(),
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: TextScaler.linear(scale),
            disableAnimations: reducedMotion,
          ),
          child: Scaffold(
            body: SingleChildScrollView(
              child: Padding(padding: const EdgeInsets.all(8), child: card),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

Future<void> openCard(WidgetTester tester) async {
  await tester.tap(find.text('Research'));
  await tester.pump();
}

/// The framework's accessibility guidelines over what is on screen.
///
/// Geometry and semantics run everywhere. The contrast guideline samples
/// rendered pixels, which Linux rasterises differently, so it runs where the
/// goldens are drawn (test/golden/golden_harness.dart, pixelInstrumentSkip);
/// the token contrast tests carry that proof on every platform.
Future<void> expectGuidelines(WidgetTester tester) async {
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  if (Platform.isMacOS && Platform.environment['SPECIMEN_GOLDENS'] != 'skip') {
    await expectLater(tester, meetsGuideline(textContrastGuideline));
  }
}
