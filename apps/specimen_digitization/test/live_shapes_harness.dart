// Shapes a live collection produces, and the scaffolding that puts them on a
// screen (`docs/execution/FRONT_END_REFACTOR.md` section 3I, slot B3).
//
// Every shape under `test/fixtures/live_shapes/` is a wire body, not a
// `Specimen`, and every helper here sends it through `ApiSpecimenRepository`
// over a `MockClient` before a screen ever sees it. That is the point: the
// record a reviewer reads is the record the client's own parse produced, so a
// test here fails for the same reason the live client would fail rather than
// for a reason a hand built fixture invented.
//
// Every digest in these fixtures is sixty zeros and a counter. It is shaped
// like a digest, because the wire's is and the client reads it as one, and it
// is visibly not one, because nothing here was hashed from a specimen. That
// also keeps a fixture out of the repository's secret baselines, which is
// where a file full of real looking hashes otherwise ends up.
//
// None of the bytes are real. The thousand real slides live in Cloud Storage
// and are not reachable from a workstation, so each fixture carries the
// evidence it was shaped from in its own `evidence` field: the ten specimen
// pilot scope in `docs/execution/CURRENT_RELEASE_CHECKLIST.md`, the intake
// bounds in `docs/execution/backend-openapi.json`, the honesty rules in
// `design/00-north-star.md`, and the confusions two readers make on 1946
// handwriting.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widget_test.dart' show TestRepository, TestSession;

/// Where the shapes live.
const String liveShapeDirectory = 'test/fixtures/live_shapes';

/// The photograph every shape is drawn with.
///
/// The small checked in original, because the six thousand by four thousand
/// pixel shape is metadata: a repository does not check in twenty four
/// megabytes to prove a decode bound it can prove on a thousand pixels.
final Uint8List liveShapePreviewBytes = File(
  'test/fixtures/synthetic-label.png',
).readAsBytesSync();

/// The collection the shapes belong to.
const CollectionScope liveShapeScope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Entomology, live shapes',
  permissions: <String>['reviewer'],
);

/// The collection key the router uses for [liveShapeScope].
const String liveShapeCollection = 'org/insects';

/// Reads one shape file whole.
Json liveShapeDocument(String name) =>
    jsonDecode(File('$liveShapeDirectory/$name').readAsStringSync()) as Json;

/// The wire body inside one shape file.
Json liveShapeWire(String name) =>
    liveShapeDocument(name)['workspace_response'] as Json;

/// Sends [wire] through the client's own parse and answers the record.
///
/// [unknownFields] are added to the body first. A live service adds a field
/// the day it ships one, and a client that only survives the fields it was
/// written against is a client that breaks on a Tuesday.
Future<Specimen> liveShapeRecord(
  Json wire, {
  bool withPhotograph = true,
  Json unknownFields = const <String, dynamic>{},
}) async {
  final ApiSpecimenRepository repository = ApiSpecimenRepository(
    baseUrl: Uri.parse('https://api.example.org'),
    token: () async => 'live-shape-token',
    appCheckToken: () async => 'live-shape-app-check',
    client: MockClient((http.Request request) async {
      if (request.url.path.endsWith('/content')) {
        return withPhotograph
            ? http.Response.bytes(liveShapePreviewBytes, 200)
            : http.Response('{"error":{"code":"forbidden"}}', 403);
      }
      return http.Response(
        jsonEncode(<String, dynamic>{...wire, ...unknownFields}),
        200,
      );
    }),
  );
  try {
    return await repository.specimen(
      liveShapeScope,
      textOf(wire['specimen_id'], ''),
    );
  } finally {
    repository.close();
  }
}

/// A page of [count] queue rows derived from the checked in row template.
///
/// The template is one summary row off the wire. Each row is stamped with its
/// own identifier, version and disposition, so the page carries every
/// disposition the wire has, the null one included, rather than a thousand
/// copies of one state.
List<Specimen> liveShapeQueue(int count) {
  final Json row = liveShapeDocument('queue-row-template.json')['row'] as Json;
  const List<String?> dispositions = <String?>[
    'needs_human_review',
    'cleared',
    'deferred',
    null,
  ];
  return <Specimen>[
    for (int index = 0; index < count; index++)
      Specimen(<String, dynamic>{
        ...row,
        'specimen_id': 'FMNH-INS ${(index + 1001)}',
        'display_name': 'FMNH-INS ${(index + 1001)}',
        'revision': index + 1,
        'disposition': dispositions[index % dispositions.length],
        'operational_state': dispositions[index % dispositions.length] == null
            ? 'processing'
            : 'completed',
        'stage': dispositions[index % dispositions.length] == null
            ? 'transcribing'
            : 'finalized',
        'record_version_id': '${row['active_run_id']}:${index + 1}',
        'reason_codes':
            dispositions[index % dispositions.length] == 'needs_human_review'
            ? <String>['transcription_disagreement']
            : const <String>[],
      }),
  ];
}

