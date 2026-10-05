import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

// Synthetic data shaped like the native API response observed in production.
// These interactions neither authenticate nor change a production specimen.
const record = Specimen({
  'specimen_id': 'internal-record-id',
  'filename': 'subject_105526322.jpg',
  'revision': 1,
  'disposition': 'needs_human_review',
  'available_actions': ['field'],
  'fields': [
    {'field_key': 'country', 'state': 'unknown', 'required': true},
    {'field_key': 'taxon', 'state': 'unknown', 'required': true},
    {
      'field_key': 'collection_code',
      'state': 'supported',
      'literal_value': 'FMNHINS',
    },
  ],
  'validation_findings': [
    {'reason_code': 'mandatory_unresolved:country', 'severity': 'hard'},
    {
      'reason_code': 'mandatory_evidence_unresolved:country',
      'severity': 'hard',
    },
    {'reason_code': 'institutional_policy_unapproved', 'severity': 'hard'},
    {'reason_code': 'new_check:private-diagnostic-id', 'severity': 'hard'},
  ],
  'run': {
    'review_risk': {'composite': null, 'calibrated': false},
    'risk_policy_snapshot': {'checksum': 'internal-policy-checksum'},
    'authority_results': {
      'country-match': {
        'field_key': 'country',
        'tool_id': 'geography',
        'status': 'ambiguous',
      },
      'taxon-match': {
        'field_key': 'taxon',
        'tool_id': 'taxonomy',
        'status': 'ambiguous',
      },
    },
  },
});

Future<void> openDisclosure(WidgetTester tester, String title) async {
  final header = find
      .descendant(
        of: uiDisclosure(title),
        matching: find.byWidgetPredicate(
          (widget) => widget is Pressable && widget.onPressed != null,
        ),
      )
      .first;
  await tester.ensureVisible(header);
  await tester.pumpAndSettle();
  await tester.tap(header);
  await tester.pumpAndSettle();
}

void main() {
  for (final size in [compactWindow, largeWindow]) {
    testWidgets('native-shaped review stays field-centered at $size', (
      tester,
    ) async {
      useWindow(tester, size);
      var reads = 0;
      var mutations = 0;
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: record,
            onChange: (_) async {
              mutations++;
              return true;
            },
            onRetry: (_) async {},
            onRefresh: () {},
            loadArtifact: (request) async {
              reads++;
              return {};
            },
            fieldResearchHost: (buildFields) =>
                buildFields((key) => Text('Research context for $key')),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Location'), findsOneWidget);
      expect(find.text('Identification'), findsOneWidget);
      expect(find.text('mandatory_unresolved:country'), findsNothing);
      expect(find.textContaining('private-diagnostic-id'), findsNothing);
      expect(find.textContaining('internal-policy-checksum'), findsNothing);
      expect(find.text('Country needs a supported value'), findsNothing);
      expect(find.text('Saved authority matches'), findsNothing);
      expect(find.text('Research context for country'), findsNothing);
      expect(reads, 0);

      await openDisclosure(tester, 'Country');
      expect(find.text('Country needs a supported value'), findsOneWidget);
      expect(find.text('Country needs supporting evidence'), findsOneWidget);
      expect(find.text('Research context for country'), findsOneWidget);
      expect(find.text('Research context for taxon'), findsNothing);
      expect(find.text('Saved authority matches'), findsOneWidget);
      expect(find.text('Taxon · ambiguous'), findsNothing);
      expect(reads, 0);
      expect(mutations, 0);
      expect(tester.takeException(), isNull);
    });
  }
}
