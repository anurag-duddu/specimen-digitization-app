import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;

import 'derivation_models.dart';

/// A sanitized rejection of an incompatible research response.
class ResearchContractException implements Exception {
  const ResearchContractException();
  @override
  String toString() => 'Research response could not be verified.';
}

/// A complete research locator supplied by the trusted host.
///
/// Discovery is a separate contract. A legacy active run ID is not a job ID.
class ResearchScope {
  factory ResearchScope({
    required String organizationId,
    required String collectionId,
    required String specimenId,
    required String jobId,
    required int generation,
    required String inputDigest,
    required String profileDigest,
    required bool sensitive,
  }) => ResearchScope.fromJson({
    'organization_id': organizationId,
    'collection_id': collectionId,
    'specimen_id': specimenId,
    'job_id': jobId,
    'generation': generation,
    'input_digest': inputDigest,
    'profile_digest': profileDigest,
    'sensitive': sensitive,
  });

  ResearchScope._(this.json);

  /// Validates every scope field without coercing wire values.
  factory ResearchScope.fromJson(Object? value) {
    final json = _object(value);
    _validate('ResearchScope', json);
    if (!json.containsKey('sensitive')) _invalid();
    return ResearchScope._(_freezeMap(json));
  }

  final Map<String, Object?> json;
  String get organizationId => json['organization_id'] as String;
  String get collectionId => json['collection_id'] as String;
  String get specimenId => json['specimen_id'] as String;
  String get jobId => json['job_id'] as String;
  int get generation => json['generation'] as int;
  String get inputDigest => json['input_digest'] as String;
  String get profileDigest => json['profile_digest'] as String;
  bool get sensitive => json['sensitive'] as bool;

  /// Whether all identity and scientific input bindings match.
  bool matches(ResearchScope other) => _same(json, other.json);
}

/// The server's field phase, with a nonactionable compatibility fallback.
enum ResearchWorkState {
  pending,
  researching,
  resolved,
  waitingSource,
  waitingPolicy,
  retryScheduled,
  operationalFailed,
  waitingHuman,
  nonblockingException,
  cancelled,
  unknown;

  static ResearchWorkState parse(String value) => switch (value) {
    'pending' => pending,
    'researching' => researching,
    'resolved' => resolved,
    'waiting_source' => waitingSource,
    'waiting_policy' => waitingPolicy,
    'retry_scheduled' => retryScheduled,
    'operational_failed' => operationalFailed,
    'waiting_human' => waitingHuman,
    'nonblocking_exception' => nonblockingException,
    'cancelled' => cancelled,
    _ => unknown,
  };

  String get label => switch (this) {
    pending => 'Pending',
    researching => 'Researching',
    resolved => 'Resolved',
    waitingSource => 'Waiting for a source',
    waitingPolicy => 'Waiting for policy',
    retryScheduled => 'Queued',
    operationalFailed => 'Research interrupted',
    waitingHuman => 'Needs information',
    nonblockingException => 'Policy exception',
    cancelled => 'Cancelled',
    unknown => 'Status unavailable',
  };
}

/// The unchanged scientific value layers and their provenance.
class ResearchValue {
  ResearchValue._(this.json);
  factory ResearchValue.fromJson(Object? value) =>
      ResearchValue._fromJson(value);

  factory ResearchValue._fromJson(
    Object? value, {
    bool allowAuthorityProjection = false,
  }) {
    final json = _object(value);
    _validate(
      'FieldValue',
      json,
      allowAuthorityProjection: allowAuthorityProjection,
    );
    return ResearchValue._(
      Map<String, Object?>.unmodifiable(
        json.map(
          (key, item) => MapEntry(
            key,
            _freeze(
              item,
              allowNonfiniteProjection:
                  allowAuthorityProjection && key == 'authority_identity',
            ),
          ),
        ),
      ),
    );
  }

  final Map<String, Object?> json;
  String get state => json['state'] as String? ?? 'unknown';
  String? get literal => json['literal'] as String?;
  String? get parsed => json['parsed'] as String?;
  String? get normalized => json['normalized'] as String?;
  String? get authorityId => json['authority_id'] as String?;
  List<String> get evidenceIds => _strings(json['evidence_ids']);
  Map<String, String> get verbatimByObservation =>
      Map<String, String>.unmodifiable(
        _object(json['verbatim_by_observation'] ?? {}),
      );
}

/// A scoped prerequisite receipt retained from the server.
class ResearchSourceCoverage {
  ResearchSourceCoverage._(this.json);
  factory ResearchSourceCoverage.fromJson(Object? value) {
    final json = _object(value);
    _validate('SourceCoverageReceipt', json);
    if (json['exact_join_proven'] == true &&
        json['exact_join_attempted'] != true) {
      _invalid();
    }
    if (json['state'] == 'exhausted' &&
        (json['exact_join_attempted'] != true ||
            _strings(json['receipt_ids']).isEmpty ||
            json['query_digest'] == null ||
            json['qualification_digest'] == null)) {
      _invalid();
    }
    return ResearchSourceCoverage._(_freezeMap(json));
  }
  final Map<String, Object?> json;
  String get sourceId => json['source_id'] as String;
  String get state => json['state'] as String;
  String get coverageLimit => json['coverage_limit'] as String;
  String get reason => json['reason'] as String;
}

/// A server question displayed without inventing a submission endpoint.
class ResearchHumanQuestion {
  ResearchHumanQuestion._(this.json);
  final Map<String, Object?> json;
  String get text => json['question'] as String;
  String get reason => json['reason'] as String;
  List<String> get evidenceIds => _strings(json['evidence_ids']);
}

/// One possibility a source returned, exactly as the source named it.
///
/// The source's display label and its exact field value are separate: a
/// geography label can name a region while `selectionValue` is the precise
/// value the source proposed for this field.
class ResearchReviewCandidate {
  ResearchReviewCandidate._(this.json);
  factory ResearchReviewCandidate.fromJson(Object? value) {
    final json = _object(value);
    _validate('ReviewCandidate', json);
    return ResearchReviewCandidate._(_freezeMap(json));
  }

  /// Adapts a retained proposal only for the existing opaque-token save path.
  /// Its label and exact field value are both the server's full proposed value.
  factory ResearchReviewCandidate.fromDerivationProposal(
    ResearchDerivationProposal proposal,
  ) {
    final selectionId = proposal.selectionId;
    if (selectionId == null || selectionId.isEmpty) {
      throw const ResearchContractException();
    }
    return ResearchReviewCandidate._(
      Map<String, Object?>.unmodifiable({
        'label': proposal.value,
        'source_id': 'georeference_spatial',
        'selection_id': selectionId,
        'selection_value': proposal.value,
      }),
    );
  }
  final Map<String, Object?> json;
  String get label => json['label'] as String;
  List<String> get details => _strings(json['details']);
  int? get distanceKm => json['distance_km'] as int?;
  String? get authorityId => json['authority_id'] as String?;
  int? get rank => json['rank'] as int?;
  String get sourceId => json['source_id'] as String;
  String? get evidenceId => json['evidence_id'] as String?;
  String? get selectionId => json['selection_id'] as String?;
  String? get selectionValue => json['selection_value'] as String?;
}

/// One captured source lookup: what was asked and what the source answered.
class ResearchReviewEvidence {
  ResearchReviewEvidence._(this.json);
  factory ResearchReviewEvidence.fromJson(Object? value) {
    final json = _object(value);
    _validate('ReviewEvidence', json);
    return ResearchReviewEvidence._(_freezeMap(json));
  }
  final Map<String, Object?> json;
  String get evidenceId => json['evidence_id'] as String;
  String get sourceId => json['source_id'] as String;
  String get kind => json['kind'] as String;
  String? get quote => json['quote'] as String?;
  String? get searchedText => json['searched_text'] as String?;
  String? get outcome => json['outcome'] as String?;
  String? get note => json['note'] as String?;
}

