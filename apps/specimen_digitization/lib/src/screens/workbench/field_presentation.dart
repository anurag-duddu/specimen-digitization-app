/// Field names and correction guidance drawn from the existing field keys.
library;

import '../../models.dart';
import '../../widgets/field_row.dart';

/// Elevation endpoints retain the unit named by their schema field.
String fieldReviewName(Json field) => switch (field['field_key']) {
  'elevation_from_m' => 'Elevation from (m)',
  'elevation_to_m' => 'Elevation to (m)',
  'elevation_from_ft' => 'Elevation from (ft)',
  'elevation_to_ft' => 'Elevation to (ft)',
  _ => textOf(field['display_name'], field['field_key'].toString()),
};

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
