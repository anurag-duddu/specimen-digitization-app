/// Field names and correction guidance drawn from the existing field keys.
library;

import '../../models.dart';
import '../../widgets/field_row.dart';

/// Elevation endpoints retain the unit named by their schema field.
String fieldReviewName(Json field) => switch (field['field_key']) {
  'country' => 'Country',
  'province_state' => 'Province or state',
  'county' => 'County',
  'city' => 'City',
  'precise_location' => 'Precise location',
  'elevation_from_m' => 'Elevation from (m)',
  'elevation_to_m' => 'Elevation to (m)',
  'elevation_from_ft' => 'Elevation from (ft)',
  'elevation_to_ft' => 'Elevation to (ft)',
  'habitat' => 'Habitat',
  'collection_method' => 'Collection method',
  'date_visited_from' => 'Date visited from',
  'date_visited_to' => 'Date visited to',
  'collectors' => 'Collectors',
  // Its meaning is still awaiting collection policy. Preserve the owner's
  // term rather than presenting an invented interpretation of the acronym.
  'verbatim_dts' => 'Verbatim D/T/S',
  'taxon' => 'Taxon',
  'date_identified' => 'Date identified',
  'identified_by_irn' => 'Identified by IRN',
  'fmnh_ins_number' => 'FMNH INS number',
  'collection_code' => 'Collection code',
  _ => textOf(field['display_name'], field['field_key'].toString()),
};

/// Review domains, in the order a specimen reviewer scans them.
const List<String> fieldReviewGroups = <String>[
  'Location',
  'Collection',
  'Identification',
  'Record identifiers',
  'Other',
];

/// Keys within each domain retain a stable semantic order; the wire's map
/// insertion order is not a useful geography or date order.
const Map<String, List<String>> _groupKeys = <String, List<String>>{
  'Location': <String>[
    'country',
    'province_state',
    'county',
    'city',
    'precise_location',
    'elevation_from_m',
    'elevation_to_m',
    'elevation_from_ft',
    'elevation_to_ft',
  ],
  'Collection': <String>[
    'date_visited_from',
    'date_visited_to',
    'collectors',
    'habitat',
    'collection_method',
    'verbatim_dts',
  ],
  'Identification': <String>['taxon', 'date_identified', 'identified_by_irn'],
  'Record identifiers': <String>['fmnh_ins_number', 'collection_code'],
};

String fieldReviewGroup(Json field) {
  final key = field['field_key'].toString();
  return _groupKeys.entries
          .where((entry) => entry.value.contains(key))
          .map((entry) => entry.key)
          .firstOrNull ??
      'Other';
}

int fieldReviewOrder(Json field) {
  final keys = _groupKeys[fieldReviewGroup(field)];
  return keys?.indexOf(field['field_key'].toString()) ?? 0;
}

/// A value's unresolved state is separate from whether it happens to contain
/// text. Supported values with attached findings also need review.
bool fieldNeedsReview(String? state, {bool hasIssues = false}) =>
    hasIssues ||
    !const <String>{
      'supported',
      'not_present',
      'not_applicable',
    }.contains(state);

/// Keeps source wording, interpretation and normalization separate while a
/// reviewer corrects geography. This guidance never supplies a missing value.
String fieldCorrectionHelp(Json field, FieldLayer layer) {
  final key = field['field_key'].toString();
  if (key.startsWith('elevation_')) {
    return switch (layer) {
      FieldLayer.asWritten =>
        'Keep the number and unit exactly as written on the label.',
      FieldLayer.readAs =>
        'Check the unit and range endpoint against the field name.',
      FieldLayer.standardized =>
        'Keep a converted value separate from the original wording and retain its evidence.',
    };
  }
  if (key == 'country') {
    return switch (layer) {
      FieldLayer.asWritten =>
        'Copy the country text on the label, keeping abbreviations as written.',
      FieldLayer.readAs =>
        'Interpret the country wording only as far as the retained evidence supports.',
      FieldLayer.standardized =>
        'Use a supported country name and retain its authority evidence.',
    };
  }
  if (const {
    'province_state',
    'county',
    'city',
    'precise_location',
  }.contains(key)) {
    return switch (layer) {
      FieldLayer.asWritten =>
        'Keep locality wording exactly as written, including abbreviations.',
      FieldLayer.readAs =>
        'Expand locality wording only when the retained evidence supports it.',
      FieldLayer.standardized =>
        'Use a locality supported by authority evidence. Keep uncertain matches unresolved.',
    };
  }
  return switch (layer) {
    FieldLayer.asWritten =>
      'Keep the text exactly as written. Do not add missing evidence.',
    FieldLayer.readAs =>
      'Keep your interpretation separate from the source wording.',
    FieldLayer.standardized => 'Needs an authority match and evidence.',
  };
}
