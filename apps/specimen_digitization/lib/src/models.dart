import 'dart:typed_data';

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
  String get status => labelOf(disposition ?? state);
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
