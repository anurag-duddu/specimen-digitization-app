/// The field settlement codes of the units path
/// (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4):
/// `cleared:<field>:<label>` and `marked:<field>:<label>:<why>`.
///
/// Read by the blockers list (`screens/workbench/blockers.dart`) and by the
/// record's reasons offered in the decision sheet (`reason_codes.dart`).
library;

import 'models.dart';

const String clearedCode = 'cleared';
const String markedCode = 'marked';

/// The exact fields named by the specimen contract. A reason suffix is a
/// routing hint only when it names a real field in this response.
const Map<String, String> contractFieldNames = <String, String>{
  'fmnh_ins_number': 'Catalog number',
  'collection_code': 'Collection code',
  'country': 'Country',
  'province_state': 'State or province',
  'county': 'County',
  'city': 'City',
  'precise_location': 'Locality',
  'elevation_from_m': 'Minimum elevation (m)',
  'elevation_to_m': 'Maximum elevation (m)',
  'elevation_from_ft': 'Minimum elevation (ft)',
  'elevation_to_ft': 'Maximum elevation (ft)',
  'habitat': 'Habitat',
  'collection_method': 'Collection method',
  'date_visited_from': 'Collection start date',
  'date_visited_to': 'Collection end date',
  'collectors': 'Collectors',
  'verbatim_dts': 'Verbatim D/T/S',
  'taxon': 'Taxon',
  'identified_by_irn': 'Identifier',
  'date_identified': 'Identification date',
};

/// The field a settlement code's suffix names: its first part.
String settlementField(String suffix) => suffix.split(':').first;

/// The label a settlement code's suffix names (its second part) when
/// [specimen] holds that label, else null.
String? settlementLabel(Specimen specimen, String suffix) {
  final List<String> parts = suffix.split(':');
  return parts.length > 1 &&
          specimen.regions.any((Json region) => region['region_id'] == parts[1])
      ? parts[1]
      : null;
}

/// "Label N", N counting [specimen]'s regions from 1.
String settlementLabelName(Specimen specimen, String regionId) =>
    'Label ${specimen.regions.indexWhere((Json r) => r['region_id'] == regionId) + 1}';

/// The words for a `marked:` code's `why` (its suffix's third part), or null
/// for a why the app has no words for.
String? markedReasonWords(String suffix) {
  final List<String> parts = suffix.split(':');
  return switch (parts.length > 2 ? parts[2] : '') {
    'text_only' => 'only the readings back it',
    'conflict' => 'another reading competes',
    _ => null,
  };
}

/// A `cleared:` or `marked:` code in words, for a list of the record's
/// reasons: the field's contract name ("A field" when it has none), the
/// label's name when [specimen] holds that label, and why. Null for any other
/// code.
String? settlementPhrase(Specimen specimen, String code) {
  final int separator = code.indexOf(':');
  if (separator < 0) return null;
  final String base = code.substring(0, separator);
  if (base != clearedCode && base != markedCode) return null;
  final String suffix = code.substring(separator + 1);
  final String field = settlementField(suffix);
  final String? name = contractFieldNames[field];
  final String? region = settlementLabel(specimen, suffix);
  final String where = region == null
      ? ''
      : ' on ${settlementLabelName(specimen, region)}';
  final String subject = name == null
      ? 'A field is'
      : '$name ${field == 'collectors' ? 'are' : 'is'}';
  if (base == clearedCode) {
    return '$subject confirmed$where by the image, a source or a person';
  }
  final String? why = markedReasonWords(suffix);
  return '$subject marked for review$where${why == null ? '' : ': $why'}';
}
