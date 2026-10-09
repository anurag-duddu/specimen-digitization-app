import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/value_basis_chip.dart';

import '../ui_finders.dart';
import '../widgets/harness.dart';

// The data tab shows the field model v2's four groups, and a basis on each row
// that has one. The record is a fixture of the 20 keys the server writes today:
// the basis comes from the layer and the stored values, with one field stating
// its own basis the way a later writer would. The server and the thread reader
// are not involved.

const Map<String, dynamic> _written = {'state': 'supported'};

Json _field(String key, Map<String, dynamic> data) => {
  'field_key': key,
  ...data,
};

final Specimen fixture = Specimen({
  'specimen_id': 'four-groups',
  'regions': const [
    {'region_id': 'label-one'},
  ],
  // Deliberately not in group order: the wire's order is not a reading order.
  'fields': <Json>[
    _field('taxon', {
      ..._written,
      'layer': 'settled',
      'literal_value': 'Carabidae',
      'normalized': 'Carabidae',
    }),
    _field('verbatim_dts', {'state': 'unknown'}),
    _field('collectors', {
      'state': 'ambiguous',
      'layer': 'verbatim',
      'literal_value': 'F.G. Werner',
    }),
    _field('country', {
      ..._written,
      'required': true,
      'layer': 'settled',
      'literal_value': 'P.I.',
      'normalized': 'Philippines',
    }),
    _field('collection_code', {
      ..._written,
      'layer': 'settled',
      'literal_value': 'INS',
      'normalized': 'ins',
    }),
    _field('date_visited_to', {
      ..._written,
      'layer': 'derived',
      'literal_value': "3 Sept. '46",
      'normalized': '1946-09-03',
      'derived_from': ['date_visited_from'],
    }),
    _field('fmnh_ins_number', {
      ..._written,
      'layer': 'verbatim',
      'literal_value': 'FMNH-INS-105526321',
    }),
    _field('county', {'state': 'unknown', 'required': true}),
    _field('elevation_from_m', {
      ..._written,
      'layer': 'derived',
      'literal_value': "6400'",
      'normalized': '1950.72',
      'derived_from': ['elevation_from_ft'],
    }),
    _field('city', {..._written, 'literal_value': 'Manila'}),
    _field('province_state', {
      ..._written,
      'layer': 'settled',
      'literal_value': 'Davao',
      'normalized': 'Davao',
    }),
    _field('elevation_from_ft', {
      ..._written,
      'layer': 'settled',
      'literal_value': "6400'",
      'parsed_value': '6400',
    }),
    _field('precise_location', {
      ..._written,
      'layer': 'settled',
      'normalized': 'E. slope Mt. McKinley',
      'verbatim_by_observation': {'reader-a': 'E. slope Mt. McKinley'},
    }),
    _field('habitat', {
      ..._written,
      'layer': 'verbatim',
      'literal_value': 'Mossy forest',
      'basis': 'inferred',
    }),
    _field('date_visited_from', {
      ..._written,
      'layer': 'settled',
      'literal_value': "3 Sept. '46",
      'normalized': '1946-09-03',
    }),
    _field('elevation_to_m', {'state': 'unknown'}),
    _field('elevation_to_ft', {'state': 'unknown'}),
    _field('collection_method', {'state': 'unknown'}),
    _field('date_identified', {'state': 'unknown'}),
    _field('identified_by_irn', {'state': 'unknown'}),
  ],
});

/// Each field's name on screen, and the chip it shows, or null for none.
const Map<String, String?> chipOf = {
  'FMNH INS number': 'As written',
  'Collection code': 'As written',
  'Country': 'Derived',
  'Province or state': 'As written',
  'County': null,
  'City': null,
  'Precise location': 'As written',
  'Elevation from (m)': 'Derived',
  'Elevation to (m)': null,
  'Elevation from (ft)': 'As written',
  'Elevation to (ft)': null,
  'Collectors': 'As written',
  'Habitat': 'Inferred',
  'Collection method': null,
  'Date visited from': 'Derived',
  'Date visited to': 'Derived',
  'Date identified': null,
  'Verbatim D/T/S': null,
  'Taxon': 'As written',
  'Identified by IRN': null,
};

/// The four groups, in order, with the names of the fields each holds.
const Map<String, List<String>> groups = {
  'IDs': ['FMNH INS number', 'Collection code'],
  'Collection': [
    'Country',
    'Province or state',
    'County',
    'City',
    'Precise location',
    'Elevation from (m)',
    'Elevation to (m)',
    'Elevation from (ft)',
    'Elevation to (ft)',
    'Collectors',
    'Habitat',
    'Collection method',
  ],
  'Date': [
    'Date visited from',
    'Date visited to',
    'Date identified',
    'Verbatim D/T/S',
  ],
  'Taxa': ['Taxon', 'Identified by IRN'],
};

Future<void> show(
  WidgetTester tester, {
  Specimen? specimen,
  List<PendingFieldChange> pending = const [],
  Size size = const Size(900, 2600),
}) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: WorkbenchFields(
      specimen: specimen ?? fixture,
      anchors: const {},
      pending: pending,
      onPendingChanged: (_) =>
          fail('Inspecting fields must not stage a change'),
    ),
  ),
  size: size,
);

double top(WidgetTester tester, Finder finder) => tester.getTopLeft(finder).dy;

