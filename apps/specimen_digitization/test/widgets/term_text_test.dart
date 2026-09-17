// Pass criterion 10.2: every domain term has a one-sentence definition
// reachable from where it appears.
//
// The glossary was already complete and on the help sheet. What was missing
// was the second half of the criterion, "from where it appears", so these
// tests are about the affordance and about the five components the term is
// drawn in.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/glossary.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'harness.dart';

Finder termNamed(String term) => find.byWidgetPredicate(
  (Widget widget) => widget is TermText && widget.term == term,
);

void main() {
  group('the glossary itself', () {
    test('every entry is one sentence, in plain words', () {
      expect(glossary, isNotEmpty);
      for (final MapEntry<String, String> entry in glossary.entries) {
        expect(
          entry.key,
          entry.key.toLowerCase(),
          reason:
              'glossary keys are the word, lower case, so a lookup from '
              'a screen cannot miss on capitalisation',
        );
        expect(entry.value.endsWith('.'), isTrue, reason: entry.key);
        expect(
          entry.value.substring(0, entry.value.length - 1),
          isNot(contains('.')),
          reason: '${entry.key} is more than one sentence',
        );
        expect(entry.value, isNot(contains('—')), reason: entry.key);
        expect(entry.value, isNot(contains('–')), reason: entry.key);
      }
    });

    test('a lookup ignores case and a trailing measurement', () {
      expect(glossaryDefinition('Cleared'), glossary['cleared']);
      expect(glossaryDefinition('Risk 62 of 100'), glossary['risk']);
      expect(glossaryDefinition('Specimen identifier 4471'), isNull);
    });

    test('a word that is not a domain term has no definition', () {
      expect(isGlossaryTerm('Chicago'), isFalse);
      expect(glossaryDefinition(''), isNull);
    });
  });

  group('TermText', () {
    testWidgets('announces itself in the phrase the criterion names', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(tester, const TermText('Standardized'));
      expect(
        find.bySemanticsLabel('Standardized, term, double tap for definition'),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('speaks the value beside the term, not only the term', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(tester, const TermText('Version', trailing: ' 17'));
      expect(
        find.bySemanticsLabel('Version 17, term, double tap for definition'),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('a tap opens the definition, and it closes again', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, const TermText('Deferred'));
      await tester.tap(find.byType(TermText));
      await tester.pumpAndSettle();
      expect(find.text(glossary['deferred']!), findsOneWidget);
      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();
      expect(find.text(glossary['deferred']!), findsNothing);
    });

    testWidgets('the term is underlined and the value beside it is not', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, const TermText('Version', trailing: ' 17'));
      final RichText rich = tester.widget<RichText>(
        find.descendant(
          of: find.byType(TermText),
          matching: find.byType(RichText),
        ),
      );
      final List<TextSpan> spans = <TextSpan>[];
      rich.text.visitChildren((InlineSpan span) {
        if (span is TextSpan && span.text != null) spans.add(span);
        return true;
      });
      expect(spans, hasLength(2));
      expect(spans.first.text, 'Version');
      expect(spans.first.style?.decoration, TextDecoration.underline);
      expect(spans.first.style?.decorationStyle, TextDecorationStyle.dotted);
      expect(spans.last.text, ' 17');
      expect(spans.last.style?.decoration, isNot(TextDecoration.underline));
    });

    testWidgets('a word with no definition is plain text and no affordance', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(tester, const TermText('Chicago'));
      expect(find.text('Chicago'), findsOneWidget);
      expect(find.byType(GestureDetector), findsNothing);
      expect(
        find.bySemanticsLabel(RegExp('double tap for definition')),
        findsNothing,
      );
      handle.dispose();
    });
  });

  group('the components the terms are drawn in', () {
    testWidgets('a status chip is its own definition affordance', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(tester, const StatusChip(SpecimenStatus.needsReview));
      expect(find.byType(TermAffordance), findsOneWidget);
      // The vocabulary prefix criterion 4.16 asks for survives.
      expect(
        find.bySemanticsLabel(
          'Queue: needs review, term, double tap for definition',
        ),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('a field row names its three layers as terms', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const FieldRow(
          name: 'Country',
          state: SpecimenStatus.supported,
          asWritten: 'U.S.A.',
          readAs: 'United States',
        ),
      );
      expect(termNamed('As written'), findsOneWidget);
      expect(termNamed('Read as'), findsOneWidget);
      expect(termNamed('Standardized'), findsOneWidget);
    });

    testWidgets('a field row still says what its layers hold', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(
        tester,
        const FieldRow(
          name: 'Country',
          state: SpecimenStatus.supported,
          required: true,
          asWritten: 'U.S.A.',
          readAs: 'United States',
        ),
      );
      // A node with an action of its own is not merged into its parent, so
      // the row states its own content rather than relying on the merge.
      expect(
        find.bySemanticsLabel(RegExp('^Country, required')),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(RegExp('As written: U.S.A')),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(RegExp('Read as: United States')),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(RegExp('Standardized: Supported')),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('the risk meter opens the definition of Risk', (
      WidgetTester tester,
    ) async {
      // The one line form, which is where a reviewer first meets the word:
      // the workbench's form draws the label on a `UiDataTile`, and the tile
      // takes its label as a string rather than as a slot, so the definition
      // affordance cannot ride on it (recorded in the slot closeout).
      await pumpComponent(
        tester,
        RiskMeter(
          composite: 62,
          components: const <String>['Two readings disagree'],
          compact: true,
        ),
      );
      expect(termNamed('Risk'), findsOneWidget);
      await tester.tap(termNamed('Risk'));
      await tester.pumpAndSettle();
      expect(find.text(glossary['risk']!), findsOneWidget);
    });

    testWidgets('a reading card names its region and its provider', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const ReadingCard(
          modelName: 'Reading A',
          provider: 'synthetic',
          literal: 'Chicago 1912',
          regionName: 'Label 1',
        ),
      );
      expect(termNamed('Region'), findsOneWidget);
      expect(termNamed('Provider'), findsOneWidget);
    });

    testWidgets('the status strip names Version, Run and Step', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        WorkbenchStatusStrip(
          specimen: Specimen(const <String, dynamic>{
            'specimen_id': 'a',
            'revision': 17,
            'disposition': 'needs_human_review',
            'active_run_id': 'run-1',
            'stage': 'finalized',
          }),
          blockers: const <ClearanceBlocker>[],
          pending: const <PendingFieldChange>[],
          canOperate: false,
          busy: false,
          onAction: (Json _) async {},
          onGoToBlocker: (ClearanceBlocker _) {},
          onReviewPending: () {},
        ),
      );
      expect(termNamed('Version'), findsOneWidget);
      expect(termNamed('Run'), findsOneWidget);
      expect(termNamed('Step'), findsOneWidget);
    });
  });
}
