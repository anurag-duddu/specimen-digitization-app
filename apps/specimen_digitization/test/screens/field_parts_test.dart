import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/field_parts.dart';
import 'package:specimen_digitization/src/screens/workbench/value_basis.dart';

import 'field_parts_fixture.dart';

// The part model: the path grammar, the loader, and what a list that breaks a
// rule does. The loader is the one place the app reads the optional `parts` of
// a field, so what it ignores matters as much as what it reads. A field with
// no parts, or with parts that cannot be trusted, shows its own value as it
// always has, and the loader never throws.

typedef Raw = List<Object?>;

/// A list the tests may add anything to, as the wire may hold anything.
Raw rawOf(List<Map<String, dynamic>> parts) => <Object?>[...parts];

FieldParts read(Object? raw, {String key = 'precise_location'}) =>
    FieldParts.read(raw, fieldKey: key);

Map<String, dynamic> at(Raw raw, String path) =>
    raw.firstWhere((Object? e) => e is Map && e['path'] == path)
        as Map<String, dynamic>;

void main() {
  group('a field with no usable parts', () {
    test('parts absent, null or empty are none, with nothing to report', () {
      expect(
        FieldParts.of(<String, dynamic>{'field_key': 'country'}).isEmpty,
        isTrue,
      );
      for (final Object? raw in <Object?>[null, <Object?>[]]) {
        final FieldParts parts = read(raw);
        expect(parts.isEmpty, isTrue, reason: '$raw');
        expect(parts.ignored, isNull, reason: '$raw is not a problem');
        expect(parts.tree, isEmpty);
        expect(parts.flagged, isEmpty);
      }
    });

    test('a value that is not a list is set aside, never a crash', () {
      for (final Object raw in <Object>[
        'location/country',
        5,
        true,
        <String, dynamic>{'path': 'location/country'},
      ]) {
        final FieldParts parts = read(raw);
        expect(parts.isEmpty, isTrue, reason: '$raw');
        expect(parts.ignored, 'not_a_list', reason: '$raw');
      }
    });

    test('a field map with parts but no field key shows none', () {
      expect(
        FieldParts.of(<String, dynamic>{'parts': locationParts()}).isEmpty,
        isTrue,
      );
    });

    test('more parts than the bound are shown as no parts', () {
      final Raw twentyFour = <Object?>[
        for (int i = 1; i <= maxPartsPerField; i++) _collector(i),
      ];
      final FieldParts fits = read(twentyFour, key: 'collectors');
      expect(fits.parts, hasLength(maxPartsPerField));
      expect(fits.ignored, isNull);

      final Raw twentyFive = <Object?>[
        for (int i = 1; i <= maxPartsPerField + 1; i++) _collector(i),
      ];
      final FieldParts over = read(twentyFive, key: 'collectors');
      expect(over.isEmpty, isTrue);
      expect(over.ignored, 'too_many_parts');
    });

    test('more bytes than the bound are shown as no parts', () {
      final Raw heavy = <Object?>[
        for (int i = 1; i <= 24; i++)
          // Members the reader does not know are tolerated, but they still
          // count toward the size the writer promised to stay under.
          <String, dynamic>{..._collector(i), 'note': 'x' * 1500},
      ];
      final FieldParts parts = read(heavy, key: 'collectors');
      expect(parts.isEmpty, isTrue);
      expect(parts.ignored, 'too_large');

      final Raw light = <Object?>[
        for (int i = 1; i <= 24; i++)
          <String, dynamic>{..._collector(i), 'note': 'x' * 20},
      ];
      expect(read(light, key: 'collectors').ignored, isNull);
    });

    test('a value JSON cannot carry is set aside', () {
      final FieldParts parts = read(<Object?>[
        <Object?, Object?>{1: 'x'},
      ]);
      expect(parts.isEmpty, isTrue);
      expect(parts.ignored, 'not_json');
    });
  });

  group('the worked examples of the contract', () {
    test('105526321 place tree reads as four parts and one to check', () {
      final FieldParts parts = read(locationParts());
      expect(parts.ignored, isNull);
      expect(parts.parts, hasLength(4));

      final FieldPart country = parts.byPath('location/country')!;
      expect(country.value, 'Philippines');
      expect(country.basis, ValueBasis.derived);
      expect(country.wording, 'P.I.');
      expect(country.originalWording, 'P.I.');
      expect(country.parent!.isRoot, isTrue);
      expect(
        country.evidenceRelations['ev-rule-notation'],
        PartRelation.decides,
      );

      final FieldPart island = parts.byPath('location/island')!;
      expect(island.basis, ValueBasis.asWritten);
      expect(island.originalWording, isNull, reason: 'no wording of its own');

      final FieldPart place = parts.byPath('location/place')!;
      expect(place.originalWording, 'E. slope Mt. McKinley');
      expect(place.review!.code, PartReviewCode.doubt);
      expect(place.needsReview, isTrue);
      expect(
        place.evidenceRelations['ev-geolocate-mckinley'],
        PartRelation.contradicts,
      );

      expect(parts.flagged.map((FieldPart p) => p.path.text), <String>[
        'location/place',
      ]);
    });

    test('the tree is drawn from parent, not from the wire order', () {
      final FieldParts parts = read(locationParts());
      // The wire order is bytewise, so `place` comes before `province`, its
      // parent. The tree is country, island, province, then the place.
      expect(parts.parts.map((FieldPart p) => p.path.text), <String>[
        'location/country',
        'location/island',
        'location/place',
        'location/province',
      ]);
      expect(
        parts.tree.map((PartNode n) => (n.part.path.text, n.depth)),
        <(String, int)>[
          ('location/country', 0),
          ('location/island', 1),
          ('location/province', 2),
          ('location/place', 3),
        ],
      );
      expect(parts.tree.map((PartNode n) => n.parent?.path.text), <String?>[
        null,
        'location/country',
        'location/island',
        'location/province',
      ]);
    });

    test(
      'a broader level with two children keeps the wire order of siblings',
      () {
        final Raw raw = rawOf(locationParts());
        // A second province under the island, which repeats from 2.
        raw.add(<String, dynamic>{
          ...at(raw, 'location/province'),
          'path': 'location/province/2',
          'value': 'Davao Oriental',
          'wording': 'Davao Or.',
        });
        final FieldParts parts = read(raw);
        expect(parts.ignored, isNull);
        expect(parts.tree.map((PartNode n) => n.part.path.text), <String>[
          'location/country',
          'location/island',
          'location/province',
          'location/place',
          'location/province/2',
        ]);
        expect(parts.tree.last.depth, 2);
      },
    );

    test('105526322 elevation reads the inferred unit and its dependants', () {
      final FieldParts parts = read(
        inferredElevationParts(),
        key: 'elevation_from_m',
      );
      expect(parts.ignored, isNull);
      final FieldPart unit = parts.byPath('elevation/unit')!;
      expect(unit.basis, ValueBasis.inferred);
      expect(unit.valueText, 'Feet');
      expect(unit.derivedFrom.map((PartPath p) => p.text), <String>[
        'location/country',
      ]);
      expect(unit.needsReview, isTrue);

      final FieldPart from = parts.byPath('elevation/from')!;
      expect(from.basis, ValueBasis.inferred);
      expect(from.valueText, '1950.72 m');
      expect(from.originalWording, 'Elev. 6400');
      expect(from.derivedFrom.single.text, 'elevation/unit');

      final FieldPart kind = parts.byPath('elevation/kind')!;
      expect(kind.basis, ValueBasis.asWritten);
      expect(kind.valueText, 'Point');
      expect(kind.needsReview, isFalse);

      // Parts outside the place tree are all at the top, in wire order.
      expect(parts.tree.map((PartNode n) => n.depth), <int>[0, 0, 0]);
      expect(parts.tree.map((PartNode n) => n.part.path.text), <String>[
        'elevation/from',
        'elevation/kind',
        'elevation/unit',
      ]);
    });

    test('collectors conflict reads the alternative and the sentence', () {
      final FieldParts parts = read(collectorParts(), key: 'collectors');
      final FieldPart collector = parts.parts.single;
      expect(collector.review!.code, PartReviewCode.conflict);
      expect(collector.alternatives.single.value, 'F.G. Wermer');
      expect(
        partReviewSentence(collector),
        'Two readings differ: F.G. Werner, F.G. Wermer.',
      );
    });

    test('the same parts on any other field are left out', () {
      for (final String key in <String>[
        'country',
        'elevation_from_m',
        'collectors',
      ]) {
        final FieldParts parts = read(locationParts(), key: key);
        expect(parts.isEmpty, isTrue, reason: key);
        expect(
          parts.ignored,
          isNull,
          reason: '$key: not a problem, not its parts',
        );
      }
    });
  });

  group('what a reader meets that it does not know', () {
    test('a path from a later release is left out and the rest is read', () {
      final Raw raw = rawOf(locationParts());
      raw.addAll(<Object?>[
        // A level written in a spelling the grammar does not allow.
        <String, dynamic>{
          ...at(raw, 'location/island'),
          'path': 'location/Island',
        },
        // A value this reader has no carrier for: parts add nothing to it.
        <String, dynamic>{
          ...at(raw, 'location/island'),
          'path': 'habitat/text',
        },
        // A value that has no carrier at all yet.
        <String, dynamic>{
          ...at(raw, 'location/island'),
          'path': 'identified_by/1',
        },
        // Not a spelling of the grammar.
        <String, dynamic>{...at(raw, 'location/island'), 'path': 'when/start'},
        // The elevation is carried on another field.
        <String, dynamic>{
          ...at(raw, 'location/island'),
          'path': 'elevation/unit',
        },
      ]);
      final FieldParts parts = read(raw);
      expect(parts.ignored, isNull);
      expect(parts.parts.map((FieldPart p) => p.path.text), <String>[
        'location/country',
        'location/island',
        'location/place',
        'location/province',
      ]);
    });

    test('a list of nothing but unknown paths is none, with no complaint', () {
      final FieldParts parts = read(<Object?>[
        <String, dynamic>{'path': 'habitat/text', 'state': 'supported'},
        <String, dynamic>{'path': 'identified_by/1'},
      ]);
      expect(parts.isEmpty, isTrue);
      expect(parts.ignored, isNull);
    });

    test(
      'a basis word it does not know shows no chip but is still a basis',
      () {
        final Raw raw = rawOf(locationParts());
        at(raw, 'location/island')['basis'] = 'estimated';
        final FieldPart island = read(raw).byPath('location/island')!;
        expect(island.basis, isNull);
        expect(island.basisStated, isTrue);
        expect(island.value, 'Mindanao');
      },
    );

    test('a review code it does not know is read as a doubt', () {
      final Raw raw = rawOf(locationParts());
      (at(raw, 'location/place')['review'] as Map<String, dynamic>)['code'] =
          'suspicion';
      final FieldPart place = read(raw).byPath('location/place')!;
      expect(place.review!.code, PartReviewCode.doubt);
      expect(place.review!.reason, startsWith('No approved source'));
    });

    test('a decision action it does not know is read as a confirmation', () {
      final Raw raw = rawOf(locationParts());
      final Map<String, dynamic> place = at(raw, 'location/place');
      place.remove('review');
      place['decision'] = <String, dynamic>{
        'event_id': 'evt-1',
        'action': 'endorse',
        'actor': 'user-1',
        'at': '2026-10-09T10:00:00Z',
      };
      final FieldPart part = read(raw).byPath('location/place')!;
      expect(part.decision!.action, PartDecisionAction.other);
      expect(part.needsReview, isFalse);
      expect(part.decision!.at, '2026-10-09T10:00:00Z');
    });

    test('a part a person edited has a value and no basis', () {
      final Raw raw = rawOf(locationParts());
      final Map<String, dynamic> place = at(raw, 'location/place')
        ..remove('review')
        ..remove('basis')
        ..['value'] = 'Mount Apo'
        ..['decision'] = <String, dynamic>{
          'event_id': 'evt-2',
          'action': 'edit',
          'actor': 'user-1',
          'at': '2026-10-09T10:00:00Z',
        };
      place['evidence_ids'] = <String>[];
      place['evidence_relations'] = <String, String>{};
      final FieldPart part = read(raw).byPath('location/place')!;
      expect(read(raw).ignored, isNull);
      expect(part.editedByPerson, isTrue);
      expect(part.basis, isNull);
      expect(part.basisStated, isFalse);
      expect(part.value, 'Mount Apo');
    });

    test('members it does not know are tolerated', () {
      final Raw raw = rawOf(locationParts());
      at(raw, 'location/island')['confidence_band'] = <String, dynamic>{'x': 1};
      expect(read(raw).ignored, isNull);
      expect(read(raw).parts, hasLength(4));
    });
  });

  // One rule of the contract broken at a time, on the place tree. Each sets the
  // whole list aside, and says which rule did.
  group('a list that breaks a rule is shown as no parts', () {
    final Map<String, (void Function(Raw), String)> cases =
        <String, (void Function(Raw), String)>{
          'an entry that is not an object': (
            (Raw r) => r.add('location/country'),
            'not_an_object',
          ),
          'a path that is not text': (
            (Raw r) => at(r, 'location/island')['path'] = 5,
            'bad_path',
          ),
          'a missing path': (
            (Raw r) => at(r, 'location/island').remove('path'),
            'bad_path',
          ),
          'a path over 64 characters': (
            (Raw r) =>
                at(r, 'location/island')['path'] = 'location/${'a' * 60}',
            'bad_path',
          ),
          'the root as a part': (
            (Raw r) => at(r, 'location/island')['path'] = 'location/verbatim',
            'root_as_part',
          ),
          'a repeated path': (
            (Raw r) => r.add(<String, dynamic>{...at(r, 'location/island')}),
            'duplicate_path',
          ),
          'a state it does not know': (
            (Raw r) => at(r, 'location/island')['state'] = 'probably',
            'bad_state',
          ),
          'a value on a part that is not supported': (
            (Raw r) => at(r, 'location/island')['state'] = 'unknown',
            'value_on_unsupported_state',
          ),
          'a supported part with no value': (
            (Raw r) => at(r, 'location/island').remove('value'),
            'supported_without_value',
          ),
          'a value with no basis': (
            (Raw r) => at(r, 'location/island').remove('basis'),
            'value_without_basis',
          ),
          'a basis with no value': (
            (Raw r) => at(r, 'location/island')
              ..remove('value')
              ..['state'] = 'unresolved',
            'basis_without_value',
          ),
          'a basis that is not text': (
            (Raw r) => at(r, 'location/island')['basis'] = 3,
            'bad_basis',
          ),
          'a derived value with no wording': (
            (Raw r) => at(r, 'location/country').remove('wording'),
            'derived_without_wording',
          ),
          'a value that is a number': (
            (Raw r) => at(r, 'location/island')['value'] = 6400,
            'bad_value',
          ),
          'an empty value': (
            (Raw r) => at(r, 'location/island')['value'] = '',
            'bad_value',
          ),
          'a value over 240 characters': (
            (Raw r) => at(r, 'location/island')['value'] = 'x' * 241,
            'bad_value',
          ),
          'a control character in a text': (
            (Raw r) => at(r, 'location/place')['wording'] = 'E. slope\nMt.',
            'bad_wording',
          ),
          'a place part with no parent': (
            (Raw r) => at(r, 'location/island').remove('parent'),
            'bad_parent',
          ),
          'a parent that is not a path': (
            (Raw r) => at(r, 'location/island')['parent'] = 'north',
            'bad_parent',
          ),
          'a parent that is not in the list': (
            (Raw r) => at(r, 'location/island')['parent'] = 'location/district',
            'parent_missing',
          ),
          'a parent that is its own part': (
            (Raw r) => at(r, 'location/country')['parent'] = 'location/country',
            'parent_loop',
          ),
          'a chain of parents that loops': (
            (Raw r) => at(r, 'location/country')['parent'] = 'location/place',
            'parent_loop',
          ),
          'derived_from that is not a path': (
            (Raw r) =>
                at(r, 'location/country')['derived_from'] = <String>['x'],
            'bad_derived_from',
          ),
          'derived_from that names the part itself': (
            (Raw r) => at(r, 'location/country')['derived_from'] = <String>[
              'location/country',
            ],
            'bad_derived_from',
          ),
          'more than eight derived_from': (
            (Raw r) => at(r, 'location/country')['derived_from'] = <String>[
              for (int i = 1; i <= 9; i++) 'collectors/$i',
            ],
            'bad_derived_from',
          ),
          'the same evidence cited twice': (
            (Raw r) => at(r, 'location/island')['evidence_ids'] = <String>[
              'ev-2A-locality',
              'ev-2A-locality',
            ],
            'duplicate_evidence',
          ),
          'more than twelve evidence rows': (
            (Raw r) {
              final Map<String, dynamic> island = at(r, 'location/island');
              final List<String> ids = <String>[
                for (int i = 1; i <= 13; i++) 'ev-$i',
              ];
              island['evidence_ids'] = ids;
              island['evidence_relations'] = <String, String>{
                for (final String id in ids) id: 'supports',
              };
            },
            'bad_evidence_ids',
          ),
          'a relation missing for a cited row': (
            (Raw r) =>
                (at(r, 'location/island')['evidence_relations']
                        as Map<String, dynamic>)
                    .remove('ev-2B-locality'),
            'relations_do_not_match_evidence',
          ),
          'a relation for a row that is not cited': (
            (Raw r) =>
                (at(r, 'location/island')['evidence_relations']
                        as Map<String, dynamic>)['ev-other'] =
                    'supports',
            'relations_do_not_match_evidence',
          ),
          'a relation word it does not know': (
            (Raw r) =>
                (at(r, 'location/island')['evidence_relations']
                        as Map<String, dynamic>)['ev-2A-locality'] =
                    'mentions',
            'bad_evidence_relations',
          ),
          'a supported part that cites nothing and was not decided': (
            (Raw r) => at(r, 'location/island')
              ..['evidence_ids'] = <String>[]
              ..['evidence_relations'] = <String, String>{},
            'supported_without_evidence',
          ),
          'a review with no reason': (
            (Raw r) =>
                (at(r, 'location/place')['review'] as Map<String, dynamic>)
                    .remove('reason'),
            'bad_review',
          ),
          'a review that is not an object': (
            (Raw r) => at(r, 'location/place')['review'] = 'doubt',
            'bad_review',
          ),
          'a decision that is not an object': (
            (Raw r) => at(r, 'location/place')['decision'] = 'accepted',
            'bad_decision',
          ),
          'no support with a value': (
            (Raw r) => at(r, 'location/place')['review'] = <String, dynamic>{
              'code': 'no_support',
              'reason': 'Nothing supports this.',
            },
            'no_support_with_value',
          ),
        };

    cases.forEach((String name, (void Function(Raw), String) rule) {
      test(name, () {
        final Raw raw = rawOf(locationParts());
        rule.$1(raw);
        final FieldParts parts = read(raw);
        expect(parts.isEmpty, isTrue, reason: 'no parts are drawn');
        expect(parts.tree, isEmpty);
        expect(parts.ignored, rule.$2);
      });
    });

    final Map<String, (void Function(Raw), String)> collectorCases =
        <String, (void Function(Raw), String)>{
          'a conflict with nothing to choose from': (
            (Raw r) => at(r, 'collectors/1').remove('alternatives'),
            'conflict_without_alternatives',
          ),
          'an ambiguous part with fewer than two alternatives': (
            (Raw r) => at(r, 'collectors/1')
              ..['state'] = 'ambiguous'
              ..remove('value')
              ..remove('basis'),
            'ambiguous_shape',
          ),
          'an ambiguous part whose review is not a conflict': (
            (Raw r) {
              at(r, 'collectors/1')
                ..['state'] = 'ambiguous'
                ..remove('value')
                ..remove('basis')
                ..['alternatives'] = <Map<String, dynamic>>[
                  <String, dynamic>{
                    'value': 'F.G. Werner',
                    'evidence_ids': <String>[],
                  },
                  <String, dynamic>{
                    'value': 'F.G. Wermer',
                    'evidence_ids': <String>[],
                  },
                ]
                ..['review'] = <String, dynamic>{
                  'code': 'doubt',
                  'reason': 'Unsure.',
                };
            },
            'ambiguous_shape',
          ),
          'more than four alternatives': (
            (Raw r) =>
                at(r, 'collectors/1')['alternatives'] = <Map<String, dynamic>>[
                  for (int i = 0; i < 5; i++)
                    <String, dynamic>{'value': 'Werner $i'},
                ],
            'bad_alternatives',
          ),
          'an alternative with no value': (
            (Raw r) =>
                at(r, 'collectors/1')['alternatives'] = <Map<String, dynamic>>[
                  <String, dynamic>{'basis': 'label'},
                ],
            'bad_alternatives',
          ),
          'an alternative citing a row the part does not': (
            (Raw r) =>
                ((at(r, 'collectors/1')['alternatives'] as List).first
                    as Map<String, dynamic>)['evidence_ids'] = <String>[
                  'ev-elsewhere',
                ],
            'alternative_evidence_not_cited',
          ),
          'an alternative citing more than two rows': (
            (Raw r) =>
                ((at(r, 'collectors/1')['alternatives'] as List).first
                    as Map<String, dynamic>)['evidence_ids'] = <String>[
                  'a',
                  'b',
                  'c',
                ],
            'bad_alternatives',
          ),
        };
    collectorCases.forEach((String name, (void Function(Raw), String) rule) {
      test(name, () {
        final Raw raw = rawOf(collectorParts());
        rule.$1(raw);
        final FieldParts parts = read(raw, key: 'collectors');
        expect(parts.isEmpty, isTrue);
        expect(parts.ignored, rule.$2);
      });
    });

    test('a parent on a part outside the place tree', () {
      final Raw raw = rawOf(elevationParts());
      at(raw, 'elevation/unit')['parent'] = 'location/verbatim';
      final FieldParts parts = read(raw, key: 'elevation_from_m');
      expect(parts.isEmpty, isTrue);
      expect(parts.ignored, 'parent_outside_location');
    });

    test('a part with no value and no basis needs neither', () {
      final Raw raw = rawOf(locationParts());
      at(raw, 'location/island')
        ..remove('value')
        ..remove('basis')
        ..['state'] = 'unresolved'
        ..['evidence_ids'] = <String>[]
        ..['evidence_relations'] = <String, String>{}
        ..['review'] = <String, dynamic>{
          'code': 'no_support',
          'reason': 'No source supports an island.',
        };
      final FieldParts parts = read(raw);
      expect(parts.ignored, isNull);
      final FieldPart island = parts.byPath('location/island')!;
      expect(island.valueText, 'Unresolved', reason: 'absence is words');
      expect(island.value, isNull);
    });
  });

  group('the path grammar', () {
    const Map<String, String> valid = <String, String>{
      'location/country': 'Country',
      'location/island': 'Island',
      'location/province': 'Province',
      'location/place': 'Named place',
      'location/place/2': 'Named place 2',
      'location/department': 'Department',
      'location/municipality': 'Municipality',
      'location/sub_district': 'Sub district',
      'location/verbatim': 'Verbatim',
      'elevation/from': 'Elevation from',
      'elevation/to': 'Elevation to',
      'elevation/unit': 'Elevation unit',
      'elevation/kind': 'Elevation kind',
      'collectors/1': 'Collector 1',
      'collectors/24': 'Collector 24',
      'collectors/999999': 'Collector 999999',
      'identified_by/3': 'Identified by 3',
      'when/collected/start': 'Collection start date',
      'when/collected/end': 'Collection end date',
      'when/collected/time': 'Collection time',
      'when/identified/start': 'Identification date',
      'taxon/name': 'Name as written',
      'taxon/accepted': 'Accepted name',
      'ids/catalog_number': 'Catalogue number',
      'ids/collection': 'Collection',
      'habitat/text': 'Habitat',
      'collection_method/text': 'Collection method',
    };

    valid.forEach((String path, String label) {
      test('$path parses, round-trips and reads as "$label"', () {
        final PartPath? parsed = PartPath.tryParse(path);
        expect(parsed, isNotNull);
        expect(parsed!.text, path, reason: 'the canonical spelling');
        expect(parsed.label, label);
        expect(PartPath.tryParse(parsed.text), parsed);
      });
    });

    const List<String> invalid = <String>[
      '',
      'location',
      'location/',
      '/country',
      'location//country',
      'location/country/',
      'Location/country',
      'location/Country',
      'location/country/1',
      'location/country/02',
      'location/country/2/3',
      'location/country/two',
      'location/verbatim/2',
      'location/2country',
      'location/_country',
      'location/country_',
      'location/coun try',
      'location/country\n',
      'location/país',
      'collectors',
      'collectors/',
      'collectors/0',
      'collectors/01',
      'collectors/1/2',
      'collectors/x',
      'collectors/1234567',
      'collectors/-1',
      'elevation',
      'elevation/height',
      'elevation/to/2',
      'when/start',
      'when/collected',
      'when/collected/start/2',
      'taxon/',
      'taxon/family',
      'ids/barcode',
      'habitat',
      'bogus/x',
    ];
    for (final String path in invalid) {
      test('"${path.replaceAll('\n', r'\n')}" is not a path', () {
        expect(PartPath.tryParse(path), isNull);
      });
    }

    test('a value that is not text is not a path', () {
      expect(PartPath.tryParse(null), isNull);
      expect(PartPath.tryParse(5), isNull);
      expect(PartPath.tryParse(<String>['location/country']), isNull);
    });

    test('only the root is the root', () {
      expect(PartPath.tryParse(locationRoot)!.isRoot, isTrue);
      expect(PartPath.tryParse('location/place')!.isRoot, isFalse);
      expect(PartPath.tryParse('elevation/from')!.isRoot, isFalse);
    });

    test('a part is carried on the field its prefix names', () {
      const Map<String, String?> carriers = <String, String?>{
        'location/country': 'precise_location',
        'location/place/2': 'precise_location',
        'elevation/unit': 'elevation_from_m',
        'when/collected/start': 'date_visited_from',
        'when/collected/time': 'date_visited_from',
        'when/identified/start': 'date_identified',
        'collectors/1': 'collectors',
        'taxon/accepted': 'taxon',
        'ids/collection': 'fmnh_ins_number',
        // The contract guesses a carrier for these two and has not settled it.
        'habitat/text': null,
        'collection_method/text': null,
        // No carrier until a person's name has its own value.
        'identified_by/1': null,
      };
      carriers.forEach((String path, String? carrier) {
        expect(PartPath.tryParse(path)!.carrierField, carrier, reason: path);
      });
    });

    test(
      'a whole value is named for a sentence, and carried when one field does',
      () {
        expect(partValueLabel('location'), 'location');
        expect(partValueLabel('when'), 'dates');
        expect(partValueLabel('ids'), 'identifiers');
        expect(partValueLabel('bogus'), isNull);
        expect(partValueCarrier('location'), 'precise_location');
        expect(
          partValueCarrier('when'),
          isNull,
          reason: 'two fields carry dates',
        );
        expect(partValueCarrier('bogus'), isNull);
      },
    );
  });

  group('what a part reads as', () {
    test('a value is shown in its unit, and absence is words', () {
      final FieldParts parts = read(elevationParts(), key: 'elevation_from_m');
      expect(parts.byPath('elevation/from')!.valueText, '1950.72 m');
      expect(parts.byPath('elevation/unit')!.valueText, 'Feet');
      expect(parts.byPath('elevation/kind')!.valueText, 'Point');
      final FieldPart empty = FieldPart(
        path: PartPath.tryParse('location/island')!,
        state: 'not_present',
      );
      expect(empty.valueText, 'Not present');
    });

    test(
      'the wording is shown only where it says something the value does not',
      () {
        final Raw raw = rawOf(locationParts());
        at(raw, 'location/province')['wording'] = 'Davao';
        final FieldParts parts = read(raw);
        expect(parts.byPath('location/province')!.originalWording, isNull);
        expect(parts.byPath('location/country')!.originalWording, 'P.I.');
      },
    );

    test('a conflict names the readings, cut to 40 characters each', () {
      final Raw raw = rawOf(collectorParts());
      final Map<String, dynamic> part = at(raw, 'collectors/1');
      part['value'] = 'A' * 60;
      (part['alternatives'] as List).add(<String, dynamic>{
        'value': 'Frederick Gordon Werner',
        'evidence_ids': <String>[],
      });
      final FieldPart collector = read(raw, key: 'collectors').parts.single;
      final String? sentence = partReviewSentence(collector);
      expect(sentence, startsWith('Three readings differ: ${'A' * 39}…, '));
      expect(sentence, endsWith('Frederick Gordon Werner.'));
    });

    test('a conflict names sources where an alternative rests on a lookup', () {
      final FieldPart collector = read(
        collectorParts(),
        key: 'collectors',
      ).parts.single;
      expect(
        partReviewSentence(
          collector,
          evidenceKinds: const <String, String>{'ev-2B-collector': 'literal'},
        ),
        startsWith('Two readings differ'),
      );
      expect(
        partReviewSentence(
          collector,
          evidenceKinds: const <String, String>{'ev-2B-collector': 'lookup'},
        ),
        startsWith('Two sources differ'),
      );
    });

    test('no support says so, and a doubt has no sentence of its own', () {
      final Raw raw = rawOf(locationParts());
      at(raw, 'location/island')
        ..remove('value')
        ..remove('basis')
        ..['state'] = 'unresolved'
        ..['evidence_ids'] = <String>[]
        ..['evidence_relations'] = <String, String>{}
        ..['review'] = <String, dynamic>{
          'code': 'no_support',
          'reason': 'No source supports an island.',
        };
      final FieldParts parts = read(raw);
      expect(
        partReviewSentence(parts.byPath('location/island')!),
        'No source supports this part.',
      );
      expect(partReviewSentence(parts.byPath('location/place')!), isNull);
      expect(partReviewSentence(parts.byPath('location/country')!), isNull);
    });

    test('a level the app does not know is shown, not hidden', () {
      expect(PartPath.tryParse('location/barangay')!.label, 'Barangay');
      expect(PartPath.tryParse('location/barangay/2')!.label, 'Barangay 2');
    });
  });
}

Map<String, dynamic> _collector(int index) => <String, dynamic>{
  'path': 'collectors/$index',
  'state': 'supported',
  'value': 'Collector $index',
  'basis': 'label',
  'evidence_ids': <String>['ev-2A-collector'],
  'evidence_relations': <String, String>{'ev-2A-collector': 'supports'},
};
