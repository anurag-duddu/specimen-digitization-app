/// Typed, read-only views of the retained location research request and result.
///
/// A proposal is never a specimen value. Only its opaque server selection token
/// can enter the existing human review decision flow.
library;

const derivableResearchFieldKeys = <String>{
  'country',
  'province_state',
  'county',
  'city',
  'precise_location',
  'elevation_from_m',
  'elevation_to_m',
  'elevation_from_ft',
  'elevation_to_ft',
};

const _geographyResearchFieldKeys = <String>{
  'country',
  'province_state',
  'county',
  'city',
  'precise_location',
};
final _sha256Pattern = RegExp(r'^[a-f0-9]{64}$');

Map<String, Object?> _map(Object? value) => value is Map
    ? Map<String, Object?>.from(value)
    : throw const FormatException();

List<Object?> _list(Object? value) =>
    value is List ? List<Object?>.from(value) : throw const FormatException();

String _string(Object? value) =>
    value is String && value.isNotEmpty ? value : throw const FormatException();

int _positiveInt(Object? value) =>
    value is int && value > 0 ? value : throw const FormatException();

List<String> _fieldKeys(Object? value, {required Set<String> allowed}) {
  final keys = _list(value).map(_string).toList(growable: false);
  if (keys.toSet().length != keys.length || !allowed.containsAll(keys)) {
    throw const FormatException();
  }
  return List<String>.unmodifiable(keys);
}

/// What the authenticated service currently permits a reviewer to request.
class ResearchDerivationCapability {
  ResearchDerivationCapability._({
    required this.available,
    required this.canonicalRevision,
    required this.eligibleFields,
    required this.blockedReason,
  });

  factory ResearchDerivationCapability.fromJson(Object? value) {
    final json = _map(value);
    if (json['contract_version'] != 'research-derivation-capability/v1' ||
        json['available'] is! bool) {
      throw const FormatException();
    }
    final fields = _fieldKeys(
      json['eligible_fields'] ?? const <Object?>[],
      allowed: derivableResearchFieldKeys,
    );
    return ResearchDerivationCapability._(
      available: json['available'] as bool,
      canonicalRevision: _positiveInt(json['canonical_revision']),
      eligibleFields: fields,
      blockedReason: json['blocked_reason'] as String?,
    );
  }

  final bool available;
  final int canonicalRevision;
  final List<String> eligibleFields;
  final String? blockedReason;

  bool appliesTo(int recordRevision) =>
      available &&
      eligibleFields.isNotEmpty &&
      canonicalRevision == recordRevision;
}

/// A server acknowledgment that the request was saved and queued.
class ResearchDerivationAccepted {
  ResearchDerivationAccepted._({
    required this.requestId,
    required this.sourceRevision,
    required this.queuedRevision,
    required this.canonicalRunId,
  });

  factory ResearchDerivationAccepted.fromJson(
    Object? value, {
    required int expectedSourceRevision,
  }) {
    final json = _map(value);
    final source = _positiveInt(json['source_revision']);
    final queued = _positiveInt(json['queued_revision']);
    final requestId = _string(json['request_id']);
    if (json['contract_version'] != 'research-derivation-accepted/v1' ||
        json['status'] != 'queued' ||
        !_sha256Pattern.hasMatch(requestId) ||
        source != expectedSourceRevision ||
        queued != source + 1) {
      throw const FormatException();
    }
    return ResearchDerivationAccepted._(
      requestId: requestId,
      sourceRevision: source,
      queuedRevision: queued,
      canonicalRunId: _string(json['canonical_run_id']),
    );
  }

  final String requestId;
  final int sourceRevision;
  final int queuedRevision;
  final String canonicalRunId;
}

/// A retained worker proposal. Coordinates and source details remain audit
/// metadata; this view exposes only the field value and the review token.
class ResearchDerivationProposal {
  ResearchDerivationProposal._({
    required this.fieldKey,
    required this.value,
    required this.inputFields,
    required this.inputRevisions,
    required this.evidenceIds,
    required this.authorityId,
    required this.datasetIds,
    required this.toolCallId,
    required this.ruleVersion,
    required this.selectionId,
  });

