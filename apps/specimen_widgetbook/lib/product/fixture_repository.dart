import 'dart:async';
import 'dart:typed_data';

import 'package:specimen_digitization/specimen_application.dart';

/// Deterministic examples, never collection data or service credentials.
enum ProductPreviewCase {
  queueLoaded,
  queueEmpty,
  queueError,
  intakeEmpty,
  intakeSaved,
  workbench,
}

class PreviewSession implements SessionAccess {
  PreviewSession(this.userId);
  final _changes = StreamController<bool>.broadcast();
  @override
  final String userId;
  @override
  bool signedIn = true;
  @override
  String get displayName => 'Synthetic reviewer';
  @override
  Stream<bool> get changes => _changes.stream;
  @override
  Future<String?> token() async => null;
  @override
  Future<void> signIn(String email, String password) async {
    signedIn = true;
    _changes.add(true);
  }

  @override
  Future<void> resetPassword(String email) async => throw const ApiFailure(
    'Password reset email is unavailable in this synthetic preview.',
  );
  @override
  Future<void> signOut() async {
    signedIn = false;
    _changes.add(false);
  }

  void dispose() => unawaited(_changes.close());
}

/// The same wire-shaped fixture used by the app's visual tests. The PNG is
/// copied as a runtime asset; no test package or page implementation is copied.
Specimen previewSpecimen(Uint8List pixels) => Specimen({
  'specimen_id': 'preview-specimen-001',
  'filename': 'synthetic-label.png',
  'display_name': 'Synthetic insect label',
  'revision': 3,
  'record_version_id': 'preview-version-3',
  'operational_state': 'completed',
  'disposition': 'needs_human_review',
  'profile_version': 'synthetic-v1',
  'available_actions': [
    'field',
    'transcription',
    'coverage',
    'approve',
    'regions',
  ],
  'assets': [
    {
      'asset_id': 'preview-photo',
      'filename': 'synthetic-label.png',
      'width': 1000,
      'height': 520,
      'preview_bytes': pixels,
      'preview_is_derivative': true,
      'pixel_basis': 'original_pixel_edges',
      'view_derivative': {
        'transform': {
          'matrix': [1, 0, 0, 0, 1, 0],
          'original_width': 1000,
          'view_width': 1000,
          'view_height': 520,
        },
      },
    },
  ],
  'regions': [
    {
      'region_id': 'r1',
      'bbox': [40, 40, 460, 220],
      'order': 0,
      'rotation_quarter_turns': 0,
    },
    {
      'region_id': 'r2',
      'bbox': [520, 260, 940, 470],
      'order': 1,
      'rotation_quarter_turns': 0,
    },
  ],
  'transcriptions': [
    {
      'region_id': 'r1',
      'verbatim_text': 'Chicago 1912',
      'value_state': 'supported',
    },
    {'region_id': 'r2', 'verbatim_text': null, 'value_state': 'unresolved'},
  ],
  'observations': [
    {
      'observation_id': 'o1',
      'model_id': 'Synthetic reader A',
      'region_id': 'r1',
      'literal_text': 'Chicago 1912',
    },
    {
      'observation_id': 'o2',
      'model_id': 'Synthetic reader B',
      'region_id': 'r1',
      'literal_text': 'Chicago 1917',
    },
  ],
  'disagreements': [
    {
      'region_id': 'r1',
      'alternatives': ['1912', '1917'],
      'resolved': false,
    },
  ],
  'evidence': [
    {
      'evidence_id': 'preview-evidence-a',
      'region_id': 'r1',
      'kind': 'literal',
      'source': 'bounded_extraction_v1',
      'observation_ids': ['o1'],
      'excerpt': 'Chicago',
    },
    {
      'evidence_id': 'preview-evidence-b',
      'region_id': 'r1',
      'kind': 'literal',
      'source': 'bounded_extraction_v1',
      'observation_ids': ['o2'],
      'excerpt': 'Chicago',
    },
  ],
  'fields': [
    {
      'field_key': 'country',
      'display_name': 'Country',
      'required': true,
      'state': 'supported',
      'literal_value': 'U.S.A.',
      'parsed_value': 'United States',
      'normalized': 'United States of America',
    },
    {
      'field_key': 'city',
      'display_name': 'City',
      'state': 'supported',
      'literal_value': 'Chicago',
      'evidence_ids': ['preview-evidence-a', 'preview-evidence-b'],
    },
    {
      'field_key': 'date_visited_from',
      'display_name': 'Date visited from',
      'state': 'ambiguous',
      'literal_value': '1912 or 1917',
      'verbatim_by_observation': {'o1': '1912', 'o2': '1917'},
      'input_source_by_observation': {'o1': 'raw_reading', 'o2': 'raw_reading'},
    },
    {
      'field_key': 'collectors',
      'display_name': 'Collectors',
      'required': true,
      'state': 'unknown',
    },
    {
      'field_key': 'habitat',
      'display_name': 'Habitat',
      'required': false,
      'state': 'unreadable',
    },
    {
      'field_key': 'elevation_from_m',
      'display_name': 'Elevation from',
      'required': false,
      'state': 'not_present',
    },
  ],
  'validation_findings': [
    {
      'field_key': 'collectors',
      'message': 'A supported collector is required',
      'severity': 'hard',
    },
  ],
  'audit_events': [
    {
      'revision': 3,
      'action': 'transcribe',
      'actor_id': 'synthetic-system',
      'created_at': '2026-09-07T10:04:00Z',
    },
  ],
});

