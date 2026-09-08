import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/risk_assessment.dart';

void main() {
  final fixture =
      jsonDecode(
            File(
              'test/fixtures/backend-runtime-wire-examples.json',
            ).readAsStringSync(),
          )
          as Json;
  testWidgets(
    'two pinned policies retain measured component differences without a partial composite',
    (tester) async {
      for (final entry in {'first': 20, 'second': 40}.entries) {
        final run = fixture['profile_variants'][entry.key]['run'] as Json;
        final risk = run['review_risk'] as Json;
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: ReviewRiskPanel(
                  risk: risk,
                  policy: run['risk_policy_snapshot'],
                ),
              ),
            ),
          ),
        );
        expect(find.text('Unmeasured'), findsOneWidget);
        expect(
          find.textContaining(
            'numeral disagreement · Count 1 · Weight ${entry.value} · Contribution ${entry.value}',
          ),
          findsOneWidget,
        );
        expect(
          find.text('Policy digest: ${risk['policy_reference']['digest']}'),
          findsOneWidget,
        );
        expect(find.text('0 / 100'), findsNothing);
        final label = (risk['labels'] as List).first as Json;
        final target = find.text('${label['target_id']} · Unmeasured');
        await tester.ensureVisible(target);
        await tester.pumpAndSettle();
        await tester.tap(target);
        await tester.pumpAndSettle();
        expect(
          find.textContaining(
            'numeral disagreement · Count 1 · Weight ${entry.value} · Contribution ${entry.value}',
          ),
          findsNWidgets(2),
        );
        expect(find.textContaining('Unmeasured dimensions:'), findsNWidgets(2));
      }
    },
  );
  test(
    'blocked or partial assessment cannot display a fabricated zero composite',
    () {
      expect(
        riskComposite({'status': 'blocked', 'composite': 0}),
        'Unmeasured',
      );
      expect(
        riskComposite({'status': 'unmeasured', 'composite': 0}),
        'Unmeasured',
      );
      expect(
        riskComposite({
          'status': 'scored',
          'measurement_complete': false,
          'composite': 0,
        }),
        'Unmeasured',
      );
      expect(
        riskComposite({
          'status': 'scored',
          'measurement_complete': true,
          'composite': 0,
        }),
        '0 / 100',
      );
    },
  );
  testWidgets(
    'measured execution retains actual timing, reported model and absent parameters',
    (tester) async {
      final observation =
          fixture['observation_telemetry']['workspace']['observations'][0]
              as Json;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ObservationExecutionDetails(observation: observation),
            ),
          ),
        ),
      );
      expect(
        find.text('Latency: ${observation['latency_seconds']} seconds'),
        findsOneWidget,
      );
      expect(
        find.text('Reported model: synthetic-model-runtime'),
        findsOneWidget,
      );
      expect(
        find.text('Input tokens: 314 · Output tokens: 95'),
        findsOneWidget,
      );
      expect(find.text('Model parameters: Not reported'), findsOneWidget);
      expect(
        find.text('Input crop reference: ${observation['input_crop_ref']}'),
        findsOneWidget,
      );
      final absent =
          fixture['profile_variants']['first']['observations'][0] as Json;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ObservationExecutionDetails(observation: absent),
          ),
        ),
      );
      expect(find.text('Latency: Not measured'), findsOneWidget);
      expect(find.text('Reported model: Not reported'), findsOneWidget);
    },
  );
  testWidgets(
    'unavailable comparison remains unmeasured rather than zero disagreement',
    (tester) async {
      final comparison =
          fixture['profile_variants']['first']['run']['transcripts'][0] as Json;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TranscriptionComparisonSummary(transcription: comparison),
          ),
        ),
      );
      expect(
        find.text(
          'Comparison: disagreement · Difference fraction: ${comparison['disagreement_ratio']}',
        ),
        findsOneWidget,
      );
      // Negative presentation probe: even a contradictory numeric value cannot
      // make a policy-blocked status look like measured agreement.
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TranscriptionComparisonSummary(
              transcription: {
                ...comparison,
                'alignment_status': 'policy_blocked',
                'disagreement_ratio': 0,
                'alignment_reasons': ['text_limit'],
              },
            ),
          ),
        ),
      );
      expect(
        find.text(
          'Comparison: policy blocked · Difference fraction: Unmeasured',
        ),
        findsOneWidget,
      );
      expect(
        find.text(
          'Comparison limits prevented measurement. This is not agreement.',
        ),
        findsOneWidget,
      );
    },
  );
}
