// The app's reader of a run's reading units (docs/execution/units/PLAN.md,
// WP 1.1). The record with units is the one the server's workspace route
// returned in tests/test_reading_units.py; the record without them is the
// shared API contract corpus, which main's server wrote.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/reading_units.dart';

const s = '00000000-0000-4000-8000-000000000001';
const r = '00000000-0000-4000-8000-000000000002';
const scope = CollectionScope(
  organizationId: s,
  collectionId: r,
  name: 'Synthetic',
);
const label = '00000000-0000-4000-8000-0000000000e2';
const a = '00000000-0000-4000-8000-00000000000a';
const b = '00000000-0000-4000-8000-00000000000b';
const c = '00000000-0000-4000-8000-00000000000c';

Json readJson(String path) =>
    Json.from(jsonDecode(utf8.decode(File(path).readAsBytesSync())) as Map);

/// The units of one label, as the server's workspace route returned them.
Json get withUnits =>
    readJson('../../tests/fixtures/reading_units_workspace.json');

Json get corpus => readJson('../../tests/fixtures/general_api_contracts.json');

/// The workspace body main's server returned, without units.
Json get workspaceBody => Json.from(
  jsonDecode(corpus['responses']['workspace']['body_utf8'] as String) as Map,
);

/// [text]'s code points from [start] to [end], as the server indexes them.
String codePoints(String text, int start, int end) =>
    String.fromCharCodes(text.runes.toList().sublist(start, end));

void expectPilotLabel(Map<String, LabelReadingUnits> found) {
  expect(found.keys, <String>[label]);
  final List<ReadingUnit> units = found[label]!.units;
  expect(units.map((ReadingUnit u) => u.id), <String>[
    '$label:1',
    '$label:2',
    '$label:3',
  ]);
  final ReadingUnit elevation = units[1];
  expect((elevation.firstLine, elevation.lastLine), (1, 1));
  expect(elevation.readers.keys, <String>[a, b, c]);
  expect(elevation.readers[b]!.text, "Elev.6400'");
  expect(
    (elevation.readers[b]!.startCodePoint, elevation.readers[b]!.endCodePoint),
    (13, 23),
  );
  expect(elevation.image, 'uncertain');
  expect(elevation.means, 'elevation 6400, unit not certain from the image');
  expect(elevation.fields, <String>['elevation_from_ft']);
  expect(elevation.note, 'Only reader B saw a foot mark.');
  expect(elevation.role, '');
  expect(units[2].image, 'Sp.30 ♀');
  expect(units[2].fields, isEmpty);
}