class PreviewRepository implements SpecimenRepository, BulkIntakeRepository {
  PreviewRepository({required this.example, required this.pixels})
    : record = previewSpecimen(pixels);
  final ProductPreviewCase example;
  final Uint8List pixels;
  final Specimen record;
  bool _queueFailed = false;
  static const scope = CollectionScope(
    organizationId: 'widgetbook',
    collectionId: 'synthetic',
    name: 'Synthetic collection',
    permissions: ['reviewer'],
  );
  static const writeMessage =
      'This preview does not save or submit changes. Reset to restore the example.';
  Never _readOnly() => throw const ApiFailure(writeMessage);
  @override
  String get mode => 'synthetic';
  @override
  List<dynamic> get blockers => const [];
  @override
  Future<List<CollectionScope>> scopes() async => [scope];
  @override
  Future<List<Json>> profiles(CollectionScope scope) async => [];
  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async {
    if (example == ProductPreviewCase.queueEmpty) return [];
    if (example == ProductPreviewCase.queueError && !_queueFailed) {
      _queueFailed = true;
      throw const ApiFailure(
        'Synthetic queue failure. Retry to load the example.',
      );
    }
    if (query.isNotEmpty &&
        !record.displayReference.toLowerCase().contains(query.toLowerCase())) {
      return [];
    }
    if (status.isNotEmpty && status != record.disposition) return [];
    return [record];
  }

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async => SpecimenPage(
    await specimens(
      scope,
      query: filters['specimen_id'] ?? '',
      status: filters['disposition'] ?? filters['state'] ?? '',
    ),
  );
  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async => record;
  @override
  Future<HistoryPage> historyPage(
    CollectionScope scope,
    String id, {
    required int throughRevision,
    int afterRevision = 0,
  }) async =>
      HistoryPage(items: record.audit, throughRevision: throughRevision);
  @override
  Future<Specimen> historicalSpecimen(
    CollectionScope scope,
    String id,
    int revision, {
    String? runId,
    String? runSha256,
  }) async => record;
  @override
  Future<Json> artifact(
    CollectionScope scope,
    Specimen specimen,
    ArtifactRequest artifact,
  ) async => {};
  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async => _readOnly();
  @override
  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  ) async => _readOnly();
  @override
  Future<BulkDecisionReport> reviewMany(
    CollectionScope scope,
    List<Specimen> specimens,
    BulkDecisionKind kind,
    String reason,
    String key,
  ) async => _readOnly();
  @override
  Future<Json> preflight(CollectionScope scope, IntakeFile file) async =>
      _readOnly();
  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => _readOnly();
  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async =>
      _readOnly();
  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async => _readOnly();
  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => _readOnly();

  Json get _draft => {
    'id': 'preview-draft',
    'name': 'Synthetic saved batch',
    'state': 'draft',
    'revision': 1,
    'created_at': '2026-09-07T10:00:00Z',
  };
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (method != 'GET') return _readOnly();
    return switch (path) {
      '/capabilities' => {
        'providers': <Object>[],
        'bulk_source_admission': false,
      },
      '/drafts' => {
        'items': example == ProductPreviewCase.intakeSaved
            ? [_draft]
            : <Object>[],
      },
      '/drafts/preview-draft' => _draft,
      '/drafts/preview-draft/items' => {
        'items': [
          {
            'id': 'preview-photo',
            'filename': 'synthetic-label.png',
            'state': 'ready',
            'included': true,
            'photo_sensitive': false,
            'size_bytes': pixels.length,
            'source_kind': 'upload',
          },
        ],
      },
      '/submissions' || '/connections' || '/sources' => {'items': <Object>[]},
      _ => throw const ApiFailure(
        'This source is unavailable in the synthetic preview.',
      ),
    };
  }

  @override
  Future<Uint8List> intakePreview(
    CollectionScope scope,
    String itemId, {
    bool full = false,
  }) async => pixels;
}
