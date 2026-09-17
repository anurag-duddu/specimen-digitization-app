// One row in a source listing (`lib/src/widgets/source_object_row.dart`).
//
// What is load bearing: the state is carried by a word and a glyph rather
// than by colour, a measurement the server did not make renders as words, and
// a row with nothing behind it does not announce itself as a button.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/sources.dart';
import 'package:specimen_digitization/src/widgets/source_object_row.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../sources/source_fixtures.dart';
import 'harness.dart';

void main() {
  for (final MapEntry<String, ThemeData> entry in productThemes.entries) {
    group('in ${entry.key}', () {
      testWidgets('names the photograph, its format and its size', (
        WidgetTester tester,
      ) async {
        await pumpComponent(
          tester,
          SourceObjectRow(object: object('subject_105526321.jpg')),
          theme: entry.value,
        );

        expect(find.text('subject_105526321.jpg'), findsOneWidget);
        expect(find.textContaining('JPEG'), findsOneWidget);
        expect(find.textContaining('0.3 MB'), findsOneWidget);
      });

      testWidgets('states every row state as a word', (
        WidgetTester tester,
      ) async {
        for (final MapEntry<String, String> row in <String, String>{
          'available': 'Available',
          'imported': 'In the queue',
          'unsupported_media_type': 'Unsupported format',
        }.entries) {
          await pumpComponent(
            tester,
            SourceObjectRow(object: object('a.jpg', state: row.key)),
            theme: entry.value,
          );
          // Colour is never the only carrier of a state.
          expect(find.text(row.value), findsOneWidget);
        }
      });
    });
  }

  testWidgets('a size the server did not report renders as words', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SourceObjectRow(object: object('a.jpg', sizeBytes: null)),
    );

    // Never 0.0 MB, which would be a measurement this row does not have.
    expect(find.textContaining('Size not recorded'), findsOneWidget);
    expect(find.textContaining('0.0 MB'), findsNothing);
  });

  testWidgets('a media type this client has no word for is shown, not hidden', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SourceObjectRow(object: object('a.bin', mediaType: 'application/pdf')),
    );

    // A reviewer looking at a row the source refused needs to see what it is.
    expect(find.textContaining('application/pdf'), findsOneWidget);
  });

  testWidgets('a photograph that is not a record announces no button', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, SourceObjectRow(object: object('a.jpg')));

    expect(
      tester.getSemantics(find.byType(SourceObjectRow)),
      isNot(matchesSemantics(isButton: true)),
    );
    handle.dispose();
  });

  testWidgets('a photograph that is a record opens it', (
    WidgetTester tester,
  ) async {
    int opened = 0;
    await pumpComponent(
      tester,
      SourceObjectRow(
        object: object('a.jpg', state: 'imported', specimenId: 'spec-a'),
        onOpen: () => opened++,
      ),
    );

    await tester.tap(find.byType(SourceObjectRow));
    await tester.pumpAndSettle();
    expect(opened, 1);
  });

  testWidgets('an unsupported photograph cannot be selected', (
    WidgetTester tester,
  ) async {
    // Adding it would be refused, so the affordance is not offered.
    expect(SourceObjectState.unsupportedMediaType.selectable, isFalse);
    // Already a record is selectable: re-importing is a no op that reads no
    // bytes, which is what makes a select all safe to run twice.
    expect(SourceObjectState.imported.selectable, isTrue);
    expect(SourceObjectState.available.selectable, isTrue);
  });

  testWidgets('reads as one stop, with its state in the label', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      SourceObjectRow(object: object('a.jpg', state: 'imported')),
    );

    // A reader paging a thousand photographs hears one stop per photograph.
    expect(
      find.bySemanticsLabel(RegExp('a.jpg, Photograph: in the queue, JPEG')),
      findsOneWidget,
    );
    handle.dispose();
  });

  testWidgets('inside a selectable row, meets the target and label rules', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SelectableRow(
        selected: false,
        label: 'subject_105526321.jpg',
        onToggle: () {},
        child: SourceObjectRow(object: object('subject_105526321.jpg')),
      ),
    );

    await expectAccessible(tester);
  });

  group('the count', () {
    test('is singular for one and plural for the rest', () {
      expect(photographsLabel(1), '1 photograph');
      expect(photographsLabel(0), '0 photographs');
      expect(photographsLabel(1000), '1,000 photographs');
      expect(photographsLabel(999), '999 photographs');
      expect(photographsLabel(1000000), '1,000,000 photographs');
    });
  });
}
