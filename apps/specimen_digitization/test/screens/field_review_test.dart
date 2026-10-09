import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/widgets/field_row.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart' hide FieldLayer;

import '../ui_finders.dart';
import '../widgets/harness.dart';
import '../workbench_harness.dart';

// Synthetic retained values and evidence exercise presentation and callbacks.
// They do not represent a production research result or perform repository IO.
const specimen = Specimen({
  'specimen_id': 'synthetic-field-review',
  'revision': 1,
  'regions': [
    {'region_id': 'r1'},
    {'region_id': 'r2'},
  ],
  'evidence': [
    {'evidence_id': 'e1', 'region_id': 'r1', 'excerpt': 'U.S.A. · 304.8 m'},
    {'evidence_id': 'e2', 'region_id': 'r2', 'excerpt': 'Chicago, Ills.'},
  ],
  'fields': [
    {
      'field_key': 'country',
      'display_name': 'Country',
      'required': true,
      'state': 'supported',
      'literal_value': 'U.S.A.',
      'parsed_value': 'United States',
      'normalized': 'United States of America',
      'authority_id': 'synthetic-country-match',
      'evidence_ids': ['e1'],
    },
    {
      'field_key': 'elevation_from_m',
      'display_name': 'Elevation From M',
      'required': true,
      'state': 'supported',
      'literal_value': '304.8 m',
      'parsed_value': '304.8',
      'evidence_ids': ['e1'],
    },
    {
      'field_key': 'precise_location',
      'display_name': 'Precise location',
      'required': true,
      'state': 'ambiguous',
      'literal_value': 'Chicago, Ills.',
      'parsed_value': 'Chicago, Illinois',
      'evidence_ids': ['e1', 'e2'],
    },
    {
      'field_key': 'elevation_to_ft',
      'display_name': 'Elevation To Ft',
      'required': false,
      'state': 'unknown',
      'evidence_ids': [],
    },
  ],
  'validation_findings': [
    {
      'field_key': 'precise_location',
      'message': 'Two locality candidates remain',
      'severity': 'warning',
      'rule_id': 'synthetic-locality-rule',
    },
  ],
});

Future<void> showFields(
  WidgetTester tester, {
  Specimen record = specimen,
  List<PendingFieldChange> pending = const [],
  ValueChanged<List<PendingFieldChange>>? onPendingChanged,
  ValueChanged<String?>? onFocusRegion,
  String? blockedReason,
  Size size = const Size(900, 1600),
  double textScale = 1,
}) => pumpComponent(
  tester,
  Builder(
    builder: (context) => MediaQuery(
      data: MediaQuery.of(
        context,
      ).copyWith(textScaler: TextScaler.linear(textScale)),
      child: SingleChildScrollView(
        child: WorkbenchFields(
          specimen: record,
          anchors: const {},
          pending: pending,
          onPendingChanged: onPendingChanged ?? (_) {},
          onFocusRegion: onFocusRegion,
          fieldBlockedReason: blockedReason,
        ),
      ),
    ),
  ),
  size: size,
);

