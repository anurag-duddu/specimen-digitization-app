// Owner, 2026-10-12: "once it ends up in the main queue, we dont need that in
// the intake right?" A photo the server has put in the main Queue leaves the
// Intake list and this device's saved list by itself, is announced once, and
// takes nobody's keyboard focus with it. Every other state stays.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';

import 'widgets/harness.dart';

const CollectionScope _scope = CollectionScope(
  organizationId: 'moved-org',
  collectionId: 'moved-collection',
  name: 'Moved fixture',
  permissions: <String>['upload'],
);

String _storageKey(String user) => 'upload-handles-v1:$user:${_scope.key}';

String _digest(String id) => id.padRight(64, 'a');

Json _summary(
  String id, {
  String status = 'running',
  String? disposition,
  String? blocker,
  bool inLine = false,
  int revision = 2,
}) => <String, dynamic>{
  'specimen_id': id,
  'organization_id': _scope.organizationId,
  'collection_id': _scope.collectionId,
  'active_run_id': 'run-$id',
  'status': status,
  'blocker': blocker,
  'disposition': disposition,
  'available_actions': <String>[],
  'revision': revision,
  if (inLine) 'intake_progress': <String, dynamic>{'waiting_in_line': true},
};

/// A server that answers each photo's status from [summaries].
ApiSpecimenRepository _server(Map<String, Json> summaries) =>
    ApiSpecimenRepository(
      baseUrl: Uri.parse('http://localhost:8000'),
      token: () async => 'synthetic-moved-token',
      client: MockClient((http.Request request) async {
        final String id = request.url.pathSegments.last;
        final Json? summary = summaries[id];
        if (request.method != 'GET' || summary == null) {
          return http.Response('{"detail":"not found"}', 404);
        }
        return http.Response(jsonEncode(summary), 200);
      }),
    );

ManifestEntry _tracked(String id) => ManifestEntry.tracking(
  digest: _digest(id),
  name: '$id.jpg',
  handle: <String, dynamic>{'upload_id': 'upload-$id'},
  specimenId: id,
);

Map<String, Object> _saved(String user, Map<String, String> states) =>
    <String, Object>{
      _storageKey(user): jsonEncode(<Json>[
        for (final MapEntry<String, String> row in states.entries)
          <String, dynamic>{
            'digest': _digest(row.key),
            'upload_id': 'upload-${row.key}',
            'specimen_id': row.key,
            'state': row.value,
          },
      ]),
    };

Future<List<String>> _savedSpecimens(String user) async {
  final SharedPreferences prefs = await SharedPreferences.getInstance();
  final String? saved = prefs.getString(_storageKey(user));
  if (saved == null) return <String>[];
  return <String>[
    for (final dynamic row in jsonDecode(saved) as List<dynamic>)
      (row as Map<String, dynamic>)['specimen_id'] as String,
  ];
}

