import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/value_basis.dart';

// The basis is computed for display only, from what a record written before
// the field model v2 already holds (PRD, "Field model v2: four groups"). A
// wrong chip is worse than none, so every case the stored values cannot tell
// apart expects null.

/// The letter [code] names, so no test source line holds an accent.
String char(int code) => String.fromCharCode(code);

void main() {
  group('layer verbatim and derived', () {
    test('verbatim is as written and derived is derived', () {
      expect(
        valueBasisFor(layer: 'verbatim', literal: 'Mindanao'),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(layer: 'derived', literal: '6400', normalized: '1950.72'),
        ValueBasis.derived,
      );
    });

    test('a layer that holds no value has no basis to show', () {
      expect(valueBasisFor(layer: 'verbatim'), isNull);
      expect(valueBasisFor(layer: 'derived', literal: '  '), isNull);
      expect(valueBasisFor(layer: 'settled'), isNull);
    });
  });

  group('layer settled, the named cases', () {
    test('P.I. settled as Philippines is derived', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'P.I.',
          normalized: 'Philippines',
        ),
        ValueBasis.derived,
      );
    });

    test("a written 6400' read as 6400 is as written", () {
      expect(
        valueBasisFor(layer: 'settled', literal: "6400'", parsed: '6400'),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(layer: 'settled', literal: '6400 ft.', parsed: '6400'),
        ValueBasis.asWritten,
      );
    });

    test('Mindanao confirmed by a lookup is as written', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Mindanao',
          normalized: 'Mindanao',
        ),
        ValueBasis.asWritten,
      );
    });

    test('Chimaltenago settled as Chimaltenango is derived', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Chimaltenago',
          normalized: 'Chimaltenango',
        ),
        ValueBasis.derived,
      );
    });
  });

  group('plain numbers compare by value', () {
    test("6400' with parsed 6400 and normalized 6400.00 is as written", () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_ft',
          literal: "6400'",
          parsed: '6400',
          normalized: '6400.00',
        ),
        ValueBasis.asWritten,
      );
    });

    test('1950.7 m with normalized 1950.70 is as written', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_m',
          literal: '1950.7 m',
          normalized: '1950.70',
        ),
        ValueBasis.asWritten,
      );
    });

    test('1950.7248 does not equal 1950.72', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_m',
          literal: '1950.7248 m',
          normalized: '1950.72',
        ),
        ValueBasis.derived,
      );
    });

    test('the readings 6400 ft with normalized 6400.00 is as written', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_ft',
          normalized: '6400.00',
          readings: <String>['6400 ft', '6400 ft'],
        ),
        ValueBasis.asWritten,
      );
    });

    test('a number is not a longer number with a point taken out', () {
      expect(
        valueBasisFor(layer: 'settled', literal: '6400.5', normalized: '64005'),
        ValueBasis.derived,
      );
    });

    test('a leading zero is an identifier, kept as text', () {
      expect(
        valueBasisFor(layer: 'settled', literal: '0042', normalized: '42'),
        ValueBasis.derived,
      );
      expect(
        valueBasisFor(layer: 'settled', literal: '0042', normalized: '0042'),
        ValueBasis.asWritten,
      );
    });

    test('a thousands separator is ignored', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_m',
          literal: '1,950 m',
          normalized: '1950',
        ),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_m',
          literal: '1,950 m',
          normalized: '1950.00',
        ),
        ValueBasis.asWritten,
      );
    });
  });

  group('the unit a field holds', () {
    test('a reading in feet that differs from the metres value is derived', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_m',
          literal: '6400 ft',
          parsed: '6400',
          normalized: '1950.72',
        ),
        ValueBasis.derived,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_to_m',
          literal: "6400'",
          normalized: '1950.72',
        ),
        ValueBasis.derived,
      );
    });

    test('a reading in metres that differs from the feet value is derived', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_ft',
          literal: '1950 m',
          normalized: '6397.64',
        ),
        ValueBasis.derived,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_to_ft',
          literal: '1950 metres',
          normalized: '6397.64',
        ),
        ValueBasis.derived,
      );
    });

    test('the same number in the other unit shows nothing', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_m',
          literal: '6400 ft',
          normalized: '6400.00',
        ),
        isNull,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_ft',
          literal: '1950.7 m',
          normalized: '1950.70',
        ),
        isNull,
      );
    });

    test('a wording with no unit mark is read in the field unit', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'elevation_from_m',
          literal: '1950.7',
          normalized: '1950.70',
        ),
        ValueBasis.asWritten,
      );
    });

    test('a field with no unit key gives the unit marks no meaning', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'habitat',
          literal: '6400 ft',
          normalized: '6400.00',
        ),
        ValueBasis.asWritten,
      );
    });
  });

  group('words fold punctuation and diacritics', () {
    test('Mt. Kinabalu and Mt Kinabalu are as written', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Mt. Kinabalu',
          normalized: 'Mt Kinabalu',
        ),
        ValueBasis.asWritten,
      );
    });

    test('Cordoba and its accented spelling are as written', () {
      final String accented = 'C${char(0xF3)}rdoba';
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Cordoba',
          normalized: accented,
        ),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: accented,
          normalized: 'CORDOBA',
        ),
        ValueBasis.asWritten,
      );
      // A decomposed accent, as some sources send it.
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Co${char(0x301)}rdoba',
          normalized: 'Cordoba',
        ),
        ValueBasis.asWritten,
      );
    });

    test('a different letter is still a difference', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Cordoba',
          normalized: 'Cordova',
        ),
        ValueBasis.derived,
      );
    });

    test('case and spacing are ignored, spelling is not', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'MT.  McKinley',
          normalized: 'mt. mckinley',
        ),
        ValueBasis.asWritten,
      );
    });

    test('a unit mark is ignored only after a number', () {
      // The m of Mindanao is not a unit.
      expect(
        valueBasisFor(layer: 'settled', literal: 'Mindanao', parsed: 'Indanao'),
        ValueBasis.derived,
      );
      expect(
        valueBasisFor(layer: 'settled', literal: '12 mm', parsed: '12'),
        ValueBasis.derived,
      );
    });

    test('any value that differs makes it derived', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: "6400'",
          parsed: '6400',
          normalized: '1950.72',
        ),
        ValueBasis.derived,
      );
    });
  });

  group('the date fields', () {
    test('a settled date shows nothing, whatever the values say', () {
      for (final key in <String>[
        'date_visited_from',
        'date_visited_to',
        'date_identified',
        'verbatim_dts',
      ]) {
        expect(
          valueBasisFor(
            layer: 'settled',
            fieldKey: key,
            literal: '3 Sept. 1946',
            normalized: '1946-09-03',
          ),
          isNull,
          reason: key,
        );
        expect(
          valueBasisFor(
            layer: 'settled',
            fieldKey: key,
            literal: '1946',
            normalized: '1946',
          ),
          isNull,
          reason: '$key: agreeing text cannot tell a parse from a copy',
        );
      }
    });

    test('their verbatim and derived layers still show their chip', () {
      expect(
        valueBasisFor(
          layer: 'verbatim',
          fieldKey: 'date_visited_from',
          literal: "3 Sept. '46",
        ),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(
          layer: 'derived',
          fieldKey: 'date_visited_to',
          literal: "3 Sept. '46",
          normalized: '1946-09-03',
        ),
        ValueBasis.derived,
      );
    });

    test('a stated basis is still honoured on a date', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'date_visited_from',
          basis: 'label',
          literal: '3 Sept. 1946',
          normalized: '1946-09-03',
        ),
        ValueBasis.asWritten,
      );
    });

    test('other fields keep the rule', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          fieldKey: 'country',
          literal: 'P.I.',
          normalized: 'Philippines',
        ),
        ValueBasis.derived,
      );
    });
  });

  group('the readings', () {
    test('stand in for a missing literal when they agree', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: 'Philippines',
          readings: <String>['P.I.', 'p.i.'],
        ),
        ValueBasis.derived,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: 'Mindanao',
          readings: <String>['Mindanao', 'mindanao'],
        ),
        ValueBasis.asWritten,
      );
    });

    test('that disagree give no wording as written', () {
      // Two spellings of one value: the label's wording cannot be named, and
      // the one value left cannot tell.
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: 'Chimaltenango',
          readings: <String>['Chimaltenago', 'Chimaltenango'],
        ),
        isNull,
      );
    });

    test('that are a whole observation are not a field wording', () {
      final String whole =
          'E. slope Mt. McKinley / Davao Prov. / Mindanao, P.I. / '
          'Mossy forest 6400 / 3 Sept. 1946 / F.G. Werner';
      expect(whole.length, greaterThan(maxFieldWordingLength));
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: 'Mindanao',
          readings: <String>[whole, whole],
        ),
        isNull,
      );
      // Even where the other values would have said Derived.
      expect(
        valueBasisFor(
          layer: 'settled',
          parsed: 'Mindanao',
          normalized: 'Mindanao, Philippines',
          readings: <String>[whole],
        ),
        ValueBasis.derived,
        reason: 'values that already disagree need no wording to say so',
      );
    });

    test('that run over a line are not a field wording', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: 'Davao',
          readings: <String>['Davao\nProv.'],
        ),
        isNull,
      );
    });

    test('are trusted up to the length bound and no further', () {
      final String atBound = 'D' * maxFieldWordingLength;
      final String over = 'D' * (maxFieldWordingLength + 1);
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: atBound,
          readings: <String>[atBound],
        ),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: over,
          readings: <String>[over],
        ),
        isNull,
      );
    });

    test('one long reading among short ones is not trusted either', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          normalized: 'Mindanao',
          readings: <String>['Mindanao', 'M' * 200],
        ),
        isNull,
      );
    });
  });

  group('where the stored values cannot tell', () {
    test('a lone value, or agreeing values with no wording, show nothing', () {
      expect(valueBasisFor(layer: 'settled', literal: 'Smith'), isNull);
      expect(valueBasisFor(layer: 'settled', normalized: 'Smith'), isNull);
      expect(
        valueBasisFor(
          layer: 'settled',
          parsed: 'Mindanao',
          normalized: 'mindanao',
        ),
        isNull,
      );
    });

    test('no layer, or a layer this app does not know, shows nothing', () {
      expect(
        valueBasisFor(layer: null, literal: 'P.I.', normalized: 'Philippines'),
        isNull,
      );
      expect(
        valueBasisFor(
          layer: 'reconciled',
          literal: 'P.I.',
          normalized: 'Philippines',
        ),
        isNull,
      );
    });

    test('an old record is never shown as inferred', () {
      for (final layer in <String?>[null, 'verbatim', 'settled', 'derived']) {
        expect(
          valueBasisFor(
            layer: layer,
            literal: 'P.I.',
            parsed: 'P.I.',
            normalized: 'Philippines',
          ),
          isNot(ValueBasis.inferred),
        );
      }
    });
  });

  group('a basis the record states itself', () {
    test('wins over the layer, and can say inferred', () {
      expect(
        valueBasisFor(layer: 'verbatim', basis: 'inferred', literal: 'feet'),
        ValueBasis.inferred,
      );
      expect(
        valueBasisFor(layer: 'derived', basis: 'label', literal: 'Davao'),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(layer: 'settled', basis: 'derived', literal: 'Davao'),
        ValueBasis.derived,
      );
    });

    test('a word this app does not know is not guessed around', () {
      expect(
        valueBasisFor(layer: 'verbatim', basis: 'estimated', literal: 'Davao'),
        isNull,
      );
      expect(
        valueBasisFor(layer: 'verbatim', basis: 7, literal: 'Davao'),
        isNull,
      );
    });

    test('a field with no value has none', () {
      expect(valueBasisFor(layer: 'settled', basis: 'label'), isNull);
    });
  });

  group('a specimen field', () {
    test('reads the key, the layer, the three values and the readings', () {
      expect(
        fieldValueBasis(<String, dynamic>{
          'field_key': 'country',
          'layer': 'settled',
          'normalized': 'Philippines',
          'verbatim_by_observation': <String, dynamic>{
            'reader-a': 'P.I.',
            'reader-b': 'P.I.',
          },
        }),
        ValueBasis.derived,
      );
      expect(
        fieldValueBasis(<String, dynamic>{
          'field_key': 'elevation_from_ft',
          'layer': 'settled',
          'literal_value': "6400'",
          'parsed_value': '6400',
          'normalized': '6400.00',
        }),
        ValueBasis.asWritten,
      );
      expect(
        fieldValueBasis(<String, dynamic>{
          'field_key': 'date_visited_from',
          'layer': 'settled',
          'literal_value': "3 Sept. '46",
          'normalized': '1946-09-03',
        }),
        isNull,
      );
      expect(
        fieldValueBasis(<String, dynamic>{
          'field_key': 'city',
          'layer': 'verbatim',
          'literal_value': 'Manila',
          'basis': 'inferred',
        }),
        ValueBasis.inferred,
      );
    });

    test('tolerates values that are not text', () {
      expect(
        fieldValueBasis(<String, dynamic>{
          'field_key': 'collectors',
          'layer': 4,
          'literal_value': 4,
          'verbatim_by_observation': 'not a map',
        }),
        isNull,
      );
    });
  });

  group('the chip words', () {
    test(
      'fit a chip, read in sentence case and are named by their wire word',
      () {
        expect(
          <String>[for (final b in ValueBasis.values) b.label],
          <String>['As written', 'Derived', 'Inferred'],
        );
        for (final basis in ValueBasis.values) {
          expect(basis.label.length, lessThanOrEqualTo(20));
          expect(basis.semanticsLabel, startsWith('Basis: '));
        }
        expect(ValueBasis.fromWire('label'), ValueBasis.asWritten);
        expect(ValueBasis.fromWire('derived'), ValueBasis.derived);
        expect(ValueBasis.fromWire('inferred'), ValueBasis.inferred);
        expect(ValueBasis.fromWire('As written'), isNull);
        expect(ValueBasis.fromWire(null), isNull);
      },
    );
  });
}