void main() {
  testWidgets('the specimen data tab shows the four groups in order', (
    tester,
  ) async {
    await show(tester);

    final headers = [
      for (final title in groups.keys)
        top(tester, find.byKey(ValueKey<String>('field-group:$title'))),
    ];
    expect(groups.keys, ['IDs', 'Collection', 'Date', 'Taxa']);
    expect(headers, orderedEquals([...headers]..sort()));
    expect(headers.toSet(), hasLength(4));
    expect(
      find.byKey(const ValueKey<String>('field-group:Other')),
      findsNothing,
    );

    // Every field is drawn once, inside its own group, whatever the wire order.
    for (final (index, entry) in groups.entries.indexed) {
      final start = headers[index];
      final end = index + 1 < headers.length ? headers[index + 1] : 1e9;
      for (final name in entry.value) {
        expect(uiDisclosure(name), findsOneWidget, reason: name);
        final y = top(tester, uiDisclosure(name));
        expect(y, greaterThan(start), reason: '$name below ${entry.key}');
        expect(y, lessThan(end), reason: '$name above the next group');
      }
    }
    expect(
      uiDisclosure(RegExp('.')).evaluate().length,
      chipOf.length,
      reason: 'twenty rows and no others',
    );
  });

  testWidgets('each row carries the basis its layer and values give', (
    tester,
  ) async {
    await show(tester);

    for (final entry in chipOf.entries) {
      final chips = find.descendant(
        of: uiDisclosure(entry.key),
        matching: find.byType(ValueBasisChip),
      );
      if (entry.value == null) {
        expect(chips, findsNothing, reason: '${entry.key} has no chip');
      } else {
        expect(chips, findsOneWidget, reason: entry.key);
        expect(
          find.descendant(
            of: uiDisclosure(entry.key),
            matching: uiChip(entry.value!),
          ),
          findsOneWidget,
          reason: '${entry.key} reads ${entry.value}',
        );
      }
    }
    expect(find.byType(ValueBasisChip), findsNWidgets(12));
    expect(uiChip('As written'), findsNWidgets(7));
    expect(uiChip('Derived'), findsNWidgets(4));
    expect(uiChip('Inferred'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the review state reads exactly as it did without a chip', (
    tester,
  ) async {
    await show(tester);

    expect(find.text('Supported · Philippines · Required'), findsOneWidget);
    expect(find.text('Needs review · Unknown · Required'), findsOneWidget);
    expect(find.text('Needs review · Ambiguous · F.G. Werner'), findsOneWidget);
    expect(find.text('Supported · Carabidae'), findsOneWidget);
    // Each group's own count is untouched too: IDs has none.
    expect(find.text('5 to review'), findsOneWidget);
    expect(find.text('2 to review'), findsOneWidget);
    expect(find.text('1 to review'), findsOneWidget);
    expect(find.textContaining('to review'), findsNWidgets(3));
  });

  testWidgets('a screen reader hears the basis with the row', (tester) async {
    final handle = tester.ensureSemantics();
    await show(tester);

    expect(
      find.bySemanticsLabel(
        'Country, required. Supported · Philippines · Required. '
        'Basis: derived',
      ),
      findsOneWidget,
    );
    expect(
      find.bySemanticsLabel(
        'Habitat, optional. Supported · Mossy forest. Basis: inferred',
      ),
      findsOneWidget,
    );
    // A row with no chip says nothing about a basis.
    expect(
      find.bySemanticsLabel('City, optional. Supported · Manila'),
      findsOneWidget,
    );
    expect(
      find.bySemanticsLabel(RegExp('Basis: as written')),
      findsNWidgets(7),
    );
    handle.dispose();
  });

  testWidgets('the chip leaves the targets and labels guidelines intact', (
    tester,
  ) async {
    await show(tester);
    await expectAccessible(tester);
  });

  testWidgets('a correction not yet saved is not drawn over the stored basis', (
    tester,
  ) async {
    await show(
      tester,
      pending: const [
        PendingFieldChange(
          fieldKey: 'country',
          displayName: 'Country',
          state: 'supported',
          literal: 'P.I.',
          normalized: 'Philippines',
        ),
      ],
    );
    expect(
      find.descendant(
        of: uiDisclosure('Country'),
        matching: find.byType(ValueBasisChip),
      ),
      findsNothing,
    );
    expect(find.byType(ValueBasisChip), findsNWidgets(11));
  });

  testWidgets('a narrow window at double text size keeps every chip whole', (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await show(tester, size: const Size(320, 6000));

    expect(find.byType(ValueBasisChip), findsNWidgets(12));
    expect(uiChip('As written'), findsNWidgets(7));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a record with no layer and no stated basis shows no chip', (
    tester,
  ) async {
    await show(
      tester,
      specimen: Specimen({
        'specimen_id': 'unlayered',
        'regions': const [],
        'fields': <Json>[
          _field('country', {
            ..._written,
            'literal_value': 'P.I.',
            'normalized': 'Philippines',
          }),
          // A basis the app does not know is not guessed around.
          _field('city', {
            ..._written,
            'layer': 'verbatim',
            'literal_value': 'Manila',
            'basis': 'estimated',
          }),
        ],
      }),
    );
    expect(uiDisclosure('Country'), findsOneWidget);
    expect(find.byType(ValueBasisChip), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
