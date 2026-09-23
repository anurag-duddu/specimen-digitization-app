import 'dart:typed_data';

import 'vocabulary.dart';

/// Protected-access denials must reach the workspace even when a child panel
/// handles its own request failure. Only an explicit role recheck recovers.
abstract interface class AccessFailureSource {
  Stream<ApiFailure> get accessFailures;
}

typedef Json = Map<String, dynamic>;
const knownFieldStates = {
  'supported',
  'unknown',
  'unreadable',
  'not_present',
  'not_applicable',
  'ambiguous',
  'unresolved',
};

String textOf(dynamic value, [String fallback = 'Not recorded']) =>
    value == null || value.toString().isEmpty ? fallback : value.toString();
List<Json> objects(dynamic value) => value is List
    ? value.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
    : [];

/// How many different texts a transcription's readers returned.
///
/// `alternatives` is the set of distinct reading texts for one label region
/// (the adjudicate step and the pilot review stop both build it that way).
int distinctReadings(Json transcription) {
  final Object? alternatives = transcription['alternatives'];
  return alternatives is List
      ? alternatives.map((Object? a) => a.toString()).toSet().length
      : 0;
}

/// True when a transcription's readings differ.
///
/// Unresolved is a different claim: the pilot leaves every transcription
/// unresolved, including those whose readings are identical.
bool readingsDiffer(Json transcription) => distinctReadings(transcription) > 1;

/// The mechanical part of turning a server enum into words.
///
/// User-facing text goes through `vocabularyLabel` instead, which renames
/// the terms the UX writing guidelines retire before falling back to this.
String labelOf(String value) => value.replaceAll('_', ' ');

class ApiFailure implements Exception {
  const ApiFailure(
    this.message, {
    this.code = 'unavailable',
    this.status,
    this.details = const {},
  });
  final String message;
  final String code;
  final int? status;
  final Json details;
  bool get artifactRequired =>
      status == 413 && code == 'workspace_artifact_required';
  bool get conflict => status == 409 || status == 412;
  @override
  String toString() => message;
}

class CollectionScope {
  const CollectionScope({
    required this.organizationId,
    required this.collectionId,
    required this.name,
    this.permissions = const [],
    this.configuration = const {},
  });
  final String organizationId;
  final String collectionId;
  final String name;
  final List<String> permissions;
  final Json configuration;
  String get key => '$organizationId/$collectionId';
}

class Specimen {
  const Specimen(this.data);
  final Json data;
  String get id => textOf(data['specimen_id'], '');
  String get title =>
      textOf(data['display_name'], textOf(data['filename'], id));
  int get revision => (data['revision'] as num?)?.toInt() ?? 0;

  /// The run and revision the server last answered for this record.
  ///
  /// The list endpoint names it `record_version_id`; the workspace response is
  /// renamed to `latest_record_version_id` on the way in, so a record built
  /// from either answers here. Empty when neither was sent, which is the
  /// signal that this record cannot carry an optimistic concurrency check.
  String get recordVersionId =>
      textOf(data['record_version_id'] ?? data['latest_record_version_id'], '');
  String get state =>
      textOf(data['operational_state'], textOf(data['status'], 'unknown'));
  String? get disposition =>
      data['disposition'] is String ? data['disposition'] : null;
  String get status => vocabularyLabel(disposition ?? state);
  String get profile => textOf(data['profile_version']);
  List<Json> get assets => objects(data['assets']);
  List<Json> get regions => objects(data['regions']);
  List<Json> get observations => objects(data['observations']);
  List<Json> get fields => objects(data['fields']);
  List<Json> get findings => objects(data['validation_findings']);
  List<Json> get evidence => objects(data['evidence']);
  List<Json> get audit => objects(data['audit_events']);
}

class IntakeFile {
  IntakeFile({
    required this.name,
    required this.bytes,
    required this.mimeType,
    required this.sha256,
    required this.method,
    this.sensitive = true,
    this.width,
    this.height,
  });
  final String name;
  final Uint8List bytes;
  final String mimeType;
  final String sha256;
  final String method;
  final bool sensitive;
  final int? width;
  final int? height;
}

enum ArtifactKind {
  activeGraph,
  phase,
  readingMetadata,
  readingDeclarations,
  authority,
  disagreement,
  observationRaw,
  authorityRaw,
}

class ArtifactRequest {
  const ArtifactRequest(this.kind, this.id, {this.fieldKey, this.sha256});
  final ArtifactKind kind;
  final String id;
  final String? fieldKey, sha256;
}

class SpecimenPage {
  const SpecimenPage(this.items, {this.nextCursor});
  final List<Specimen> items;
  final String? nextCursor;
}

