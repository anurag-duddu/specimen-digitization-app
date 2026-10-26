import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_ui/specimen_ui.dart';

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
      'normalized': '6400.00',
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
  'Date visited from': 'Settled',
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
  bool dark = false,
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
  theme: productThemes[dark ? 'dark' : 'light'],
);

Future<void> toggleField(WidgetTester tester, String name) async {
  final header = find
      .descendant(
        of: uiDisclosure(name),
        matching: find.byWidgetPredicate((widget) => widget is Pressable),
      )
      .first;
  await tester.ensureVisible(header);
  await tester.tap(header);
  await tester.pumpAndSettle();
}

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

  testWidgets(
    'each field keeps compact provenance visible before and after expansion',
    (tester) async {
      await show(tester);

      for (final entry in chipOf.entries) {
        expect(
          tester.widget<UiDisclosure>(uiDisclosure(entry.key)).metadata,
          entry.value,
          reason: entry.key,
        );
        for (final expanded in [false, true]) {
          if (expanded) await toggleField(tester, entry.key);
          if (entry.value != null) {
            expect(
              find.descendant(
                of: uiDisclosure(entry.key),
                matching: find.text('· ${entry.value!}'),
              ),
              findsOneWidget,
              reason: '${entry.key} provenance visible exactly once',
            );
          }
        }
        await toggleField(tester, entry.key);
      }
      expect(find.byType(UiChip), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('values lead while exceptional field states stay explicit', (
    tester,
  ) async {
    await show(tester);

    expect(find.text('Philippines'), findsOneWidget);
    expect(find.text('Unknown'), findsNWidgets(7));
    expect(find.text('Ambiguous · F.G. Werner'), findsOneWidget);
    expect(find.text('Carabidae'), findsOneWidget);
    expect(find.textContaining('to review'), findsNothing);
    expect(find.textContaining('Needs review'), findsNothing);
  });

  testWidgets('section counts prioritize review and missing independently', (
    tester,
  ) async {
    await show(tester);
    for (final (group, summary) in [
      ('IDs', '0 review · 0 missing'),
      ('Collection', '5 review · 4 missing'),
      ('Date', '2 review · 2 missing'),
      ('Taxa', '1 review · 1 missing'),
    ]) {
      expect(
        tester
            .widget<Text>(find.byKey(ValueKey('field-group-count:$group')))
            .data,
        summary,
      );
    }
    final country = tester.widget<UiDisclosure>(uiDisclosure('Country'));
    final collectors = tester.widget<UiDisclosure>(uiDisclosure('Collectors'));
    expect(country.collapsedIcon, UiIcons.check);
    expect(collectors.collapsedIcon, isNull);
    final ui = tester.element(uiDisclosure('Country')).ui;
    expect(country.style!.summaryColor, ui.color.inkSecondary);
    expect(collectors.style!.summaryColor, ui.color.ink);
  });

  testWidgets(
    'findings, absent values and pending corrections never gain a completion check',
    (tester) async {
      await show(
        tester,
        specimen: Specimen({
          'specimen_id': 'attention',
          'regions': const [],
          'validation_findings': [
            {'field_key': 'country', 'reason_code': 'evidence_missing'},
            {
              'field_key': 'country',
              'reason_code': 'mandatory_evidence_unresolved',
            },
          ],
          'fields': [
            _field('country', {
              'state': 'supported',
              'literal_value': 'Philippines',
            }),
            _field('city', {'state': 'not_present'}),
            _field('county', {'state': 'not_applicable'}),
            _field('province_state', {'state': 'supported'}),
          ],
        }),
      );
      expect(find.text('2 review · 2 missing'), findsOneWidget);
      for (final name in ['Country', 'City', 'County', 'Province or state']) {
        expect(
          tester.widget<UiDisclosure>(uiDisclosure(name)).collapsedIcon,
          isNull,
        );
      }
      expect(find.textContaining('needs supporting evidence'), findsNothing);
      await toggleField(tester, 'Country');
      expect(find.textContaining('needs supporting evidence'), findsWidgets);
    },
  );

  testWidgets(
    'informational provenance stays visible in details without changing review counts',
    (tester) async {
      await show(
        tester,
        specimen: Specimen({
          'specimen_id': 'contextual-notes',
          'regions': const [],
          'fields': [
            _field('country', {
              'state': 'supported',
              'literal_value': 'Philippines',
            }),
          ],
          'validation_findings': [
            {
              'field_key': 'country',
              'severity': 'info',
              'rule_id': 'transcript_literal',
              'message': 'The label states P.I.',
            },
            {
              'field_key': 'country',
              'severity': 'warning',
              'rule_id': 'normalization_note',
              'message': 'Original punctuation is retained.',
            },
          ],
        }),
      );
      expect(find.text('0 review · 0 missing'), findsOneWidget);
      expect(
        tester.widget<UiDisclosure>(uiDisclosure('Country')).collapsedIcon,
        UiIcons.check,
      );
      await toggleField(tester, 'Country');
      expect(find.text('The label states P.I.'), findsOneWidget);
      expect(find.text('Original punctuation is retained.'), findsOneWidget);
    },
  );

  for (final dark in [false, true]) {
    testWidgets(
      'all four groups remain readable at320px and200percent dark=$dark',
      (tester) async {
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await show(tester, size: const Size(320, 9000), dark: dark);
        for (final entry in chipOf.entries) {
          final row = uiDisclosure(entry.key);
          if (entry.value != null) {
            final metadata = find.descendant(
              of: row,
              matching: find.text('· ${entry.value}'),
            );
            expect(
              tester.renderObject<RenderParagraph>(metadata).didExceedMaxLines,
              isFalse,
            );
          }
        }
        expect(tester.takeException(), isNull);
        await expectAccessible(tester);
      },
    );
  }

  for (final (width, gap) in [(390.0, 32.0), (900.0, 48.0)]) {
    testWidgets('field groups keep a clear section break at $width', (
      tester,
    ) async {
      await show(tester, size: Size(width, 9000));
      final ids = find.byKey(const ValueKey('field-group:IDs'));
      final collection = find.byKey(const ValueKey('field-group:Collection'));
      expect(
        tester.getTopLeft(collection).dy - tester.getBottomLeft(ids).dy,
        gap,
      );
    });
  }

  testWidgets('a screen reader hears the basis with the row', (tester) async {
    final handle = tester.ensureSemantics();
    await show(tester);

    expect(
      find.bySemanticsLabel(
        'Country, required. Supported. Philippines. '
        'Basis: derived',
      ),
      findsOneWidget,
    );
    expect(
      find.bySemanticsLabel(
        'Habitat, optional. Supported. Mossy forest. Basis: inferred',
      ),
      findsOneWidget,
    );
    // A row with no chip says nothing about a basis.
    expect(
      find.bySemanticsLabel('City, optional. Supported. Manila'),
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
        matching: find.byType(UiChip),
      ),
      findsNothing,
    );
    await toggleField(tester, 'Country');
    expect(find.byType(UiChip), findsNothing);
    expect(find.textContaining('Not saved yet:'), findsOneWidget);
    await toggleField(tester, 'Habitat');
    expect(
      find.descendant(
        of: uiDisclosure('Habitat'),
        matching: find.text('· Inferred'),
      ),
      findsOneWidget,
    );
  });

  /// How much of [name]'s title the row draws, against what it needs.
  ///
  /// The title is a label, which ellipsises rather than wraps, so a title that
  /// lost a letter to the chip beside it shows as drawn narrower than needed.
  void expectWholeTitle(WidgetTester tester, String name, String where) {
    final Finder title = find.descendant(
      of: uiDisclosure(name),
      matching: find.text(name),
    );
    expect(title, findsOneWidget, reason: '$name $where');
    final RenderParagraph paragraph = tester.renderObject<RenderParagraph>(
      title,
    );
    final TextPainter painter = TextPainter(
      text: paragraph.text,
      textDirection: TextDirection.ltr,
      textScaler: paragraph.textScaler,
      maxLines: 1,
    )..layout();
    final double needed = painter.width;
    painter.dispose();
    expect(paragraph.didExceedMaxLines, isFalse, reason: '$name $where');
    expect(
      paragraph.size.width,
      greaterThanOrEqualTo(needed - 0.5),
      reason: '$name $where is ellipsised',
    );
  }

  for (final (double width, double scale) in <(double, double)>[
    (390, 2.0),
    (320, 1.0),
  ]) {
    testWidgets('at $width wide and ${scale}x text no title is cut short', (
      tester,
    ) async {
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await show(tester, size: Size(width, 9000));

      expect(tester.takeException(), isNull, reason: 'nothing overflows');
      expect(find.byType(UiChip), findsNothing);
      for (final name in chipOf.keys) {
        expectWholeTitle(tester, name, 'at $width wide, ${scale}x');
        final text = tester.widget<UiDisclosure>(uiDisclosure(name)).summary!;
        final summary = find.descendant(
          of: uiDisclosure(name),
          matching: find.text(text),
        );
        expect(summary, findsOneWidget);
        expect(
          tester.renderObject<RenderParagraph>(summary).didExceedMaxLines,
          isFalse,
          reason: '$name value or state remains readable at $width/$scale',
        );
      }
    });
  }

  testWidgets(
    'basis stays visible without crowding the value at enlarged text',
    (tester) async {
      for (final scale in [1.0, 2.0]) {
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await tester.pumpWidget(const SizedBox.shrink());
        await show(tester, size: const Size(390, 9000));
        expect(
          tester.widget<UiDisclosure>(uiDisclosure('Country')).metadata,
          'Derived',
        );
        await toggleField(tester, 'Country');
        final chip = find.descendant(
          of: uiDisclosure('Country'),
          matching: find.text('· Derived'),
        );
        expect(chip, findsOneWidget);
        expect(
          tester.getTopLeft(chip).dy,
          greaterThanOrEqualTo(tester.getTopLeft(find.text('Country')).dy),
        );
        expect(tester.takeException(), isNull);
      }
    },
  );

  testWidgets('a narrow window at double text size leaves no overflow', (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await show(tester, size: const Size(320, 9000));

    expect(find.byType(UiChip), findsNothing);
    await toggleField(tester, 'Province or state');
    expect(
      find.descendant(
        of: uiDisclosure('Province or state'),
        matching: find.text('· As written'),
      ),
      findsOneWidget,
    );
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
    expect(find.byType(UiChip), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