/// What the harness found for a field that waits for a person.
///
/// The server bounds these lists and reports how many items it omitted.
class ResearchFieldReview {
  ResearchFieldReview._(this.json, this.evidence, this.candidates);
  factory ResearchFieldReview.fromJson(Object? value) {
    final json = _object(value);
    _validate('FieldReview', json);
    return ResearchFieldReview._(
      _freezeMap(json),
      List.unmodifiable(
        _array(json['evidence'] ?? []).map(ResearchReviewEvidence.fromJson),
      ),
      List.unmodifiable(
        _array(json['candidates'] ?? []).map(ResearchReviewCandidate.fromJson),
      ),
    );
  }
  final Map<String, Object?> json;
  final List<ResearchReviewEvidence> evidence;
  final List<ResearchReviewCandidate> candidates;
  String? get questionReason => json['question_reason'] as String?;
  String? get reason => json['reason'] as String?;
  int get evidenceNotShown => json['evidence_not_shown'] as int? ?? 0;
  int get candidatesNotShown => json['candidates_not_shown'] as int? ?? 0;
}

/// A nonblocking policy exception that remains visible to the reviewer.
class ResearchPolicyException {
  ResearchPolicyException._(this.json);
  final Map<String, Object?> json;
  String get reason => json['reason'] as String;
  String get dependency => json['dependency'] as String;
  String get reevaluateWhen => json['reevaluate_when'] as String;
}

/// A verified field resolution with evidence and distinct value layer.
class ResearchResolution {
  ResearchResolution._(this.json, this.value);
  factory ResearchResolution.fromJson(Object? value) {
    final json = _object(value);
    _validate('FieldResolution', json);
    final key = json['field_key'];
    for (final name in ['question', 'exception']) {
      if (json[name] != null && _object(json[name])['field_key'] != key) {
        _invalid();
      }
    }
    for (final raw in _array(json['source_coverage'] ?? [])) {
      final coverage = ResearchSourceCoverage.fromJson(raw);
      if (coverage.json['field_key'] != key) _invalid();
    }
    final question = json['question'];
    if (question != null) {
      // Mirrors HumanQuestion.no_operational_review: every receipt is
      // exhausted, or every receipt is a searched GEOLocate no_match or
      // ambiguous outcome for a geography field; never mixed.
      final receipts = _array(
        _object(question)['coverage'],
      ).map(ResearchSourceCoverage.fromJson).toList();
      if (receipts.any((coverage) => coverage.json['field_key'] != key) ||
          !(receipts.every((coverage) => coverage.state == 'exhausted') ||
              receipts.every(
                (coverage) => _geolocateUnresolved(coverage, key as String),
              ))) {
        _invalid();
      }
    }
    final fieldValue = ResearchValue.fromJson(json['value']);
    if (json['work_state'] == 'resolved' &&
        (fieldValue.state != 'supported' ||
            _strings(json['evidence_ids']).isEmpty)) {
      _invalid();
    }
    if (json['value_layer'] == 'derived' && json['derivation'] == null) {
      _invalid();
    }
    if (json['work_state'] == 'waiting_human' && question == null) _invalid();
    if (json['work_state'] == 'nonblocking_exception' &&
        (json['exception'] == null ||
            fieldValue.state == 'supported' ||
            fieldValue.authorityId != null ||
            fieldValue.json['authority_identity'] != null ||
            fieldValue.parsed != null ||
            fieldValue.normalized != null)) {
      _invalid();
    }
    return ResearchResolution._(_freezeMap(json), fieldValue);
  }
  final Map<String, Object?> json;
  final ResearchValue value;
  String get fieldKey => json['field_key'] as String;
  ResearchWorkState get workState =>
      ResearchWorkState.parse(json['work_state'] as String);
  String get valueLayer => json['value_layer'] as String? ?? 'verbatim';
  String get reason => json['reason'] as String;
  List<String> get evidenceIds => _strings(json['evidence_ids']);
  List<String> get assemblyIds => _strings(json['assembly_ids']);
  List<ResearchSourceCoverage> get sourceCoverage => List.unmodifiable(
    _array(json['source_coverage'] ?? []).map(ResearchSourceCoverage.fromJson),
  );
  ResearchHumanQuestion? get question => json['question'] == null
      ? null
      : ResearchHumanQuestion._(_freezeMap(_object(json['question'])));
  ResearchPolicyException? get exception => json['exception'] == null
      ? null
      : ResearchPolicyException._(_freezeMap(_object(json['exception'])));
  Map<String, Object?>? get derivation => json['derivation'] == null
      ? null
      : _freezeMap(_object(json['derivation']));
  Map<String, Object?>? get measurement => json['measurement'] == null
      ? null
      : _freezeMap(_object(json['measurement']));
}

/// A checkpoint bound to the complete requested scope and owning field.
class ResearchCheckpoint {
  ResearchCheckpoint._(this.json, this.scope, this.resolution);
  factory ResearchCheckpoint.fromJson(
    Object? value, {
    required ResearchScope expectedScope,
    required String expectedFieldKey,
  }) {
    final json = _object(value);
    _validate('FieldCheckpoint', json);
    final scope = ResearchScope.fromJson(json['scope']);
    final resolution = ResearchResolution.fromJson(json['resolution']);
    if (!scope.matches(expectedScope) ||
        json['field_key'] != expectedFieldKey ||
        resolution.fieldKey != expectedFieldKey) {
      _invalid();
    }
    final source = json['reused_from_scope_digest'];
    final checkpoint = json['reused_from_checkpoint_digest'];
    if ((source == null) != (checkpoint == null)) _invalid();
    return ResearchCheckpoint._(_freezeMap(json), scope, resolution);
  }
  final Map<String, Object?> json;
  final ResearchScope scope;
  final ResearchResolution resolution;
  String get fieldKey => json['field_key'] as String;
  int get revision => json['revision'] as int;
  String? get retryCommandId => json['retry_command_id'] as String?;
  List<String> get effectReceiptIds => _strings(json['effect_receipt_ids']);
}

/// A preserved ordinary human decision, separate from native research.
///
/// Values are parsed structural views, whose numeric metadata may round or
/// overflow on web. Exact provenance remains in
/// [ResearchFieldThread.preservedHumanOutcomesJson] after thread verification.
class ResearchPreservedHumanOutcome {
  ResearchPreservedHumanOutcome._(this.json, this.value, this.originalValue);

  factory ResearchPreservedHumanOutcome.fromJson(Object? value) =>
      ResearchPreservedHumanOutcome._fromJson(value);

  factory ResearchPreservedHumanOutcome._fromJson(
    Object? value, {
    bool allowAuthorityProjection = false,
  }) {
    final json = _object(value);
    _validate(
      'PreservedHumanFieldOutcome',
      json,
      allowAuthorityProjection: allowAuthorityProjection,
    );
    if (json['contract_version'] != 'preserved-human-field/v1' ||
        <String>[
          'canonical_run_id',
          'origin_run_id',
          'origin_event_id',
          'actor',
          'reason',
        ].any((key) => (json[key] as String).trim().isEmpty) ||
        json['origin_run_id'] == json['canonical_run_id'] ||
        (json['origin_revision'] as int) >=
            (json['fresh_run_revision'] as int)) {
      _invalid();
    }
    final current = ResearchValue._fromJson(
      json['value'],
      allowAuthorityProjection: allowAuthorityProjection,
    );
    final original = ResearchValue._fromJson(
      json['original_value'],
      allowAuthorityProjection: allowAuthorityProjection,
    );
    final evidence = current.evidenceIds;
    final originalEvidence = _strings(json['original_evidence_ids']);
    if (originalEvidence.toSet().length != originalEvidence.length ||
        !_same(originalEvidence, original.evidenceIds) ||
        evidence.length != 1 ||
        evidence.single.isEmpty ||
        !_same(current.json, {
          ...original.json,
          'evidence_ids': evidence,
          'evidence_relations': {evidence.single: 'decides'},
          'input_source': null,
          'source_region_id': null,
          'source_observation_id': null,
          'verbatim_by_observation': <String, Object?>{},
          'input_source_by_observation': <String, Object?>{},
          'settled_observation_ids': <String>[],
        })) {
      _invalid();
    }
    return ResearchPreservedHumanOutcome._(
      Map<String, Object?>.unmodifiable(
        json.map(
          (key, item) => MapEntry(key, switch (key) {
            'value' => current.json,
            'original_value' => original.json,
            _ => _freeze(item),
          }),
        ),
      ),
      current,
      original,
    );
  }

