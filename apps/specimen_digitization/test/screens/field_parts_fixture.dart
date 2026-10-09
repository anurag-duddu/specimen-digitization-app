// Fixtures for the field parts tests: the worked examples of the planned wire
// contract (`docs/execution/FIELD_PARTS_WIRE.md` on pull request 288, section
// 4), built as the workspace map the app reads.
//
// The server does not write `parts` yet, so these are what a later writer is
// agreed to send, not what any record holds today. Each function builds a
// fresh structure, so a test may change it without touching another.
//
// The label is the one the PRD's worked example uses: locality "E. slope Mt.
// McKinley / Davao Prov. / Mindanao, P.I.", "Mossy forest 6400'", "F.G.
// Werner". The evidence ids are symbolic, as the contract's are; real ids are
// UUIDs.

import 'package:specimen_digitization/src/models.dart';

/// The verbatim locality of subject 105526321.
const String locality = 'E. slope Mt. McKinley / Davao Prov. / Mindanao, P.I.';

Map<String, dynamic> _row(
  String id,
  String kind,
  String excerpt, {
  String? source,
}) => <String, dynamic>{
  'evidence_id': id,
  'kind': kind,
  'excerpt': excerpt,
  'region_id': 'label-one',
  'source': ?source,
};

/// The evidence rows the parts cite, as the workspace lists them.
List<Map<String, dynamic>> partEvidence() => <Map<String, dynamic>>[
  _row('ev-2A-locality', 'literal', locality),
  _row('ev-2B-locality', 'literal', locality),
  _row(
    'ev-rule-notation',
    'rule',
    'P.I. stands for Philippine Islands, the name of the country before '
        'independence',
  ),
  _row('ev-tgn-philippines', 'authority', 'Philippines', source: 'tgn'),
  _row('ev-wikidata-davao', 'lookup', 'Davao', source: 'wikidata'),
  _row('ev-geolocate-mckinley', 'lookup', 'Denali', source: 'geolocate'),
  _row('ev-2A-elevation', 'literal', "Mossy forest 6400'"),
  _row('ev-rule-feet-to-metres', 'rule', '1 ft = 0.3048 m'),
  _row('ev-2A-collector', 'literal', 'F.G. Werner'),
  _row('ev-2B-collector', 'literal', 'F.G. Wermer'),
  // Subject 105526322: both readers dropped the foot mark.
  _row('ev-A-elevation', 'literal', 'Elev. 6400'),
  _row('ev-B-elevation', 'literal', 'Elev. 6400'),
  _row(
    'ev-check-unit-not-written',
    'derived',
    'The elevation has no unit written',
    source: 'elevation_parser',
  ),
  _row(
    'ev-rule-unit-from-highest-point',
    'rule',
    'A number with no unit is taken in the unit that keeps it below the '
        'highest point of the country',
  ),
  _row(
    'ev-highest-point-philippines',
    'lookup',
    'Mt. Apo, about 2,954 m',
    source: 'wikidata',
  ),
  _row(
    'ev-reasoning-unit',
    'reasoning',
    '6400 m would be higher than the highest point in the Philippines, so '
        'the unit is taken as feet',
  ),
];

