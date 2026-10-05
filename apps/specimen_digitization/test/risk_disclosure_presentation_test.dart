import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/risk_assessment.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

void main() {
  testWidgets('risk metadata is available only through technical details', (
    tester,
  ) async {
    final checksum = 'b' * 64;
    const recordId = 'e98a924c-9fba-5981-b061-9f4f37127f23';
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: ReviewRiskPanel(
              risk: {
                'target_id': recordId,
                'scope': 'specimen',
                'status': 'unmeasured',
                'measurement_complete': false,
                'composite': 0,
                'calibrated': false,
                'policy_reference': {
                  'id': 'risk-policy',
                  'version': 'v1',
                  'digest': checksum,
                },
                'registry_version': 'internal-registry-v1',
                'feature_version': 'internal-features-v1',
                'reasons': ['unmeasured:field_agreement'],
                'unmeasured': ['field_agreement', 'image_quality'],
              },
            ),
          ),
        ),
      ),
    );
    expect(find.text('Not measured'), findsOneWidget);
    expect(find.textContaining(recordId), findsNothing);
    expect(find.textContaining(checksum), findsNothing);
    expect(find.text('0 of 100'), findsNothing);
    await tester.tap(find.text('Review risk'));
    await tester.pumpAndSettle();
    expect(find.text('2 signals have not been measured.'), findsOneWidget);
    expect(find.textContaining(checksum), findsNothing);
    expect(find.textContaining('internal-registry-v1'), findsNothing);
    await tester.tap(find.text('Technical details'));
    await tester.pumpAndSettle();
    expect(find.textContaining(checksum), findsOneWidget);
    expect(find.textContaining(recordId), findsOneWidget);
    expect(find.textContaining('unmeasured:field_agreement'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