class HistoryPage {
  const HistoryPage({
    required this.items,
    required this.throughRevision,
    this.nextCursor,
  });
  final List<Json> items;
  final int throughRevision;
  final int? nextCursor;
}

abstract class SpecimenRepository {
  String get mode;
  List<dynamic> get blockers;
  Future<List<CollectionScope>> scopes();
  Future<List<Json>> profiles(CollectionScope scope);
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  });
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  });
  Future<Json> artifact(
    CollectionScope scope,
    Specimen specimen,
    ArtifactRequest artifact,
  );
  Future<Specimen> specimen(CollectionScope scope, String id);
  Future<HistoryPage> historyPage(
    CollectionScope scope,
    String id, {
    required int throughRevision,
    int afterRevision = 0,
  });
  Future<Specimen> historicalSpecimen(
    CollectionScope scope,
    String id,
    int revision, {
    String? runId,
    String? runSha256,
  });
  Future<Json> preflight(CollectionScope scope, IntakeFile file);
  Future<Json> createIntake(CollectionScope scope, IntakeFile file, String key);
  Future<Json> resumeIntake(CollectionScope scope, String id);
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  );
  Future<Json> completeIntake(CollectionScope scope, String id, String key);
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  );

  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  );

  /// Takes one decision across many records in one call.
  ///
  /// Pass criterion 7.3. The wire used to take one decision per call, which
  /// made the count on a bulk confirmation a promise it could not keep: some
  /// calls land, some do not, and nothing says which. This answers a
  /// [BulkDecisionReport] with one row per record instead.
  ///
  /// [key] is the batch's key. Each record's decision reconciles on its own
  /// key derived from it, so a retry after an uncertain answer records each
  /// decision once rather than twice.
  Future<BulkDecisionReport> reviewMany(
    CollectionScope scope,
    List<Specimen> specimens,
    BulkDecisionKind kind,
    String reason,
    String key,
  );
}

/// The decisions this product takes on many records at once.
///
/// An enumeration rather than free-form decision bodies, because the decisions
/// that carry a record-specific target cannot be meant across records: a field
/// correction names a field on one record, and there is no sense in which five
/// records share it. Adding a case here is a product decision.
enum BulkDecisionKind {
  /// Records the reviewer's approval on each record.
  approve('approve'),

  /// Records that every label on each record has been read.
  confirmCoverage('coverage');

  const BulkDecisionKind(this.wire);

  /// The `kind` the decisions endpoint takes. The words a reviewer reads live
  /// with the control that shows them, in `widgets/selection_bar.dart`.
  final String wire;
}

/// What one record's decision did.
enum BulkOutcome {
  /// The server recorded it and answered a newer version.
  applied,

  /// The server refused it. [BulkDecisionResult.message] says why.
  refused,

  /// Never attempted, because an earlier decision on the same record was
  /// refused. Different from refused, and a reviewer is owed the difference.
  skipped,
}

/// One record's row in a [BulkDecisionReport].
class BulkDecisionResult {
  const BulkDecisionResult({
    required this.specimenId,
    required this.outcome,
    this.revision,
    this.code = '',
    this.message = '',
  });

  /// Reads one row of the endpoint's answer.
  factory BulkDecisionResult.fromWire(Json row) {
    final Json error = row['error'] is Map
        ? Json.from(row['error'] as Map)
        : const <String, dynamic>{};
    return BulkDecisionResult(
      specimenId: textOf(row['specimen_id'], ''),
      outcome: switch (row['outcome']) {
        'applied' => BulkOutcome.applied,
        'skipped' => BulkOutcome.skipped,
        _ => BulkOutcome.refused,
      },
      revision: (row['revision'] as num?)?.toInt(),
      code: textOf(error['code'], ''),
      message: textOf(error['message'], ''),
    );
  }

  final String specimenId;
  final BulkOutcome outcome;

  /// The version the decision produced, when it was applied.
  final int? revision;

  /// The server's error code, for a decision that was refused.
  final String code;

  /// The server's message, for a decision that was refused.
  final String message;

  bool get changed => outcome == BulkOutcome.applied;
}

/// What a bulk decision did, record by record.
///
/// Never a single opaque failure: a batch that half worked says exactly which
/// records changed and which did not, because this product supersedes rather
/// than deletes and a reviewer has to know which version they are now looking
/// at.
class BulkDecisionReport {
  const BulkDecisionReport(this.results);

  /// Reads the endpoint's answer.
  factory BulkDecisionReport.fromWire(Json body) => BulkDecisionReport(
    objects(body['results']).map(BulkDecisionResult.fromWire).toList(),
  );

  /// One row per decision sent, in the order they were sent.
  final List<BulkDecisionResult> results;

  int get requested => results.length;

  int get applied => _counted(BulkOutcome.applied);

