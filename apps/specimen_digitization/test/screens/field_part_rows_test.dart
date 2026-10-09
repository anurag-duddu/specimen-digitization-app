import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/part_rows.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widgets/harness.dart';
import 'field_parts_fixture.dart';

// The rows a field with parts opens into. The records are the worked examples
// of the planned wire contract: the place tree of subject 105526321, with its
// named place flagged for a person, and the elevation of subject 105526322,
// whose unit is inferred. The server does not write `parts` yet, so a record
// today has none, and the first group of tests pins that nothing changes for it.

Future<void> show(
  WidgetTester tester,
  Specimen specimen, {
  Size size = const Size(900, 3200),
  List<PendingFieldChange> pending = const <PendingFieldChange>[],
  String? blockedReason,
  bool reduceMotion = false,
  Key? boundary,
}) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: RepaintBoundary(
      key: boundary,
      child: WorkbenchFields(
        specimen: specimen,
        anchors: const <String, GlobalKey>{},
        pending: pending,
        onPendingChanged: (_) {},
        fieldBlockedReason: blockedReason,
      ),
    ),
  ),
  size: size,
  reduceMotion: reduceMotion,
);

/// Opens a field's own row, as a reviewer does with a tap on its header.
Future<void> openField(
  WidgetTester tester,
  Specimen specimen,
  String key,
) async {
  final Finder row = find.byKey(
    ValueKey<String>('field-row:${specimen.id}:$key'),
  );
  expect(row, findsOneWidget, reason: key);
  final Finder header = find
      .descendant(
        of: row,
        matching: find.byWidgetPredicate(
          (Widget w) => w is Pressable && w.onPressed != null,
        ),
      )
      .first;
  await tester.ensureVisible(header);
  await tester.tap(header);
  await tester.pumpAndSettle();
}

Finder partRow(Specimen specimen, String field, String path) =>
    find.byKey(ValueKey<String>('part-row:${specimen.id}:$field:$path'));

/// The press target in a part row's header, the first control in the row.
Finder partHeader(Finder row) => find
    .descendant(
      of: row,
      matching: find.byWidgetPredicate(
        (Widget w) => w is Pressable && w.onPressed != null,
      ),
    )
    .first;

List<String> chipsIn(WidgetTester tester, Finder row) => <String>[
  for (final UiChip chip in tester.widgetList<UiChip>(
    find.descendant(of: row, matching: find.byType(UiChip)),
  ))
    chip.label,
];

Finder textIn(Finder row, Object text) => find.descendant(
  of: row,
  matching: text is RegExp ? find.textContaining(text) : find.text('$text'),
);

Finder whyIn(Finder row) => find.descendant(of: row, matching: uiButton('Why'));

Future<void> tapIn(WidgetTester tester, Finder target) async {
  await tester.ensureVisible(target);
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}

const List<String> placePaths = <String>[
  'location/country',
  'location/island',
  'location/province',
  'location/place',
];