void main() {
  test('parses the units the workspace route returned', () {
    final Json fixture = withUnits;
    final Specimen specimen = Specimen(<String, dynamic>{
      'run': fixture['run'],
      'observations': fixture['observations'],
    });
    expectPilotLabel(specimen.readingUnits);
    // Every reader's span is its text's code points at the stored offsets.
    final Map<String, String> readings = <String, String>{
      for (final Json o in specimen.observations)
        o['observation_id'] as String: o['verbatim_text'] as String,
    };
    for (final ReadingUnit unit in specimen.readingUnits[label]!.units) {
      for (final MapEntry<String, UnitReading> entry in unit.readers.entries) {
        final UnitReading reading = entry.value;
        expect(
          codePoints(
            readings[entry.key]!,
            reading.startCodePoint,
            reading.endCodePoint,
          ),
          reading.text,
        );
      }
    }
  });

  test('a workspace record main wrote, without units, has none', () {
    final Json body = workspaceBody;
    expect((body['run'] as Map).containsKey('reading_units'), isFalse);
    expect(Specimen(body).readingUnits, isEmpty);
    expect(readingUnitsOf(null), isEmpty);
    expect(readingUnitsOf(<String, dynamic>{}), isEmpty);
  });

  test('the repository reads a workspace with units and one without', () async {
    final Json plain = workspaceBody;
    final Json units = Json.from(plain)
      ..['run'] = <String, dynamic>{
        ...Json.from(plain['run'] as Map),
        'reading_units': withUnits['run']['reading_units'],
      };
    for (final (Json body, bool expected) in <(Json, bool)>[
      (plain, false),
      (units, true),
    ]) {
      final ApiSpecimenRepository repository = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8000'),
        token: () async => 'synthetic',
        client: MockClient((http.Request request) async {
          if (request.url.path.endsWith('/content')) {
            return http.Response.bytes(
              base64Decode(corpus['png_base64'] as String),
              200,
            );
          }
          expect(
            request.url.path,
            '/v1/organizations/$s/specimens/$s/workspace',
          );
          return http.Response(
            jsonEncode(body),
            200,
            headers: <String, String>{
              'content-type': 'application/json; charset=utf-8',
            },
          );
        }),
      );
      addTearDown(repository.close);
      final Specimen specimen = await repository.specimen(scope, s);
      if (expected) {
        expectPilotLabel(specimen.readingUnits);
      } else {
        expect(specimen.readingUnits, isEmpty);
      }
    }
  });

  test('offsets stay code points, never UTF-16 code units', () {
    // A butterfly is one code point and two UTF-16 code units.
    const String reading = '\u{1F98B} Elev.6400';
    final Map<String, LabelReadingUnits> found = readingUnitsOf(
      <String, dynamic>{
        'reading_units': <Object?>[
          <String, Object?>{
            'label': 'L',
            'units': <Object?>[
              <String, Object?>{
                'id': 'L:1',
                'label': 'L',
                'lines': <int>[1, 1],
                'readers': <String, Object?>{
                  a: <String, Object?>{
                    'text': '\u{1F98B}',
                    'start': 0,
                    'end': 1,
                  },
                },
                'image': '\u{1F98B}',
                'means': '',
                'role': '',
                'fields': <String>[],
                'note': '',
              },
              <String, Object?>{
                'id': 'L:2',
                'label': 'L',
                'lines': <int>[1, 1],
                'readers': <String, Object?>{
                  a: <String, Object?>{
                    'text': 'Elev.6400',
                    'start': 2,
                    'end': 11,
                  },
                },
                'image': 'Elev.6400',
                'means': 'elevation 6400',
                'role': '',
                'fields': <String>['elevation_from_ft'],
                'note': '',
              },
            ],
          },
        ],
      },
    );
    final UnitReading first = found['L']!.units[0].readers[a]!;
    final UnitReading second = found['L']!.units[1].readers[a]!;
    expect((first.startCodePoint, first.endCodePoint), (0, 1));
    expect((second.startCodePoint, second.endCodePoint), (2, 11));
    expect(codePoints(reading, 2, 11), 'Elev.6400');
    // The same numbers as UTF-16 offsets would cut the text one unit early.
    expect(reading.substring(2, 11), isNot('Elev.6400'));
  });

  test('an entry that does not parse is left out; the others stay', () {
    final Json good = Json.from(
      (withUnits['run']['reading_units'] as List).single as Map,
    );
    Json firstUnit(Map<String, Object?> changes) => <String, dynamic>{
      ...good,
      'label': 'other',
      'units': <Object?>[
        <String, dynamic>{
          ...Json.from((good['units'] as List).first as Map),
          'label': 'other',
          ...changes,
        },
      ],
    };
    for (final Object? bad in <Object?>[
      null,
      'units',
      <String, Object?>{'label': 'other', 'units': <Object?>[]},
      firstUnit(<String, Object?>{'label': label}),
      firstUnit(<String, Object?>{
        'lines': <int>[1],
      }),
      firstUnit(<String, Object?>{
        'lines': <double>[1.0, 1.5],
      }),
      firstUnit(<String, Object?>{'readers': <String, Object?>{}}),
      firstUnit(<String, Object?>{
        'readers': <String, Object?>{
          a: <String, Object?>{'text': '6-Sept-1946,', 'start': 0, 'end': 11},
        },
      }),
      firstUnit(<String, Object?>{
        'fields': <Object?>[1],
      }),
      firstUnit(<String, Object?>{'image': null}),
    ]) {
      final Map<String, LabelReadingUnits> found = readingUnitsOf(
        <String, dynamic>{
          'reading_units': <Object?>[good, bad],
        },
      );
      expect(found.keys, <String>[label], reason: '$bad');
    }
  });
}
