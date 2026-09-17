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
// fixture the size class goldens are built from: one record with a
// photograph, two label regions, two readings that disagree, fields in four
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
import 'package:specimen_digitization/src/sources.dart';
import 'package:specimen_digitization/src/workspace.dart';

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
/// Set once by [main] before the first frame.
late final Uint8List _label;

/// The label's pixel size. The fixture's, so the regions below land where the
/// size class goldens put them.
const Size _labelSize = Size(1000, 520);

/// The seven lines the checked-in fixture carries.
const List<String> _labelLines = <String>[
  'SYNTHETIC TEST LABEL, NOT MUSEUM DATA',
  '',
  'FMNH-INS 1001',
  'Danaus plexippus',
  'Chicago, Illinois',
  'Synthetic teaching garden',
  '2020-06-01',
  'Independent readings: 1912 / 1917',
];

/// Paints the label and encodes it as a PNG.
Future<Uint8List> _drawLabel() async {
  final ui.PictureRecorder recorder = ui.PictureRecorder();
  final Canvas canvas = Canvas(recorder, Offset.zero & _labelSize);
  const Color paper = Color(0xFFF6F1E1);
  const Color ink = Color(0xFF1B1A16);
  canvas.drawRect(Offset.zero & _labelSize, Paint()..color = paper);
  canvas.drawRect(
    const Rect.fromLTWH(24, 24, 952, 472),
    Paint()
      ..color = ink
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3,
  );
  double y = 60;
  for (int i = 0; i < _labelLines.length; i++) {
    final String line = _labelLines[i];
    if (line.isEmpty) {
      y += 24;
      continue;
    }
    final ui.ParagraphBuilder builder =
        ui.ParagraphBuilder(
            ui.ParagraphStyle(
              fontSize: i == 0 ? 30 : 34,
              textAlign: TextAlign.left,
            ),
          )
          ..pushStyle(ui.TextStyle(color: ink))
          ..addText(line);
    final ui.Paragraph paragraph = builder.build()
      ..layout(const ui.ParagraphConstraints(width: 880));
    canvas.drawParagraph(paragraph, Offset(70, y));
    y += paragraph.height + 12;
  }
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
/// The same shape as `test/golden/golden_harness.dart`'s `goldenSpecimen`, so
/// a device capture and a size class golden are of the same record.
Specimen _record() => Specimen(<String, dynamic>{
  'specimen_id': 'fixture-001',
  'display_name': 'Pinned beetle, Chicago 1912',
  'revision': 17,
  'operational_state': 'completed',
  'disposition': 'needs_human_review',
  'reason_codes': const <String>['human_approval_required'],
  'profile_version': 'insects-v3',
  'available_actions': const <String>[
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
      'bbox': <int>[100, 52, 400, 212],
      'order': 0,
      'rotation_quarter_turns': 0,
    },
    <String, dynamic>{
      'region_id': 'r2',
      'bbox': <int>[420, 52, 700, 212],
      'order': 1,
      'rotation_quarter_turns': 0,
    },
  ],
  'observations': const <Json>[
    <String, dynamic>{
      'observation_id': 'o1',
      'model_id': 'Reading A',
      'region_id': 'r1',
      'literal_text': 'Chicago 1912',
    },
    <String, dynamic>{
      'observation_id': 'o2',
      'model_id': 'Reading B',
      'region_id': 'r1',
      'literal_text': 'Chicago 1917',
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
      'normalized_value': 'United States of America',
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

/// The four records the queue lists.
List<Specimen> _queue() => <Specimen>[
  for (int i = 1; i <= 4; i++)
    Specimen(<String, dynamic>{
      ..._record().data,
      'specimen_id': 'fixture-00$i',
      'display_name': 'Pinned beetle $i, Chicago 1912',
    }),
];

/// The collection API, answering from the fixture rather than from a server.
class _CaptureRepository implements SpecimenRepository, SourceRepository {
  final List<Specimen> _records = _queue();

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
  }) async => _records;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => SpecimenPage(_records);

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async =>
      _records.where((Specimen record) => record.id == id).firstOrNull ??
      _records.first;

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
    items: const <Json>[
      <String, dynamic>{
        'revision': 17,
        'action': 'transcribe',
        'actor_id': 'system',
        'created_at': '2026-09-07T10:04:00Z',
      },
      <String, dynamic>{
        'revision': 16,
        'action': 'intake',
        'actor_id': 'operator-1',
        'created_at': '2026-09-07T10:00:00Z',
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
  }) async => _records.first;

  @override
  Future<Json> preflight(CollectionScope scope, IntakeFile file) async =>
      const <String, dynamic>{};

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => const <String, dynamic>{};

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async =>
      const <String, dynamic>{};

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {}

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => const <String, dynamic>{};

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async => Specimen(<String, dynamic>{
    ...specimen.data,
    'revision': specimen.revision + 1,
  });

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
  ) async => BulkDecisionReport(<BulkDecisionResult>[
    for (final Specimen specimen in specimens)
      BulkDecisionResult(
        specimenId: specimen.id,
        outcome: BulkOutcome.applied,
        revision: specimen.revision + 1,
      ),
  ]);

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
