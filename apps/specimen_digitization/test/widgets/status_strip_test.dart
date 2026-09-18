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
}
