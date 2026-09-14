import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/evidence_panel.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  testWidgets(
    'authority alternatives require explicit reason and preserve source while selecting exact retained identifier',
    (tester) async {
      tester.view.physicalSize = const Size(1000, 2000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      Json? change;
      var reads = 0;
      final source = Specimen({
        'specimen_id': 's',
        'revision': 9,
        'run': {
          'authority_results': {
            'one': {
              'tool_id': 'parties',
              'field_key': 'identified_by_irn',
              'status': 'ambiguous',
            },
          },
        },
      });
      final result = <String, dynamic>{
        'status': 'ambiguous',
        'source_id': 'parties',
        'literal': 'A. Smith',
        'candidates': [
          {
            'name': 'A. Smith',
            'identifier': 'candidate-1',
            'relation': 'unresolved',
            'reason': 'Name alone cannot determine identity',
            'identity': {
              'source_system': 'emu',
              'connection_id': 'synthetic',
              'tenant': 'test',
              'environment': 'synthetic',
              'module': 'eparties',
              'irn': 1,
            },
          },
          {
            'name': 'A. Smith',
            'identifier': 'candidate-2',
            'relation': 'unresolved',
            'reason': 'Another retained alternative',
            'identity': {
              'source_system': 'emu',
              'connection_id': 'synthetic',
              'tenant': 'test',
              'environment': 'synthetic',
              'module': 'eparties',
              'irn': 2,
            },
          },
        ],
      };
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: EvidencePanel(
                specimen: source,
                canReview: true,
                onChange: (value) async {
                  change = value;
                },
                load: (request) async {
                  expect(request.kind, ArtifactKind.authority);
                  expect(request.fieldKey, 'identified_by_irn');
                  reads++;
                  if (reads == 1) {
                    throw const ApiFailure('Current access must be checked');
                  }
                  return result;
                },
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Read authority alternatives'));
      await tester.pumpAndSettle();
      expect(find.text('Current access must be checked'), findsOneWidget);
      expect(find.text('Use this match'), findsNothing);
      await tester.tap(find.text('Retry read authority alternatives'));
      await tester.pumpAndSettle();
      expect(find.text('candidate-1'), findsOneWidget);
      expect(find.text('candidate-2'), findsOneWidget);
      await tester.tap(find.text('Use this match').last);
      await tester.pumpAndSettle();
      // The row button and the dialog primary share one label for one intent,
      // so target the dialog explicitly.
      final confirm = find.descendant(
        of: find.byType(AlertDialog),
        matching: find.widgetWithText(FilledButton, 'Use this match'),
      );
      await tester.tap(confirm);
      await tester.pumpAndSettle();
      expect(find.text('Enter a reason for this decision.'), findsOneWidget);
      expect(change, isNull);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Reason'),
        'Matched retained institutional evidence',
      );
      await tester.tap(confirm);
      await tester.pumpAndSettle();
      expect(change?['identifier'], 'candidate-2');
      expect(change?['target_id'], 'identified_by_irn');
      expect(change?['kind'], 'authority_resolution');
      expect(source.revision, 9);
      expect(result['literal'], 'A. Smith');
      expect(result['candidates'], hasLength(2));
    },
  );
  testWidgets(
    'blocked phases and unmeasured risk never become completed or zero',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: EvidencePanel(
                specimen: const Specimen({
                  'specimen_id': 's',
                  'revision': 1,
                  'run': {
                    'phase_results': {
                      'lookup': {
                        'applicability': 'blocked',
                        'reason': 'credentials_required',
                      },
                    },
                    'review_risk': {
                      'composite': null,
                      'calibrated': false,
                      'unmeasured': ['reading_disagreement'],
                    },
                  },
                }),
                canReview: false,
                onChange: (_) async {},
                load: (_) async => {},
              ),
            ),
          ),
        ),
      );
      expect(find.text('Review risk'), findsOneWidget);
      expect(find.text('Not measured'), findsOneWidget);
      expect(find.text('lookup · blocked'), findsOneWidget);
      expect(find.text('credentials required'), findsOneWidget);
      expect(find.text('0 of 100'), findsNothing);
      expect(find.text('Use this match'), findsNothing);
    },
  );
}