/// Records what the app asks the platform to speak.
List<String> _recordAnnouncements(WidgetTester tester) {
  final List<String> announced = <String>[];
  tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<dynamic>(
    SystemChannels.accessibility,
    (dynamic message) async {
      final Map<Object?, Object?> event = message! as Map<Object?, Object?>;
      if (event['type'] != 'announce') return;
      announced.add(
        (event['data']! as Map<Object?, Object?>)['message'].toString(),
      );
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger
        .setMockDecodedMessageHandler<dynamic>(
          SystemChannels.accessibility,
          null,
        ),
  );
  return announced;
}

Future<void> _pumpManifest(
  WidgetTester tester,
  IntakeTransferSession session, {
  bool reduceMotion = false,
}) => pumpComponent(
  tester,
  AnimatedBuilder(
    animation: session,
    builder: (BuildContext context, Widget? child) => IntakeManifest(
      entries: session.entries,
      busy: session.busy,
      stopping: session.stopping,
      onStop: session.stop,
      onRemove: session.remove,
      onServerCheck: (ManifestEntry _) {},
    ),
  ),
  size: const Size(390, 2400),
  reduceMotion: reduceMotion,
);

/// A server whose every upload completes straight into the main Queue.
class _ImmediateQueueRepository implements SpecimenRepository {
  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => <String, dynamic>{'upload_id': file.sha256, 'state': 'ready'};

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async =>
      <String, dynamic>{'upload_id': id, 'state': 'ready'};

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async => progress(1);

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => <String, dynamic>{
    'upload_id': id,
    'specimen_id': 'specimen-$id',
    'status': 'completed',
    'disposition': 'cleared',
    'revision': 1,
    'available_actions': <String>[],
  };

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

ManifestEntry _readyPhoto(String id) => ManifestEntry(
  digest: _digest(id),
  name: '$id.jpg',
  file: IntakeFile(
    name: '$id.jpg',
    bytes: Uint8List.fromList(<int>[1, 2, 3]),
    mimeType: 'image/jpeg',
    sha256: _digest(id),
    method: 'camera',
  ),
  state: UploadState.ready,
);

Future<void> _pumpScreen(
  WidgetTester tester,
  SpecimenRepository repository,
  String user, {
  bool reduceMotion = false,
}) async {
  await tester.binding.setSurfaceSize(const Size(1000, 2200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Builder(
        builder: (BuildContext context) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(supportsAnnounce: true, disableAnimations: reduceMotion),
          child: Scaffold(
            body: IntakeScreen(
              repository: repository,
              scope: _scope,
              userId: user,
              onComplete: () {},
            ),
          ),
        ),
      ),
    ),
  );
  for (var i = 0; i < 3; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test(
    'a finished photo leaves Intake and the saved list; others stay',
    () async {
      final Map<String, Json> summaries = <String, Json>{
        'done': _summary('done', status: 'completed', disposition: 'cleared'),
        'running': _summary('running'),
        'blocked': _summary(
          'blocked',
          status: 'processing_blocked',
          blocker: 'model_output_invalid',
        ),
        'waiting': _summary('waiting', status: 'pending', inLine: true),
      };
      final ApiSpecimenRepository repository = _server(summaries);
      addTearDown(repository.close);
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        _scope,
        'moved-operator',
        processingPollInterval: Duration.zero,
      );
      final ManifestEntry ready = ManifestEntry(
        digest: _digest('ready'),
        name: 'ready.jpg',
        state: UploadState.ready,
      );
      final ManifestEntry failed = ManifestEntry(
        digest: _digest('failed'),
        name: 'failed.jpg',
        state: UploadState.failed,
        reason: 'The server refused this file.',
      );
      session.entries.addAll(<ManifestEntry>[
        _tracked('done'),
        _tracked('running'),
        _tracked('blocked'),
        _tracked('waiting'),
        ready,
        failed,
      ]);
      var handoffs = 0;
      session.attachHandoff(() => handoffs++);

      await session.refreshProcessingStatuses();

      expect(session.entries.map((ManifestEntry e) => e.name), <String>[
        'running.jpg',
        'blocked.jpg',
        'waiting.jpg',
        'ready.jpg',
        'failed.jpg',
      ]);
      expect(session.entries.map((ManifestEntry e) => e.state), <UploadState>[
        UploadState.processing,
        UploadState.processingBlocked,
        UploadState.processing,
        UploadState.ready,
        UploadState.failed,
      ]);
      expect(handoffs, 1, reason: 'the main Queue still refreshes once');
      expect(session.movedToQueue, 1);
      expect(await _savedSpecimens('moved-operator'), <String>[
        'running',
        'blocked',
        'waiting',
      ]);
      expect(
        ingestionQueueLine(session.entries),
        '5 photographs · 1 ready, 2 processing, 2 need attention',
      );

      // A second check of the same server state moves nothing again.
      await session.refreshProcessingStatuses();
      expect(session.movedToQueue, 1);
      expect(handoffs, 1);
      session.close();
    },
  );

  test('every Queue outcome leaves Intake', () async {
    for (final String disposition in <String>[
      'cleared',
      'needs_human_review',
      'deferred',
    ]) {
      final ApiSpecimenRepository repository = _server(<String, Json>{
        disposition: _summary(
          disposition,
          status: 'completed',
          disposition: disposition,
        ),
      });
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        _scope,
        'outcome-$disposition',
        processingPollInterval: Duration.zero,
      );
      session.entries.add(_tracked(disposition));
      await session.refreshProcessingStatuses();
      expect(session.entries, isEmpty, reason: disposition);
      expect(await _savedSpecimens('outcome-$disposition'), isEmpty);
      session.close();
      repository.close();
    }
  });

  test(
    'rows saved as finished in an earlier session are cleared on restore',
    () async {
      // The owner's phones each held three such rows on 2026-10-12.
      SharedPreferences.setMockInitialValues(
        _saved('phone-operator', <String, String>{
          'old-1': 'inMainQueue',
          'old-2': 'inMainQueue',
          'still-running': 'processing',
          'old-3': 'inMainQueue',
        }),
      );
      final ApiSpecimenRepository repository = _server(<String, Json>{
        'still-running': _summary('still-running'),
      });
      addTearDown(repository.close);
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        _scope,
        'phone-operator',
        processingPollInterval: Duration.zero,
      );

      await session.restore();

      expect(session.entries.map((ManifestEntry e) => e.specimenId), <String>[
        'still-running',
      ]);
      expect(session.entries.single.state, UploadState.processing);
      expect(await _savedSpecimens('phone-operator'), <String>[
        'still-running',
      ]);
      // Nothing visible changed, so nothing is announced for these.
      expect(session.movedToQueue, 0);
      session.close();
    },
  );

  test(
    'a restored row that finished meanwhile leaves on its first check',
    () async {
      SharedPreferences.setMockInitialValues(
        _saved('restart-operator', <String, String>{
          'finished-overnight': 'processing',
          'blocked': 'processingBlocked',
        }),
      );
      final ApiSpecimenRepository repository = _server(<String, Json>{
        'finished-overnight': _summary(
          'finished-overnight',
          status: 'completed',
          disposition: 'needs_human_review',
        ),
        'blocked': _summary(
          'blocked',
          status: 'processing_blocked',
          blocker: 'model_output_invalid',
        ),
      });
      addTearDown(repository.close);
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        _scope,
        'restart-operator',
        processingPollInterval: Duration.zero,
      );

      await session.restore();

      expect(session.entries.map((ManifestEntry e) => e.specimenId), <String>[
        'blocked',
      ]);
      expect(await _savedSpecimens('restart-operator'), <String>['blocked']);
      expect(session.movedToQueue, 1);
      session.close();
    },
  );

  for (final bool reduceMotion in <bool>[false, true]) {
    testWidgets(
      'the finished row leaves the manifest and focus moves to its neighbour'
      '${reduceMotion ? ' under reduced motion' : ''}',
      (WidgetTester tester) async {
        final Map<String, Json> summaries = <String, Json>{
          'first': _summary('first'),
          'second': _summary('second'),
        };
        final ApiSpecimenRepository repository = _server(summaries);
        addTearDown(repository.close);
        final IntakeTransferSession session = IntakeTransferSession(
          repository,
          _scope,
          'focus-operator-$reduceMotion',
          processingPollInterval: Duration.zero,
        );
        session.entries.addAll(<ManifestEntry>[
          _tracked('first'),
          _tracked('second'),
        ]);
        await tester.runAsync(session.refreshProcessingStatuses);
        await _pumpManifest(tester, session, reduceMotion: reduceMotion);
        expect(find.text('first.jpg'), findsOneWidget);
        expect(find.textContaining('2 photographs'), findsOneWidget);

        // The operator is reading the first row's progress details.
        final Finder firstDetails = find.descendant(
          of: find.byKey(
            ValueKey<String>('intake-progress-details-${_digest('first')}'),
          ),
          matching: find.byWidgetPredicate(
            (Widget w) => w is Focus || w is FocusableActionDetector,
          ),
        );
        expect(firstDetails, findsWidgets);
        final FocusNode firstNode = Focus.of(
          tester.element(firstDetails.first),
        );
        firstNode.requestFocus();
        await tester.pump();
        expect(firstNode.hasFocus, isTrue);

        summaries['first'] = _summary(
          'first',
          status: 'completed',
          disposition: 'needs_human_review',
          revision: 3,
        );
        await tester.runAsync(session.refreshProcessingStatuses);
        await tester.pump();
        if (reduceMotion) {
          // Under reduced motion the row is simply gone.
          expect(find.text('first.jpg'), findsNothing);
        } else {
          // Collapsing, it is still drawn but can no longer be pressed.
          await tester.pump(const Duration(milliseconds: 50));
          expect(find.text('first.jpg'), findsOneWidget);
          expect(find.text('first.jpg').hitTestable(), findsNothing);
        }
        await tester.pumpAndSettle();

        expect(find.text('first.jpg'), findsNothing);
        expect(find.text('second.jpg'), findsOneWidget);
        expect(
          find.textContaining('1 photograph · 1 processing'),
          findsOneWidget,
        );
        final FocusNode? focused = FocusManager.instance.primaryFocus;
        expect(focused, isNotNull);
        expect(focused!.context, isNotNull);
        final Finder secondRow = find.byKey(
          ValueKey<String>(_digest('second')),
        );
        expect(
          find.descendant(
            of: secondRow,
            matching: find.byElementPredicate(
              (Element e) => identical(e, focused.context),
            ),
          ),
          findsOneWidget,
          reason: 'focus moves to the next row, not to nowhere',
        );
        await tester.pumpWidget(const SizedBox());
        session.close();
      },
    );
  }

  testWidgets('the Intake screen announces a move once and drops the section', (
    WidgetTester tester,
  ) async {
    SharedPreferences.setMockInitialValues(
      _saved('owner', <String, String>{'tracked': 'processing'}),
    );
    final Map<String, Json> summaries = <String, Json>{
      'tracked': _summary('tracked'),
    };
    final ApiSpecimenRepository repository = _server(summaries);
    addTearDown(repository.close);
    final List<String> announced = _recordAnnouncements(tester);
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.binding.setSurfaceSize(const Size(1000, 2200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    var completions = 0;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (BuildContext context) => MediaQuery(
            data: MediaQuery.of(context).copyWith(supportsAnnounce: true),
            child: Scaffold(
              body: IntakeScreen(
                repository: repository,
                scope: _scope,
                userId: 'owner',
                onComplete: () => completions++,
              ),
            ),
          ),
        ),
      ),
    );
    for (var i = 0; i < 5; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 20)),
      );
      await tester.pump();
    }
    expect(find.text('Photos'), findsOneWidget);
    expect(
      find.text('Photograph ${_digest('tracked').substring(0, 12)}'),
      findsOneWidget,
    );
    expect(announced, isEmpty);

    summaries['tracked'] = _summary(
      'tracked',
      status: 'completed',
      disposition: 'cleared',
      revision: 3,
    );
    final IntakeTransferSession session = intakeTransferSession(
      repository,
      _scope,
      'owner',
    );
    await tester.runAsync(session.refreshProcessingStatuses);
    await tester.pumpAndSettle();

    expect(find.text('Photos'), findsNothing);
    expect(session.entries, isEmpty);
    expect(await _savedSpecimens('owner'), isEmpty);
    expect(announced, <String>['Photo moved to the main Queue.']);
    expect(completions, 1, reason: 'the main Queue refreshes for the move');

    // Later frames and checks do not repeat it.
    await tester.runAsync(session.refreshProcessingStatuses);
    await tester.pumpAndSettle();
    expect(announced, <String>['Photo moved to the main Queue.']);
    semantics.dispose();
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('two moves before one frame are one announcement of two', (
    WidgetTester tester,
  ) async {
    final List<String> announced = _recordAnnouncements(tester);
    final SemanticsHandle semantics = tester.ensureSemantics();
    final _ImmediateQueueRepository repository = _ImmediateQueueRepository();
    await _pumpScreen(tester, repository, 'two-moves');
    final IntakeTransferSession session = intakeTransferSession(
      repository,
      _scope,
      'two-moves',
    );
    session.entries.addAll(<ManifestEntry>[
      _readyPhoto('first'),
      _readyPhoto('second'),
    ]);
    session.changed();
    await tester.pumpAndSettle();
    expect(find.text('first.jpg'), findsOneWidget);

    // Both uploads complete straight into the main Queue with no frame
    // between them, so the screen hears two separate moves.
    await tester.runAsync(session.start);
    expect(session.movedToQueue, 2);
    await tester.pumpAndSettle();

    expect(announced, <String>['2 photos moved to the main Queue.']);
    expect(find.text('first.jpg'), findsNothing);
    expect(find.text('second.jpg'), findsNothing);
    semantics.dispose();
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the last row collapses before the Photos section closes', (
    WidgetTester tester,
  ) async {
    final _ImmediateQueueRepository repository = _ImmediateQueueRepository();
    await _pumpScreen(tester, repository, 'lone-row');
    final IntakeTransferSession session = intakeTransferSession(
      repository,
      _scope,
      'lone-row',
    );
    session.entries.add(_readyPhoto('lone'));
    session.changed();
    await tester.pumpAndSettle();
    expect(find.text('lone.jpg'), findsOneWidget);

    await tester.runAsync(session.start);
    expect(session.entries, isEmpty);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // Mid-exit: the row is still drawn, collapsing, and cannot be pressed.
    expect(find.text('Photos'), findsOneWidget);
    expect(find.text('lone.jpg'), findsOneWidget);
    expect(find.text('lone.jpg').hitTestable(), findsNothing);

    await tester.pumpAndSettle();
    expect(find.text('lone.jpg'), findsNothing);
    expect(find.text('Photos'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('with animations off the last row and section go at once', (
    WidgetTester tester,
  ) async {
    final _ImmediateQueueRepository repository = _ImmediateQueueRepository();
    await _pumpScreen(tester, repository, 'lone-still', reduceMotion: true);
    final IntakeTransferSession session = intakeTransferSession(
      repository,
      _scope,
      'lone-still',
    );
    session.entries.add(_readyPhoto('still'));
    session.changed();
    await tester.pump();
    expect(find.text('still.jpg'), findsOneWidget);

    await tester.runAsync(session.start);
    await tester.pump();

    expect(find.text('still.jpg'), findsNothing);
    expect(find.text('Photos'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  test('the move line counts photos plainly', () {
    expect(movedToQueueLine(1), 'Photo moved to the main Queue.');
    expect(movedToQueueLine(3), '3 photos moved to the main Queue.');
  });
}
