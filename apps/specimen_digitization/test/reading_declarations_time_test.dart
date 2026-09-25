// A human declaration is a decision record, so the time it was recorded is
// absolute, on the reviewer's clock, never the raw instant the server sent
// (02 section 4.14; #182's review found "Recorded by … · 2026-…Z").

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/reading_declarations.dart';

import 'widgets/harness.dart';

void main() {
  testWidgets('a declaration says when it was recorded, in words', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SingleChildScrollView(
        child: ReadingDeclarationView(
          provenance: <String, dynamic>{
            'revision': 3,
            'human_history': <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'declaration-1',
                'actor': 'Reviewer A',
                'created_at': '2026-09-07T10:00:00Z',
                'reason': 'The label is in Spanish.',
                'candidates': <String, dynamic>{},
              },
            ],
          },
        ),
      ),
      size: const Size(800, 1600),
    );
    expect(
      find.text('Recorded by Reviewer A · 7 Sep 2026, 05:00 CDT'),
      findsOneWidget,
    );
    expect(find.textContaining('2026-09-07T10:00:00Z'), findsNothing);
  });
}
