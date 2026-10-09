import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/value_basis.dart';

// The basis is computed for display only, from what a record written before
// the field model v2 already holds (PRD, "Field model v2: four groups").

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

  group('layer settled', () {
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
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: '1950.72 m',
          parsed: '1950.72',
        ),
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

    test('case and spacing are ignored, spelling is not', () {
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'MT.  McKinley',
          normalized: 'mt. mckinley',
        ),
        ValueBasis.asWritten,
      );
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Chimaltenago',
          normalized: 'Chimaltenango',
        ),
        ValueBasis.derived,
      );
    });

    test('a unit mark is ignored only after a number', () {
      // The m of Mindanao is not a unit.
      expect(
        valueBasisFor(
          layer: 'settled',
          literal: 'Mindanao',
          parsed: 'Mindanao',
        ),
        ValueBasis.asWritten,
      );
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

    test('the readings stand in for a missing literal when they agree', () {
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

    test('readings that disagree give no wording as written', () {
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

    test('shows nothing where the stored values cannot tell', () {
      // One value only.
      expect(valueBasisFor(layer: 'settled', literal: 'Smith'), isNull);
      expect(valueBasisFor(layer: 'settled', normalized: 'Smith'), isNull);
      // Values agree, but nothing says the label stated them.
      expect(
        valueBasisFor(
          layer: 'settled',
          parsed: 'Mindanao',
          normalized: 'mindanao',
        ),
        isNull,
      );
    });
  });

  group('a record the rule cannot read', () {
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
    test('reads the layer, the three values and the readings', () {
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
        }),
        ValueBasis.asWritten,
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
