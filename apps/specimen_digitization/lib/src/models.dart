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
  /// [keyPrefix] is one prefix for the whole batch. Every call inside it is
  /// `<keyPrefix>-<index>`, so an identical retry of the same batch
  /// reconciles on the server call by call rather than recording twice, and
  /// a reader of the server's idempotency log can see which calls were one
  /// reviewer action.
  ///
  /// The batch stops at the first failure and rethrows. Whatever landed
  /// before it stays landed, which is what the wire does; the caller reports
  /// how many of the changes are still outstanding.
  Future<Specimen> reviewBatch(
    CollectionScope scope,
    Specimen specimen,
    List<Json> changes,
    String reason,
    String keyPrefix,
  ) async {
    Specimen current = specimen;
    for (final (int index, Json change) in changes.indexed) {
      try {
        current = await review(scope, current, <String, dynamic>{
          ...change,
          'reason': reason,
        }, '$keyPrefix-$index');
      } catch (error) {
        throw ReviewBatchFailure(saved: index, specimen: current, cause: error);
      }
    }
    return current;
  }
}

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