/// The place tree of subject 105526321, on `precise_location` (contract 4.1).
///
/// Country is derived ("P.I."), island and province are as written, and the
/// named place is the one part a person is asked about: a lookup of "Mt.
/// McKinley" returns Denali, which is not in Davao. The list is in the
/// contract's bytewise order, so `location/place` comes before
/// `location/province`, its parent.
List<Map<String, dynamic>> locationParts() => <Map<String, dynamic>>[
  <String, dynamic>{
    'path': 'location/country',
    'state': 'supported',
    'value': 'Philippines',
    'basis': 'derived',
    'wording': 'P.I.',
    'parent': 'location/verbatim',
    'authority_id': 'tgn:RECORD-ID',
    'evidence_ids': <String>[
      'ev-2A-locality',
      'ev-2B-locality',
      'ev-rule-notation',
      'ev-tgn-philippines',
    ],
    'evidence_relations': <String, String>{
      'ev-2A-locality': 'supports',
      'ev-2B-locality': 'supports',
      'ev-rule-notation': 'decides',
      'ev-tgn-philippines': 'supports',
    },
  },
  <String, dynamic>{
    'path': 'location/island',
    'state': 'supported',
    'value': 'Mindanao',
    'basis': 'label',
    'parent': 'location/country',
    'evidence_ids': <String>['ev-2A-locality', 'ev-2B-locality'],
    'evidence_relations': <String, String>{
      'ev-2A-locality': 'supports',
      'ev-2B-locality': 'supports',
    },
  },
  <String, dynamic>{
    'path': 'location/place',
    'state': 'supported',
    'value': 'Mt. McKinley',
    'basis': 'label',
    'wording': 'E. slope Mt. McKinley',
    'parent': 'location/province',
    'evidence_ids': <String>[
      'ev-2A-locality',
      'ev-2B-locality',
      'ev-geolocate-mckinley',
    ],
    'evidence_relations': <String, String>{
      'ev-2A-locality': 'supports',
      'ev-2B-locality': 'supports',
      'ev-geolocate-mckinley': 'contradicts',
    },
    'review': <String, dynamic>{
      'code': 'doubt',
      'reason':
          'No approved source holds this mountain. A lookup of Mt. McKinley '
          'returns Denali, which is not in Davao.',
    },
  },
  <String, dynamic>{
    'path': 'location/province',
    'state': 'supported',
    'value': 'Davao',
    'basis': 'label',
    'wording': 'Davao Prov.',
    'parent': 'location/island',
    'evidence_ids': <String>[
      'ev-2A-locality',
      'ev-2B-locality',
      'ev-wikidata-davao',
    ],
    'evidence_relations': <String, String>{
      'ev-2A-locality': 'supports',
      'ev-2B-locality': 'supports',
      'ev-wikidata-davao': 'supports',
    },
  },
];

/// The elevation of subject 105526321, on `elevation_from_m` (contract 4.1):
/// 6400 ft stored as 1950.72 m, with the unit as the label stated it.
List<Map<String, dynamic>> elevationParts() => <Map<String, dynamic>>[
  <String, dynamic>{
    'path': 'elevation/from',
    'state': 'supported',
    'value': '1950.72',
    'basis': 'derived',
    'wording': "6400'",
    'evidence_ids': <String>['ev-2A-elevation', 'ev-rule-feet-to-metres'],
    'evidence_relations': <String, String>{
      'ev-2A-elevation': 'supports',
      'ev-rule-feet-to-metres': 'decides',
    },
  },
  <String, dynamic>{
    'path': 'elevation/kind',
    'state': 'supported',
    'value': 'point',
    'basis': 'label',
    'wording': "6400'",
    'evidence_ids': <String>['ev-2A-elevation'],
    'evidence_relations': <String, String>{'ev-2A-elevation': 'supports'},
  },
  <String, dynamic>{
    'path': 'elevation/unit',
    'state': 'supported',
    'value': 'ft',
    'basis': 'label',
    'wording': "6400'",
    'evidence_ids': <String>['ev-2A-elevation'],
    'evidence_relations': <String, String>{'ev-2A-elevation': 'supports'},
  },
];

/// The elevation of subject 105526322, on `elevation_from_m` (contract 4.2):
/// the unit is inferred, and the metres follow from it, so both go to a
/// person. The kind is read as written and does not.
List<Map<String, dynamic>> inferredElevationParts() => <Map<String, dynamic>>[
  <String, dynamic>{
    'path': 'elevation/from',
    'state': 'supported',
    'value': '1950.72',
    'basis': 'inferred',
    'wording': 'Elev. 6400',
    'derived_from': <String>['elevation/unit'],
    'evidence_ids': <String>[
      'ev-A-elevation',
      'ev-B-elevation',
      'ev-rule-feet-to-metres',
    ],
    'evidence_relations': <String, String>{
      'ev-A-elevation': 'supports',
      'ev-B-elevation': 'supports',
      'ev-rule-feet-to-metres': 'decides',
    },
    'review': <String, dynamic>{
      'code': 'doubt',
      'reason': 'These metres follow from a unit that is inferred.',
    },
  },
  <String, dynamic>{
    'path': 'elevation/kind',
    'state': 'supported',
    'value': 'point',
    'basis': 'label',
    'wording': 'Elev. 6400',
    'evidence_ids': <String>['ev-A-elevation', 'ev-B-elevation'],
    'evidence_relations': <String, String>{
      'ev-A-elevation': 'supports',
      'ev-B-elevation': 'supports',
    },
  },
  <String, dynamic>{
    'path': 'elevation/unit',
    'state': 'supported',
    'value': 'ft',
    'basis': 'inferred',
    'derived_from': <String>['location/country'],
    'evidence_ids': <String>[
      'ev-A-elevation',
      'ev-B-elevation',
      'ev-check-unit-not-written',
      'ev-rule-unit-from-highest-point',
      'ev-highest-point-philippines',
      'ev-reasoning-unit',
    ],
    'evidence_relations': <String, String>{
      'ev-A-elevation': 'supports',
      'ev-B-elevation': 'supports',
      'ev-check-unit-not-written': 'supports',
      'ev-rule-unit-from-highest-point': 'decides',
      'ev-highest-point-philippines': 'supports',
      'ev-reasoning-unit': 'supports',
    },
    'review': <String, dynamic>{
      'code': 'doubt',
      'reason':
          'Feet is inferred: 6400 m would be higher than any point in the '
          'Philippines.',
    },
  },
];

