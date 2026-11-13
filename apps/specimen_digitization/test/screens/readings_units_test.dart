// The readings segment shows a label's reading units (docs/execution/units/
// PLAN.md, WP 1.6). The record is the one the server's workspace route
// returned in tests/test_reading_units.py (tests/fixtures/
// reading_units_workspace.json), given the three reader routes' recorded model
// ids (src/specimen_digitization/model_gateway.py) and a label region. Each
// unit's readers are named by the model the record names for that reading.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/reading_units.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_heading.dart';
import 'package:specimen_digitization/src/screens/workbench/reading_units_view.dart';
import 'package:specimen_digitization/src/screens/workbench/readings_panel.dart';
import 'package:specimen_digitization/src/widgets/caveat_text.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../widgets/harness.dart';

const String label = '00000000-0000-4000-8000-0000000000e2';
const String a = '00000000-0000-4000-8000-00000000000a';
const String b = '00000000-0000-4000-8000-00000000000b';
const String c = '00000000-0000-4000-8000-00000000000c';

/// The reader routes' model ids (model_gateway.py, handwriting-*).
const String qwen = 'Qwen/Qwen3-VL-30B-A3B-Instruct';
const String muse = 'meta-models/Muse-Glimmer-30B';
const String nemotron = 'nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4';
const Map<String, String> models = <String, String>{
  a: qwen,
  b: muse,
  c: nemotron,
};

Json get fixture => Json.from(
  jsonDecode(
        utf8.decode(
          File(
            '../../tests/fixtures/reading_units_workspace.json',
          ).readAsBytesSync(),
        ),
      )
      as Map,
);

/// The fixture's record: its run and readings, each reading named by model.
///
/// [readers] keeps only those readers, in the readings and in every unit;
/// [units] changes the stored units; [transcription] is the label's.
Specimen record({
  Set<String> readers = const <String>{a, b, c},
  List<Json> Function(List<Json> units)? units,
  Json? transcription,
  bool withUnits = true,
}) {
  final Json stored = fixture;
  final Json entry = Json.from((stored['run']['reading_units'] as List).single);
  List<Json> kept = <Json>[
    for (final Object? unit in entry['units'] as List)
      <String, dynamic>{
        ...Json.from(unit! as Map),
        'readers': <String, dynamic>{
          for (final MapEntry<dynamic, dynamic> reader
              in ((unit as Map)['readers'] as Map).entries)
            if (readers.contains(reader.key)) reader.key: reader.value,
        },
      },
  ];
  if (units != null) kept = units(kept);
  return Specimen(<String, dynamic>{
    'specimen_id': 'units',
    'revision': 3,
    'regions': <Json>[
      <String, dynamic>{'region_id': label},
    ],
    'observations': <Json>[
      for (final Object? o in stored['observations'] as List)
        if (readers.contains((o! as Map)['observation_id']))
          <String, dynamic>{
            ...Json.from(o as Map),
            'id': o['observation_id'],
            'region_id': label,
            'model_id': models[o['observation_id']],
            'literal_text': o['verbatim_text'],
          },
    ],
    'transcriptions': <Json>[?transcription],
    'run': <String, dynamic>{
      if (withUnits)
        'reading_units': <Json>[
          <String, dynamic>{'label': label, 'units': kept},
        ],
    },
  });
}

Future<void> pumpLabel(
  WidgetTester tester,
  Specimen specimen, {
  Size size = const Size(1000, 3200),
}) => pumpComponent(
  tester,
  SingleChildScrollView(
    child: WorkbenchReadings(
      specimen: specimen,
      anchors: <String, GlobalKey>{label: GlobalKey()},
      selectedRegionId: label,
      onSelectRegion: (_) {},
      onChange: (_) async {},
      transcriptionBlockedReason: null,
      declarationsBlocked: true,
    ),
  ),
  size: size,
);

/// The card of part [number] of the label.
Finder part(int number) => find
    .ancestor(
      of: find.textContaining(RegExp('^Part $number · ')),
      matching: find.byType(Surface),
    )
    .first;

Finder inPart(int number, Finder matching) =>
    find.descendant(of: part(number), matching: matching);

Finder rich(String text) => find.text(text, findRichText: true);

/// The texts each reader group of part [number] is headed by.
List<String> namesIn(WidgetTester tester, int number) => <String>[
  for (final Text text in tester.widgetList<Text>(
    inPart(number, find.byType(Text)),
  ))
    if (text.data != null &&
        models.values.any((String model) => text.data!.contains(model)))
      text.data!,
];

