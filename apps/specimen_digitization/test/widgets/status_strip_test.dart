// The record's status strip (13 sections 3.2 and 4.1).
//
// Three facts from medium up, each a glossary term whose definition opens on
// the line it is read on (polish 3; pass criterion 10.2), and none on a
// phone, where the line holds the disposition and what blocks clearance and
// nothing else (13 section 4.1, the slot A2 amendment).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/glossary.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'harness.dart';

/// A tablet in portrait, the narrowest window that carries the provenance.
const Size medium = Size(768, 1024);

/// The phone 13 section 4.1 is written for.
const Size phone = Size(390, 844);

/// A record at version 17 whose current run has reached the transcribe step,
/// or one with no run at all.
Specimen record({bool inRun = true}) => Specimen(<String, dynamic>{
  'specimen_id': 'strip-001',
  'revision': 17,
  'disposition': 'needs_human_review',
  if (inRun) 'active_run_id': 'run-42',
  if (inRun) 'run': <String, dynamic>{'stage': 'transcribe'},
});

WorkbenchStatusStrip strip(Specimen specimen) => WorkbenchStatusStrip(
  specimen: specimen,
  blockers: const <ClearanceBlocker>[],
  pending: const <PendingFieldChange>[],
  onGoToBlocker: (ClearanceBlocker _) {},
);

/// The strip's provenance slots, in reading order.
///
/// The disposition chip is a `TermAffordance` and not a `TermText`, so this
/// finds the facts and nothing else.
List<TermText> factsOf(WidgetTester tester) => tester
    .widgetList<TermText>(
      find.descendant(
        of: find.byType(UiStatusStrip),
        matching: find.byType(TermText),
      ),
    )
    .toList();

