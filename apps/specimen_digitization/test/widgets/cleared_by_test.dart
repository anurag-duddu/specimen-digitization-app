// Who cleared a record: a person's approval or the system's clearance, shown
// as two things on the chip, the queue row, the Cleared view and the record.
//
// The owner's words, typed 2026-11-17 in session f9614090, to the plan he
// answered "Yes, go ahead": "'Cleared by the system' in the app. The design
// says 'Green means a human affirmed it.'"

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/glossary.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_digitization/src/widgets/status_chip.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../screens/queue_test.dart' show ScriptedRepository, pumpQueue;
import '../ui_finders.dart';
import 'harness.dart';

Specimen cleared(String id, {Object? by}) => Specimen(<String, dynamic>{
  'specimen_id': id,
  'filename': '$id.jpg',
  'revision': 4,
  'status': 'completed',
  'disposition': 'cleared',
  'cleared_by': ?by,
});

/// A triple's three colours, comparable by value.
List<Color> colorsOf(UiStatusTriple triple) => <Color>[
  triple.content,
  triple.fill,
  triple.onFill,
];

void main() {
  group('the record', () {
    test('reads who cleared it, and nothing it was not told', () {
      expect(cleared('a', by: 'person').clearedBy, 'person');
      expect(cleared('a', by: 'system').clearedBy, 'system');
      expect(cleared('a').clearedBy, isNull);
      for (final Object odd in <Object>['Person', 'machine', '', true, 1]) {
        expect(cleared('a', by: odd).clearedBy, isNull, reason: '$odd');
      }
    });

    test('draws a cleared record as who cleared it', () {
      SpecimenStatus of(String? disposition, String? by) =>
          SpecimenStatus.ofRecord(
            disposition: disposition,
            state: 'completed',
            clearedBy: by,
          );
      expect(of('cleared', 'person'), SpecimenStatus.approvedByPerson);
      expect(of('cleared', 'system'), SpecimenStatus.clearedBySystem);
      // An older server, or a run that does not say: never either answer.
      expect(of('cleared', null), SpecimenStatus.cleared);
      expect(of('cleared', 'machine'), SpecimenStatus.cleared);
      // Only a cleared record is drawn by who cleared it.
      expect(of('needs_human_review', 'person'), SpecimenStatus.needsReview);
      expect(of('deferred', 'system'), SpecimenStatus.deferred);
      expect(of(null, 'person'), SpecimenStatus.unknown);
      for (final SpecimenStatus status in <SpecimenStatus>[
        SpecimenStatus.cleared,
        SpecimenStatus.approvedByPerson,
        SpecimenStatus.clearedBySystem,
      ]) {
        expect(status.isQueue, isTrue, reason: status.name);
        expect(status.isCleared, isTrue, reason: status.name);
        expect(status.isRecordStatus, isTrue, reason: status.name);
        expect(status.isRunState, isFalse, reason: status.name);
      }
    });

    test('names each case in plain words a definition is one tap from', () {
      expect(SpecimenStatus.approvedByPerson.label, 'Approved by a person');
      expect(SpecimenStatus.clearedBySystem.label, 'Cleared by system');
      expect(SpecimenStatus.cleared.label, 'Cleared');
      expect(
        SpecimenStatus.approvedByPerson.semanticsLabel,
        'Queue: approved by a person',
      );
      expect(
        SpecimenStatus.clearedBySystem.semanticsLabel,
        'Queue: cleared by the system',
      );
      expect(SpecimenStatus.cleared.semanticsLabel, 'Queue: cleared');
      for (final SpecimenStatus status in <SpecimenStatus>[
        SpecimenStatus.cleared,
        SpecimenStatus.approvedByPerson,
        SpecimenStatus.clearedBySystem,
      ]) {
        expect(status.label.length, inInclusiveRange(2, 20));
        expect(
          glossaryDefinition(status.label),
          isNotNull,
          reason: status.label,
        );
      }
      expect(
        glossaryDefinition('Approved by a person'),
        isNot(glossaryDefinition('Cleared by system')),
      );
    });
  });

  group('the chip', () {
    testWidgets('green and the cleared glyph only for a person', (
      WidgetTester tester,
    ) async {
      for (final ThemeData theme in productThemes.values) {
        late UiStatusColors colors;
        Future<StatusPresentation> present(SpecimenStatus status) async {
          late StatusPresentation presentation;
          await pumpComponent(
            tester,
            Builder(
              builder: (BuildContext context) {
                colors = context.ui.color.status;
                presentation = status.presentation(context);
                return StatusChip(status);
              },
            ),
            theme: theme,
          );
          expect(find.text(status.label), findsOneWidget);
          return presentation;
        }

        final StatusPresentation person = await present(
          SpecimenStatus.approvedByPerson,
        );
        expect(colorsOf(person.triple), colorsOf(colors.cleared));
        expect(person.glyph.resolve(), UiIcons.cleared.resolve());

        final StatusPresentation system = await present(
          SpecimenStatus.clearedBySystem,
        );
        expect(colorsOf(system.triple), colorsOf(colors.model));
        expect(system.glyph.resolve(), UiIcons.modelReading.resolve());

        final StatusPresentation unsaid = await present(SpecimenStatus.cleared);
        expect(
          colorsOf(unsaid.triple),
          colorsOf(colors.model),
          reason: 'green says a person',
        );
        expect(colorsOf(colors.model), isNot(colorsOf(colors.cleared)));
        expect(unsaid.glyph.resolve(), UiIcons.cleared.resolve());

        expect(system.glyph.resolve(), isNot(person.glyph.resolve()));
        expect(system.label, isNot(unsaid.label));
      }
    });

    testWidgets('is one labelled node with a 48 dp target', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      for (final SpecimenStatus status in <SpecimenStatus>[
        SpecimenStatus.approvedByPerson,
        SpecimenStatus.clearedBySystem,
      ]) {
        await pumpComponent(tester, StatusChip(status));
        expect(
          find.bySemanticsLabel(
            '${status.semanticsLabel}, term, double tap for definition',
          ),
          findsOneWidget,
        );
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      }
      handle.dispose();
    });
  });

  group('the record screen', () {
    Specimen live(String? disposition, {String? by}) =>
        Specimen(<String, dynamic>{
          'specimen_id': 'cleared-live',
          'revision': 3,
          'status': disposition == null ? 'running' : 'completed',
          'disposition': disposition,
          'cleared_by': ?by,
        });

    Widget announcing(Specimen specimen) => Builder(
      builder: (BuildContext context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(supportsAnnounce: true),
        child: WorkbenchStatusStrip(
          specimen: specimen,
          saved: false,
          blockers: const <ClearanceBlocker>[],
          pending: const [],
          staleChanges: const [],
          onGoToBlocker: (ClearanceBlocker _) {},
        ),
      ),
    );

    List<String> heard(WidgetTester tester) => tester
        .takeAnnouncements()
        .map((CapturedAccessibilityAnnouncement a) => a.message)
        .toList();

    testWidgets('announces who cleared it, once', (WidgetTester tester) async {
      await pumpComponent(tester, announcing(live('needs_human_review')));
      expect(heard(tester), isEmpty);
      await pumpComponent(tester, announcing(live('cleared', by: 'system')));
      expect(heard(tester), <String>['Queue: cleared by the system']);
      await pumpComponent(tester, announcing(live('cleared', by: 'system')));
      expect(heard(tester), isEmpty, reason: 'once, not on every poll');
      await pumpComponent(tester, announcing(live('cleared', by: 'person')));
      expect(heard(tester), <String>['Queue: approved by a person']);
    });
  });

  group('the queue', () {
    testWidgets('the Cleared view tells a person from the system per row', (
      WidgetTester tester,
    ) async {
      final ScriptedRepository repository = ScriptedRepository()
        ..results = <Specimen>[
          cleared('SD-person', by: 'person'),
          cleared('SD-system', by: 'system'),
          cleared('SD-unsaid'),
        ];
      await pumpQueue(tester, repository);
      await pickSpecimenQueue(tester, 'Cleared');
      expect(repository.requests.last['disposition'], 'cleared');

      String rowText(String id) => tester
          .widgetList<Text>(
            find.descendant(
              of: find.byKey(ValueKey<String>('queue-row-$id')),
              matching: find.byType(Text),
            ),
          )
          .map((Text text) => text.data ?? text.textSpan?.toPlainText() ?? '')
          .join(' | ');

      expect(rowText('SD-person'), contains('Approved by a person'));
      expect(rowText('SD-system'), contains('Cleared by system'));
      // The view already says cleared; a row that cannot say who adds nothing.
      expect(rowText('SD-unsaid'), isNot(contains('Cleared')));
      expect(rowText('SD-unsaid'), isNot(contains('Approved')));
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('every view names who cleared a cleared row', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final ScriptedRepository repository = ScriptedRepository()
        ..results = <Specimen>[
          cleared('SD-person', by: 'person'),
          cleared('SD-system', by: 'system'),
        ];
      await pumpQueue(tester, repository);
      expect(
        find.bySemanticsLabel(RegExp('Queue: approved by a person')),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(RegExp('Queue: cleared by the system')),
        findsOneWidget,
      );
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });
  });
}