  final Map<String, Object?> json;

  /// The parsed structural projection of the current value.
  final ResearchValue value;

  /// The parsed structural projection of the saved value.
  final ResearchValue originalValue;
  String get fieldKey => json['field_key'] as String;
  String get organizationId => json['organization_id'] as String;
  String get collectionId => json['collection_id'] as String;
  String get specimenId => json['specimen_id'] as String;
  String get canonicalRunId => json['canonical_run_id'] as String;
  int get freshRunRevision => json['fresh_run_revision'] as int;
  String get originRunId => json['origin_run_id'] as String;
  String get originEventId => json['origin_event_id'] as String;
  int get originRevision => json['origin_revision'] as int;
  String get actor => json['actor'] as String;
  String get reason => json['reason'] as String;
  String get createdAt => json['created_at'] as String;
  List<String> get originalEvidenceIds =>
      _strings(json['original_evidence_ids']);
  String get carryDigest => json['carry_digest'] as String;
  String get proofDigest => json['proof_digest'] as String;
  String get sourceSha256 => json['source_sha256'] as String;
}

/// The server's registration base for its preserved human outcomes.
class ResearchPreservedHumanBase {
  ResearchPreservedHumanBase._(this.json, this._outcomesProjection);

  factory ResearchPreservedHumanBase.fromJson(Object? value) {
    final json = _object(value);
    _validate('PreservedHumanBase', json);
    if (json['contract_version'] != 'preserved-human-base/v2' ||
        (json['canonical_run_id'] as String).trim().isEmpty) {
      _invalid();
    }
    final raw = json['outcomes_json'] as String;
    final bytes = utf8.encode(raw);
    if (bytes.length > 4 * 1024 * 1024 ||
        crypto.sha256.convert(bytes).toString() != json['outcome_digest']) {
      _invalid();
    }
    Map<String, Object?> projection;
    try {
      projection = _freezeMap(
        _object(jsonDecode(raw)),
        allowNonfiniteProjection: true,
      );
    } on FormatException {
      _invalid();
    }
    return ResearchPreservedHumanBase._(_freezeMap(json), projection);
  }

  final Map<String, Object?> json;
  final Map<String, Object?> _outcomesProjection;
  String get canonicalRunId => json['canonical_run_id'] as String;
  int get registrationRecordRevision =>
      json['registration_record_revision'] as int;
  String get registrationSnapshotSha256 =>
      json['registration_snapshot_sha256'] as String;
  String get sourceSha256 => json['source_sha256'] as String;
  int get outcomeCount => json['outcome_count'] as int;
  String get outcomeDigest => json['outcome_digest'] as String;

  /// The exact server outcome-map text whose UTF-8 bytes match the digest.
  String get outcomesJson => json['outcomes_json'] as String;
}

/// One server field phase, separate from its retained checkpoint.
class ResearchFieldThread {
  ResearchFieldThread._(
    this.scope,
    this.fieldKey,
    this.workState,
    this.value,
    this.checkpoint,
    this.blockerCode,
    this.actions,
    this.review,
    this.preservedHumanOutcome,
    this.preservedHumanOutcomesJson,
  );
  factory ResearchFieldThread.fromJson(Object? value, ResearchScope scope) =>
      ResearchFieldThread._fromJson(value, scope);

  factory ResearchFieldThread._fromJson(
    Object? value,
    ResearchScope scope, {
    bool allowAuthorityProjection = false,
  }) {
    final json = _object(value);
    _validate(
      'FieldThread',
      json,
      allowAuthorityProjection: allowAuthorityProjection,
    );
    final key = json['field_key'] as String;
    final fieldValue = ResearchValue._fromJson(
      json['value'],
      allowAuthorityProjection: allowAuthorityProjection,
    );
    final checkpoint = json['checkpoint'] == null
        ? null
        : ResearchCheckpoint.fromJson(
            json['checkpoint'],
            expectedScope: scope,
            expectedFieldKey: key,
          );
    if (checkpoint != null &&
        !_same(fieldValue.json, checkpoint.resolution.value.json)) {
      _invalid();
    }
    final state = ResearchWorkState.parse(json['work_state'] as String);
    final preserved = json['preserved_human'] == null
        ? null
        : ResearchPreservedHumanOutcome._fromJson(
            json['preserved_human'],
            allowAuthorityProjection: allowAuthorityProjection,
          );
    final actions = _strings(json['actions']);
    final review = json['review'] == null
        ? null
        : ResearchFieldReview.fromJson(json['review']);
    if (preserved != null &&
        (preserved.fieldKey != key ||
            preserved.organizationId != scope.organizationId ||
            preserved.collectionId != scope.collectionId ||
            preserved.specimenId != scope.specimenId ||
            !_same(preserved.value.json, fieldValue.json) ||
            state != ResearchWorkState.waitingHuman ||
            checkpoint != null ||
            actions.isNotEmpty ||
            review != null ||
            json['blocker_code'] != 'preserved_human_decision')) {
      _invalid();
    }
    if (state != ResearchWorkState.unknown) {
      if (checkpoint == null &&
          preserved == null &&
          state != ResearchWorkState.pending &&
          state != ResearchWorkState.waitingPolicy) {
        _invalid();
      }
      final retainedState = checkpoint?.resolution.workState;
      if (retainedState != null &&
          retainedState != ResearchWorkState.unknown &&
          state != retainedState) {
        final commandOverlay =
            state == ResearchWorkState.retryScheduled ||
            state == ResearchWorkState.researching;
        final retainedFailure =
            retainedState == ResearchWorkState.operationalFailed ||
            retainedState == ResearchWorkState.retryScheduled;
        if (!commandOverlay || !retainedFailure) _invalid();
      }
    }
    return ResearchFieldThread._(
      scope,
      key,
      state,
      fieldValue,
      checkpoint,
      json['blocker_code'] as String?,
      actions,
      review,
      preserved,
      null,
    );
  }
  final ResearchScope scope;
  final String fieldKey;
  final ResearchWorkState workState;
  final ResearchValue value;
  final ResearchCheckpoint? checkpoint;
  final String? blockerCode;
  final List<String> actions;

  /// Bounded source findings for a field that waits for a reviewer.
  final ResearchFieldReview? review;

  /// The server's preserved outcome projection for this field.
  final ResearchPreservedHumanOutcome? preservedHumanOutcome;

  /// The exact validated outcome-map text, absent in isolated field views.
  final String? preservedHumanOutcomesJson;

  ResearchFieldThread _withPreservedHumanOutcomesJson(String raw) =>
      ResearchFieldThread._(
        scope,
        fieldKey,
        workState,
        value,
        checkpoint,
        blockerCode,
        actions,
        review,
        preservedHumanOutcome,
        raw,
      );

