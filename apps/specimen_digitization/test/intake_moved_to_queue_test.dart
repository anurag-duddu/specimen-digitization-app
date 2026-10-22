import 'dart:async';
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
  /// When set, an upload waits here, so a test can act mid-upload.
  Completer<void>? gate;

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
  ) async {
    await gate?.future;
    progress(1);
  }

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
    'handed-off photos leave the list and polling; only unsent rows stay',
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
        'ready.jpg',
        'failed.jpg',
      ]);
      expect(session.entries.map((ManifestEntry e) => e.state), <UploadState>[
        UploadState.ready,
        UploadState.failed,
      ]);
      expect(handoffs, 1, reason: 'the main Queue still refreshes once');
      expect(session.movedToQueue, 4);
      expect(await _savedSpecimens('moved-operator'), isEmpty);
      expect(session.needsProcessingPoll, isFalse);
      expect(ingestionQueueLine(session.entries), '1 to fix · 1 ready');

      // A second check of the same server state moves nothing again.
      await session.refreshProcessingStatuses();
      expect(session.movedToQueue, 4);
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
        'still-running': _summary('still-running', status: 'pending'),
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
          blocker: 'sensitive_record_not_processed',
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
          'first': _summary('first', status: 'pending'),
          'second': _summary('second', status: 'pending'),
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
        expect(find.text('2 sending'), findsOneWidget);

        // The operator is reading the first row's details control.
        final Finder firstDetails = find.descendant(
          of: find.byKey(ValueKey<String>(_digest('first'))),
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

        summaries['first'] = _summary('first', status: 'running', revision: 3);
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
        expect(find.textContaining('1 sending'), findsOneWidget);
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

  testWidgets(
    'the Intake screen announces a move once and retains the completion',
    (WidgetTester tester) async {
      SharedPreferences.setMockInitialValues(
        _saved('owner', <String, String>{'tracked': 'processing'}),
      );
      final Map<String, Json> summaries = <String, Json>{
        'tracked': _summary('tracked', status: 'pending'),
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
      expect(find.text('Saved photo'), findsOneWidget);
      expect(announced, isEmpty);

      summaries['tracked'] = _summary(
        'tracked',
        status: 'running',
        revision: 3,
      );
      final IntakeTransferSession session = intakeTransferSession(
        repository,
        _scope,
        'owner',
      );
      await tester.runAsync(session.refreshProcessingStatuses);
      await tester.pumpAndSettle();

      expect(find.text('Photos'), findsOneWidget);
      expect(session.entries, isEmpty);
      expect(await _savedSpecimens('owner'), isEmpty);
      expect(announced, <String>['1 photo sent']);
      expect(completions, 1, reason: 'the main Queue refreshes for the move');

      // Later frames and checks do not repeat it.
      await tester.runAsync(session.refreshProcessingStatuses);
      await tester.pumpAndSettle();
      expect(announced, <String>['1 photo sent']);
      semantics.dispose();
      await tester.pumpWidget(const SizedBox());
    },
  );

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

    expect(announced, <String>['2 photos sent']);
    expect(find.text('first.jpg'), findsNothing);
    expect(find.text('second.jpg'), findsNothing);
    semantics.dispose();
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the last row collapses while completion stays visible', (
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
    expect(find.text('Photos'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('with animations off the last row leaves and completion stays', (
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
    expect(find.text('Photos'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  for (final bool reduceMotion in <bool>[false, true]) {
    testWidgets('focus in the last row ends on the completion summary'
        '${reduceMotion ? ' with animations off' : ''}', (
      WidgetTester tester,
    ) async {
      final _ImmediateQueueRepository repository = _ImmediateQueueRepository();
      final String user = 'focused-last-$reduceMotion';
      await _pumpScreen(tester, repository, user, reduceMotion: reduceMotion);
      final IntakeTransferSession session = intakeTransferSession(
        repository,
        _scope,
        user,
      );
      session.entries.add(_readyPhoto('focused'));
      session.changed();
      await tester.pumpAndSettle();

      // The operator is reading the only row's details control.
      final Finder details = find.descendant(
        of: find.byKey(ValueKey<String>(_digest('focused'))),
        matching: find.byWidgetPredicate(
          (Widget w) => w is Focus || w is FocusableActionDetector,
        ),
      );
      expect(details, findsWidgets);
      final FocusNode rowNode = Focus.of(tester.element(details.first));
      rowNode.requestFocus();
      await tester.pump();
      expect(rowNode.hasFocus, isTrue);

      await tester.runAsync(session.start);
      expect(session.entries, isEmpty);
      await tester.pump();
      await tester.pump();
      if (!reduceMotion) {
        // Mid-exit, focus already rests on the persistent summary.
        expect(find.text('Photos'), findsOneWidget);
        expect(
          FocusManager.instance.primaryFocus?.debugLabel,
          'Intake manifest summary',
        );
      }
      await tester.pumpAndSettle();

      expect(find.text('Photos'), findsOneWidget);
      final FocusNode? focused = FocusManager.instance.primaryFocus;
      expect(focused?.debugLabel, 'Intake manifest summary');
      expect(focused?.context, isNotNull, reason: 'focus is not left nowhere');
      await tester.pumpWidget(const SizedBox());
    });
  }

  for (final bool reduceMotion in <bool>[false, true]) {
    testWidgets(
      'focus on Stop ends on the completion summary when the upload is queued'
      '${reduceMotion ? ' with animations off' : ''}',
      (WidgetTester tester) async {
        final _ImmediateQueueRepository repository = _ImmediateQueueRepository()
          ..gate = Completer<void>();
        final String user = 'stop-focus-$reduceMotion';
        await _pumpScreen(tester, repository, user, reduceMotion: reduceMotion);
        final IntakeTransferSession session = intakeTransferSession(
          repository,
          _scope,
          user,
        );
        session.entries.add(_readyPhoto('sending'));
        session.changed();
        await tester.pump();

        late Future<void> run;
        await tester.runAsync(() async {
          run = session.start();
          await Future<void>.delayed(const Duration(milliseconds: 20));
        });
        await tester.pump();
        await tester.pump();

        // The operator has moved to the header's Stop button.
        final Finder stop = find.byKey(const ValueKey<String>('intake-stop'));
        expect(stop, findsOneWidget);
        final FocusNode stopNode = Focus.of(
          tester.element(
            find
                .descendant(of: stop, matching: find.text('Stop sending'))
                .first,
          ),
        );
        stopNode.requestFocus();
        await tester.pump();
        expect(stopNode.hasFocus, isTrue);

        await tester.runAsync(() async {
          repository.gate!.complete();
          await run;
        });
        expect(session.entries, isEmpty);
        await tester.pump();
        await tester.pump();
        expect(
          FocusManager.instance.primaryFocus?.debugLabel,
          'Intake manifest summary',
        );

        await tester.pumpAndSettle();
        expect(find.text('Photos'), findsOneWidget);
        final FocusNode? focused = FocusManager.instance.primaryFocus;
        expect(focused?.debugLabel, 'Intake manifest summary');
        expect(focused?.context, isNotNull);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }

  test('the move line counts photos plainly', () {
    expect(movedToQueueLine(1), '1 photo sent');
    expect(movedToQueueLine(3), '3 photos sent');
  });
}
