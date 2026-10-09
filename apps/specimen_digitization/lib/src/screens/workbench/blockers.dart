/// One list of everything that blocks clearance
/// (audit finding H6.3, severity 4; pass criterion 6.3).
///
/// Today a reviewer assembles this list from five places on every record:
/// validation findings, reason codes, the run blocker, phase findings and the
/// operational panel. This collects them once, in plain words, each with the
/// control that resolves it.
library;

import 'package:flutter/foundation.dart';

import '../../models.dart';
import '../../review_context.dart';
import 'part_reasons.dart';
import 'workbench_layout.dart';

/// Whether an issue belongs to a field, a label, or an operator's work.
enum ClearanceBlockerKind { field, label, processing, record }

/// One unmet gate, and where the reviewer goes to resolve it.
@immutable
class ClearanceBlocker {
  const ClearanceBlocker({
    required this.message,
    required this.segment,
    this.detail,
    this.fieldKey,
    this.regionId,
    this.kind = ClearanceBlockerKind.record,
    this.rawCode,
    this.diagnosticRuleId,
  });

  /// What is outstanding, as a sentence a reviewer can act on.
  final String message;

  /// Where the control that resolves it lives.
  final WorkbenchSegment segment;

  /// A plain-language next step. Internal codes belong in diagnostics.
  final String? detail;

  /// The field this belongs to, when it belongs to one.
  final String? fieldKey;

  /// The label region this belongs to, when it belongs to one.
  final String? regionId;

  final ClearanceBlockerKind kind;

  /// Retained for an optional diagnostic disclosure, never primary copy.
  final String? rawCode;

  /// The original validator identity, retained without displaying it as copy.
  final String? diagnosticRuleId;

  bool get isOperational => kind == ClearanceBlockerKind.processing;
  bool get isTargeted => fieldKey != null || regionId != null;

  /// The anchor the evidence pane scrolls to.
  String? get anchor => fieldKey ?? regionId;
}

/// Everything that currently blocks clearance on [specimen].
///
/// Order is the order a reviewer works in: readings first, then fields, then
/// the operational state, because a run blocker is rarely theirs to fix.
List<ClearanceBlocker> blockersFor(Specimen specimen) {
  final List<ClearanceBlocker> blockers = <ClearanceBlocker>[];
  final Map<String, int> identities = <String, int>{};
  final Set<String> representedCodes = <String>{'human_approval_required'};
  final Json run = objectOf(specimen.data['run']);

  void add(ClearanceBlocker issue) {
    final String code =
        issue.rawCode ?? issue.diagnosticRuleId ?? issue.message;
    final int separator = code.indexOf(':');
    final String base = separator < 0 ? code : code.substring(0, separator);
    final String suffix = separator < 0 ? '' : code.substring(separator + 1);
    final bool knownTarget =
        (_fieldReasons.containsKey(base) && suffix == issue.fieldKey) ||
        (base == 'unresolved_transcription' && suffix == issue.regionId);
    final String identity = <String>[
      knownTarget ? base : code,
      issue.fieldKey ?? '',
      issue.regionId ?? '',
      // Only recognized target suffixes are interchangeable with structured
      // targets. Unknown suffixes remain distinct even on the same field.
    ].join('|');
    final int? existing = identities[identity];
    if (existing == null) {
      identities[identity] = blockers.length;
      blockers.add(issue);
    } else if (issue.isOperational && !blockers[existing].isOperational) {
      blockers[existing] = issue;
    }
    if (issue.rawCode != null) representedCodes.add(issue.rawCode!);
  }

  for (final Json t in objects(specimen.data['transcriptions'])) {
    if (t['resolved'] == true) continue;
    final String region = _regionName(specimen, t['region_id']);
    final String? regionId = _matchingRegion(specimen, t['region_id']);
    add(
      ClearanceBlocker(
        // "Differ" only when the readings do (02 section 2.3). An unresolved
        // region whose readings agree still blocks clearance, because
        // clearance needs completed adjudication (CONTRACTS.md 239-240).
        message: readingsDiffer(t, specimen.observations)
            ? '${_countWord(distinctReadings(t, specimen.observations))} '
                  'readings differ for $region'
            : 'Transcription not resolved for $region',
        detail: 'Resolve the transcription, or record why it cannot be read',
        segment: WorkbenchSegment.readings,
        regionId: regionId,
        kind: regionId == null
            ? ClearanceBlockerKind.record
            : ClearanceBlockerKind.label,
        rawCode: 'unresolved_transcription:${textOf(t['region_id'], '')}',
      ),
    );
  }

  for (final Json f in specimen.findings) {
    final String code = textOf(
      f['reason_code'] ?? f['code'],
      textOf(f['rule_id'], ''),
    );
    if (code == 'human_approval_required') continue;
    add(_issueFor(specimen, code, finding: f));
  }

  // Approval is the final action, not an additional issue to resolve before
  // that same action. Specific findings already explain their generic codes;
  // keep each field's finding while avoiding a second record-level copy.
  for (final Object? rawCode
      in specimen.data['reason_codes'] as List? ?? const <Object?>[]) {
    final String code = rawCode.toString();
    if (representedCodes.contains(code)) continue;
    add(_issueFor(specimen, code));
  }

  final String blocker = textOf(
    run['blocker'],
    textOf(specimen.data['blocker'], ''),
  );
  if (blocker.isNotEmpty && blocker != 'Not recorded') {
    add(_issueFor(specimen, blocker, processing: true));
  }

  return blockers;
}