  /// Whether the server advertises a retry for this exact failed checkpoint.
  bool get canRetry =>
      preservedHumanOutcome == null &&
      actions.contains('retry_field') &&
      blockerCode != 'research_retry_blocked' &&
      (workState == ResearchWorkState.operationalFailed ||
          workState == ResearchWorkState.retryScheduled) &&
      checkpoint != null &&
      checkpoint!.revision > 0 &&
      (checkpoint!.resolution.workState ==
              ResearchWorkState.operationalFailed ||
          checkpoint!.resolution.workState == ResearchWorkState.retryScheduled);
}

/// An immutable thread verified against the host's trusted binding.
class ResearchThread {
  ResearchThread._(
    this.scope,
    this.paused,
    this.historical,
    this.canonicalRevision,
    this.reviewSavedRevision,
    this.fields,
    this.effects,
    this.resolvedCount,
    this.exceptionCount,
    this.preservedHumanCount,
    this.preservedHumanBase,
    this.traceIds,
  );
  factory ResearchThread.fromJson(
    Object? value, {
    required ResearchScope expectedScope,
  }) {
    final json = _object(value);
    final preservedBase = json['preserved_human_base'] == null
        ? null
        : ResearchPreservedHumanBase.fromJson(json['preserved_human_base']);
    _validateNode(
      _threadSchema,
      json,
      _threadSchema,
      allowAuthorityProjection: preservedBase != null,
    );
    if (json['contract_version'] != 'research-thread-v1') _invalid();
    final scope = ResearchScope.fromJson(json['scope']);
    if (!scope.matches(expectedScope)) _invalid();
    final fields = _array(json['fields'])
        .map(
          (item) => ResearchFieldThread._fromJson(
            item,
            scope,
            allowAuthorityProjection:
                preservedBase != null &&
                _object(item)['preserved_human'] != null,
          ),
        )
        .toList();
    final fieldKeys = fields.map((item) => item.fieldKey).toSet();
    if (fieldKeys.length != fields.length ||
        fieldKeys.length != researchFieldKeys.length ||
        !fieldKeys.containsAll(researchFieldKeys)) {
      _invalid();
    }
    final resolved = json['resolved_count'] as int;
    final exceptions = json['exception_count'] as int;
    final preservedCount = json['preserved_human_count'] as int? ?? 0;
    final preserved = <String, ResearchPreservedHumanOutcome>{
      for (final field in fields)
        if (field.preservedHumanOutcome != null)
          field.fieldKey: field.preservedHumanOutcome!,
    };
    if (preserved.isEmpty) {
      if (preservedCount != 0 || preservedBase != null) _invalid();
    } else {
      if (preservedBase == null ||
          preservedCount != preserved.length ||
          preservedBase.outcomeCount != preserved.length ||
          preservedBase.registrationSnapshotSha256 != scope.inputDigest ||
          !_same(preservedBase._outcomesProjection, {
            for (final entry in preserved.entries) entry.key: entry.value.json,
          }) ||
          preserved.values.any(
            (outcome) =>
                outcome.organizationId != scope.organizationId ||
                outcome.collectionId != scope.collectionId ||
                outcome.specimenId != scope.specimenId ||
                outcome.canonicalRunId != preservedBase.canonicalRunId ||
                outcome.sourceSha256 != preservedBase.sourceSha256 ||
                outcome.freshRunRevision >
                    preservedBase.registrationRecordRevision,
          ) ||
          resolved !=
              fields
                  .where(
                    (field) =>
                        field.checkpoint != null &&
                        field.workState == ResearchWorkState.resolved,
                  )
                  .length ||
          exceptions !=
              fields
                  .where(
                    (field) =>
                        field.checkpoint != null &&
                        field.workState ==
                            ResearchWorkState.nonblockingException,
                  )
                  .length) {
        _invalid();
      }
    }
    if (resolved < 0 ||
        exceptions < 0 ||
        resolved > fields.length ||
        exceptions > fields.length) {
      _invalid();
    }
    if (fields.every((item) => item.workState != ResearchWorkState.unknown) &&
        (resolved !=
                fields
                    .where(
                      (item) => item.workState == ResearchWorkState.resolved,
                    )
                    .length ||
            exceptions !=
                fields
                    .where(
                      (item) =>
                          item.workState ==
                          ResearchWorkState.nonblockingException,
                    )
                    .length)) {
      _invalid();
    }
    final effects = _array(json['effects']).map(_object).toList();
    final effectIds = <Object?>{};
    for (final effect in effects) {
      final generation = effect['generation'] as int;
      if (generation > scope.generation ||
          !effectIds.add(effect['effect_id'])) {
        _invalid();
      }
      if (generation < scope.generation &&
          !fields.any(
            (field) =>
                field.checkpoint?.json['reused_from_scope_digest'] != null &&
                (field.checkpoint?.effectReceiptIds.contains(
                      effect['effect_id'],
                    ) ??
                    false),
          )) {
        _invalid();
      }
    }
    return ResearchThread._(
      scope,
      json['paused'] as bool,
      json['historical'] as bool? ?? false,
      json['canonical_revision'] as int?,
      json['review_saved_revision'] as int?,
      List.unmodifiable(
        fields.map(
          (field) => field.preservedHumanOutcome == null
              ? field
              : field._withPreservedHumanOutcomesJson(
                  preservedBase!.outcomesJson,
                ),
        ),
      ),
      List.unmodifiable(effects.map(_freezeMap)),
      resolved,
      exceptions,
      preservedCount,
      preservedBase,
      _strings(json['trace_ids']),
    );
  }
  final ResearchScope scope;
  final bool paused;

  /// Whether this retained report belongs to an earlier human-reviewed revision.
  final bool historical;
  final int? canonicalRevision;
  final int? reviewSavedRevision;
  final List<ResearchFieldThread> fields;
  final List<Map<String, Object?>> effects;
  final int resolvedCount;
  final int exceptionCount;
  final int preservedHumanCount;
  final ResearchPreservedHumanBase? preservedHumanBase;
  final List<String> traceIds;
  ResearchFieldThread? field(String key) {
    for (final field in fields) {
      if (field.fieldKey == key) return field;
    }
    return null;
  }

  /// Whether an unfamiliar field phase requires a read-only fallback.
  bool get hasUnknownState => fields.any(
    (field) =>
        field.workState == ResearchWorkState.unknown ||
        field.checkpoint?.resolution.workState == ResearchWorkState.unknown,
  );

  /// Whether a fresh server capability can be used for this field.
  bool canRetry(String key) =>
      !paused &&
      !historical &&
      !hasUnknownState &&
      (field(key)?.canRetry ?? false);
}

/// A queued acknowledgment bound to the request, never a saved field value.
class ResearchRetryAck {
  ResearchRetryAck._(
    this.scope,
    this.fieldKey,
    this.checkpointRevision,
    this.commandId,
  );
  factory ResearchRetryAck.fromJson(
    Object? value, {
    required ResearchScope expectedScope,
    required String expectedFieldKey,
    required int expectedCheckpointRevision,
  }) {
    final json = _object(value);
    _validateNode(_retrySchema, json, _retrySchema);
    if (json['contract_version'] != 'research-retry-v1' ||
        json['status'] != 'queued' ||
        json['generation'] != expectedScope.generation ||
        json['field_key'] != expectedFieldKey ||
        json['expected_checkpoint_revision'] != expectedCheckpointRevision) {
      _invalid();
    }
    return ResearchRetryAck._(
      expectedScope,
      expectedFieldKey,
      expectedCheckpointRevision,
      json['command_id'] as String,
    );
  }
  final ResearchScope scope;
  final String fieldKey;
  final int checkpointRevision;
  final String commandId;
}