void main() {
  testWidgets('from medium up the facts are glossary terms with their values', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, strip(record()), size: medium);
    final List<TermText> facts = factsOf(tester);
    expect(facts.map((TermText fact) => fact.term), <String>[
      WorkbenchStatusStrip.versionTerm,
      WorkbenchStatusStrip.runTerm,
      WorkbenchStatusStrip.stepTerm,
    ]);
    expect(facts.map((TermText fact) => fact.trailing), <String>[
      ' 17',
      ' run-42',
      ' transcribe',
    ]);
    for (final TermText fact in facts) {
      expect(
        isGlossaryTerm(fact.term),
        isTrue,
        reason: '${fact.term} promises a definition it does not have',
      );
    }
    // Spoken whole, value included, with the affordance every term in the
    // product announces, and each on a node of its own: a paragraph merges
    // an inline widget's semantics into its own unless the widget is a
    // boundary, which the strip makes each fact.
    final SemanticsHandle handle = tester.ensureSemantics();
    for (final String spoken in <String>[
      'Version 17',
      'Run run-42',
      'Step transcribe',
    ]) {
      expect(
        find.bySemanticsLabel(TermText.semanticsFor(spoken)),
        findsOneWidget,
        reason: '$spoken is not read as one term with its value',
      );
    }
    handle.dispose();
  });

  testWidgets('a record with no run states its version alone', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, strip(record(inRun: false)), size: medium);
    expect(factsOf(tester).map((TermText fact) => fact.term), <String>[
      WorkbenchStatusStrip.versionTerm,
    ]);
  });

  testWidgets('a phone states the disposition and the blockers, not the run', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, strip(record()), size: phone);
    expect(
      factsOf(tester),
      isEmpty,
      reason:
          '13 section 4.1: on a phone the run and the version leave the line '
          'rather than ellipsising a word to a letter',
    );
    expect(find.byType(StatusChip), findsOneWidget);
  });

  testWidgets('a fact scales with the text once, not twice', (
    WidgetTester tester,
  ) async {
    // The strip sets each fact as a placeholder in one paragraph, and a
    // paragraph scales a placeholder by the text scale itself, so a fact that
    // also read the scale drew at four times its size at 200 percent: the
    // record's goldens at 768 by 1024 carried "Version 17" over four lines of
    // display type. A fact at 200 percent is twice its height at default type
    // and no more.
    await pumpComponent(tester, strip(record()), size: medium);
    final Finder version = find.byWidgetPredicate(
      (Widget widget) =>
          widget is TermText && widget.term == WorkbenchStatusStrip.versionTerm,
    );
    final double atDefault = tester.getRect(version).height;

    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpComponent(tester, strip(record()), size: medium);
    final double atDouble = tester.getRect(version).height;
    expect(
      atDouble,
      closeTo(atDefault * 2, 2),
      reason:
          'the version fact is $atDouble dp tall at 200 percent against '
          '$atDefault at default type; it scales once with the paragraph',
    );
    // And it is still one line beside the chip, not a column of its own.
    expect(
      atDouble,
      lessThanOrEqualTo(tester.getRect(find.byType(StatusChip)).height + 1),
    );
  });

  testWidgets('a fact opens its definition on the line it is read on', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, strip(record()), size: medium);
    await tester.tap(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is TermText &&
            widget.term == WorkbenchStatusStrip.versionTerm,
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(glossaryDefinition(WorkbenchStatusStrip.versionTerm)!),
      findsOneWidget,
      reason: 'pass criterion 10.2: the definition is reachable from the term',
    );
  });

  // PLAN section 3, "Client": the strip read `operational_state`, which no
  // response carries, so every record without a disposition, the ten pilot
  // records among them, said "State unknown". The summary sends `status`.
  testWidgets('a record with no disposition shows the state the server sent', (
    WidgetTester tester,
  ) async {
    for (final (String wire, String word) in <(String, String)>[
      ('processing_blocked', 'Processing blocked'),
      ('running', 'Processing'),
      ('retry_scheduled', 'Retry scheduled'),
      ('paused', 'Paused'),
      ('cancelled', 'Cancelled'),
    ]) {
      await pumpComponent(
        tester,
        strip(
          Specimen(<String, dynamic>{
            'specimen_id': 'pilot-$wire',
            'revision': 2,
            'status': wire,
            'disposition': null,
          }),
        ),
        size: medium,
      );
      expect(find.text(word), findsOneWidget, reason: wire);
      expect(find.text('State unknown'), findsNothing, reason: wire);
    }
  });

  // CLAUDE.md: status changes are announced once. The strip shows the live
  // run state, so a move the poll brings is heard, in the chip's own words
  // and without the "Saved" that belongs to a decision.
  group('announcements', () {
    Specimen live(String status, {String? disposition}) =>
        Specimen(<String, dynamic>{
          'specimen_id': 'pilot-live',
          'revision': 3,
          'status': status,
          'disposition': disposition,
        });

    Widget announcing(Specimen specimen) => Builder(
      builder: (BuildContext context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(supportsAnnounce: true),
        child: strip(specimen),
      ),
    );

    List<String> heard(WidgetTester tester) => tester
        .takeAnnouncements()
        .map((CapturedAccessibilityAnnouncement a) => a.message)
        .toList();

    testWidgets('a run state change is announced once', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, announcing(live('running')), size: medium);
      expect(heard(tester), isEmpty, reason: 'opening a record is not news');
      await pumpComponent(
        tester,
        announcing(live('processing_blocked')),
        size: medium,
      );
      expect(heard(tester), <String>['Run: processing blocked']);
      await pumpComponent(
        tester,
        announcing(live('processing_blocked')),
        size: medium,
      );
      expect(heard(tester), isEmpty, reason: 'once, not on every poll');
    });

    testWidgets('a decision is announced as saved', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, announcing(live('running')), size: medium);
      heard(tester);
      await pumpComponent(
        tester,
        announcing(live('completed', disposition: 'needs_human_review')),
        size: medium,
      );
      expect(heard(tester), <String>['Saved. Queue: needs review']);
    });
  });
}