  int get refused => _counted(BulkOutcome.refused);

  int get skipped => _counted(BulkOutcome.skipped);

  /// The records that did not change, refused and never attempted alike.
  List<BulkDecisionResult> get unchanged =>
      results.where((BulkDecisionResult row) => !row.changed).toList();

  /// True when every decision landed.
  bool get complete => results.isNotEmpty && unchanged.isEmpty;

  int _counted(BulkOutcome outcome) =>
      results.where((BulkDecisionResult row) => row.outcome == outcome).length;
}

/// One reviewer action that the wire can only take one decision at a time.
///
/// An extension rather than a method on [SpecimenRepository] because every
/// repository in this client `implements` that interface rather than
/// extending it, so a default body on the interface would reach none of
/// them. The moment the API publishes a batch endpoint this becomes a method
/// on the interface and `ApiSpecimenRepository` overrides it with one call.
extension ReviewBatch on SpecimenRepository {
  /// Sends [changes] as one reviewer action under one [reason].
  ///
  /// Pass criterion 7.2 asks for five corrections on one record to save with
  /// one round trip and one reason. One reason and one reviewer action are
  /// what this delivers today. One round trip is not, and cannot be from the
  /// client: the review API takes one decision per call, so five corrections
  /// are five calls. Until it grows a batch endpoint this sends them in
  /// order, threading the record forward so each call carries the revision
  /// the one before it produced, and returns only the last result so the
  /// caller moves the screen once rather than five times.
  ///
  /// [keyPrefix] is one prefix for the whole batch, so a reader of the
  /// server's idempotency log can see which calls were one reviewer action.
  /// Every call inside it is `<keyPrefix>-<index>` by default.
  ///
  /// [keyFor] overrides that per call, and the workspace supplies one: a call
  /// that is being retried after an uncertain answer has to carry the key it
  /// carried the first time, or the server records the decision twice. The
  /// prefix names the batch; the key identifies the decision.
  ///
  /// [stillApplies] is asked before each call, against the record the call
  /// before it produced. A batch cannot re-read the screen between its own
  /// calls, so this is how it keeps the guarantee the one at a time path gets
  /// for free: a correction whose field moved under the reviewer is never
  /// sent automatically against a newer revision. The batch stops there and
  /// reports how many landed, with `stopped` true.
  ///
  /// A result that is not a newer version of the same record is refused, the
  /// same rule `WorkspaceController.mutate` applies to a single decision: the
  /// server has not confirmed a save until it answers with one.
  ///
  /// The batch stops at the first failure and throws [ReviewBatchFailure].
  /// Whatever landed before it stays landed, which is what the wire does; the
  /// caller reports how many of the changes are still outstanding.
  Future<ReviewBatchResult> reviewBatch(
    CollectionScope scope,
    Specimen specimen,
    List<Json> changes,
    String reason,
    String keyPrefix, {
    bool Function(Specimen current, Json change)? stillApplies,
    String Function(Specimen current, Json change, int index)? keyFor,
  }) async {
    Specimen current = specimen;
    for (final (int index, Json change) in changes.indexed) {
      if (stillApplies != null && !stillApplies(current, change)) {
        return (specimen: current, saved: index, stopped: true);
      }
      final Json body = <String, dynamic>{...change, 'reason': reason};
      final String key =
          keyFor?.call(current, body, index) ?? '$keyPrefix-$index';
      final Specimen result;
      try {
        result = await review(scope, current, body, key);
      } catch (error) {
        throw ReviewBatchFailure(saved: index, specimen: current, cause: error);
      }
      if (result.id != current.id || result.revision <= current.revision) {
        throw ReviewBatchFailure(
          saved: index,
          specimen: current,
          cause: const ApiFailure(
            'The server has not confirmed this save with a newer record '
            'version.',
            code: 'unconfirmed_save',
          ),
        );
      }
      current = result;
    }
    return (specimen: current, saved: changes.length, stopped: false);
  }
}

/// What a batch did: the record it left behind, how many calls the server
/// acknowledged, and whether it stopped because a later correction no longer
/// applied rather than because it finished.
typedef ReviewBatchResult = ({Specimen specimen, int saved, bool stopped});

/// A batch that stopped part way through.
///
/// Carries the record as the server now has it, so the screen can still show
/// what landed, and the count, so the reviewer is told how many corrections
/// are still theirs to make rather than being told the save failed.
class ReviewBatchFailure implements Exception {
  const ReviewBatchFailure({
    required this.saved,
    required this.specimen,
    required this.cause,
  });

  /// How many of the changes the server accepted before it stopped.
  final int saved;

  /// The record after the last change that landed.
  final Specimen specimen;

  /// What the failing call threw.
  final Object cause;

  @override
  String toString() => cause.toString();
}
