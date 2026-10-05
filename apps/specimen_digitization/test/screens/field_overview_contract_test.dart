import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widgets/harness.dart';

// Synthetic partial and unresolved shapes only. These tests exercise review
// presentation, retained locators and existing correction gates; no API IO.
const record = Specimen({
  'specimen_id': 'field-overview-contract',
  'regions': [
    {'region_id': 'label-one'},
  ],
  'fields': [
    {
      'field_key': 'collection_code',
      'state': 'supported',
      'literal_value': 'FMNHINS',
    },
    {
      'field_key': 'taxon',
      'state': 'supported',
      'literal_value': 'Lepidoptera',
    },
    {'field_key': 'city', 'state': 'supported', 'literal_value': 'Manila'},
    {
      'field_key': 'country',
      'state': 'unknown',
      'required': true,
      'source_region_id': 'label-one',
      'verbatim_by_observation': {'reader-a': 'P.I.'},
    },
    {'field_key': 'collectors', 'state': 'ambiguous', 'literal_value': 'Smith'},
  ],
});

Future<void> showOverview(
  WidgetTester tester, {
  Specimen specimen = record,
  ValueChanged<String?>? onFocus,
  List<ClearanceBlocker> issues = const [],
  Widget Function(String, ValueChanged<ResearchReviewCandidate>?)?
  researchForField,
  ValueChanged<List<PendingFieldChange>>? onPendingChanged,
}) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: WorkbenchFields(
      specimen: specimen,
      anchors: const {},
      pending: const [],
      onPendingChanged:
          onPendingChanged ??
          (_) => fail('Inspecting fields must not stage a correction'),
      onFocusRegion: onFocus,
      issues: issues,
      researchForField: researchForField,
    ),
  ),
  size: const Size(900, 1600),
);