/// The frozen field vocabulary accepted by this contract version.
const researchFieldKeys = <String>{
  'fmnh_ins_number',
  'collection_code',
  'country',
  'province_state',
  'county',
  'city',
  'precise_location',
  'elevation_from_m',
  'elevation_to_m',
  'elevation_from_ft',
  'elevation_to_ft',
  'habitat',
  'collection_method',
  'date_visited_from',
  'date_visited_to',
  'collectors',
  'verbatim_dts',
  'taxon',
  'identified_by_irn',
  'date_identified',
};

/// The five geography fields GEOLocate can settle or fail to settle.
const _geolocateFieldKeys = <String>{
  'country',
  'province_state',
  'county',
  'city',
  'precise_location',
};

/// Mirrors `_geolocate_unresolved` in the server's contracts: a searched
/// GEOLocate outcome whose reason leads with its typed status.
bool _geolocateUnresolved(ResearchSourceCoverage coverage, String fieldKey) =>
    coverage.state == 'searched' &&
    coverage.sourceId == 'geolocate' &&
    _geolocateFieldKeys.contains(fieldKey) &&
    RegExp(r'^(?:no_match|ambiguous): \S[\s\S]*$').hasMatch(coverage.reason);

Never _invalid() => throw const ResearchContractException();
Map<String, Object?> _object(Object? value) {
  if (value is! Map || value.keys.any((key) => key is! String)) _invalid();
  return Map<String, Object?>.from(value);
}

List<Object?> _array(Object? value) {
  if (value is! List) _invalid();
  return List<Object?>.from(value);
}

List<String> _strings(Object? value) =>
    List<String>.unmodifiable(_array(value ?? []).cast<String>());
Map<String, Object?> _freezeMap(
  Map<String, Object?> value, {
  bool allowNonfiniteProjection = false,
}) => Map<String, Object?>.unmodifiable(
  value.map(
    (key, item) => MapEntry(
      key,
      _freeze(item, allowNonfiniteProjection: allowNonfiniteProjection),
    ),
  ),
);
Object? _freeze(Object? value, {bool allowNonfiniteProjection = false}) {
  if (value is Map) {
    return _freezeMap(
      _object(value),
      allowNonfiniteProjection: allowNonfiniteProjection,
    );
  }
  if (value is List) {
    return List<Object?>.unmodifiable(
      value.map(
        (item) =>
            _freeze(item, allowNonfiniteProjection: allowNonfiniteProjection),
      ),
    );
  }
  if (value is double && !value.isFinite && !allowNonfiniteProjection) {
    _invalid();
  }
  if (value == null || value is String || value is num || value is bool) {
    return value;
  }
  return _invalid();
}

bool _same(Object? left, Object? right) {
  if (left is Map && right is Map) {
    return left.length == right.length &&
        left.keys.every(
          (key) => right.containsKey(key) && _same(left[key], right[key]),
        );
  }
  if (left is List && right is List) {
    return left.length == right.length &&
        Iterable<int>.generate(
          left.length,
        ).every((i) => _same(left[i], right[i]));
  }
  return left == right;
}

void _validate(
  String name,
  Object? value, {
  bool allowAuthorityProjection = false,
}) => _validateNode(
  _object(_object(_threadSchema[r'$defs'])[name]),
  value,
  _threadSchema,
  allowAuthorityProjection: allowAuthorityProjection,
);
void _validateNode(
  Map<String, Object?> node,
  Object? value,
  Map<String, Object?> root, {
  bool allowAuthorityProjection = false,
}) {
  final ref = node[r'$ref'];
  if (ref is String) {
    final name = ref.split('/').last;
    // Unknown work phases are readable but cannot expose actions.
    if (name == 'WorkState' && value is String && value.isNotEmpty) return;
    _validateNode(
      _object(_object(root[r'$defs'])[name]),
      value,
      root,
      allowAuthorityProjection: allowAuthorityProjection,
    );
    return;
  }
  final alternatives = node['anyOf'];
  if (alternatives is List) {
    for (final alternative in alternatives) {
      try {
        _validateNode(
          _object(alternative),
          value,
          root,
          allowAuthorityProjection: allowAuthorityProjection,
        );
        return;
      } on ResearchContractException {
        // Another declared alternative may match.
      }
    }
    _invalid();
  }
  switch (node['type']) {
    case 'object':
      final object = _object(value);
      final projectAuthority =
          allowAuthorityProjection &&
          (node['title'] != 'FieldThread' || object['preserved_human'] != null);
      final properties = _object(node['properties'] ?? {});
      for (final key in _array(node['required'] ?? [])) {
        if (!object.containsKey(key)) _invalid();
      }
      for (final entry in object.entries) {
        if (properties.containsKey(entry.key)) {
          if (projectAuthority &&
              node['title'] == 'FieldValue' &&
              entry.key == 'authority_identity') {
            // Only a validated v2 carry has this approximate numeric view;
            // exact numeric tokens remain in its raw outcome-map text.
            if (entry.value != null) {
              _freeze(_object(entry.value), allowNonfiniteProjection: true);
            }
          } else {
            _validateNode(
              _object(properties[entry.key]),
              entry.value,
              root,
              allowAuthorityProjection: projectAuthority,
            );
          }
        } else if (node['additionalProperties'] == false) {
          _invalid();
        } else if (node['additionalProperties'] is Map) {
          _validateNode(
            _object(node['additionalProperties']),
            entry.value,
            root,
            allowAuthorityProjection: projectAuthority,
          );
        } else {
          _freeze(entry.value);
        }
      }
      break;
    case 'array':
      final values = _array(value);
      if (node['minItems'] is int &&
          values.length < (node['minItems'] as int)) {
        _invalid();
      }
      if (node['maxItems'] is int &&
          values.length > (node['maxItems'] as int)) {
        _invalid();
      }
      for (final item in values) {
        _validateNode(
          _object(node['items']),
          item,
          root,
          allowAuthorityProjection: allowAuthorityProjection,
        );
      }
      break;
    case 'integer':
      if (value is! int) _invalid();
      if (node['minimum'] is num && value < (node['minimum'] as num)) {
        _invalid();
      }
      if (node['maximum'] is num && value > (node['maximum'] as num)) {
        _invalid();
      }
      break;
    case 'string':
      if (value is! String) _invalid();
      if (node['minLength'] is int &&
          value.runes.length < (node['minLength'] as int)) {
        _invalid();
      }
      if (node['maxLength'] is int &&
          value.runes.length > (node['maxLength'] as int)) {
        _invalid();
      }
      if (node['pattern'] is String) {
        final match = RegExp(node['pattern'] as String).firstMatch(value);
        if (match == null || match.start != 0 || match.end != value.length) {
          _invalid();
        }
      }
      break;
    case 'boolean':
      if (value is! bool) _invalid();
      break;
    case 'null':
      if (value != null) _invalid();
      break;
    default:
      _invalid();
  }
  if (node.containsKey('const') && value != node['const']) _invalid();
  if (node['enum'] is List && !(node['enum'] as List).contains(value)) {
    _invalid();
  }
}