void main() {
  group('a field without parts draws exactly as it did before', () {
    Specimen withParts(Object? parts) => Specimen(<String, dynamic>{
      'specimen_id': 'plain',
      'regions': const <Map<String, dynamic>>[
        <String, dynamic>{'region_id': 'label-one'},
      ],
      'fields': <Map<String, dynamic>>[
        workspaceField(
          'precise_location',
          layer: 'verbatim',
          literal: locality,
          evidenceIds: <String>['ev-2A-locality'],
          parts: parts,
        ),
        workspaceField('country', layer: 'verbatim', literal: 'Philippines'),
      ],
      'evidence': partEvidence(),
    });

    Future<Uint8List> paint(
      WidgetTester tester,
      Specimen specimen, {
      bool hasParts = false,
    }) async {
      const Key boundary = ValueKey<String>('paint');
      await tester.pumpWidget(const SizedBox());
      await show(
        tester,
        specimen,
        size: const Size(900, 1400),
        boundary: boundary,
      );
      await openField(tester, specimen, 'precise_location');
      expect(
        find.byType(FieldPartRows),
        hasParts ? findsOneWidget : findsNothing,
      );
      final RenderRepaintBoundary render = tester
          .renderObject<RenderRepaintBoundary>(find.byKey(boundary));
      final Uint8List? bytes = await tester.runAsync(() async {
        final ui.Image image = await render.toImage();
        final ByteData? data = await image.toByteData();
        image.dispose();
        return data!.buffer.asUint8List();
      });
      return bytes!;
    }

    testWidgets(
      'the field is the same with no parts as with parts it cannot use',
      (tester) async {
        final Uint8List plain = await paint(tester, withParts(null));
        expect(plain, isNotEmpty);

        // The comparison can tell: the same field with parts it can use draws
        // differently.
        final Uint8List drawn = await paint(
          tester,
          withParts(locationParts()),
          hasParts: true,
        );
        expect(listEquals(drawn, plain), isFalse);

        final Map<String, Object?> unusable = <String, Object?>{
          'an empty list': <Object?>[],
          'a value that is not a list': 'location/country',
          'a list of nothing but paths a later release adds': <Object?>[
            <String, dynamic>{'path': 'habitat/text', 'state': 'supported'},
            <String, dynamic>{'path': 'identified_by/1', 'state': 'supported'},
          ],
          'parts that break a rule': <Object?>[
            <String, dynamic>{...locationParts().first, 'state': 'probably'},
          ],
          'parts on a field that does not carry them': locationParts(),
        };
        for (final MapEntry<String, Object?> entry in unusable.entries) {
          final Specimen specimen =
              entry.key == 'parts on a field that does not carry them'
              ? Specimen(<String, dynamic>{
                  'specimen_id': 'plain',
                  'regions': const <Map<String, dynamic>>[
                    <String, dynamic>{'region_id': 'label-one'},
                  ],
                  'fields': <Map<String, dynamic>>[
                    workspaceField(
                      'precise_location',
                      layer: 'verbatim',
                      literal: locality,
                      evidenceIds: <String>['ev-2A-locality'],
                    ),
                    workspaceField(
                      'country',
                      layer: 'verbatim',
                      literal: 'Philippines',
                      parts: entry.value,
                    ),
                  ],
                  'evidence': partEvidence(),
                })
              : withParts(entry.value);
          final Uint8List drawn = await paint(tester, specimen);
          expect(
            listEquals(drawn, plain),
            isTrue,
            reason: '${entry.key} changes nothing on the screen',
          );
        }
        await tester.pumpWidget(const SizedBox());
      },
    );

    testWidgets(
      'no section, no chip and no count appear for a record with none',
      (tester) async {
        await show(tester, withParts(null));
        await openField(tester, withParts(null), 'precise_location');
        expect(find.text(FieldPartRows.heading), findsNothing);
        expect(find.text(FieldPartRows.checkChipLabel), findsNothing);
        expect(find.textContaining('to check'), findsNothing);
        expect(
          find.byType(UiChip),
          findsWidgets,
          reason: 'the basis chips stay',
        );
        expect(tester.takeException(), isNull);
      },
    );
  });

  group('subject 105526321: the place tree', () {
    final Specimen subject = subject105526321();

    testWidgets('a field with parts opens into one row per part, in tree order', (
      tester,
    ) async {
      await show(tester, subject);
      expect(find.text(FieldPartRows.heading), findsNothing, reason: 'closed');
      await openField(tester, subject, 'precise_location');

      expect(find.text(FieldPartRows.heading), findsOneWidget);
      expect(find.text(FieldPartRows.toCheck(1)), findsOneWidget);
      final List<double> tops = <double>[];
      final List<double> starts = <double>[];
      for (final String path in placePaths) {
        final Finder row = partRow(subject, 'precise_location', path);
        expect(row, findsOneWidget, reason: path);
        tops.add(tester.getTopLeft(row).dy);
        starts.add(
          tester
              .getTopLeft(
                find.descendant(of: row, matching: find.byType(UiLabel)).first,
              )
              .dx,
        );
      }
      expect(
        tops,
        orderedEquals(<double>[...tops]..sort()),
        reason: 'top to bottom',
      );
      expect(tops.toSet(), hasLength(4));
      // The named place sits under the province, the province under the island,
      // the island under the country: each is indented further than its parent.
      expect(starts[0], lessThan(starts[1]));
      expect(starts[1], lessThan(starts[2]));
      expect(starts[2], lessThan(starts[3]));
      expect(find.byType(FieldPartRows), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('each part names its level and carries one basis chip', (
      tester,
    ) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');

      const Map<String, (String, String, List<String>)> expected =
          <String, (String, String, List<String>)>{
            'location/country': ('Country', 'Philippines', <String>['Derived']),
            'location/island': ('Island', 'Mindanao', <String>['As written']),
            'location/province': ('Province', 'Davao', <String>['As written']),
            'location/place': (
              'Named place',
              'Mt. McKinley',
              <String>['As written', 'Check this part'],
            ),
          };
      for (final MapEntry<String, (String, String, List<String>)> entry
          in expected.entries) {
        final Finder row = partRow(subject, 'precise_location', entry.key);
        expect(textIn(row, entry.value.$1), findsOneWidget, reason: entry.key);
        expect(textIn(row, entry.value.$2), findsOneWidget, reason: entry.key);
        expect(chipsIn(tester, row), entry.value.$3, reason: entry.key);
        final int basisChips = chipsIn(tester, row)
            .where(
              (String c) =>
                  <String>['As written', 'Derived', 'Inferred'].contains(c),
            )
            .length;
        expect(
          basisChips,
          1,
          reason: '${entry.key} has exactly one basis chip',
        );
      }
    });

    testWidgets('the check chip is neutral, never a status colour', (
      tester,
    ) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');
      final UiChip check = tester.widget<UiChip>(
        find.descendant(
          of: partRow(subject, 'precise_location', 'location/place'),
          matching: uiChip(FieldPartRows.checkChipLabel),
        ),
      );
      expect(check.status, isNull, reason: 'a data question is not an error');
      expect(check.variant, UiChipVariant.tag);
      expect(check.label.length, lessThanOrEqualTo(20));
    });

    testWidgets('the original wording sits beneath an interpreted value', (
      tester,
    ) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');

      const Map<String, String?> wording = <String, String?>{
        'location/country': 'P.I.',
        'location/island': null,
        'location/province': 'Davao Prov.',
        'location/place': 'E. slope Mt. McKinley',
      };
      for (final MapEntry<String, String?> entry in wording.entries) {
        final Finder row = partRow(subject, 'precise_location', entry.key);
        final Finder line = textIn(
          row,
          RegExp('^${FieldPartRows.writtenPrefix}'),
        );
        if (entry.value == null) {
          expect(
            line,
            findsNothing,
            reason: '${entry.key} has no wording of its own',
          );
          continue;
        }
        expect(
          textIn(row, '${FieldPartRows.writtenPrefix}${entry.value}'),
          findsOneWidget,
          reason: entry.key,
        );
        // Beneath the value, in the same header.
        final double value = tester
            .getTopLeft(
              textIn(
                row,
                entry.key == 'location/country'
                    ? 'Philippines'
                    : entry.key == 'location/province'
                    ? 'Davao'
                    : 'Mt. McKinley',
              ),
            )
            .dy;
        expect(
          tester.getTopLeft(line).dy,
          greaterThan(value),
          reason: entry.key,
        );
      }
    });

    testWidgets('only the part a person is asked about opens by default', (
      tester,
    ) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');

      final Finder place = partRow(
        subject,
        'precise_location',
        'location/place',
      );
      expect(whyIn(place), findsOneWidget, reason: 'the flagged part is open');
      expect(
        find.descendant(
          of: place,
          matching: uiButton(FieldPartRows.correctLabel),
        ),
        findsOneWidget,
      );
      for (final String path in <String>[
        'location/country',
        'location/island',
        'location/province',
      ]) {
        final Finder row = partRow(subject, 'precise_location', path);
        expect(whyIn(row), findsNothing, reason: '$path stays closed');
        expect(
          find.descendant(
            of: row,
            matching: uiButton(FieldPartRows.correctLabel),
          ),
          findsNothing,
          reason: '$path is not asked about',
        );
      }
      expect(whyIn(find.byType(FieldPartRows)), findsOneWidget);
    });

    testWidgets('a reviewer opens any part, and Why lists what it rests on', (
      tester,
    ) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');

      final Finder country = partRow(
        subject,
        'precise_location',
        'location/country',
      );
      await tapIn(tester, partHeader(country));
      expect(whyIn(country), findsOneWidget);
      expect(find.text('Readings'), findsNothing, reason: 'Why is closed');

      await tapIn(tester, whyIn(country));
      expect(textIn(country, 'Readings'), findsOneWidget);
      expect(
        textIn(country, locality),
        findsNWidgets(2),
        reason: 'both readings',
      );
      expect(textIn(country, 'Lookups'), findsOneWidget);
      expect(textIn(country, 'Getty TGN: Philippines'), findsOneWidget);
      expect(textIn(country, 'Rules and checks'), findsOneWidget);
      expect(
        textIn(
          country,
          RegExp(r'^P\.I\. stands for Philippine Islands.* · decides$'),
        ),
        findsOneWidget,
        reason: 'the rule that made it derived, and that it decided',
      );
      expect(textIn(country, 'Reasoning'), findsNothing, reason: 'none cited');

      // Why shuts again.
      await tapIn(tester, whyIn(country));
      expect(textIn(country, 'Readings'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'the flagged part says why in the writer own words, then what it cites',
      (tester) async {
        await show(tester, subject);
        await openField(tester, subject, 'precise_location');
        final Finder place = partRow(
          subject,
          'precise_location',
          'location/place',
        );
        await tapIn(tester, whyIn(place));

        final Finder reason = textIn(
          place,
          RegExp('^No approved source holds this mountain'),
        );
        expect(reason, findsOneWidget);
        expect(
          tester.getTopLeft(reason).dy,
          lessThan(tester.getTopLeft(textIn(place, 'Readings')).dy),
          reason: 'the reason comes before the evidence',
        );
        expect(
          textIn(place, 'GEOLocate: Denali · disagrees'),
          findsOneWidget,
          reason: 'the lookup that refused the candidate',
        );
      },
    );

    testWidgets(
      'a part nothing supports says so and shows its state in words',
      (tester) async {
        final List<Map<String, dynamic>> parts = locationParts();
        parts[1]
          ..remove('value')
          ..remove('basis')
          ..['state'] = 'unresolved'
          ..['evidence_ids'] = <String>[]
          ..['evidence_relations'] = <String, String>{}
          ..['review'] = <String, dynamic>{
            'code': 'no_support',
            'reason': 'No source supports an island for this label.',
          };
        final Specimen unsupported = Specimen(<String, dynamic>{
          ...subject.data,
          'fields': <Map<String, dynamic>>[
            workspaceField(
              'precise_location',
              layer: 'verbatim',
              literal: locality,
              evidenceIds: <String>['ev-2A-locality'],
              parts: parts,
            ),
          ],
        });
        await show(tester, unsupported);
        await openField(tester, unsupported, 'precise_location');
        final Finder island = partRow(
          unsupported,
          'precise_location',
          'location/island',
        );
        expect(chipsIn(tester, island), <String>[FieldPartRows.checkChipLabel]);
        expect(
          textIn(island, 'Unresolved'),
          findsOneWidget,
          reason: 'never blank',
        );
        expect(textIn(island, 'No source supports this part.'), findsOneWidget);
        await tapIn(tester, whyIn(island));
        expect(
          textIn(island, 'No source supports an island for this label.'),
          findsOneWidget,
        );
        // The named place is still flagged too.
        expect(find.text(FieldPartRows.toCheck(2)), findsOneWidget);
      },
    );

    testWidgets('a part a person confirmed shows who decided it, not a check', (
      tester,
    ) async {
      final List<Map<String, dynamic>> parts = locationParts();
      parts[2]
        ..remove('review')
        ..['decision'] = <String, dynamic>{
          'event_id': 'evt-1',
          'action': 'accept',
          'actor': 'user-1',
          'at': '2026-10-09T10:00:00Z',
        };
      final Specimen confirmed = Specimen(<String, dynamic>{
        ...subject.data,
        'fields': <Map<String, dynamic>>[
          workspaceField(
            'precise_location',
            layer: 'verbatim',
            literal: locality,
            evidenceIds: <String>['ev-2A-locality'],
            parts: parts,
          ),
        ],
      });
      await show(tester, confirmed);
      await openField(tester, confirmed, 'precise_location');
      final Finder place = partRow(
        confirmed,
        'precise_location',
        'location/place',
      );
      expect(chipsIn(tester, place), <String>[
        'As written',
        FieldPartRows.confirmedChipLabel,
      ]);
      expect(find.text(FieldPartRows.toCheck(1)), findsNothing);
      expect(
        textIn(place, 'user-1'),
        findsNothing,
        reason: 'never the actor id',
      );
      // Nobody is asked, so the field is no longer in review.
      expect(find.textContaining('Needs review'), findsNothing);
    });

    testWidgets('a part a person entered has no basis chip', (tester) async {
      final List<Map<String, dynamic>> parts = locationParts();
      parts[2]
        ..remove('review')
        ..remove('basis')
        ..['value'] = 'Mount Apo'
        ..['evidence_ids'] = <String>[]
        ..['evidence_relations'] = <String, String>{}
        ..['decision'] = <String, dynamic>{
          'event_id': 'evt-2',
          'action': 'edit',
          'actor': 'user-1',
          'at': '2026-10-09T10:00:00Z',
        };
      final Specimen edited = Specimen(<String, dynamic>{
        ...subject.data,
        'fields': <Map<String, dynamic>>[
          workspaceField(
            'precise_location',
            layer: 'verbatim',
            literal: locality,
            evidenceIds: <String>['ev-2A-locality'],
            parts: parts,
          ),
        ],
      });
      await show(tester, edited);
      await openField(tester, edited, 'precise_location');
      final Finder place = partRow(
        edited,
        'precise_location',
        'location/place',
      );
      expect(chipsIn(tester, place), <String>[FieldPartRows.editedChipLabel]);
      expect(textIn(place, 'Mount Apo'), findsOneWidget);
    });

    testWidgets('the field is in review while a part is, and the count says so', (
      tester,
    ) async {
      await show(tester, subject);
      // Precise location, elevation (flagged parts: none) and collectors (one):
      // the group counts the fields a person is asked about.
      expect(find.textContaining(RegExp('^Needs review')), findsNWidgets(2));
      expect(find.text('2 to review'), findsOneWidget);
    });

    testWidgets('correcting a part opens the correction the whole field has', (
      tester,
    ) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');
      final Finder place = partRow(
        subject,
        'precise_location',
        'location/place',
      );
      expect(textIn(place, FieldPartRows.correctNote), findsOneWidget);
      await tapIn(
        tester,
        find.descendant(
          of: place,
          matching: uiButton(FieldPartRows.correctLabel),
        ),
      );

      expect(find.text('Correct Precise location'), findsOneWidget);
      expect(
        find.byType(FieldPartRows),
        findsNothing,
        reason: 'the editor replaces the row',
      );
      expect(uiField('As written'), findsOneWidget);
    });

    testWidgets('a field the server blocks keeps the control but disables it', (
      tester,
    ) async {
      await show(
        tester,
        subject,
        blockedReason: 'Another reviewer saved version 4.',
      );
      await openField(tester, subject, 'precise_location');
      final Finder button = find.descendant(
        of: partRow(subject, 'precise_location', 'location/place'),
        matching: uiButton(FieldPartRows.correctLabel),
      );
      expect(button, findsOneWidget);
      expect(tester.widget<UiButton>(button).onPressed, isNull);
      expect(
        tester.widget<UiButton>(button).disabledReason,
        'Another reviewer saved version 4.',
      );
    });

    testWidgets(
      'a correction not yet saved is not drawn over the stored parts',
      (tester) async {
        await show(
          tester,
          subject,
          pending: const <PendingFieldChange>[
            PendingFieldChange(
              fieldKey: 'precise_location',
              displayName: 'Precise location',
              state: 'supported',
              literal: 'Mt. McKinley, Davao',
            ),
          ],
        );
        await openField(tester, subject, 'precise_location');
        expect(find.byType(FieldPartRows), findsNothing);
        expect(find.text(FieldPartRows.heading), findsNothing);
      },
    );

    testWidgets('a screen reader hears each part as one complete phrase', (
      tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');

      expect(
        find.bySemanticsLabel(
          'Named place, in Province. Mt. McKinley. '
          'As written: E. slope Mt. McKinley. Basis: as written. Check this part',
        ),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(
          'Country. Philippines. As written: P.I.. Basis: derived',
        ),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(
          'Island, in Country. Mindanao. Basis: as written',
        ),
        findsOneWidget,
      );
      // The state of each header is its own, not its chips': the flagged part
      // is open and the others are closed.
      expect(
        tester.getSemantics(find.bySemanticsLabel(RegExp(r'^Named place, in'))),
        containsSemantics(hasExpandedState: true, isExpanded: true),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel(RegExp(r'^Country\. '))),
        containsSemantics(hasExpandedState: true, isExpanded: false),
      );
      handle.dispose();
    });

    testWidgets('the rows leave the targets and labels guidelines intact', (
      tester,
    ) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');
      await tapIn(
        tester,
        whyIn(partRow(subject, 'precise_location', 'location/place')),
      );
      await expectAccessible(tester);
    });
  });

  group('subject 105526321: the collectors', () {
    final Specimen subject = subject105526321();

    testWidgets(
      'a conflict names the readings, with the source as the subject',
      (tester) async {
        await show(tester, subject);
        await openField(tester, subject, 'collectors');
        final Finder row = partRow(subject, 'collectors', 'collectors/1');
        expect(textIn(row, 'Collector 1'), findsOneWidget);
        expect(chipsIn(tester, row), <String>['As written', 'Check this part']);
        expect(
          textIn(row, 'Two readings differ: F.G. Werner, F.G. Wermer.'),
          findsOneWidget,
        );
        await tapIn(tester, whyIn(row));
        expect(textIn(row, 'F.G. Wermer · differs'), findsOneWidget);
        expect(textIn(row, RegExp('^The two readings differ')), findsOneWidget);
      },
    );
  });

  group('subject 105526322: an inferred unit', () {
    final Specimen subject = subject105526322();

    testWidgets(
      'the unit is inferred, and so are the metres that follow from it',
      (tester) async {
        await show(tester, subject);
        await openField(tester, subject, 'elevation_from_m');

        final Finder unit = partRow(
          subject,
          'elevation_from_m',
          'elevation/unit',
        );
        final Finder from = partRow(
          subject,
          'elevation_from_m',
          'elevation/from',
        );
        final Finder kind = partRow(
          subject,
          'elevation_from_m',
          'elevation/kind',
        );
        expect(chipsIn(tester, unit), <String>['Inferred', 'Check this part']);
        expect(chipsIn(tester, from), <String>['Inferred', 'Check this part']);
        expect(chipsIn(tester, kind), <String>['As written']);
        expect(textIn(unit, 'Feet'), findsOneWidget);
        expect(textIn(from, '1950.72 m'), findsOneWidget);
        expect(textIn(from, 'As written: Elev. 6400'), findsOneWidget);
        expect(textIn(kind, 'Point'), findsOneWidget);
        expect(find.text(FieldPartRows.toCheck(2)), findsOneWidget);

        // Both parts a person is asked about are open; the one that is not, is
        // not.
        expect(whyIn(unit), findsOneWidget);
        expect(whyIn(from), findsOneWidget);
        expect(whyIn(kind), findsNothing);
        // The elevation parts are all at the top, in the order the wire gives.
        expect(
          <double>[
            for (final Finder f in <Finder>[from, kind, unit])
              tester.getTopLeft(f).dy,
          ],
          orderedEquals(<double>[
            tester.getTopLeft(from).dy,
            tester.getTopLeft(kind).dy,
            tester.getTopLeft(unit).dy,
          ]),
        );
        expect(
          tester.getTopLeft(from).dy,
          lessThan(tester.getTopLeft(kind).dy),
        );
        expect(
          tester.getTopLeft(kind).dy,
          lessThan(tester.getTopLeft(unit).dy),
        );
        expect(tester.getTopLeft(from).dx, tester.getTopLeft(unit).dx);
      },
    );

    testWidgets(
      'Why lists the readings, the lookup and the one reasoning line',
      (tester) async {
        await show(tester, subject);
        await openField(tester, subject, 'elevation_from_m');
        final Finder unit = partRow(
          subject,
          'elevation_from_m',
          'elevation/unit',
        );
        await tapIn(tester, whyIn(unit));

        expect(
          textIn(unit, RegExp('^Feet is inferred')),
          findsOneWidget,
          reason: 'the writer own words come first',
        );
        expect(textIn(unit, 'Readings'), findsOneWidget);
        expect(textIn(unit, 'Elev. 6400'), findsNWidgets(2));
        expect(textIn(unit, 'Lookups'), findsOneWidget);
        expect(
          textIn(unit, 'Wikidata: Mt. Apo, about 2,954 m'),
          findsOneWidget,
        );
        expect(textIn(unit, 'Rules and checks'), findsOneWidget);
        expect(
          textIn(unit, 'Elevation parser: The elevation has no unit written'),
          findsOneWidget,
        );
        expect(textIn(unit, 'Reasoning'), findsOneWidget);
        expect(
          textIn(
            unit,
            '6400 m would be higher than the highest point in the Philippines, '
            'so the unit is taken as feet',
          ),
          findsOneWidget,
        );
        expect(textIn(unit, 'Follows from: Country'), findsOneWidget);
      },
    );

    testWidgets('a cited row that is not on the record is said so', (
      tester,
    ) async {
      final Specimen thin = Specimen(<String, dynamic>{
        ...subject.data,
        'evidence': <Map<String, dynamic>>[
          for (final Map<String, dynamic> row in partEvidence())
            if (row['evidence_id'] != 'ev-reasoning-unit') row,
        ],
      });
      await show(tester, thin);
      await openField(tester, thin, 'elevation_from_m');
      final Finder unit = partRow(thin, 'elevation_from_m', 'elevation/unit');
      await tapIn(tester, whyIn(unit));
      expect(
        textIn(unit, 'Some cited sources are not in this view.'),
        findsOneWidget,
      );
      expect(textIn(unit, 'Reasoning'), findsNothing);
    });

    testWidgets('the field is in review, and its group counts it', (
      tester,
    ) async {
      await show(tester, subject);
      expect(find.text('Needs review · Unresolved · Required'), findsOneWidget);
      expect(find.text('1 to review'), findsOneWidget);
    });
  });

  group('window size, text size and motion', () {
    final Specimen subject = subject105526321();
    final Specimen inferred = subject105526322();

    /// How much of [text]'s line the row draws, against what it needs: a label
    /// ellipsises rather than wraps, so one that lost a letter is drawn
    /// narrower than it needs.
    void expectWhole(
      WidgetTester tester,
      Finder row,
      String text,
      String where,
    ) {
      final Finder title = textIn(row, text);
      expect(title, findsWidgets, reason: '$text $where');
      final RenderParagraph paragraph = tester.renderObject<RenderParagraph>(
        title.first,
      );
      final TextPainter painter = TextPainter(
        text: paragraph.text,
        textDirection: TextDirection.ltr,
        textScaler: paragraph.textScaler,
        maxLines: 1,
      )..layout();
      final double needed = painter.width;
      painter.dispose();
      expect(paragraph.didExceedMaxLines, isFalse, reason: '$text $where');
      expect(
        paragraph.size.width,
        greaterThanOrEqualTo(needed - 0.5),
        reason: '$text $where is cut short',
      );
    }

    for (final (double width, double scale) in <(double, double)>[
      (390, 1.0),
      (390, 2.0),
      (320, 1.0),
      (320, 2.0),
    ]) {
      testWidgets(
        'at $width wide and ${scale}x text no title or value is cut',
        (tester) async {
          tester.platformDispatcher.textScaleFactorTestValue = scale;
          addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
          final String where = 'at $width wide, ${scale}x';

          await show(tester, subject, size: Size(width, 9000));
          await openField(tester, subject, 'precise_location');
          expect(
            tester.takeException(),
            isNull,
            reason: 'nothing overflows $where',
          );
          const Map<String, (String, String)> place =
              <String, (String, String)>{
                'location/country': ('Country', 'Philippines'),
                'location/island': ('Island', 'Mindanao'),
                'location/province': ('Province', 'Davao'),
                'location/place': ('Named place', 'Mt. McKinley'),
              };
          for (final MapEntry<String, (String, String)> entry
              in place.entries) {
            final Finder row = partRow(subject, 'precise_location', entry.key);
            // Open every part, so the whole of each is on screen.
            if (whyIn(row).evaluate().isEmpty) {
              await tapIn(tester, partHeader(row));
            }
            expectWhole(tester, row, entry.value.$1, where);
            expectWhole(tester, row, entry.value.$2, where);
            for (final Element chip
                in find
                    .descendant(of: row, matching: find.byType(UiChip))
                    .evaluate()) {
              expect(
                (chip.renderObject! as RenderBox).size.width,
                lessThanOrEqualTo(width),
                reason: '${entry.key} chip $where',
              );
            }
          }
          // The Why of the flagged part: the longest text the row carries.
          final Finder flagged = partRow(
            subject,
            'precise_location',
            'location/place',
          );
          await tapIn(tester, whyIn(flagged));
          expect(tester.takeException(), isNull, reason: 'Why opens $where');
          expect(
            textIn(flagged, RegExp('^No approved source holds this mountain')),
            findsOneWidget,
          );

          await show(tester, inferred, size: Size(width, 9000));
          await openField(tester, inferred, 'elevation_from_m');
          for (final (String path, String title, String value)
              in <(String, String, String)>[
                ('elevation/from', 'Elevation from', '1950.72 m'),
                ('elevation/kind', 'Elevation kind', 'Point'),
                ('elevation/unit', 'Elevation unit', 'Feet'),
              ]) {
            final Finder row = partRow(inferred, 'elevation_from_m', path);
            if (whyIn(row).evaluate().isEmpty) {
              await tapIn(tester, partHeader(row));
            }
            expectWhole(tester, row, title, where);
            expectWhole(tester, row, value, where);
          }
          await tapIn(
            tester,
            whyIn(partRow(inferred, 'elevation_from_m', 'elevation/unit')),
          );
          expect(tester.takeException(), isNull, reason: 'Why opens $where');
        },
      );
    }

    testWidgets(
      'the rows are the same on a phone and a desk: one column of rows',
      (tester) async {
        for (final double width in <double>[390, 1180]) {
          await tester.pumpWidget(const SizedBox());
          await show(tester, subject, size: Size(width, 3200));
          await openField(tester, subject, 'precise_location');
          expect(tester.takeException(), isNull, reason: '$width');
          final List<Finder> rows = <Finder>[
            for (final String path in placePaths)
              partRow(subject, 'precise_location', path),
          ];
          for (final Finder row in rows) {
            expect(
              tester.getSize(row).width,
              lessThanOrEqualTo(width),
              reason: '$width',
            );
          }
        }
      },
    );

    testWidgets(
      'under reduced motion a part opens at once, with no size animation',
      (tester) async {
        await show(tester, subject, reduceMotion: true);
        await openField(tester, subject, 'precise_location');
        final Finder country = partRow(
          subject,
          'precise_location',
          'location/country',
        );
        final Finder place = partRow(
          subject,
          'precise_location',
          'location/place',
        );
        expect(
          find.descendant(of: place, matching: find.byType(AnimatedSize)),
          findsNothing,
        );
        await tester.tap(partHeader(country));
        await tester.pump();
        expect(
          whyIn(country),
          findsOneWidget,
          reason: 'open on the next frame',
        );
        await tester.tap(whyIn(country));
        await tester.pump();
        expect(textIn(country, 'Readings'), findsOneWidget);
        expect(
          find.descendant(of: country, matching: find.byType(AnimatedSize)),
          findsNothing,
        );
      },
    );

    testWidgets('with motion on, the body eases open', (tester) async {
      await show(tester, subject);
      await openField(tester, subject, 'precise_location');
      expect(
        find.descendant(
          of: partRow(subject, 'precise_location', 'location/place'),
          matching: find.byType(AnimatedSize),
        ),
        findsWidgets,
      );
    });
  });
}
