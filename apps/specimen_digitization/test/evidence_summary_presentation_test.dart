import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/evidence_picker.dart';

void main() {
  test('label prose stays readable without changing retained evidence', () {
    final evidence = <String, dynamic>{
      'evidence_id': 'citation-a',
      'excerpt': 'Collected in\n  Manila, 1954',
    };
    expect(evidenceDisplaySummary(evidence), 'Collected in Manila, 1954');
    expect(evidence['excerpt'], 'Collected in\n  Manila, 1954');
  });

  test('JSON and newline candidates show values without internal keys', () {
    const payload =
        '{"field_key":"country","value":"Philippines","authority_id":"opaque:1"}\n'
        '{"field_key":"country","value":"Japan","authority_id":"opaque:2"}';
    final evidence = <String, dynamic>{'source': 'gbif', 'excerpt': payload};
    expect(evidenceDisplaySummary(evidence), 'GBIF · Philippines · Japan');
    expect(evidence['excerpt'], payload);
  });

  test('older dictionary excerpts summarize only known candidate properties', () {
    expect(
      evidenceDisplaySummary({
        'source': 'geolocate',
        'excerpt':
            "{'name': 'Manila', 'authority_id': 'opaque:1', 'accepted': False}",
      }),
      'GEOLocate · Manila',
    );
    expect(
      evidenceDisplaySummary({
        'excerpt': "{'name': 'St. John\\'s', 'id': None}",
      }),
      "St. John's",
    );
  });

  test('unknown structured payload and opaque IDs stay behind details', () {
    final digest = 'a' * 64;
    expect(
      evidenceDisplaySummary({
        'excerpt': '{"sha256":"$digest","backend_rule":"not_qualified"}',
      }),
      'Retained source evidence',
    );
    expect(evidenceDisplaySummary({'excerpt': digest}), 'Retained evidence');
  });

  test('picker keeps citation identity while offering a readable label', () {
    final specimen = Specimen({
      'specimen_id': 'record',
      'evidence': [
        {
          'evidence_id': 'citation-a',
          'source': 'gbif',
          'excerpt': '{"value":"Philippines","field_key":"country"}',
        },
        {
          'evidence_id': 'not-citable',
          'field_citation_supported': false,
          'excerpt': 'Not an accepted citation',
        },
      ],
    });
    final choices = evidenceChoices(specimen);
    expect(choices, hasLength(1));
    expect(choices.single.id, 'citation-a');
    expect(choices.single.label, 'Record: GBIF · Philippines');
  });
}