void main() {
  // One row per state the acceptance names. Each row: the record, then what
  // the part shows for the image, its entries (the readers' names, each on a
  // line of its own, then their text) and the text the image names, if any.
  final List<
    (String, Specimen, int, String, List<(List<String>, String)>, String?)
  >
  states =
      <(String, Specimen, int, String, List<(List<String>, String)>, String?)>[
        (
          "names a reader's text",
          record(),
          3,
          'Image: Sp.30 ♀',
          <(List<String>, String)>[
            (<String>[qwen, muse], 'Sp.30 ♀'),
            (<String>[nemotron], 'Sp.30 ♂'),
          ],
          'Sp.30 ♀',
        ),
        (
          'is uncertain',
          record(),
          2,
          'Image: Uncertain',
          <(List<String>, String)>[
            (<String>[qwen, nemotron], 'Elev.6400'),
            (<String>[muse], "Elev.6400'"),
          ],
          null,
        ),
        (
          'is not visible',
          record(
            units: (List<Json> units) => <Json>[
              units[0],
              <String, dynamic>{...units[1], 'image': 'not visible'},
              units[2],
            ],
          ),
          2,
          'Image: Not visible',
          <(List<String>, String)>[
            (<String>[qwen, nemotron], 'Elev.6400'),
            (<String>[muse], "Elev.6400'"),
          ],
          null,
        ),
        (
          'is uncertain on a person-decided label with one reader',
          record(
            transcription: <String, dynamic>{
              'region_id': label,
              'resolved': true,
              'actor': 'reviewer-1',
              'verbatim_text': '6-Sept-1946, Elev.6400 ft',
            },
            units: (List<Json> units) => <Json>[
              <String, dynamic>{
                ...units[0],
                'readers': <String, dynamic>{
                  'person': <String, dynamic>{
                    'text': '6-Sept-1946,',
                    'start': 0,
                    'end': 12,
                  },
                },
                'image': 'uncertain',
              },
              <String, dynamic>{
                ...units[1],
                'readers': <String, dynamic>{
                  'person': <String, dynamic>{
                    'text': 'Elev.6400 ft',
                    'start': 13,
                    'end': 25,
                  },
                },
                'image': 'uncertain',
                'note': '',
              },
            ],
          ),
          2,
          'Image: Uncertain',
          <(List<String>, String)>[
            (<String>[personReaderName], 'Elev.6400 ft'),
          ],
          null,
        ),
      ];

  for (final (
        String state,
        Specimen specimen,
        int number,
        String image,
        List<(List<String>, String)> lines,
        String? matching,
      )
      in states) {
    testWidgets('a part whose image $state', (WidgetTester tester) async {
      await pumpLabel(tester, specimen);
      expect(find.text(ReadingUnitsView.title), findsOneWidget);
      expect(inPart(number, rich(image)), findsOneWidget);
      for (final (List<String> names, String text) in lines) {
        expect(inPart(number, find.text(text)), findsOneWidget, reason: text);
        // Each name is a line of its own in the entry that holds the text.
        expect(
          find.ancestor(
            of: inPart(number, find.text(text)),
            matching: find.byWidgetPredicate(
              (Widget w) =>
                  w is Column &&
                  w.children.length ==
                      names.length + 1 + (text == matching ? 1 : 0) &&
                  <String?>[
                        for (final Widget child in w.children.take(
                          names.length + 1,
                        ))
                          child is Text ? child.data : null,
                      ].join('|') ==
                      <String>[...names, text].join('|'),
            ),
          ),
          findsOneWidget,
          reason: '$names $text',
        );
      }
      // A model the part does not list is named nowhere in it.
      for (final String model in models.values) {
        if (lines.any(
          ((List<String>, String) line) => line.$1.contains(model),
        )) {
          continue;
        }
        expect(inPart(number, find.textContaining(model)), findsNothing);
      }
      // Only the line whose text the image names carries the mark, and it is
      // a word beside an icon, never colour alone.
      expect(
        inPart(number, find.text(ReadingUnitsView.matchesImage)),
        matching == null ? findsNothing : findsOneWidget,
      );
      if (matching != null) {
        expect(
          find.ancestor(
            of: inPart(number, find.text(ReadingUnitsView.matchesImage)),
            matching: find.byWidgetPredicate(
              (Widget w) =>
                  w is Column &&
                  w.children.whereType<Text>().any(
                    (Text t) => t.data == matching,
                  ),
            ),
          ),
          findsWidgets,
        );
      }
      // Every offset matched its reading: no part shows the mismatch caveat.
      expect(find.byType(CaveatText), findsNothing);
      await expectAccessible(tester);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('a record without units keeps the readings view', (
    WidgetTester tester,
  ) async {
    await pumpLabel(tester, record(withUnits: false));
    expect(find.text(ReadingUnitsView.title), findsNothing);
    // Every reader's whole reading, named by its model, each against the first.
    expect(find.byType(ReaderHeading), findsNWidgets(3));
    for (final String model in models.values) {
      expect(find.text(model), findsOneWidget);
    }
    final List<DiffText> texts = tester
        .widgetList<DiffText>(find.byType(DiffText))
        .toList();
    expect(texts.map((DiffText d) => d.text), <String>[
      "6-Sept-1946, Elev.6400\nSp.30 ♀",
      "6-Sept-1946, Elev.6400'\nSp.30 ♀",
      "6-Sept-1946, Elev.6400\nSp.30 ♂",
    ]);
    expect(texts.map((DiffText d) => d.reference), <String?>[
      null,
      "6-Sept-1946, Elev.6400\nSp.30 ♀",
      "6-Sept-1946, Elev.6400\nSp.30 ♀",
    ]);
    await expectAccessible(tester);
  });

  testWidgets('a label with units keeps every whole reading, uncompared', (
    WidgetTester tester,
  ) async {
    await pumpLabel(tester, record());
    expect(find.byType(ReaderHeading), findsNWidgets(3));
    expect(
      tester
          .widgetList<DiffText>(find.byType(DiffText))
          .map((DiffText d) => d.reference),
      <String?>[null, null, null],
    );
    // The units come first, then the readings.
    expect(
      tester.getTopLeft(find.text(ReadingUnitsView.title)).dy,
      lessThan(tester.getTopLeft(find.byType(ReaderHeading).first).dy),
    );
  });

  // The owner, 2026-11-12: every reader's transcription when a label is
  // selected, each named by its model. Two readers show two; three, three.
  for (final Set<String> readers in <Set<String>>[
    <String>{a, b},
    <String>{a, b, c},
  ]) {
    testWidgets('${readers.length} readers name ${readers.length} models in '
        'every part', (WidgetTester tester) async {
      await pumpLabel(tester, record(readers: readers));
      for (int number = 1; number <= 3; number++) {
        final String named = namesIn(tester, number).join(' · ');
        for (final String key in <String>[a, b, c]) {
          expect(
            RegExp(RegExp.escape(models[key]!)).allMatches(named).length,
            readers.contains(key) ? 1 : 0,
            reason: 'part $number, ${models[key]}',
          );
        }
      }
      expect(find.byType(ReaderHeading), findsNWidgets(readers.length));
    });
  }

  testWidgets('each unit meaning, field and note shows in words', (
    WidgetTester tester,
  ) async {
    await pumpLabel(
      tester,
      record(
        units: (List<Json> units) => <Json>[
          <String, dynamic>{...units[0], 'role': 'day'},
          ...units.skip(1),
        ],
      ),
    );
    expect(inPart(1, find.text('Part 1 · Line 1')), findsOneWidget);
    expect(inPart(1, rich('Meaning: 1946-09-06')), findsOneWidget);
    expect(
      inPart(1, rich('Possible fields: Date visited from')),
      findsOneWidget,
    );
    expect(inPart(1, rich('Role: day')), findsOneWidget);
    expect(
      inPart(2, rich('Possible fields: Elevation from (ft)')),
      findsOneWidget,
    );
    expect(
      inPart(2, rich('Note: Only reader B saw a foot mark.')),
      findsOneWidget,
    );
    expect(inPart(3, find.text('Part 3 · Line 2')), findsOneWidget);
    expect(find.text('3 parts'), findsOneWidget);
  });

  // Offsets are code points; the check slices the saved reading with them
  // after converting to UTF-16. An emoji before the unit moves the two apart.
  for (final (String why, int start, int end, bool mismatch)
      in <(String, int, int, bool)>[
        ('code points after an emoji', 2, 9, false),
        ('UTF-16 offsets', 3, 10, true),
        ('an offset past the reading', 8, 15, true),
      ]) {
    for (final Size size in <Size>[
      const Size(390, 3200),
      const Size(1180, 3200),
    ]) {
      testWidgets('a unit at $why ${mismatch ? 'shows' : 'shows no'} '
          'mismatch at ${size.width.toInt()} wide', (
        WidgetTester tester,
      ) async {
        final Specimen specimen = Specimen(<String, dynamic>{
          'specimen_id': 'emoji',
          'regions': <Json>[
            <String, dynamic>{'region_id': label},
          ],
          'observations': <Json>[
            <String, dynamic>{
              'id': a,
              'region_id': label,
              'model_id': qwen,
              'literal_text': '🦋 Chicago 1912',
            },
          ],
          'run': <String, dynamic>{
            'reading_units': <Json>[
              <String, dynamic>{
                'label': label,
                'units': <Json>[
                  <String, dynamic>{
                    'id': '$label:1',
                    'label': label,
                    'lines': <int>[1, 1],
                    'readers': <String, dynamic>{
                      a: <String, dynamic>{
                        'text': 'Chicago',
                        'start': start,
                        'end': end,
                      },
                    },
                    'image': 'Chicago',
                    'means': '',
                    'role': '',
                    'fields': <String>[],
                    'note': '',
                  },
                ],
              },
            ],
          },
        });
        await pumpLabel(tester, specimen, size: size);
        final String text = tester
            .widgetList<Text>(inPart(1, find.byType(Text)))
            .map((Text t) => t.data ?? t.textSpan!.toPlainText())
            .join('\n');
        expect(text, contains('Chicago'));
        expect(
          find.text(ReadingUnitsView.mismatch),
          mismatch ? findsOneWidget : findsNothing,
        );
        // The caveat's "Why" is the one control a part can hold: labelled and
        // 48 dp, closed and open.
        await expectAccessible(tester);
        final Finder whyButton = inPart(1, find.text(CaveatText.affordance));
        expect(whyButton, mismatch ? findsOneWidget : findsNothing);
        if (mismatch) {
          await tester.ensureVisible(whyButton);
          await tester.tap(whyButton);
          await tester.pumpAndSettle();
          expect(
            inPart(1, find.text(ReadingUnitsView.mismatchWhy(qwen))),
            findsOneWidget,
          );
          await expectAccessible(tester);
        }
        expect(tester.takeException(), isNull);
      });
    }
  }

  test('readers are named by model, then a person, then not recorded', () {
    final Specimen specimen = record();
    final List<Json> observations = specimen.observations;
    for (final (Json transcription, Map<String, String> names)
        in <(Json, Map<String, String>)>[
          (
            const <String, dynamic>{},
            <String, String>{
              a: qwen,
              b: muse,
              c: nemotron,
              'person': unrecordedReaderName,
            },
          ),
          (
            const <String, dynamic>{
              'resolved': true,
              'actor': 'reviewer-1',
              'verbatim_text': 'Elev.6400',
            },
            <String, String>{
              a: qwen,
              b: muse,
              c: nemotron,
              'person': personReaderName,
            },
          ),
          // Not resolved, no actor, or no text: not a person's decision.
          (
            const <String, dynamic>{
              'resolved': false,
              'actor': 'reviewer-1',
              'verbatim_text': 'Elev.6400',
            },
            <String, String>{
              a: qwen,
              b: muse,
              c: nemotron,
              'person': unrecordedReaderName,
            },
          ),
          (
            const <String, dynamic>{
              'resolved': true,
              'verbatim_text': 'Elev.6400',
            },
            <String, String>{
              a: qwen,
              b: muse,
              c: nemotron,
              'person': unrecordedReaderName,
            },
          ),
          (
            const <String, dynamic>{'resolved': true, 'actor': 'reviewer-1'},
            <String, String>{
              a: qwen,
              b: muse,
              c: nemotron,
              'person': unrecordedReaderName,
            },
          ),
        ]) {
      final Map<String, UnitReader> readers = unitReaders(
        units: unitsNaming(<String>[a, b, c, 'person']),
        // Listed C first: the order of the readings decides the order here.
        observations: <Json>[observations[2], observations[0], observations[1]],
        transcription: transcription,
        nameOf: (Json o) => o['model_id'] as String,
      );
      expect(
        readers.map((String k, UnitReader r) => MapEntry(k, r.name)),
        names,
        reason: '$transcription',
      );
      expect(readers.keys, <String>[c, a, b, 'person']);
    }
  });
}

/// One unit naming [keys], each with an empty text.
LabelReadingUnits unitsNaming(List<String> keys) =>
    LabelReadingUnits.fromJson(<String, dynamic>{
      'label': label,
      'units': <Json>[
        <String, dynamic>{
          'id': '$label:1',
          'label': label,
          'lines': <int>[1, 1],
          'readers': <String, dynamic>{
            for (final String key in keys)
              key: <String, dynamic>{'text': '', 'start': 0, 'end': 0},
          },
          'image': 'uncertain',
          'means': '',
          'role': '',
          'fields': <String>[],
          'note': '',
        },
      ],
    })!;
