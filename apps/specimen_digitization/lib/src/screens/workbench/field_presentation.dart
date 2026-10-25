/// Field names and correction guidance drawn from the existing field keys.
library;

import '../../models.dart';
import '../../widgets/field_row.dart';
import 'pending_changes.dart';

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

/// Where a key belongs when no group lists it, so a field is never dropped.
///
/// It draws only when a record carries a key no group names, as a later key
/// set might. Today's 20 keys all have a home above it.
const String otherFieldGroup = 'Other';

/// The four groups of the field model v2, in the order a reviewer scans them.
///
/// Each group lists the keys it holds, in reading order. A later key set joins
/// a group by adding its keys here; nothing else in the panel names a group.
/// The four are the owner's: IDs, Collection, Date and Taxa (PRD, "Field model
/// v2: four groups"). The keys are the 20 the server writes today.
const List<(String, List<String>)> _fieldGroups = <(String, List<String>)>[
  ('IDs', <String>['fmnh_ins_number', 'collection_code']),
  (
    'Collection',
    <String>[
      'country',
      'province_state',
      'county',
      'city',
      'precise_location',
      'elevation_from_m',
      'elevation_to_m',
      'elevation_from_ft',
      'elevation_to_ft',
      'collectors',
      'habitat',
      'collection_method',
    ],
  ),
  (
    'Date',
    <String>[
      'date_visited_from',
      'date_visited_to',
      'date_identified',
      'verbatim_dts',
    ],
  ),
  ('Taxa', <String>['taxon', 'identified_by_irn']),
];

/// The group titles in reading order, with the catch-all last.
final List<String> fieldReviewGroups = <String>[
  for (final (String title, List<String> _) in _fieldGroups) title,
  otherFieldGroup,
];

/// The group a field belongs to.
String fieldReviewGroup(Json field) {
  final key = field['field_key'].toString();
  return _fieldGroups
          .where((group) => group.$2.contains(key))
          .map((group) => group.$1)
          .firstOrNull ??
      otherFieldGroup;
}

/// Keys within each group retain a stable semantic order; the wire's map
/// insertion order is not a useful geography or date order.
int fieldReviewOrder(Json field) {
  final key = field['field_key'].toString();
  final keys = _fieldGroups
      .where((group) => group.$2.contains(key))
      .map((group) => group.$2)
      .firstOrNull;
  return keys?.indexOf(key) ?? 0;
}

/// A value's unresolved state is separate from whether it happens to contain
/// text. Supported values with attached findings also need review.
bool fieldNeedsReview(
  String? state, {
  bool hasIssues = false,
  bool hasValue = true,
  bool isPending = false,
}) =>
    isPending ||
    hasIssues ||
    (state == 'supported' && !hasValue) ||
    !const <String>{
      'supported',
      'not_present',
      'not_applicable',
    }.contains(state);

/// Presentation counts never change the record's clearance or lifecycle.
///
/// Missing is absence of a current value, including an explicit `not_present`
/// decision. A policy-approved absence need not require review; consequently
/// missing and review are independent counts and may overlap.
class FieldReviewStatus {
  const FieldReviewStatus({
    required this.needsReview,
    required this.isMissing,
    required this.isSettledValue,
  });

  /// An unresolved state, empty supported value, finding or unsaved change.
  final bool needsReview;

  /// A missing current value, excluding fields explicitly not applicable.
  final bool isMissing;

  /// A supported, present value without findings or unsaved changes.
  /// This is a review affordance, independent of the stored value's layer.
  final bool isSettledValue;
}

/// Uses exactly the same value layers as the field row, highest layer first.
/// Observation transcripts are evidence, not a substitute for a field value.
FieldReviewStatus fieldReviewStatus(
  Json field, {
  bool hasIssues = false,
  PendingFieldChange? pending,
}) {
  final state = pending?.state ?? field['state'] as String?;
  final values = pending == null
      ? <Object?>[
          field['normalized'],
          field['parsed_value'],
          field['literal_value'],
        ]
      : pending.state == 'supported'
      ? <Object?>[pending.normalized, pending.parsed, pending.literal]
      : const <Object?>[];
  final hasValue = values.any(
    (value) => value is String && value.trim().isNotEmpty,
  );
  final needsReview = fieldNeedsReview(
    state,
    hasIssues: hasIssues,
    hasValue: hasValue,
    isPending: pending != null,
  );
  return FieldReviewStatus(
    needsReview: needsReview,
    isMissing:
        state != 'not_applicable' && (state == 'not_present' || !hasValue),
    isSettledValue: state == 'supported' && hasValue && !needsReview,
  );
}

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