Future<void> open(WidgetTester tester, String title) async {
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
  testWidgets('candidate selection stages exact source value for normal save', (
    tester,
  ) async {
    const specimen = Specimen({
      'specimen_id': 'candidate-review',
      'regions': [
        {'region_id': 'label-one'},
      ],
      'fields': [
        {
          'field_key': 'country',
          'state': 'unresolved',
          'literal_value': 'P.I.',
          'source_region_id': 'label-one',
        },
      ],
    });
    List<PendingFieldChange> pending = const [];
    await showOverview(
      tester,
      specimen: specimen,
      onPendingChanged: (changes) => pending = changes,
      researchForField: (key, onSelect) => UiButton(
        label: 'Test select $key',
        onPressed: () => onSelect?.call(
          ResearchReviewCandidate.fromJson({
            'label': 'Mindanao',
            'source_id': 'geolocate',
            'evidence_id': 'evidence-1',
            'selection_id': 'server-receipt',
            'selection_value': 'Philippines',
          }),
        ),
      ),
    );
    await open(tester, 'Country');
    await tester.tap(find.text('Test select country'));
    await tester.pump();
    expect(pending, hasLength(1));
    expect(pending.single.candidateLabel, 'Mindanao');
    expect(pending.single.candidateValue, 'Philippines');
    expect(pending.single.literal, 'P.I.');
    expect(pending.single.baseLiteral, 'P.I.');
    expect(pending.single.toChange('review this candidate'), {
      'kind': 'research_candidate',
      'target_id': 'country',
      'selection_id': 'server-receipt',
      'reason': 'review this candidate',
    });
  });

  testWidgets(
    'domain groups ignore wire ordering and unresolved fields lead their group',
    (tester) async {
      await showOverview(tester);
      for (final name in [
        'Location',
        'Collection',
        'Identification',
        'Record identifiers',
      ]) {
        expect(find.text(name), findsOneWidget);
      }
      expect(
        tester.getTopLeft(uiDisclosure('Country')).dy,
        lessThan(tester.getTopLeft(uiDisclosure('City')).dy),
      );
      expect(
        tester.getTopLeft(find.text('Location')).dy,
        lessThan(tester.getTopLeft(find.text('Collection')).dy),
      );
      expect(
        tester.getTopLeft(find.text('Collection')).dy,
        lessThan(tester.getTopLeft(find.text('Identification')).dy),
      );
      expect(find.text('Needs review · Unknown · Required'), findsOneWidget);
      expect(find.text('Needs review · Ambiguous · Smith'), findsOneWidget);
      expect(find.text('Supported · Lepidoptera'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'an unknown field has one state and a direct label link without a citation',
    (tester) async {
      final focused = <String?>[];
      await showOverview(tester, onFocus: focused.add);
      await open(tester, 'Country');
      expect(focused, ['label-one']);
      expect(
        find.text('No value has been recorded for this field.'),
        findsOneWidget,
      );
      expect(find.text('Needs review · Unknown · Required'), findsOneWidget);
      expect(find.text('Unknown'), findsNothing);
      expect(find.text('As written'), findsNothing);
      expect(uiDisclosure('Value details'), findsNothing);
      expect(find.text('P.I.'), findsOneWidget);
      expect(uiButton('View Label 1'), findsOneWidget);
      await tester.tap(uiButton('View Label 1'));
      await tester.pumpAndSettle();
      expect(focused, ['label-one', 'label-one']);
      await tester.tap(uiButton('Correct value'));
      await tester.pumpAndSettle();
      await pickUiSelect(tester, 'Evidence state', 'Supported');
      await tester.enterText(uiField('As written'), 'Philippines');
      await tester.pumpAndSettle();
      expect(
        find.text('This record carries no evidence to cite yet.'),
        findsOneWidget,
      );
      expect(
        tester.widget<UiButton>(uiButton('Keep this correction')).onPressed,
        isNull,
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('issues and research stay attached to the field they concern', (
    tester,
  ) async {
    await showOverview(
      tester,
      issues: const [
        ClearanceBlocker(
          message: 'Check the country against the label.',
          segment: WorkbenchSegment.fields,
          fieldKey: 'country',
          rawCode: 'mandatory_unresolved:country',
          diagnosticRuleId: 'internal-country-rule',
        ),
      ],
      researchForField: (key, _) => Text('Research detail for $key'),
    );
    expect(find.text('Check the country against the label.'), findsNothing);
    expect(find.text('Research detail for country'), findsNothing);
    await open(tester, 'Country');
    expect(find.text('Check the country against the label.'), findsOneWidget);
    expect(find.text('Research detail for country'), findsOneWidget);
    expect(find.text('Research detail for city'), findsNothing);
    expect(find.textContaining('mandatory_unresolved'), findsNothing);
    expect(find.textContaining('internal-country-rule'), findsNothing);
  });

  testWidgets(
    'source payloads are summarized with raw evidence available only on demand',
    (tester) async {
      const raw =
          '{"name":"Philippines","id":"internal-source-match","confidence":0.9}';
      final specimen = Specimen({
        ...record.data,
        'evidence': [
          {
            'evidence_id': 'source-one',
            'region_id': 'label-one',
            'excerpt': raw,
          },
        ],
        'fields': [
          {
            ...record.fields.firstWhere(
              (field) => field['field_key'] == 'country',
            ),
            'evidence_ids': ['source-one'],
          },
        ],
      });
      await showOverview(tester, specimen: specimen);
      await open(tester, 'Country');
      expect(find.text('Philippines'), findsOneWidget);
      expect(find.text(raw), findsNothing);
      expect(find.textContaining('confidence'), findsNothing);
      expect(find.text('Needs review · Unknown · Required'), findsOneWidget);
      await open(tester, 'Evidence details');
      expect(find.text(raw), findsOneWidget);
    },
  );

  testWidgets(
    'supported derived values name their source fields without erasing label wording',
    (tester) async {
      final specimen = Specimen({
        ...record.data,
        'fields': [
          {
            'field_key': 'date_visited_from',
            'state': 'supported',
            'literal_value': "3 Sept. '46",
          },
          {
            'field_key': 'date_visited_to',
            'state': 'supported',
            'literal_value': "3 Sept. '46",
            'normalized': '1946-09-03',
            'layer': 'derived',
            'derived_from': ['date_visited_from'],
          },
        ],
      });
      await showOverview(tester, specimen: specimen);
      await open(tester, 'Date visited to');
      expect(find.text('Derived from Date visited from'), findsOneWidget);
      await open(tester, 'Value details');
      expect(find.text("3 Sept. '46"), findsOneWidget);
      expect(find.text('As written'), findsOneWidget);
      expect(find.text('Read as'), findsNothing);
      expect(find.text('Standardized'), findsOneWidget);
    },
  );
}