  factory ResearchDerivationProposal.fromJson(Object? value) {
    final json = _map(value);
    final fieldKey = _string(json['field_key']);
    final inputFields = _fieldKeys(
      json['input_fields'],
      allowed: _geographyResearchFieldKeys,
    );
    final revisionRows = _list(json['input_revisions']);
    final revisions = <String, int>{};
    for (final row in revisionRows) {
      final tuple = _list(row);
      if (tuple.length != 2) throw const FormatException();
      final key = _string(tuple[0]);
      if (!_geographyResearchFieldKeys.contains(key) ||
          revisions.containsKey(key)) {
        throw const FormatException();
      }
      revisions[key] = _positiveInt(tuple[1]);
    }
    final evidence = _stringList(json['evidence_ids']);
    final datasets = _stringList(json['dataset_ids']);
    final selectionId = json['selection_id'] as String?;
    if (!derivableResearchFieldKeys.contains(fieldKey) ||
        json['value_layer'] != 'derived' ||
        inputFields.isEmpty ||
        inputFields.contains(fieldKey) ||
        revisions.keys.toSet().difference(inputFields.toSet()).isNotEmpty ||
        revisions.keys.toSet().length != inputFields.length ||
        evidence.isEmpty ||
        datasets.isEmpty ||
        (selectionId != null && !_sha256Pattern.hasMatch(selectionId))) {
      throw const FormatException();
    }
    return ResearchDerivationProposal._(
      fieldKey: fieldKey,
      value: _string(json['value']),
      inputFields: inputFields,
      inputRevisions: Map<String, int>.unmodifiable(revisions),
      evidenceIds: evidence,
      authorityId: _string(json['authority_id']),
      datasetIds: datasets,
      toolCallId: _string(json['tool_call_id']),
      ruleVersion: _string(json['rule_version']),
      selectionId: selectionId,
    );
  }

  static List<String> _stringList(Object? value) {
    final values = _list(value).map(_string).toList(growable: false);
    if (values.toSet().length != values.length) throw const FormatException();
    return List<String>.unmodifiable(values);
  }

  final String fieldKey;
  final String value;
  final List<String> inputFields;
  final Map<String, int> inputRevisions;
  final List<String> evidenceIds;
  final String authorityId;
  final List<String> datasetIds;
  final String toolCallId;
  final String ruleVersion;
  final String? selectionId;

  bool get selectable => selectionId != null && selectionId!.isNotEmpty;
}

/// Actual retained progress from the worker, never a client-side prediction.
class ResearchDerivationResult {
  ResearchDerivationResult._({
    required this.requestId,
    required this.status,
    required this.sourceRevision,
    required this.queuedRevision,
    required this.canonicalRevision,
    required this.stale,
    required this.proposals,
    required this.blockedReason,
  });

  factory ResearchDerivationResult.fromJson(
    Object? value, {
    required String expectedRequestId,
  }) {
    final json = _map(value);
    final requestId = _string(json['request_id']);
    final source = _positiveInt(json['source_revision']);
    final queued = _positiveInt(json['queued_revision']);
    final current = _positiveInt(json['canonical_revision']);
    final rawProposals = _list(json['proposals'] ?? const <Object?>[]);
    final proposals = rawProposals
        .map(ResearchDerivationProposal.fromJson)
        .toList(growable: false);
    final fieldKeys = proposals.map((proposal) => proposal.fieldKey).toSet();
    if (json['contract_version'] != 'research-derivation-result/v1' ||
        !_sha256Pattern.hasMatch(requestId) ||
        requestId != expectedRequestId ||
        !const {
          'queued',
          'running',
          'completed',
          'blocked',
        }.contains(json['status']) ||
        queued != source + 1 ||
        current < queued ||
        json['stale'] is! bool ||
        fieldKeys.length != proposals.length ||
        (json['stale'] == true && proposals.isNotEmpty)) {
      throw const FormatException();
    }
    return ResearchDerivationResult._(
      requestId: requestId,
      status: json['status'] as String,
      sourceRevision: source,
      queuedRevision: queued,
      canonicalRevision: current,
      stale: json['stale'] as bool,
      proposals: List<ResearchDerivationProposal>.unmodifiable(proposals),
      blockedReason: json['blocked_reason'] as String?,
    );
  }

  final String requestId;
  final String status;
  final int sourceRevision;
  final int queuedRevision;
  final int canonicalRevision;
  final bool stale;
  final List<ResearchDerivationProposal> proposals;
  final String? blockedReason;

  List<ResearchDerivationProposal> proposalsFor(String fieldKey) => stale
      ? const []
      : proposals
            .where((proposal) => proposal.fieldKey == fieldKey)
            .toList(growable: false);
}
