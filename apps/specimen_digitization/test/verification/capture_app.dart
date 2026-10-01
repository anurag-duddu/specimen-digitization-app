// The capture target for the device matrix of the second verification report
// (`design/12-verification-report-v2.md`, item 4).
//
// `flutter run -t test/verification/capture_app.dart -d <device>` puts the
// real client on a real device with a record on it. The application's own
// `main()` needs either Firebase and a production API or a local synthetic
// API on loopback, and neither is reachable from a simulator, an emulator or
// a browser tab without standing a server up outside this worktree. A device
// capture of the setup screen would say nothing about the queue, the record
// or intake, which is what the report has to show.
//
// So this target composes the shipped `SpecimenDigitizationApp` with the same
// explicitly synthetic fixtures: records with a
// photograph, three label regions, three actual synthetic readers, fields in four
// states, an outstanding finding and a decision history. Nothing here is a
// screen, a widget or a token. Every pixel a capture shows is the product's.
//
// The photograph is drawn at startup rather than carried here. A test fixture
// is not in the asset bundle and `pubspec.yaml` is not this slot's file, and
// the obvious answer, the fixture PNG as base64, is 317 lines the secret
// scanner reads as 317 high entropy strings. So the label is painted: the same
// seven lines the checked-in fixture carries, on the same cream, at the same
// 1000 by 520, with the two label regions of the fixture falling on real
// words.

import 'dart:async';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/review_context.dart';
import 'package:specimen_digitization/src/sources.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'ingestion_repository_fixture.dart';

/// Where the window opens. `--dart-define=CAPTURE_LOCATION=...`, defaulting to
/// the queue, so one run can be pointed at a screen the navigation does not
/// reach in one tap.
const String captureLocation = String.fromEnvironment('CAPTURE_LOCATION');

/// True to open the sign in screen instead of the collection.
const bool captureSignedOut = bool.fromEnvironment('CAPTURE_SIGNED_OUT');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  _label = await _drawLabel();
  final String collection = encodeCollectionKey('org/insects');
  runApp(
    SpecimenDigitizationApp(
      session: _CaptureSession(signedIn: !captureSignedOut),
      repository: _CaptureRepository(),
      initialLocation: captureLocation.isEmpty
          ? AppRoutes.queueOf(collection)
          : captureLocation,
    ),
  );
}

/// A reviewer who is already signed in, verified and holds one collection.
class _CaptureSession implements SessionAccess {
  _CaptureSession({required this.signedIn});

  @override
  bool signedIn;

  final StreamController<bool> _changes = StreamController<bool>.broadcast();

  @override
  Stream<bool> get changes => _changes.stream;

  @override
  String get displayName => 'Synthetic reviewer';

  @override
  String get userId => 'fixture-user';

  @override
  Future<String?> token() async => 'fixture-token';

  @override
  Future<void> signIn(String email, String password) async {
    signedIn = true;
    _changes.add(true);
  }

  @override
  Future<void> signOut() async {
    signedIn = false;
    _changes.add(false);
  }

  @override
  Future<void> resetPassword(String email) async {}
}

/// The photograph every capture of the record shows.
///
/// Rebuilt by [main] so each native integration case can start a fresh fixture.
late Uint8List _label;

/// The label's pixel size. The fixture's, so the regions below land where the
/// size class goldens put them.
const Size _labelSize = Size(1000, 520);