/// The collectors of subject 105526321 (contract 4.1): one reader wrote
/// "Wermer", so the best-supported value is filled and only this part goes to
/// a person.
List<Map<String, dynamic>> collectorParts() => <Map<String, dynamic>>[
  <String, dynamic>{
    'path': 'collectors/1',
    'state': 'supported',
    'value': 'F.G. Werner',
    'basis': 'label',
    'evidence_ids': <String>['ev-2A-collector', 'ev-2B-collector'],
    'evidence_relations': <String, String>{
      'ev-2A-collector': 'supports',
      'ev-2B-collector': 'contradicts',
    },
    'alternatives': <Map<String, dynamic>>[
      <String, dynamic>{
        'value': 'F.G. Wermer',
        'basis': 'label',
        'evidence_ids': <String>['ev-2B-collector'],
      },
    ],
    'review': <String, dynamic>{
      'code': 'conflict',
      'reason':
          'The two readings differ: Werner or Wermer. No source checks a '
          "collector's name.",
    },
  },
];

/// A field as the workspace builds it from the server's map (the fields
/// `api_repository.dart` adds around the server's own).
Map<String, dynamic> workspaceField(
  String key, {
  String state = 'supported',
  String? layer,
  String? literal,
  String? normalized,
  List<String> evidenceIds = const <String>[],
  Object? parts,
  bool required = true,
}) => <String, dynamic>{
  'field_key': key,
  'state': state,
  'required': required,
  'layer': ?layer,
  'literal_value': ?literal,
  'normalized': ?normalized,
  'evidence_ids': evidenceIds,
  'parts': ?parts,
};

/// Subject 105526321: the place tree, the elevation and the collectors, each on
/// the field that carries it.
Specimen subject105526321() => Specimen(<String, dynamic>{
  'specimen_id': 'subject-105526321',
  'regions': <Map<String, dynamic>>[
    <String, dynamic>{'region_id': 'label-one'},
  ],
  'fields': <Map<String, dynamic>>[
    workspaceField(
      'precise_location',
      layer: 'verbatim',
      literal: locality,
      evidenceIds: <String>['ev-2A-locality', 'ev-2B-locality'],
      parts: locationParts(),
    ),
    workspaceField(
      'elevation_from_m',
      layer: 'derived',
      literal: "6400'",
      normalized: '1950.72',
      evidenceIds: <String>['ev-2A-elevation'],
      parts: elevationParts(),
    ),
    workspaceField(
      'collectors',
      layer: 'settled',
      literal: 'F.G. Werner',
      evidenceIds: <String>['ev-2A-collector', 'ev-2B-collector'],
      parts: collectorParts(),
    ),
    workspaceField(
      'country',
      layer: 'settled',
      literal: 'P.I.',
      normalized: 'Philippines',
    ),
  ],
  'evidence': partEvidence(),
});

/// Subject 105526322: the elevation whose unit is inferred.
Specimen subject105526322() => Specimen(<String, dynamic>{
  'specimen_id': 'subject-105526322',
  'regions': <Map<String, dynamic>>[
    <String, dynamic>{'region_id': 'label-one'},
  ],
  'fields': <Map<String, dynamic>>[
    workspaceField(
      'elevation_from_m',
      state: 'unresolved',
      evidenceIds: <String>['ev-A-elevation', 'ev-B-elevation'],
      parts: inferredElevationParts(),
    ),
    workspaceField('country', layer: 'verbatim', literal: 'Philippines'),
  ],
  'evidence': partEvidence(),
});