Future<void> expandField(WidgetTester tester, String name) async {
  final header = find
      .descendant(
        of: uiDisclosure(name),
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

Future<void> openReviewEditor(WidgetTester tester, String name) async {
  Finder correct() => find.descendant(
    of: uiDisclosure(name),
    matching: uiButton('Correct value'),
  );
  if (correct().evaluate().isEmpty) await expandField(tester, name);
  await tester.ensureVisible(correct());
  await tester.pumpAndSettle();
  await tester.tap(correct());
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'field previews name real states and layers without open detail',
    (tester) async {
      await showFields(tester);
      // Place, elevation and the rest of the collecting event are one group.
      expect(find.text('Collection'), findsOneWidget);
      expect(find.text('Location'), findsNothing);
      expect(find.text('Required'), findsNothing);
      expect(find.text('Optional'), findsNothing);
      expect(find.text('Elevation from (m)'), findsOneWidget);
      expect(find.text('Elevation to (ft)'), findsOneWidget);
      expect(
        find.text('Supported · United States of America · Required'),
        findsOneWidget,
      );
      expect(find.text('Supported · 304.8 · Required'), findsOneWidget);
      expect(
        find.text('Needs review · Ambiguous · Chicago, Illinois · Required'),
        findsOneWidget,
      );
      expect(find.text('Needs review · Unknown'), findsOneWidget);
      expect(find.text('As written'), findsNothing);
      expect(find.text('U.S.A. · 304.8 m'), findsNothing);
      expect(find.text('Two locality candidates remain'), findsNothing);
      expect(uiIconButton(RegExp('^Edit ')), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('opening a field links only its retained label and evidence', (
    tester,
  ) async {
    final focused = <String?>[];
    await showFields(tester, onFocusRegion: focused.add);
    await expandField(tester, 'Country');
    expect(focused, ['r1']);
    expect(find.text('Current value · Standardized'), findsOneWidget);
    expect(find.text('Sources: Label 1'), findsOneWidget);
    expect(find.text('Evidence for Country'), findsOneWidget);
    expect(find.text('U.S.A. · 304.8 m'), findsOneWidget);
    await expandField(tester, 'Value details');
    expect(find.text('U.S.A.'), findsOneWidget);
    expect(find.text('United States'), findsOneWidget);
    expect(
      find.descendant(
        of: uiDisclosure('Value details'),
        matching: find.text('United States of America'),
      ),
      findsOneWidget,
    );
    for (final layer in FieldLayer.values) {
      expect(find.text(layer.label), findsOneWidget);
    }
    await tester.tap(uiButton('View Label 1'));
    await tester.pumpAndSettle();
    expect(focused, ['r1', 'r1']);
    await expandField(tester, 'Country');
    expect(find.text('Evidence for Country'), findsNothing);
    expect(focused, ['r1', 'r1']);
  });

  testWidgets('a field citing several labels offers each source explicitly', (
    tester,
  ) async {
    final focused = <String?>[];
    await showFields(tester, onFocusRegion: focused.add);
    await expandField(tester, 'Precise location');
    expect(focused, [null]);
    expect(find.text('Sources: Label 1, Label 2'), findsOneWidget);
    expect(find.text('Two locality candidates remain'), findsOneWidget);
    await tester.tap(uiButton('View Label 2'));
    await tester.pumpAndSettle();
    expect(focused, [null, 'r2']);
  });

  testWidgets('a staged correction keeps the existing batch and wire values', (
    tester,
  ) async {
    var pending = <PendingFieldChange>[
      const PendingFieldChange(
        fieldKey: 'precise_location',
        displayName: 'Precise location',
        state: 'unknown',
        baseLiteral: 'Chicago, Ills.',
      ),
    ];
    final focused = <String?>[];
    await pumpComponent(
      tester,
      StatefulBuilder(
        builder: (context, setState) => SingleChildScrollView(
          child: WorkbenchFields(
            specimen: specimen,
            anchors: const {},
            pending: pending,
            onFocusRegion: focused.add,
            onPendingChanged: (next) => setState(() => pending = next),
          ),
        ),
      ),
      size: const Size(900, 1600),
    );
    await openReviewEditor(tester, 'Country');
    expect(find.text('Correct Country'), findsOneWidget);
    expect(
      find.text(
        'Copy the country text on the label, keeping abbreviations as written.',
      ),
      findsOneWidget,
    );
    await tester.enterText(uiField('As written'), 'USA');
    await tester.pumpAndSettle();
    await tester.ensureVisible(uiButton('Keep this correction'));
    await tester.pumpAndSettle();
    await tester.tap(uiButton('Keep this correction'));
    await tester.pumpAndSettle();
    expect(pending, hasLength(2));
    expect(pending.first.fieldKey, 'precise_location');
    final country = pending.last;
    expect(country.regionId, 'r1');
    expect(country.baseLiteral, 'U.S.A.');
    expect(country.toChange('Verified label'), {
      'kind': 'field_correction',
      'target_id': 'country',
      'value': 'USA',
      'state': 'supported',
      'parsed': 'United States',
      'normalized': 'United States of America',
      'authority_id': 'synthetic-country-match',
      'reason': 'Verified label',
      'evidence_ids': ['e1'],
    });
    expect(find.text('Not saved yet: Country becomes "USA"'), findsOneWidget);
    expect(focused, everyElement('r1'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('pending evidence controls source focus and no-value previews', (
    tester,
  ) async {
    final focused = <String?>[];
    await showFields(
      tester,
      pending: const [
        PendingFieldChange(
          fieldKey: 'country',
          displayName: 'Country',
          state: 'unknown',
          parsed: 'Old interpretation',
          normalized: 'Old normalized value',
          authorityId: 'Old authority',
          evidenceIds: ['e2'],
        ),
      ],
      onFocusRegion: focused.add,
    );
    final row = uiDisclosure('Country');
    expect(
      find.descendant(
        of: row,
        matching: find.text('Needs review · Unknown · Required'),
      ),
      findsOneWidget,
    );
    await expandField(tester, 'Country');
    expect(focused, ['r2']);
    expect(find.text('Sources: Label 2'), findsOneWidget);
    expect(find.text('Chicago, Ills.'), findsOneWidget);
    expect(find.text('Old interpretation'), findsNothing);
    expect(find.text('Old normalized value'), findsNothing);
    expect(find.textContaining('Old authority'), findsNothing);
    expect(find.text('United States of America'), findsNothing);
  });

  testWidgets('an unrecognized state stays inspectable and cannot be edited', (
    tester,
  ) async {
    final record = Specimen({
      ...specimen.data,
      'fields': [
        {...specimen.fields.first, 'state': 'future_server_state'},
      ],
    });
    await showFields(tester, record: record);
    expect(
      find.text(
        'Needs review · State unknown · United States of America · Required',
      ),
      findsOneWidget,
    );
    await expandField(tester, 'Country');
    expect(find.text('Current value · Standardized'), findsOneWidget);
    expect(
      tester.widget<UiButton>(uiButton('Correct value')).onPressed,
      isNull,
    );
    expect(find.text('United States of America'), findsOneWidget);
    expect(
      find.text('The server sent a field state this app does not recognize'),
      findsOneWidget,
    );
  });

  testWidgets('field evidence focus keeps specimen data selected', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    final record = Specimen({
      ...specimen.data,
      'disposition': 'needs_human_review',
      'available_actions': ['field', 'transcription', 'coverage'],
      'assets': [
        {
          'width': 1000,
          'height': 520,
          'preview_bytes': File(
            'test/fixtures/synthetic-wide-label.png',
          ).readAsBytesSync(),
        },
      ],
      'regions': [
        {
          'region_id': 'r1',
          'bbox': [100, 52, 400, 212],
        },
        {
          'region_id': 'r2',
          'bbox': [420, 52, 700, 212],
        },
      ],
    });
    await tester.pumpWidget(
      workbenchHost(
        ReviewWorkbench(
          specimen: record,
          onChange: (_) async => fail('Field inspection must not save'),
          onRetry: (_) async => fail('Field inspection must not retry'),
          onRefresh: () => fail('Field inspection must not refresh'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    WorkbenchSourcePane source() =>
        tester.widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane));
    UiTabs tabs() => tester.widget<UiTabs>(uiTabs('Record view'));
    expect(tabs().selected.value, 0);
    expect(source().selectedRegionId, isNull);
    await expandField(tester, 'Country');
    expect(source().selectedRegionId, 'r1');
    expect(source().labelReviewActive, isFalse);
    expect(tabs().selected.value, 0);
    await openReviewEditor(tester, 'Country');
    expect(find.text('Correct Country'), findsOneWidget);
    expect(source().selectedRegionId, 'r1');
    expect(tabs().selected.value, 0);
    await tester.ensureVisible(uiButton('Cancel'));
    await tester.pumpAndSettle();
    await tester.tap(uiButton('Cancel'));
    await tester.pumpAndSettle();

    await expandField(tester, 'Precise location');
    expect(source().selectedRegionId, isNull);
    expect(tabs().selected.value, 0);
    await tester.ensureVisible(uiButton('View Label 2'));
    await tester.pumpAndSettle();
    await tester.tap(uiButton('View Label 2'));
    await tester.pumpAndSettle();
    expect(source().selectedRegionId, 'r2');
    expect(tabs().selected.value, 0);
    await expandField(tester, 'Elevation to (ft)');
    expect(source().selectedRegionId, isNull);
    expect(tabs().selected.value, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('permission changes disable staging and retain an open draft', (
    tester,
  ) async {
    String? blocked;
    late StateSetter change;
    var staged = 0;
    await pumpComponent(
      tester,
      StatefulBuilder(
        builder: (context, setState) {
          change = setState;
          return SingleChildScrollView(
            child: WorkbenchFields(
              specimen: specimen,
              anchors: const {},
              pending: const [],
              onPendingChanged: (_) => staged++,
              fieldBlockedReason: blocked,
            ),
          );
        },
      ),
      size: const Size(900, 1600),
    );
    await openReviewEditor(tester, 'Country');
    expect(uiButton('Keep this correction'), findsOneWidget);
    await tester.enterText(uiField('As written'), 'USA draft');
    await tester.pumpAndSettle();
    change(() => blocked = 'Reviewer access is required');
    await tester.pumpAndSettle();
    expect(find.text('Reviewer access is required'), findsOneWidget);
    final keep = tester.widget<UiButton>(uiButton('Keep this correction'));
    expect(keep.onPressed, isNull);
    expect(keep.disabledReason, 'Reviewer access is required');
    expect(
      tester.widget<UiField>(uiField('As written')).controller!.text,
      'USA draft',
    );
    expect(staged, 0);
    change(() => blocked = null);
    await tester.pumpAndSettle();
    expect(
      tester.widget<UiField>(uiField('As written')).controller!.text,
      'USA draft',
    );
    expect(
      tester.widget<UiButton>(uiButton('Keep this correction')).onPressed,
      isNotNull,
    );
  });

  testWidgets(
    'geography details and correction remain usable with large text',
    (tester) async {
      await showFields(
        tester,
        size: const Size(390, 844),
        textScale: 2,
        onFocusRegion: (_) {},
      );
      await expandField(tester, 'Precise location');
      await tester.ensureVisible(uiButton('View Label 2'));
      await tester.pumpAndSettle();
      expect(uiButton('View Label 2').hitTestable(), findsOneWidget);
      expect(tester.takeException(), isNull);
      await openReviewEditor(tester, 'Elevation from (m)');
      expect(find.text('Correct Elevation from (m)'), findsOneWidget);
      await expandField(tester, 'Interpretation and standardization');
      expect(
        find.text('Check the unit and range endpoint against the field name.'),
        findsOneWidget,
      );
      await tester.ensureVisible(uiButton('Keep this correction'));
      await tester.pumpAndSettle();
      expect(uiButton('Keep this correction').hitTestable(), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'record switches close editors and same-record refresh retains text',
    (tester) async {
      var record = specimen;
      late StateSetter change;
      await pumpComponent(
        tester,
        StatefulBuilder(
          builder: (context, setState) {
            change = setState;
            return SingleChildScrollView(
              child: WorkbenchFields(
                specimen: record,
                anchors: const {},
                pending: const [],
                onPendingChanged: (_) => fail('A record switch must not stage'),
              ),
            );
          },
        ),
        size: const Size(900, 1600),
      );
      await openReviewEditor(tester, 'Country');
      await tester.enterText(uiField('As written'), 'USA draft');
      await tester.pumpAndSettle();
      change(() => record = Specimen({...specimen.data, 'revision': 2}));
      await tester.pumpAndSettle();
      expect(find.text('Correct Country'), findsOneWidget);
      expect(
        tester.widget<UiField>(uiField('As written')).controller!.text,
        'USA draft',
      );
      change(
        () => record = Specimen({
          ...specimen.data,
          'specimen_id': 'synthetic-field-review-next',
        }),
      );
      await tester.pumpAndSettle();
      expect(find.text('Correct Country'), findsNothing);
      expect(uiField('As written'), findsNothing);
      expect(
        find.text('Supported · United States of America · Required'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );
}