/// Paints the label and encodes it as a PNG.
Future<Uint8List> _drawLabel() async {
  final ui.PictureRecorder recorder = ui.PictureRecorder();
  final Canvas canvas = Canvas(recorder, Offset.zero & _labelSize);
  const Color paper = Color(0xFFF6F1E1);
  const Color ink = Color(0xFF1B1A16);
  canvas.drawRect(Offset.zero & _labelSize, Paint()..color = paper);
  void text(String value, Offset position, double width, double size) {
    final builder = ui.ParagraphBuilder(ui.ParagraphStyle(fontSize: size))
      ..pushStyle(ui.TextStyle(color: ink))
      ..addText(value);
    final paragraph = builder.build()
      ..layout(ui.ParagraphConstraints(width: width));
    canvas.drawParagraph(paragraph, position);
  }

  text(
    'SYNTHETIC TEST LABELS · NOT MUSEUM DATA',
    const Offset(40, 24),
    920,
    28,
  );
  for (final rect in <Rect>[
    const Rect.fromLTRB(40, 90, 650, 275),
    const Rect.fromLTRB(40, 300, 650, 475),
    const Rect.fromLTRB(700, 90, 960, 475),
  ]) {
    canvas.drawRect(
      rect,
      Paint()
        ..color = ink
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
  }
  text(
    'Chicago 1912\nIllinois, U.S.A.\nSynthetic teaching garden',
    const Offset(62, 112),
    570,
    34,
  );
  text('Museum 25\nSynthetic collection note', const Offset(62, 325), 570, 34);
  text('Damaged\nlabel\n\nNo model\nresult', const Offset(723, 112), 218, 31);
  final ui.Image image = await recorder.endRecording().toImage(
    _labelSize.width.round(),
    _labelSize.height.round(),
  );
  final ByteData? bytes = await image.toByteData(
    format: ui.ImageByteFormat.png,
  );
  image.dispose();
  return bytes!.buffer.asUint8List();
}

/// One record with everything the review screen has to draw.
///
/// Browser fixtures exercise actual reader identity, missing results and
/// acknowledged in-memory correction. Real API persistence has a separate test.
Specimen _record() => Specimen(<String, dynamic>{
  'specimen_id': 'fixture-001',
  'display_name': 'Pinned beetle, Chicago 1912',
  'revision': 17,
  'active_run_id': 'synthetic-run',
  'latest_record_version_id': 'synthetic-run:17',
  'record_version_id': 'synthetic-run:17',
  'operational_state': 'completed',
  'disposition': 'needs_human_review',
  'reason_codes': const <String>['human_approval_required'],
  'profile_version': 'insects-v3',
  'available_actions': const <String>[
    'restore_version',
    'field',
    'transcription',
    'coverage',
    'approve',
    'classification',
    'regions',
    'retry',
  ],
  'assets': <Json>[
    <String, dynamic>{
      'asset_id': 'fixture-asset',
      'width': 1000,
      'height': 520,
      'pixel_basis': 'original_pixel_edges',
      'preview_bytes': _label,
      'preview_is_derivative': true,
      'view_derivative': const <String, dynamic>{
        'transform': <String, dynamic>{
          'matrix': <num>[1, 0, 0, 0, 1, 0],
          'original_width': 1000,
          'view_width': 1000,
          'view_height': 520,
        },
      },
    },
  ],
  'regions': const <Json>[
    <String, dynamic>{
      'region_id': 'r1',
      'bbox': <int>[40, 90, 650, 275],
      'order': 0,
      'rotation_quarter_turns': 0,
    },
    <String, dynamic>{
      'region_id': 'r2',
      'bbox': <int>[40, 300, 650, 475],
      'order': 1,
      'rotation_quarter_turns': 0,
    },
    {
      'region_id': 'r3',
      'bbox': <int>[700, 90, 960, 475],
      'order': 2,
      'rotation_quarter_turns': 0,
    },
  ],
  'transcriptions': const <Json>[
    {
      'region_id': 'r1',
      'text': null,
      'state': 'unresolved',
      'resolved': false,
      'observation_ids': ['o1', 'o2', 'o3'],
    },
    {
      'region_id': 'r2',
      'text': null,
      'state': 'unresolved',
      'resolved': false,
      'observation_ids': ['o4', 'o5'],
    },
  ],
  'observations': const <Json>[
    {
      'id': 'o2',
      'model_id': 'Synthetic beta reader',
      'route_id': 'beta',
      'provider': 'Local synthetic fixture',
      'region_id': 'r1',
      'literal_text': 'Chicago 1917',
      'prompt_version': 'synthetic-v1',
    },
    {
      'id': 'o5',
      'model_id': 'Synthetic beta reader',
      'route_id': 'beta',
      'provider': 'Local synthetic fixture',
      'region_id': 'r2',
      'literal_text': 'Museum 25',
      'prompt_version': 'synthetic-v1',
    },
    {
      'id': 'o3',
      'model_id': 'Synthetic gamma reader',
      'route_id': 'gamma',
      'provider': 'Local synthetic fixture',
      'region_id': 'r1',
      'literal_text': 'Chicago 1912',
      'prompt_version': 'synthetic-v1',
    },
    {
      'id': 'o1',
      'model_id': 'Synthetic alpha reader',
      'route_id': 'alpha',
      'provider': 'Local synthetic fixture',
      'region_id': 'r1',
      'literal_text': 'Chicago 1912',
      'prompt_version': 'synthetic-v1',
    },
    {
      'id': 'o4',
      'model_id': 'Synthetic alpha reader',
      'route_id': 'alpha',
      'provider': 'Local synthetic fixture',
      'region_id': 'r2',
      'literal_text': 'Museum 25',
      'prompt_version': 'synthetic-v1',
    },
  ],
  'evidence': const <Json>[
    {
      'evidence_id': 'e1',
      'region_id': 'r1',
      'kind': 'literal_text',
      'excerpt': 'Chicago',
    },
    {
      'evidence_id': 'e2',
      'region_id': 'r2',
      'kind': 'literal_text',
      'excerpt': 'Museum 25',
    },
  ],
  'disagreements': const <Json>[
    <String, dynamic>{
      'region_id': 'r1',
      'alternatives': <String>['1912', '1917'],
      'resolved': false,
    },
  ],
  'fields': const <Json>[
    <String, dynamic>{
      'field_key': 'country',
      'display_name': 'Country',
      'required': true,
      'state': 'supported',
      'literal_value': 'U.S.A.',
      'parsed_value': 'United States',
      'normalized': 'United States of America',
      'evidence_ids': <String>['e1', 'e2'],
    },
    <String, dynamic>{
      'field_key': 'collectors',
      'display_name': 'Collectors',
      'required': true,
      'state': 'unknown',
      'literal_value': null,
    },
    <String, dynamic>{
      'field_key': 'habitat',
      'display_name': 'Habitat',
      'required': false,
      'state': 'unreadable',
      'literal_value': null,
    },
    <String, dynamic>{
      'field_key': 'elevation_from_m',
      'display_name': 'Elevation from',
      'required': false,
      'state': 'not_present',
      'literal_value': null,
    },
  ],
  'validation_findings': const <Json>[
    <String, dynamic>{
      'field_key': 'collectors',
      'message': 'A supported collector is required',
      'severity': 'hard',
    },
  ],
  'audit_events': const <Json>[
    <String, dynamic>{
      'action': 'intake',
      'actor_id': 'operator-1',
      'created_at': '2026-09-07T10:00:00Z',
    },
    <String, dynamic>{
      'action': 'transcribe',
      'actor_id': 'system',
      'created_at': '2026-09-07T10:04:00Z',
    },
  ],
});

/// Varied, clearly synthetic rows exercise state views and loaded pagination.
List<Specimen> _queue() => <Specimen>[
  for (int i = 1; i <= 8; i++)
    Specimen(<String, dynamic>{
      ..._record().data,
      'specimen_id': 'fixture-00$i',
      'display_name': 'Synthetic label study $i',
      if (i == 3) ...{
        'operational_state': 'running',
        'disposition': null,
        'available_actions': <String>[],
      },
      if (i == 4) ...{
        'operational_state': 'processing_blocked',
        'disposition': null,
        'available_actions': ['retry'],
      },
      if (i == 5) ...{
        'disposition': 'cleared',
        'available_actions': <String>[],
      },
      if (i == 6) ...{
        'disposition': 'needs_human_review',
        'available_actions': <String>[],
      },
    }),
];

/// The collection API, answering from the fixture rather than from a server.
class _CaptureRepository
    implements SpecimenRepository, SourceRepository, SpecimenHistoryRepository {
  final List<Specimen> _records = _queue();
  final PreviewRepository _intake = PreviewRepository();
  final Map<String, Map<int, Specimen>> _versions = {};
  final Map<String, Specimen> _requests = {};
  final Map<String, String> _restorePayloads = {};

  _CaptureRepository() {
    for (final record in _records) {
      _versions[record.id] = {
        1: Specimen({
          ...record.data,
          'revision': 1,
          'record_version_id': 'synthetic-run:1',
          'latest_record_version_id': 'synthetic-run:1',
          'audit_events': <Json>[
            {
              'action': 'initial_record',
              'actor_id': 'fixture-user',
              'created_at': '2026-09-07T10:00:00Z',
              'reason': 'Initial synthetic specimen data',
            },
          ],
        }),
        record.revision: record,
      };
    }
  }

  @override
  String get mode => 'synthetic';

  @override
  List<dynamic> get blockers => const <dynamic>[];

  @override
  Future<List<CollectionScope>> scopes() async => const <CollectionScope>[
    CollectionScope(
      organizationId: 'org',
      collectionId: 'insects',
      name: 'Synthetic Insects',
      permissions: <String>['reviewer'],
    ),
  ];

  @override
  Future<List<Json>> profiles(CollectionScope scope) async => const <Json>[];

  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => (await specimenPage(
    scope,
    filters: {
      if (query.isNotEmpty) 'specimen_id': query,
      if (status.isNotEmpty) 'disposition': status,
    },
  )).items;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    final matches = _records
        .where(
          (record) =>
              (filters['specimen_id'] == null ||
                  record.id == filters['specimen_id']) &&
              (filters['disposition'] == null ||
                  record.disposition == filters['disposition']) &&
              (filters['state'] == null || record.state == filters['state']),
        )
        .toList();
    final offset = int.tryParse(cursor ?? '') ?? 0;
    final page = matches.skip(offset).take(4).toList();
    return SpecimenPage(
      page,
      nextCursor: offset + page.length < matches.length
          ? '${offset + page.length}'
          : null,
    );
  }

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async {
    // Opt-in browser inspection of the real loading layout. The default fixture
    // remains immediate; this affects no production repository or live request.
    final delay = int.tryParse(Uri.base.queryParameters['detailDelayMs'] ?? '');
    if (delay != null && delay > 0) {
      await Future<void>.delayed(Duration(milliseconds: delay.clamp(0, 10000)));
    }
    return _records.where((Specimen record) => record.id == id).firstOrNull ??
        (throw const ApiFailure(
          'Synthetic record not found',
          code: 'not_found',
          status: 404,
        ));
  }

  @override
  Future<Json> artifact(
    CollectionScope scope,
    Specimen specimen,
    ArtifactRequest artifact,
  ) async => const <String, dynamic>{};

  @override
  Future<HistoryPage> historyPage(
    CollectionScope scope,
    String id, {
    required int throughRevision,
    int afterRevision = 0,
  }) async => HistoryPage(
    items: [
      for (final record in (_versions[id]?.values ?? <Specimen>[]).where(
        (r) => r.revision <= throughRevision && r.revision > afterRevision,
      ))
        {
          'revision': record.revision,
          'run_id': 'synthetic-run',
          ...record.audit.lastOrNull ??
              <String, dynamic>{'action': 'initial_record'},
          'actor_id': 'fixture-user',
        },
    ],
    throughRevision: throughRevision,
  );

  @override
  Future<Specimen> historicalSpecimen(
    CollectionScope scope,
    String id,
    int revision, {
    String? runId,
    String? runSha256,
  }) async =>
      _versions[id]?[revision] ??
      (throw const ApiFailure(
        'Synthetic version not found',
        code: 'not_found',
        status: 404,
      ));

  @override
  Future<Specimen> restoreVersion(
    CollectionScope scope,
    Specimen specimen, {
    required int sourceRevision,
    required bool resetToInitial,
    required String reason,
    required String idempotencyKey,
  }) async {
    final payload =
        '${scope.key}:${specimen.id}:${specimen.revision}:$sourceRevision:$resetToInitial:$reason';
    if (_requests.containsKey(idempotencyKey)) {
      if (_restorePayloads[idempotencyKey] != payload) {
        throw const ApiFailure(
          'Idempotency key belongs to another request.',
          code: 'conflict',
          status: 409,
        );
      }
      return _requests[idempotencyKey]!;
    }
    final current = await this.specimen(scope, specimen.id);
    if (current.revision != specimen.revision) {
      throw const ApiFailure(
        'This record changed. Refresh before restoring.',
        code: 'conflict',
        status: 409,
      );
    }
    if (reason.trim().isEmpty || (resetToInitial && sourceRevision != 1)) {
      throw const ApiFailure(
        'A reason and a valid retained version are required.',
        code: 'validation',
        status: 422,
      );
    }
    final source = await historicalSpecimen(scope, current.id, sourceRevision);
    final sourceEvidence = objects(source.data['evidence']);
    final authorityEvidenceIds = sourceEvidence
        .map(objectOf)
        .where((entry) => entry['kind'] == 'authority_selection')
        .map((entry) => entry['id'] ?? entry['evidence_id'])
        .toSet();
    final fields = [
      for (final field in source.fields)
        {
          ...field,
          if (field['authority_id'] != null ||
              field['authority_identity'] != null ||
              (field['evidence_ids'] as List? ?? const []).any(
                authorityEvidenceIds.contains,
              )) ...{
            'normalized': null,
            'normalized_value': null,
            'resolved_value': null,
          },
          'authority_id': null,
          'authority_identity': null,
          'evidence_ids': (field['evidence_ids'] as List? ?? const [])
              .where((id) => !authorityEvidenceIds.contains(id))
              .toList(),
        },
    ];
    final revision = current.revision + 1;
    final runId = 'synthetic-restore-$revision';
    final event = <String, dynamic>{
      'action': resetToInitial
          ? 'review_reset_initial'
          : 'review_restore_version',
      'actor_id': 'fixture-user',
      'source_revision': sourceRevision,
      'before': {
        'specimen_id': current.id,
        'revision': current.revision,
        'run_id': current.data['active_run_id'],
      },
      'after': {'source_revision': sourceRevision},
      'reason': reason,
      'created_at': DateTime.now().toUtc().toIso8601String(),
    };
    final restored = Specimen({
      ...source.data,
      'revision': revision,
      'active_run_id': runId,
      'record_version_id': '$runId:$revision',
      'latest_record_version_id': '$runId:$revision',
      'assets': current.assets,
      'human_approved': false,
      'disposition': null,
      'status': 'paused',
      'operational_state': 'paused',
      'blocker': 'history_restored_review_required',
      'run': {
        ...objectOf(source.data['run']),
        'id': runId,
        'stage': 'paused',
        'human_approved': false,
        'disposition': null,
        'phase_results': <String, dynamic>{},
        'review_risk': null,
        'authority_results': <dynamic>[],
        'lookups': <dynamic>[],
        'status': 'paused',
        'blocker': 'history_restored_review_required',
      },
      'fields': fields,
      'authority_results': <dynamic>[],
      'authority_unresolved': <String, dynamic>{},
      'evidence': sourceEvidence
          .where((entry) => objectOf(entry)['kind'] != 'authority_selection')
          .toList(),
      'available_actions': [
        'restore_version',
        'transcription',
        'reading_metadata',
        'field',
        'regions',
        'coverage',
        'retry',
      ],
      'audit_events': [...current.audit, event],
    });
    _records[_records.indexWhere((record) => record.id == current.id)] =
        restored;
    _versions[current.id]![revision] = restored;
    _requests[idempotencyKey] = restored;
    _restorePayloads[idempotencyKey] = payload;
    return restored;
  }

  @override
  Future<Json> preflight(CollectionScope scope, IntakeFile file) =>
      _intake.preflight(scope, file);

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) => _intake.createIntake(scope, file, key);

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) =>
      _intake.resumeIntake(scope, id);

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) => _intake.upload(scope, session, file, progress);

  @override
  Future<Json> completeIntake(CollectionScope scope, String id, String key) =>
      _intake.completeIntake(scope, id, key);

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    if (_requests.containsKey(key)) return _requests[key]!;
    final current = await this.specimen(scope, specimen.id);
    if (current.revision != specimen.revision) {
      throw const ApiFailure(
        'This record changed. Refresh before saving.',
        code: 'conflict',
        status: 409,
      );
    }
    if (textOf(change['reason'], '').trim().isEmpty) {
      throw const ApiFailure(
        'A reason is required',
        code: 'validation',
        status: 422,
      );
    }
    final kind = change['kind'];
    final permission = kind == 'transcription_adjudication'
        ? 'transcription'
        : kind == 'field_correction'
        ? 'field'
        : kind;
    if (!(current.data['available_actions'] as List).contains(permission)) {
      throw const ApiFailure(
        'This action is unavailable for this synthetic record',
        code: 'forbidden',
        status: 403,
      );
    }
    final data = <String, dynamic>{...current.data};
    if (kind == 'transcription_adjudication') {
      final transcripts = objects(current.data['transcriptions']);
      final index = transcripts.indexWhere(
        (t) => t['region_id'] == change['target_id'],
      );
      if (index < 0) {
        throw const ApiFailure(
          'No existing transcription for this label',
          code: 'validation',
          status: 422,
        );
      }
      final state = change['state'];
      if (state == 'supported' && textOf(change['value'], '').trim().isEmpty) {
        throw const ApiFailure(
          'Accepted text is required',
          code: 'validation',
          status: 422,
        );
      }
      transcripts[index] = {
        ...transcripts[index],
        'text': state == 'supported' ? change['value'] : null,
        'state': state,
        'value_state': state,
        'resolved': state == 'supported',
        'reason': change['reason'],
        'actor': 'fixture-user',
      };
      data['transcriptions'] = transcripts;
      data['disposition'] = 'needs_human_review';
      data['human_approved'] = false;
    } else if (kind == 'field_correction') {
      final ids = (change['evidence_ids'] as List? ?? []).cast<String>();
      final retained = current.evidence.map((e) => e['evidence_id']).toSet();
      if (ids.any((id) => !retained.contains(id))) {
        throw const ApiFailure(
          'Unknown retained evidence',
          code: 'validation',
          status: 422,
        );
      }
      final fields = current.fields;
      final index = fields.indexWhere(
        (f) => f['field_key'] == change['target_id'],
      );
      if (index < 0) {
        throw const ApiFailure(
          'Unknown record field',
          code: 'validation',
          status: 422,
        );
      }
      fields[index] = {
        ...fields[index],
        'literal_value': change['value'],
        'state': change['state'],
        'parsed_value': change['parsed'],
        'normalized': change['normalized'],
        'authority_id': change['authority_id'],
        'evidence_ids': ids,
        'reason': change['reason'],
      };
      data['fields'] = fields;
      data['disposition'] = 'needs_human_review';
    } else if (kind == 'coverage') {
      data['run'] = {
        ...objectOf(current.data['run']),
        'coverage_confirmed': true,
      };
    } else if (kind == 'regions') {
      data['regions'] = change['regions'];
    } else if (kind == 'approve') {
      throw const ApiFailure(
        'Required field and label checks remain unresolved',
        code: 'conflict',
        status: 409,
      );
    } else {
      throw const ApiFailure(
        'This action is not implemented in the synthetic capture',
        code: 'unavailable',
        status: 422,
      );
    }
    final revision = current.revision + 1;
    data.addAll({
      'revision': revision,
      'latest_record_version_id': 'synthetic-run:$revision',
      'record_version_id': 'synthetic-run:$revision',
      'audit_events': [
        ...current.audit,
        {
          'action': kind,
          'actor_id': 'fixture-user',
          'reason': change['reason'],
          'created_at': DateTime.now().toUtc().toIso8601String(),
        },
      ],
    });
    final saved = Specimen(data);
    _records[_records.indexWhere((r) => r.id == specimen.id)] = saved;
    _versions[specimen.id]![revision] = saved;
    _requests[key] = saved;
    return saved;
  }

  @override
  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  ) async => specimen;

  @override
  Future<BulkDecisionReport> reviewMany(
    CollectionScope scope,
    List<Specimen> specimens,
    BulkDecisionKind kind,
    String reason,
    String key,
  ) async {
    final results = <BulkDecisionResult>[];
    for (final record in specimens) {
      try {
        final saved = await review(scope, record, {
          'kind': kind.wire,
          'reason': reason,
        }, '$key:${record.id}');
        results.add(
          BulkDecisionResult(
            specimenId: record.id,
            outcome: BulkOutcome.applied,
            revision: saved.revision,
          ),
        );
      } on ApiFailure catch (error) {
        results.add(
          BulkDecisionResult(
            specimenId: record.id,
            outcome: BulkOutcome.refused,
            message: error.message,
          ),
        );
      }
    }
    return BulkDecisionReport(results);
  }

  @override
  Future<List<RegisteredSource>> sources(CollectionScope scope) async =>
      <RegisteredSource>[
        RegisteredSource(const <String, dynamic>{
          'source_id': 'src-1',
          'collection_id': 'insects',
          'bucket': 'specimen-digitization.firebasestorage.app',
          'prefix': 'microscopic-slides/',
          'media_types': <String>['image/jpeg', 'image/png', 'image/tiff'],
          'registered_by': 'administrator',
          'registered_at': '2026-09-14T10:22:00Z',
          'inventory': <String, dynamic>{
            'inventory_id': 'inv-1',
            'object_count': 1000,
            'captured_at': '2026-09-14T10:22:00Z',
          },
        }),
      ];

  @override
  Future<SourceObjectPage> sourceObjectPage(
    CollectionScope scope,
    String sourceId, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => SourceObjectPage(
    <SourceObject>[
      _object('subject_105526321.jpg'),
      _object('subject_105526322.jpg'),
      _object(
        'subject_105526323.jpg',
        state: 'imported',
        specimenId: 'fixture-001',
      ),
      _object('field_notes_1946.tiff', mediaType: 'image/tiff'),
      _object(
        'catalogue.pdf',
        state: 'unsupported_media_type',
        mediaType: 'application/pdf',
      ),
    ],
    inventoryId: 'inv-1',
    capturedAt: DateTime.utc(2026, 9, 14, 10, 22),
    objectCount: 1000,
    matchingCount: 1000,
  );

  @override
  Future<SourceImportResult> importFromSource(
    CollectionScope scope,
    String sourceId,
    List<SourceObject> selection,
    String key, {
    bool sensitive = true,
  }) async => SourceImportResult(const <String, dynamic>{
    'requested': 0,
    'imported': 0,
    'duplicates': 0,
    'items': <Map<String, dynamic>>[],
  });

  static SourceObject _object(
    String name, {
    String state = 'available',
    String mediaType = 'image/jpeg',
    String? specimenId,
  }) => SourceObject(<String, dynamic>{
    'bucket': 'specimen-digitization.firebasestorage.app',
    'object_name': 'microscopic-slides/$name',
    'generation': '1757000000000001',
    'sha256': 'sha-$name',
    'size_bytes': 312000,
    'media_type': mediaType,
    'state': state,
    'specimen_id': specimenId,
  });
}