// Copies of the server's JSON schemas; validation never discovers schemas
// remotely. The thread schema is ResearchThread.model_json_schema() and
// tests/research_harness/test_thread_embedded_schema.py fails when it drifts.
final Map<String, Object?> _threadSchema = _object(
  jsonDecode(_threadSchemaJson),
);
final Map<String, Object?> _retrySchema = _object(jsonDecode(_retrySchemaJson));
const _threadSchemaJson =
    r'''{"$defs":{"DependencyPin":{"additionalProperties":false,"properties":{"digest":{"pattern":"^[a-f0-9]{64}$","title":"Digest","type":"string"},"field_key":{"$ref":"#/$defs/FieldKey"},"revision":{"minimum":0,"title":"Revision","type":"integer"}},"required":["field_key","revision","digest"],"title":"DependencyPin","type":"object"},"DerivationRecord":{"additionalProperties":false,"properties":{"decimal_precision":{"default":34,"minimum":1,"title":"Decimal Precision","type":"integer"},"display_value":{"title":"Display Value","type":"string"},"evidence_ids":{"items":{"type":"string"},"minItems":1,"title":"Evidence Ids","type":"array"},"exact_operation":{"title":"Exact Operation","type":"string"},"factor":{"default":"1","title":"Factor","type":"string"},"operation":{"enum":["copy_endpoint","multiply","divide"],"title":"Operation","type":"string"},"rounding":{"default":"ROUND_HALF_EVEN","title":"Rounding","type":"string"},"rule_id":{"title":"Rule Id","type":"string"},"rule_version":{"title":"Rule Version","type":"string"},"source_assembly_ids":{"items":{"type":"string"},"title":"Source Assembly Ids","type":"array"},"source_digest":{"pattern":"^[a-f0-9]{64}$","title":"Source Digest","type":"string"},"source_field":{"$ref":"#/$defs/FieldKey"},"source_fragment_ids":{"items":{"type":"string"},"title":"Source Fragment Ids","type":"array"},"source_revision":{"minimum":0,"title":"Source Revision","type":"integer"},"source_value":{"title":"Source Value","type":"string"},"unrounded_value":{"title":"Unrounded Value","type":"string"}},"required":["rule_id","rule_version","operation","source_field","source_revision","source_digest","source_value","exact_operation","unrounded_value","display_value","source_assembly_ids","source_fragment_ids","evidence_ids"],"title":"DerivationRecord","type":"object"},"EffectThread":{"additionalProperties":false,"properties":{"actual_micro_usd":{"anyOf":[{"minimum":0,"type":"integer"},{"type":"null"}],"default":null,"title":"Actual Micro Usd"},"attempt_ids":{"items":{"type":"string"},"title":"Attempt Ids","type":"array"},"capture_locator":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Capture Locator"},"effect_id":{"title":"Effect Id","type":"string"},"generation":{"minimum":1,"title":"Generation","type":"integer"},"held_micro_usd":{"minimum":0,"title":"Held Micro Usd","type":"integer"},"kind":{"enum":["model","tool"],"title":"Kind","type":"string"},"status":{"enum":["reserved","sending","held_unknown","completed"],"title":"Status","type":"string"}},"required":["effect_id","generation","kind","status","attempt_ids","held_micro_usd"],"title":"EffectThread","type":"object"},"FieldCheckpoint":{"additionalProperties":false,"properties":{"effect_receipt_ids":{"default":[],"items":{"type":"string"},"title":"Effect Receipt Ids","type":"array"},"field_key":{"$ref":"#/$defs/FieldKey"},"model_settings_digest":{"pattern":"^[a-f0-9]{64}$","title":"Model Settings Digest","type":"string"},"prompt_digest":{"pattern":"^[a-f0-9]{64}$","title":"Prompt Digest","type":"string"},"resolution":{"$ref":"#/$defs/FieldResolution"},"retry_command_id":{"anyOf":[{"pattern":"^[a-f0-9]{64}$","type":"string"},{"type":"null"}],"default":null,"title":"Retry Command Id"},"reused_from_checkpoint_digest":{"anyOf":[{"pattern":"^[a-f0-9]{64}$","type":"string"},{"type":"null"}],"default":null,"title":"Reused From Checkpoint Digest"},"reused_from_scope_digest":{"anyOf":[{"pattern":"^[a-f0-9]{64}$","type":"string"},{"type":"null"}],"default":null,"title":"Reused From Scope Digest"},"revision":{"minimum":0,"title":"Revision","type":"integer"},"scope":{"$ref":"#/$defs/ResearchScope"},"source_registry_digest":{"pattern":"^[a-f0-9]{64}$","title":"Source Registry Digest","type":"string"},"trace_id":{"anyOf":[{"pattern":"^[a-f0-9]{32}$","type":"string"},{"type":"null"}],"default":null,"title":"Trace Id"}},"required":["scope","field_key","revision","resolution","prompt_digest","model_settings_digest","source_registry_digest"],"title":"FieldCheckpoint","type":"object"},"FieldKey":{"enum":["fmnh_ins_number","collection_code","country","province_state","county","city","precise_location","elevation_from_m","elevation_to_m","elevation_from_ft","elevation_to_ft","habitat","collection_method","date_visited_from","date_visited_to","collectors","verbatim_dts","taxon","identified_by_irn","date_identified"],"title":"FieldKey","type":"string"},"FieldResolution":{"additionalProperties":false,"properties":{"assembly_ids":{"default":[],"items":{"type":"string"},"title":"Assembly Ids","type":"array"},"dependencies":{"default":[],"items":{"$ref":"#/$defs/DependencyPin"},"title":"Dependencies","type":"array"},"derivation":{"anyOf":[{"$ref":"#/$defs/DerivationRecord"},{"type":"null"}],"default":null},"event_id":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Event Id"},"evidence_ids":{"default":[],"items":{"type":"string"},"title":"Evidence Ids","type":"array"},"exception":{"anyOf":[{"$ref":"#/$defs/PolicyException"},{"type":"null"}],"default":null},"field_key":{"$ref":"#/$defs/FieldKey"},"measurement":{"anyOf":[{"$ref":"#/$defs/MeasurementMetadata"},{"type":"null"}],"default":null},"question":{"anyOf":[{"$ref":"#/$defs/HumanQuestion"},{"type":"null"}],"default":null},"reason":{"title":"Reason","type":"string"},"rejected_assembly_ids":{"default":[],"items":{"type":"string"},"title":"Rejected Assembly Ids","type":"array"},"source_coverage":{"default":[],"items":{"$ref":"#/$defs/SourceCoverageReceipt"},"title":"Source Coverage","type":"array"},"value":{"$ref":"#/$defs/FieldValue"},"value_layer":{"default":"verbatim","enum":["verbatim","settled","derived"],"title":"Value Layer","type":"string"},"work_state":{"$ref":"#/$defs/WorkState"}},"required":["field_key","work_state","value","reason"],"title":"FieldResolution","type":"object"},"FieldReview":{"additionalProperties":false,"description":"What the harness found for a field that waits for a person (read-only, bounded).\n\n``question_reason`` is the harness's own code for why it asked. ``evidence`` and ``candidates``\ncome from the source lookups this field's checkpoint cites; ``*_not_shown`` counts what the\nbounds or the journal could not show, so a short list never reads as a complete one.","properties":{"candidates":{"default":[],"items":{"$ref":"#/$defs/ReviewCandidate"},"maxItems":8,"title":"Candidates","type":"array"},"candidates_not_shown":{"default":0,"minimum":0,"title":"Candidates Not Shown","type":"integer"},"evidence":{"default":[],"items":{"$ref":"#/$defs/ReviewEvidence"},"maxItems":8,"title":"Evidence","type":"array"},"evidence_not_shown":{"default":0,"minimum":0,"title":"Evidence Not Shown","type":"integer"},"question_reason":{"anyOf":[{"enum":["evidence_conflict","scoped_absence","semantic_ambiguity","derived_proposal"],"type":"string"},{"type":"null"}],"default":null,"title":"Question Reason"},"reason":{"anyOf":[{"maxLength":600,"type":"string"},{"type":"null"}],"default":null,"title":"Reason"}},"title":"FieldReview","type":"object"},"FieldThread":{"additionalProperties":false,"properties":{"actions":{"default":[],"items":{"enum":["retry_field","supply_information","review_proposal"],"type":"string"},"title":"Actions","type":"array"},"blocker_code":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Blocker Code"},"checkpoint":{"anyOf":[{"$ref":"#/$defs/FieldCheckpoint"},{"type":"null"}],"default":null},"field_key":{"$ref":"#/$defs/FieldKey"},"preserved_human":{"anyOf":[{"$ref":"#/$defs/PreservedHumanFieldOutcome"},{"type":"null"}],"default":null},"review":{"anyOf":[{"$ref":"#/$defs/FieldReview"},{"type":"null"}],"default":null},"value":{"$ref":"#/$defs/FieldValue"},"work_state":{"$ref":"#/$defs/WorkState"}},"required":["field_key","work_state","value"],"title":"FieldThread","type":"object"},"FieldValue":{"additionalProperties":false,"properties":{"authority_id":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Authority Id"},"authority_identity":{"anyOf":[{"additionalProperties":true,"type":"object"},{"type":"null"}],"default":null,"title":"Authority Identity"},"century_rule":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Century Rule"},"derived_from":{"items":{"type":"string"},"title":"Derived From","type":"array"},"evidence_ids":{"items":{"type":"string"},"title":"Evidence Ids","type":"array"},"evidence_relations":{"additionalProperties":{"enum":["decides","supports","contradicts"],"type":"string"},"title":"Evidence Relations","type":"object"},"input_source":{"anyOf":[{"enum":["decided_transcript","raw_reading"],"type":"string"},{"type":"null"}],"default":null,"title":"Input Source"},"input_source_by_observation":{"additionalProperties":{"enum":["decided_transcript","raw_reading"],"type":"string"},"title":"Input Source By Observation","type":"object"},"layer":{"anyOf":[{"enum":["verbatim","settled","derived"],"type":"string"},{"type":"null"}],"default":null,"title":"Layer"},"literal":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Literal"},"normalized":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Normalized"},"parsed":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Parsed"},"precision":{"anyOf":[{"enum":["day","month","year"],"type":"string"},{"type":"null"}],"default":null,"title":"Precision"},"reason":{"default":"No supported source value","title":"Reason","type":"string"},"settled_observation_ids":{"items":{"type":"string"},"title":"Settled Observation Ids","type":"array"},"source_observation_id":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Source Observation Id"},"source_region_id":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Source Region Id"},"state":{"$ref":"#/$defs/ValueState","default":"unknown"},"verbatim_by_observation":{"additionalProperties":{"type":"string"},"title":"Verbatim By Observation","type":"object"}},"title":"FieldValue","type":"object"},"HumanQuestion":{"additionalProperties":false,"properties":{"coverage":{"items":{"$ref":"#/$defs/SourceCoverageReceipt"},"minItems":1,"title":"Coverage","type":"array"},"evidence_ids":{"default":[],"items":{"type":"string"},"title":"Evidence Ids","type":"array"},"field_key":{"$ref":"#/$defs/FieldKey"},"question":{"minLength":1,"title":"Question","type":"string"},"reason":{"enum":["evidence_conflict","scoped_absence","semantic_ambiguity","derived_proposal"],"title":"Reason","type":"string"}},"required":["field_key","question","reason","coverage"],"title":"HumanQuestion","type":"object"},"MeasurementMetadata":{"additionalProperties":false,"properties":{"assertion_metadata":{"default":[],"items":{"type":"string"},"title":"Assertion Metadata","type":"array"},"converted_uncertainty":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Converted Uncertainty"},"decimal_context":{"default":34,"title":"Decimal Context","type":"integer"},"derived_unit":{"anyOf":[{"enum":["ft","m"],"type":"string"},{"type":"null"}],"default":null,"title":"Derived Unit"},"original_quantity":{"title":"Original Quantity","type":"string"},"original_to_quantity":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Original To Quantity"},"original_unit":{"enum":["ft","m"],"title":"Original Unit","type":"string"},"precision":{"default":"unknown","title":"Precision","type":"string"},"qualifiers":{"default":[],"items":{"type":"string"},"title":"Qualifiers","type":"array"},"rendering_rule":{"default":"decimal-2-half-even-v1","title":"Rendering Rule","type":"string"},"uncertainty":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"title":"Uncertainty"},"vertical_datum":{"default":"unknown","title":"Vertical Datum","type":"string"}},"required":["original_unit","original_quantity"],"title":"MeasurementMetadata","type":"object"},"PolicyException":{"additionalProperties":false,"properties":{"dependency":{"title":"Dependency","type":"string"},"field_key":{"$ref":"#/$defs/FieldKey"},"policy_version":{"title":"Policy Version","type":"string"},"reason":{"title":"Reason","type":"string"},"reevaluate_when":{"title":"Reevaluate When","type":"string"}},"required":["field_key","dependency","policy_version","reason","reevaluate_when"],"title":"PolicyException","type":"object"},"PreservedHumanBase":{"additionalProperties":false,"properties":{"canonical_run_id":{"title":"Canonical Run Id","type":"string"},"contract_version":{"const":"preserved-human-base/v2","default":"preserved-human-base/v2","title":"Contract Version","type":"string"},"outcome_count":{"maximum":20,"minimum":1,"title":"Outcome Count","type":"integer"},"outcome_digest":{"pattern":"^[a-f0-9]{64}$","title":"Outcome Digest","type":"string"},"outcomes_json":{"maxLength":4194304,"minLength":2,"title":"Outcomes Json","type":"string"},"registration_record_revision":{"maximum":9007199254740991,"minimum":1,"title":"Registration Record Revision","type":"integer"},"registration_snapshot_sha256":{"pattern":"^[a-f0-9]{64}$","title":"Registration Snapshot Sha256","type":"string"},"source_sha256":{"pattern":"^[a-f0-9]{64}$","title":"Source Sha256","type":"string"}},"required":["canonical_run_id","registration_record_revision","registration_snapshot_sha256","source_sha256","outcome_count","outcome_digest","outcomes_json"],"title":"PreservedHumanBase","type":"object"},"PreservedHumanFieldOutcome":{"additionalProperties":false,"description":"A separately proved human outcome, with no native question or effect.","properties":{"actor":{"title":"Actor","type":"string"},"canonical_run_id":{"title":"Canonical Run Id","type":"string"},"carry_digest":{"pattern":"^[a-f0-9]{64}$","title":"Carry Digest","type":"string"},"collection_id":{"title":"Collection Id","type":"string"},"contract_version":{"const":"preserved-human-field/v1","default":"preserved-human-field/v1","title":"Contract Version","type":"string"},"created_at":{"title":"Created At","type":"string"},"field_key":{"$ref":"#/$defs/FieldKey"},"fresh_run_revision":{"maximum":9007199254740991,"minimum":2,"title":"Fresh Run Revision","type":"integer"},"organization_id":{"title":"Organization Id","type":"string"},"origin_event_id":{"title":"Origin Event Id","type":"string"},"origin_revision":{"maximum":9007199254740991,"minimum":2,"title":"Origin Revision","type":"integer"},"origin_run_id":{"title":"Origin Run Id","type":"string"},"original_evidence_ids":{"items":{"type":"string"},"title":"Original Evidence Ids","type":"array"},"original_value":{"$ref":"#/$defs/FieldValue"},"proof_digest":{"pattern":"^[a-f0-9]{64}$","title":"Proof Digest","type":"string"},"reason":{"title":"Reason","type":"string"},"source_sha256":{"pattern":"^[a-f0-9]{64}$","title":"Source Sha256","type":"string"},"specimen_id":{"title":"Specimen Id","type":"string"},"value":{"$ref":"#/$defs/FieldValue"}},"required":["field_key","value","original_value","organization_id","collection_id","specimen_id","canonical_run_id","fresh_run_revision","origin_run_id","origin_event_id","origin_revision","actor","reason","created_at","original_evidence_ids","carry_digest","proof_digest","source_sha256"],"title":"PreservedHumanFieldOutcome","type":"object"},"ResearchScope":{"additionalProperties":false,"properties":{"collection_id":{"minLength":1,"title":"Collection Id","type":"string"},"generation":{"minimum":0,"title":"Generation","type":"integer"},"input_digest":{"pattern":"^[a-f0-9]{64}$","title":"Input Digest","type":"string"},"job_id":{"minLength":1,"title":"Job Id","type":"string"},"organization_id":{"minLength":1,"title":"Organization Id","type":"string"},"profile_digest":{"pattern":"^[a-f0-9]{64}$","title":"Profile Digest","type":"string"},"sensitive":{"default":true,"title":"Sensitive","type":"boolean"},"specimen_id":{"minLength":1,"title":"Specimen Id","type":"string"}},"required":["organization_id","collection_id","specimen_id","job_id","generation","input_digest","profile_digest"],"title":"ResearchScope","type":"object"},"ReviewCandidate":{"additionalProperties":false,"description":"One possibility a source returned, as the source named it. Never a value the harness chose.\n\n``details`` holds only words the source supplied (an administrative unit, a taxonomic rank, a\nstatus); the wording around them belongs to the client. ``distance_km`` is GEOLocate's own figure:\nhow far the match lies from the placement the geography specialist estimated for the named place.","properties":{"authority_id":{"anyOf":[{"maxLength":240,"type":"string"},{"type":"null"}],"default":null,"title":"Authority Id"},"details":{"default":[],"items":{"maxLength":80,"type":"string"},"maxItems":4,"title":"Details","type":"array"},"distance_km":{"anyOf":[{"minimum":0,"type":"integer"},{"type":"null"}],"default":null,"title":"Distance Km"},"evidence_id":{"anyOf":[{"maxLength":240,"type":"string"},{"type":"null"}],"default":null,"title":"Evidence Id"},"label":{"maxLength":240,"title":"Label","type":"string"},"rank":{"anyOf":[{"minimum":1,"type":"integer"},{"type":"null"}],"default":null,"title":"Rank"},"selection_id":{"anyOf":[{"pattern":"^[a-f0-9]{64}$","type":"string"},{"type":"null"}],"default":null,"title":"Selection Id"},"selection_value":{"anyOf":[{"maxLength":240,"type":"string"},{"type":"null"}],"default":null,"title":"Selection Value"},"source_id":{"maxLength":240,"title":"Source Id","type":"string"}},"required":["label","source_id"],"title":"ReviewCandidate","type":"object"},"ReviewEvidence":{"additionalProperties":false,"description":"One captured source lookup for the field: what was asked and what the source answered.","properties":{"evidence_id":{"maxLength":240,"title":"Evidence Id","type":"string"},"kind":{"maxLength":240,"title":"Kind","type":"string"},"note":{"anyOf":[{"maxLength":240,"type":"string"},{"type":"null"}],"default":null,"title":"Note"},"outcome":{"anyOf":[{"maxLength":240,"type":"string"},{"type":"null"}],"default":null,"title":"Outcome"},"quote":{"anyOf":[{"maxLength":240,"type":"string"},{"type":"null"}],"default":null,"title":"Quote"},"searched_text":{"anyOf":[{"maxLength":240,"type":"string"},{"type":"null"}],"default":null,"title":"Searched Text"},"source_id":{"maxLength":240,"title":"Source Id","type":"string"}},"required":["evidence_id","source_id","kind"],"title":"ReviewEvidence","type":"object"},"SourceCoverageReceipt":{"additionalProperties":false,"properties":{"candidate_count":{"anyOf":[{"minimum":0,"type":"integer"},{"type":"null"}],"default":null,"title":"Candidate Count"},"coverage_limit":{"title":"Coverage Limit","type":"string"},"exact_join_attempted":{"default":false,"title":"Exact Join Attempted","type":"boolean"},"exact_join_proven":{"default":false,"title":"Exact Join Proven","type":"boolean"},"field_key":{"$ref":"#/$defs/FieldKey"},"qualification_digest":{"anyOf":[{"pattern":"^[a-f0-9]{64}$","type":"string"},{"type":"null"}],"default":null,"title":"Qualification Digest"},"query_digest":{"anyOf":[{"pattern":"^[a-f0-9]{64}$","type":"string"},{"type":"null"}],"default":null,"title":"Query Digest"},"reason":{"title":"Reason","type":"string"},"receipt_ids":{"default":[],"items":{"type":"string"},"title":"Receipt Ids","type":"array"},"source_id":{"title":"Source Id","type":"string"},"source_version":{"title":"Source Version","type":"string"},"state":{"$ref":"#/$defs/SourceCoverageState"}},"required":["source_id","field_key","state","source_version","coverage_limit","reason"],"title":"SourceCoverageReceipt","type":"object"},"SourceCoverageState":{"enum":["not_attempted","unqualified","inaccessible","schema_only","failed","searched","exhausted"],"title":"SourceCoverageState","type":"string"},"ValueState":{"enum":["supported","unknown","unresolved","unreadable","ambiguous","not_present","not_applicable"],"title":"ValueState","type":"string"},"WorkState":{"enum":["pending","researching","resolved","waiting_source","waiting_policy","retry_scheduled","operational_failed","waiting_human","nonblocking_exception","cancelled"],"title":"WorkState","type":"string"}},"additionalProperties":false,"properties":{"canonical_revision":{"anyOf":[{"minimum":0,"type":"integer"},{"type":"null"}],"default":null,"title":"Canonical Revision"},"contract_version":{"const":"research-thread-v1","default":"research-thread-v1","title":"Contract Version","type":"string"},"effects":{"items":{"$ref":"#/$defs/EffectThread"},"title":"Effects","type":"array"},"exception_count":{"title":"Exception Count","type":"integer"},"fields":{"items":{"$ref":"#/$defs/FieldThread"},"title":"Fields","type":"array"},"historical":{"default":false,"title":"Historical","type":"boolean"},"paused":{"title":"Paused","type":"boolean"},"preserved_human_base":{"anyOf":[{"$ref":"#/$defs/PreservedHumanBase"},{"type":"null"}],"default":null},"preserved_human_count":{"default":0,"maximum":20,"minimum":0,"title":"Preserved Human Count","type":"integer"},"resolved_count":{"title":"Resolved Count","type":"integer"},"review_saved_revision":{"anyOf":[{"minimum":0,"type":"integer"},{"type":"null"}],"default":null,"title":"Review Saved Revision"},"scope":{"$ref":"#/$defs/ResearchScope"},"trace_ids":{"default":[],"items":{"type":"string"},"title":"Trace Ids","type":"array"}},"required":["scope","paused","fields","effects","resolved_count","exception_count"],"title":"ResearchThread","type":"object"}''';
const _retrySchemaJson =
    r'''{"$defs":{"FieldKey":{"enum":["fmnh_ins_number","collection_code","country","province_state","county","city","precise_location","elevation_from_m","elevation_to_m","elevation_from_ft","elevation_to_ft","habitat","collection_method","date_visited_from","date_visited_to","collectors","verbatim_dts","taxon","identified_by_irn","date_identified"],"title":"FieldKey","type":"string"}},"additionalProperties":false,"properties":{"contract_version":{"const":"research-retry-v1","default":"research-retry-v1","title":"Contract Version","type":"string"},"command_id":{"pattern":"^[a-f0-9]{64}$","title":"Command Id","type":"string"},"field_key":{"$ref":"#/$defs/FieldKey"},"generation":{"minimum":1,"title":"Generation","type":"integer"},"expected_checkpoint_revision":{"minimum":1,"title":"Expected Checkpoint Revision","type":"integer"},"status":{"const":"queued","default":"queued","title":"Status","type":"string"}},"required":["command_id","field_key","generation","expected_checkpoint_revision"],"title":"RetryAccepted","type":"object"}''';
