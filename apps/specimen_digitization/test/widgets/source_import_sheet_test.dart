// The confirmation before a selection is added, and the report of what it did
// (`lib/src/widgets/source_import_sheet.dart`).
//
// The confirmation is the point of this screen, so it has the most tests. It
// has to name the exact count before anything is sent, it has to say what the
// gesture costs, and what it says about cost has to be true: adding creates
// records and runs nothing, so it says that rather than naming a price or an
// allowance that no endpoint reports yet.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/sources.dart';
import 'package:specimen_digitization/src/widgets/source_import_sheet.dart';

import 'harness.dart';

SourceImportProgress progressOf({
  int requested = 3,
  int imported = 3,
  int duplicates = 0,
  List<Map<String, dynamic>> items = const <Map<String, dynamic>>[],
  String? stoppedReason,
}) => SourceImportProgress(
  requested: requested,
  imported: imported,
  duplicates: duplicates,
  items: items.map(SourceImportOutcome.new).toList(),
  stoppedReason: stoppedReason,
);

void main() {
  group('the confirmation', () {
    testWidgets('names the exact count in the title and on the button', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SourceImportConfirmation(count: 1000, alreadyInQueue: 0),
      );

      // A gesture that picked a thousand and one that picked one look
      // identical on screen, so the number is stated in words.
      expect(find.text('Add 1,000 photographs to the queue?'), findsOneWidget);
      // The primary button repeats the title's verb and the count.
      expect(find.text('Add 1,000 photographs'), findsOneWidget);
    });

    testWidgets('says what the gesture costs', (WidgetTester tester) async {
      await pumpComponent(
        tester,
        const SourceImportConfirmation(count: 1000, alreadyInQueue: 0),
      );

      // Adding creates records and dispatches nothing, in any mode. That is
      // what it costs, so that is what it says. It must not name a price or
      // an allowance, because no endpoint reports either yet and a
      // confirmation that invented one would look authoritative.
      expect(
        find.text('No model runs and no allowance is used.'),
        findsOneWidget,
      );
      expect(find.textContaining('cents'), findsNothing);
      expect(find.textContaining(r'$'), findsNothing);
      expect(find.textContaining('remaining'), findsNothing);
    });

    testWidgets('does not word itself as though it starts processing', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SourceImportConfirmation(count: 10, alreadyInQueue: 0),
      );

      expect(find.textContaining('Processing'), findsNothing);
      expect(find.textContaining('processing'), findsNothing);
      expect(find.textContaining('Run '), findsNothing);
      expect(
        find.text('These become records in the queue, ready to review.'),
        findsOneWidget,
      );
    });

    testWidgets('says what happens to photographs already in the queue', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SourceImportConfirmation(count: 1000, alreadyInQueue: 342),
      );

      expect(
        find.textContaining(
          '342 photographs of these are already in the queue',
        ),
        findsOneWidget,
      );
    });

    testWidgets('says nothing about duplicates when there are none', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SourceImportConfirmation(count: 10, alreadyInQueue: 0),
      );

      expect(find.textContaining('already in the queue'), findsNothing);
    });

    testWidgets('is singular for one photograph', (WidgetTester tester) async {
      await pumpComponent(
        tester,
        const SourceImportConfirmation(count: 1, alreadyInQueue: 0),
      );

      expect(find.text('Add 1 photograph to the queue?'), findsOneWidget);
      expect(find.text('Add 1 photograph'), findsOneWidget);
    });

    testWidgets('cancels without adding, and commits when confirmed', (
      WidgetTester tester,
    ) async {
      for (final MapEntry<String, bool> run in <String, bool>{
        'Cancel': false,
        'Add 3 photographs': true,
      }.entries) {
        bool? answer;
        await pumpComponent(
          tester,
          Builder(
            builder: (BuildContext context) => TextButton(
              onPressed: () async {
                answer = await confirmSourceImport(
                  context,
                  count: 3,
                  alreadyInQueue: 0,
                );
              },
              child: const Text('Open'),
            ),
          ),
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();
        await tester.tap(find.text(run.key));
        await tester.pumpAndSettle();
        expect(answer, run.value, reason: run.key);
      }
    });

    testWidgets('meets the target and label rules', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SourceImportConfirmation(count: 6, alreadyInQueue: 1),
      );
      await expectAccessible(tester);
    });

    for (final MapEntry<String, ThemeData> entry in productThemes.entries) {
      testWidgets('renders in ${entry.key}', (WidgetTester tester) async {
        await pumpComponent(
          tester,
          const SourceImportConfirmation(count: 6, alreadyInQueue: 1),
          theme: entry.value,
        );
        expect(find.text('Add 6 photographs to the queue?'), findsOneWidget);
      });
    }
  });

  group('the confirmation on a narrow window', () {
    testWidgets('opens as a sheet and still names the count', (
      WidgetTester tester,
    ) async {
      bool? answer;
      await pumpComponent(
        tester,
        Builder(
          builder: (BuildContext context) => TextButton(
            onPressed: () async {
              answer = await confirmSourceImport(
                context,
                count: 1000,
                alreadyInQueue: 0,
              );
            },
            child: const Text('Open'),
          ),
        ),
        // Compact: showAdaptiveForm draws a bottom sheet rather than a
        // dialog, and the count has to survive the change of surface.
        size: const Size(390, 844),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(find.byType(BottomSheet), findsOneWidget);
      expect(find.text('Add 1,000 photographs to the queue?'), findsOneWidget);

      await tester.tap(find.text('Add 1,000 photographs'));
      await tester.pumpAndSettle();
      expect(answer, isTrue);
    });

    testWidgets('lays out at 200 percent text without overflowing', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        MediaQuery(
          data: const MediaQueryData(textScaler: TextScaler.linear(2)),
          child: const SourceImportConfirmation(
            count: 1000,
            alreadyInQueue: 342,
          ),
        ),
        size: const Size(390, 844),
      );

      // The buttons wrap rather than run off the edge, which is what
      // OverflowBar is there for. An exception would have failed the pump.
      expect(tester.takeException(), isNull);
      expect(find.text('Add 1,000 photographs'), findsOneWidget);
    });
  });

  group('the report', () {
    testWidgets('says how many of how many landed', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        SourceImportReport(
          progress: progressOf(
            requested: 3,
            imported: 2,
            duplicates: 1,
            items: const <Map<String, dynamic>>[
              <String, dynamic>{'object_name': 'a.jpg', 'state': 'imported'},
              <String, dynamic>{'object_name': 'b.jpg', 'state': 'imported'},
              <String, dynamic>{'object_name': 'c.jpg', 'state': 'duplicate'},
            ],
          ),
        ),
      );

      expect(find.text('2 of 3 photographs added'), findsOneWidget);
      expect(find.text('c.jpg'), findsOneWidget);
      expect(find.text('Already in the queue, unchanged.'), findsOneWidget);
    });

    testWidgets('names every photograph that did not become a record', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        SourceImportReport(
          progress: progressOf(
            requested: 2,
            imported: 1,
            items: const <Map<String, dynamic>>[
              <String, dynamic>{'object_name': 'a.jpg', 'state': 'imported'},
              <String, dynamic>{
                'object_name': 'b.pdf',
                'state': 'unsupported_media_type',
              },
            ],
          ),
        ),
      );

      expect(find.text('b.pdf'), findsOneWidget);
      expect(
        find.text('Not added. This source does not admit this media type.'),
        findsOneWidget,
      );
      // A photograph that did land is not listed: the report is what needs
      // acting on, not a receipt.
      expect(find.text('a.jpg'), findsNothing);
    });

    testWidgets('a run that stopped says why, and keeps what landed', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        SourceImportReport(
          progress: progressOf(
            requested: 100,
            imported: 50,
            stoppedReason:
                'This source changed while the photographs were being '
                'added. Reload the source and add the rest.',
          ),
        ),
      );

      expect(find.text('50 of 100 photographs added'), findsOneWidget);
      expect(find.textContaining('Reload the source'), findsOneWidget);
    });
  });
}