/// The exact fields named by the specimen contract. A reason suffix is a
/// routing hint only when it names a real field in this response.
const Map<String, String> _fieldNames = <String, String>{
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

const Map<String, String> _fieldReasons = <String, String>{
  'mandatory_unresolved': 'needs a supported value',
  'mandatory_evidence_unresolved': 'needs supporting evidence',
  'evidence_missing': 'needs supporting evidence',
  'evidence_does_not_support_value': 'does not match its supporting evidence',
  'pixel_lineage_missing': 'needs a link to the label source',
  'unsupported_parsed': 'has an interpretation without supporting evidence',
  'unsupported_normalized':
      'has a standardized value without supporting evidence',
  'unsupported_authority_id':
      'has an authority match without supporting evidence',
  'literal_not_in_source_excerpt': 'does not match its label source',
  'candidate_resolution_requires_review': 'has conflicting proposed values',
  'competing_mandatory_candidates': 'has conflicting proposed values',
};

const Map<String, String> _operatorMessages = <String, String>{
  'institutional_policy_unapproved':
      'An administrator must approve the collection policy',
  'institutional_policy_not_approved':
      'An administrator must approve the collection policy',
  'mandatory_semantics_unconfirmed':
      'An administrator must confirm the required field rules',
  'field_semantics_unconfirmed':
      'An administrator must confirm the field rules',
  'worker_readiness_not_verified':
      'An operator must check that processing is ready',
  'external_outcome_unknown':
      'An operator must check the previous request before processing continues',
  'lookup_operational_failure':
      'An operator must restore the source lookup service',
  'storage_unavailable': 'An operator must restore access to specimen storage',
  'pilot_dispatch_reconciliation_required':
      'An operator must check the previous processing attempt',
  'evidence_integrity_failure':
      'An operator must check the retained evidence before processing continues',
};

const Map<String, String> _recordMessages = <String, String>{
  'label_coverage_unconfirmed':
      'Check that every label in the photograph is included',
  'coverage_unconfirmed':
      'Check that every label in the photograph is included',
  'taxonomy_unresolved': 'The taxon needs a supported identification',
  'taxonomy_lookup_missing': 'The taxon needs an authority lookup',
  'lookup_evidence_missing': 'Source lookup evidence is missing',
  'date_precision_requires_review':
      'Check the collection and identification dates',
  'date_order': 'Check the order of the collection and identification dates',
  'identifier_format': 'Check the catalog number format',
  'pilot_risk_unmeasured': 'The review priority assessment is not available',
};

ClearanceBlocker _issueFor(
  Specimen specimen,
  String code, {
  Json finding = const <String, dynamic>{},
  bool processing = false,
}) {
  final int separator = code.indexOf(':');
  final String base = separator < 0 ? code : code.substring(0, separator);
  final String suffix = separator < 0 ? '' : code.substring(separator + 1);
  final String? explicitField = _nonempty(finding['field_key']);
  final String? explicitRegion = _matchingRegion(
    specimen,
    finding['region_id'],
  );
  String? field = explicitField;
  String? region = explicitRegion;
  String? message;
  String? detail;
  ClearanceBlockerKind kind = ClearanceBlockerKind.record;

  final String? operatorMessage = _operatorMessages[base];
  if (operatorMessage != null) {
    kind = ClearanceBlockerKind.processing;
    message = operatorMessage;
    detail =
        'Open processing details for the current state and permitted actions.';
    field = null;
    region = null;
  } else if (_fieldReasons.containsKey(base)) {
    final String? matched = _matchingField(specimen, suffix);
    // Explicit structured targets remain supported for older collections.
    // Conflicting structured and encoded targets are not safe to guess.
    if (suffix.isNotEmpty && explicitField != null && suffix != explicitField) {
      field = null;
    } else {
      field ??= matched;
    }
    if (field != null) {
      kind = ClearanceBlockerKind.field;
      message = _fieldReasonMessage(specimen, field, _fieldReasons[base]!);
      detail = 'Review the value and its supporting sources.';
    }
  } else if (partReasonBases.contains(base)) {
    // A reason about one part of a value: the sentence and the field that
    // carries the part. A subject this reader does not know falls through to
    // the generic line, as any unknown code does.
    final PartIssue? part = partIssueFor(specimen, base, suffix);
    if (part != null) {
      field ??= _matchingField(specimen, part.fieldKey ?? '');
      message = part.message;
      detail = part.detail;
    }
  } else if (base == 'unresolved_transcription') {
    region ??= _matchingRegion(specimen, suffix);
    if (region != null) {
      kind = ClearanceBlockerKind.label;
      message =
          'Transcription not resolved for ${_regionName(specimen, region)}';
      detail = 'Resolve the transcription, or record why it cannot be read';
    }
  } else if (_recordMessages.containsKey(code)) {
    message = _recordMessages[code];
    if (code == 'identifier_format') {
      field ??= _matchingField(specimen, 'fmnh_ins_number');
    } else if (code == 'taxonomy_unresolved' ||
        code == 'taxonomy_lookup_missing') {
      field ??= _matchingField(specimen, 'taxon');
    }
  } else if ((base == 'elevation_invalid' || base == 'elevation_range') &&
      (suffix == 'm' || suffix == 'ft')) {
    message = 'Check the elevation range ($suffix)';
    detail =
        'Check both the minimum and maximum elevations against their sources.';
    field ??= _matchingField(specimen, 'elevation_from_$suffix');
  } else if (base == 'elevation_units_conflict' &&
      (suffix == 'from' || suffix == 'to')) {
    message = 'The elevation values in metres and feet do not agree';
    detail = 'Compare both units with the label and supporting sources.';
    field ??= _matchingField(specimen, 'elevation_${suffix}_m');
  }

  if (processing) {
    kind = ClearanceBlockerKind.processing;
    field = null;
    region = null;
    message ??= 'Processing needs an operator check before it can continue';
    detail ??=
        'Open processing details for the current state and permitted actions.';
  } else if (kind != ClearanceBlockerKind.processing) {
    kind = field != null
        ? ClearanceBlockerKind.field
        : region != null
        ? ClearanceBlockerKind.label
        : ClearanceBlockerKind.record;
    message ??= _humanMessage(finding['message']);
    message ??= field != null
        ? '${_fieldName(specimen, field)} needs review'
        : region != null
        ? '${_regionName(specimen, region)} needs review'
        : 'A specimen check needs review before approval';
    detail ??= field != null
        ? 'Review the value and its supporting sources.'
        : 'Review the recorded issue before approving the specimen.';
  }

  return ClearanceBlocker(
    message: message ?? 'A specimen check needs review before approval',
    detail: detail,
    segment: field != null || region == null
        ? WorkbenchSegment.fields
        : WorkbenchSegment.readings,
    fieldKey: field,
    regionId: region,
    kind: kind,
    rawCode: code.isEmpty ? null : code,
    diagnosticRuleId: _nonempty(finding['rule_id']),
  );
}

String? _nonempty(Object? value) =>
    value is String && value.trim().isNotEmpty ? value : null;

String? _matchingField(Specimen specimen, String key) =>
    _fieldNames.containsKey(key) &&
        specimen.fields.any((Json field) => field['field_key'] == key)
    ? key
    : null;

String? _matchingRegion(Specimen specimen, Object? id) =>
    id is String &&
        specimen.regions.any((Json region) => region['region_id'] == id)
    ? id
    : null;

String _fieldName(Specimen specimen, String key) {
  final String? known = _fieldNames[key];
  if (known != null) return known;
  for (final Json field in specimen.fields) {
    if (field['field_key'] != key) continue;
    final String? displayName = _humanMessage(field['display_name']);
    if (displayName != null) return displayName;
  }
  return 'This field';
}

String _fieldReasonMessage(Specimen specimen, String field, String reason) {
  final String verb = field == 'collectors'
      ? reason
            .replaceFirst(RegExp(r'^needs\b'), 'need')
            .replaceFirst(RegExp(r'^does\b'), 'do')
            .replaceFirst(RegExp(r'^has\b'), 'have')
      : reason;
  return '${_fieldName(specimen, field)} $verb';
}

/// Older APIs sometimes send prose in `message`, and sometimes copy a code or
/// serialized payload into it. Retain readable prose; keep internals behind
/// the diagnostic disclosure rather than exposing them on the review path.
String? _humanMessage(Object? raw) {
  final String? message = _nonempty(raw);
  if (message == null ||
      message.contains('_') ||
      message.contains('{') ||
      message.contains('}') ||
      RegExp(r'[a-zA-Z][a-zA-Z0-9]*:[a-zA-Z0-9_-]+').hasMatch(message) ||
      RegExp(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        caseSensitive: false,
      ).hasMatch(message) ||
      RegExp(r'\b[0-9a-f]{32,}\b', caseSensitive: false).hasMatch(message)) {
    return null;
  }
  return message;
}

/// The summary the status strip carries, for a record that has blockers
/// (13 section 3.2).
///
/// A record with none carries no summary: a control that opens an empty list
/// is a control that does nothing (pass criterion 5.6), and the decision bar's
/// enabled approval already says that nothing is outstanding. The count starts
/// at one for that reason.
String blockersSummary(int count) =>
    count == 1 ? '1 thing blocks clearance' : '$count things block clearance';

/// What the sheet behind the summary is called.
const String blockersSheetTitle = 'What blocks clearance';

/// What the control that moves to one blocker is called.
const String goToBlockerLabel = 'Go to';

/// A count of readings as the first word of a sentence: "Two readings
/// differ", as 02 section 2.3 writes it.
String _countWord(int count) => switch (count) {
  2 => 'Two',
  3 => 'Three',
  4 => 'Four',
  5 => 'Five',
  _ => '$count',
};

String _regionName(Specimen specimen, Object? regionId) {
  final int index = specimen.regions.indexWhere(
    (Json r) => r['region_id'] == regionId,
  );
  return index < 0 ? 'this record' : 'Label ${index + 1}';
}