/// A collection that answers one record and a queue of any length.
class LiveShapeRepository extends TestRepository {
  /// Serves [record] from the queue and from the record route.
  LiveShapeRepository(this.record, {this.queue = const <Specimen>[]});

  /// The record the workbench opens.
  final Specimen record;

  /// The rows the queue lists. Empty means the one record.
  final List<Specimen> queue;

  List<Specimen> get _rows => queue.isEmpty ? <Specimen>[record] : queue;

  @override
  Future<List<CollectionScope>> scopes() async => <CollectionScope>[
    liveShapeScope,
  ];

  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async => _rows;

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async => SpecimenPage(_rows);

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async => record;

  @override
  Future<HistoryPage> historyPage(
    CollectionScope scope,
    String id, {
    required int throughRevision,
    int afterRevision = 0,
  }) async =>
      HistoryPage(items: const <Json>[], throughRevision: throughRevision);
}

/// The windows a shape is measured in.
///
/// Compact is the phone the record screen was judged on (13 section 0) and
/// expanded is the review desk the north star names. A shape that fits both
/// fits the two windows a reviewer actually holds.
const Map<String, Size> liveShapeWindows = <String, Size>{
  'compact': Size(390, 844),
  'expanded': Size(1180, 820),
};

/// Layout errors the frames of the current test reported.
///
/// Collected rather than thrown, the way the size class goldens collect them:
/// `flutter_test` folds a second and later exception into one summary that no
/// longer names any of them, and an overflow repeats once a frame.
List<String> liveShapeLayoutErrors = <String>[];
FlutterExceptionHandler? _previousOnError;

/// Starts collecting overflows, and restores the handler afterwards.
///
/// Overflows only. Everything else goes back to the handler that was already
/// installed, so a genuine exception still fails the test where it happened
/// rather than arriving at the end as a string. An overflow is collected
/// rather than thrown because it repeats once a frame, and `flutter_test`
/// folds a second and later exception into one summary that no longer names
/// any of them.
void collectLayoutErrors() {
  liveShapeLayoutErrors = <String>[];
  _previousOnError = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final String reported = details.exceptionAsString();
    if (reported.contains('overflowed')) {
      liveShapeLayoutErrors.add(reported);
      return;
    }
    _previousOnError?.call(details);
  };
  addTearDown(() => FlutterError.onError = _previousOnError);
}

/// Fails the current test on any overflow the frames reported.
void expectNoOverflow(String where) {
  expect(
    liveShapeLayoutErrors,
    isEmpty,
    reason: 'laying out $where reported:\n${liveShapeLayoutErrors.join('\n')}',
  );
}

/// Pumps the whole application at one window, on one repository.
Future<void> pumpLiveShape(
  WidgetTester tester, {
  required Size window,
  required LiveShapeRepository repository,
  required String location,
  double textScale = 1.0,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  final TestSession session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(
      session: session,
      repository: repository,
      initialLocation: location,
      motionPreferences: MemoryMotionPreferenceStore(),
    ),
  );
  await tester.pumpAndSettle();
  await _settleImages(tester);
}

/// Decodes every image on screen, so a shape is measured with its photograph
/// drawn rather than with the empty box a fake async frame leaves behind.
Future<void> _settleImages(WidgetTester tester) async {
  final Finder images = find.byType(Image);
  if (images.evaluate().isEmpty) return;
  final BuildContext context = tester.element(images.first);
  final List<ImageProvider<Object>> providers = tester
      .widgetList<Image>(images)
      .map((Image image) => image.image)
      .toList();
  await tester.runAsync(() async {
    for (final ImageProvider<Object> provider in providers) {
      await precacheImage(provider, context);
    }
  });
  await tester.pumpAndSettle();
}

/// The text every `Text` on screen is carrying, in tree order.
List<String> visibleText(WidgetTester tester) => tester
    .widgetList<Text>(find.byType(Text))
    .map((Text text) => text.data ?? '')
    .where((String value) => value.isNotEmpty)
    .toList();
