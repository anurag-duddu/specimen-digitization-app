import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/screens/intake/stage_progress.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'widgets/harness.dart';

const CollectionScope _scope = CollectionScope(
  organizationId: 'recovery-org',
  collectionId: 'recovery-collection',
  name: 'Recovery fixture',
);
const String _id = 'saved-photo';
const String _detail = '/v1/organizations/recovery-org/specimens/saved-photo';

Json _summary({
  String status = 'processing_blocked',
  String? blocker,
  String? disposition,
  List<String> actions = const <String>['retry'],
  int revision = 2,
}) => <String, dynamic>{
  'specimen_id': _id,
  'organization_id': _scope.organizationId,
  'collection_id': _scope.collectionId,
  'active_run_id': 'same-run',
  'status': status,
  'blocker': blocker,
  'disposition': disposition,
  'available_actions': actions,
  'revision': revision,
};

http.Response _response(Json body, [int status = 200]) =>
    http.Response(jsonEncode(body), status);

ApiSpecimenRepository _repository(
  Future<http.Response> Function(http.Request request) handler,
) => ApiSpecimenRepository(
  baseUrl: Uri.parse('http://localhost:8000'),
  token: () async => 'synthetic-recovery-token',
  client: MockClient(handler),
);

IntakeTransferSession _session(ApiSpecimenRepository repository) {
  final IntakeTransferSession session = IntakeTransferSession(
    repository,
    _scope,
    'recovery-operator',
    processingPollInterval: Duration.zero,
  );
  session.entries.add(
    ManifestEntry.tracking(
      digest: 'a' * 64,
      name: 'saved-photo.jpg',
      handle: <String, dynamic>{'upload_id': 'same-upload'},
      specimenId: _id,
    ),
  );
  return session;
}

Future<void> _pumpRecovery(
  WidgetTester tester,
  IntakeTransferSession session, {
  Size size = const Size(390, 844),
  TargetPlatform platform = TargetPlatform.android,
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
      onRetry: (ManifestEntry entry) => unawaited(session.start(only: entry)),
    ),
  ),
  size: size,
  platform: platform,
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test(
    'polled milestones reach the track and survive a processing hold',
    () async {
      Json current = <String, dynamic>{
        ..._summary(status: 'running'),
        'intake_progress': <String, dynamic>{
          'next_step': 'transcribe',
          'completed_stages': <String>['segment'],
        },
      };
      final repository = _repository((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, _detail);
        return _response(current);
      });
      final session = _session(repository);
      await session.refreshProcessingStatuses();
      var progress = IntakeProgress.of(session.entries.single);
      expect(progress.label, 'Reading the label');
      expect(progress.states[IntakeStage.segment.index], IntakeStageState.done);
      current = <String, dynamic>{
        ...current,
        'status': 'processing_blocked',
        'revision': 3,
      };
      await session.refreshProcessingStatuses();
      progress = IntakeProgress.of(session.entries.single);
      expect(progress.label, 'Needs attention');
      expect(
        progress.states[IntakeStage.read.index],
        IntakeStageState.attention,
      );
      expect(progress.states[IntakeStage.segment.index], IntakeStageState.done);
      session.close();
    },
  );

  test(
    'Intake reads authoritative actions without a workspace or mutation',
    () async {
      final List<String> requests = <String>[];
      final ApiSpecimenRepository repository = _repository((
        http.Request request,
      ) async {
        requests.add('${request.method} ${request.url.path}');
        if (request.url.path.endsWith('/specimens')) {
          return _response(<String, dynamic>{
            'items': <Json>[_summary(actions: <String>[])],
          });
        }
        expect(request.url.path, _detail);
        return _response(_summary());
      });
      final SpecimenPage metadata = await repository.specimenPage(
        _scope,
        filters: <String, String>{'specimen_id': _id},
      );
      expect(metadata.items.single.data['available_actions'], isEmpty);
      final IntakeTransferSession session = _session(repository);

      await session.refreshProcessingStatuses();

      expect(session.canRetryProcessing(session.entries.single), isTrue);
      expect(requests, <String>[
        'GET /v1/organizations/recovery-org/specimens',
        'GET $_detail',
      ]);
      session.close();
      repository.close();
    },
  );

  for (final String field in <String>[
    'specimen_id',
    'organization_id',
    'collection_id',
  ]) {
    test(
      'a status response with the wrong $field cannot offer Retry',
      () async {
        final ApiSpecimenRepository repository = _repository(
          (_) async =>
              _response(<String, dynamic>{..._summary(), field: 'different'}),
        );
        final IntakeTransferSession session = _session(repository);
        await session.refreshProcessingStatuses();
        expect(session.entries.single.specimen, isNull);
        expect(session.canRetryProcessing(session.entries.single), isFalse);
        expect(session.entries.single.specimenId, _id);
        session.close();
        repository.close();
      },
    );
  }

  for (final String dispatch in <String>[
    'requested',
    'failed',
    'unconfigured',
  ]) {
    test('Retry start respects HTTP 202 dispatch $dispatch', () async {
      final List<http.Request> posts = <http.Request>[];
      final Json pending = _summary(
        status: 'pending',
        actions: <String>['start_processing'],
      );
      final ApiSpecimenRepository repository = _repository((
        http.Request request,
      ) async {
        if (request.method == 'POST') {
          posts.add(request);
          expect(request.url.path, '$_detail/process');
          expect(request.body, isEmpty);
          expect(request.headers['Idempotency-Key'], isNotEmpty);
          return _response(<String, dynamic>{
            ...pending,
            'dispatch': <String, dynamic>{'status': dispatch},
          }, 202);
        }
        expect(request.url.path, _detail);
        return _response(pending);
      });
      final IntakeTransferSession session = _session(repository);
      await session.refreshProcessingStatuses();
      final ManifestEntry photograph = session.entries.single;

      await session.start(only: photograph);
      await session.refreshProcessingStatuses();

      expect(posts, hasLength(1));
      expect(photograph.file, isNull);
      expect(photograph.session!['upload_id'], 'same-upload');
      expect(photograph.specimen!.data['active_run_id'], 'same-run');
      expect(photograph.state, UploadState.processing);
      expect(photograph.specimen!.revision, 2);
      expect(
        photograph.reason,
        contains(switch (dispatch) {
          'failed' => 'could not be started',
          'unconfigured' => 'not set up',
          _ => 'Waiting for processing',
        }),
      );
      session.close();
      repository.close();
    });
  }

  for (final bool pending in <bool>[false, true]) {
    test(
      'unconfirmed ${pending ? 'start' : 'retry'} only reads back; it never repeats POST',
      () async {
        var posts = 0;
        var reads = 0;
        final ApiSpecimenRepository repository = _repository((
          http.Request request,
        ) async {
          if (request.method == 'POST') {
            posts++;
            throw http.ClientException('Simulated lost response');
          }
          reads++;
          return _response(
            reads == 1
                ? _summary(
                    status: pending ? 'pending' : 'processing_blocked',
                    actions: <String>[pending ? 'start_processing' : 'retry'],
                  )
                : _summary(status: 'running', actions: <String>[]),
          );
        });
        final IntakeTransferSession session = _session(repository);
        await session.refreshProcessingStatuses();

        await session.start(only: session.entries.single);

        expect(posts, 1);
        expect(session.entries.single.specimen, isNull);
        expect(
          session.entries.single.reason,
          contains('could not be confirmed'),
        );
        expect(session.canRetryProcessing(session.entries.single), isFalse);
        await session.refreshProcessingStatuses();
        expect(posts, 1);
        expect(reads, 2);
        expect(session.entries.single.state, UploadState.processing);
        expect(session.entries.single.specimen!.state, 'running');
        expect(session.entries.single.specimenId, _id);
        session.close();
        repository.close();
      },
    );
  }

  test(
    'status outage removes stale actions and recovery restores them',
    () async {
      var outage = false;
      final List<String> methods = <String>[];
      final ApiSpecimenRepository repository = _repository((
        http.Request request,
      ) async {
        methods.add(request.method);
        return outage
            ? _response(<String, dynamic>{}, 503)
            : _response(_summary());
      });
      final IntakeTransferSession session = _session(repository);
      await session.refreshProcessingStatuses();
      expect(session.canRetryProcessing(session.entries.single), isTrue);
      outage = true;
      await session.refreshProcessingStatuses();
      expect(session.canRetryProcessing(session.entries.single), isFalse);
      expect(
        session.entries.single.reason,
        contains('temporarily unavailable'),
      );
      outage = false;
      await session.refreshProcessingStatuses();
      expect(session.canRetryProcessing(session.entries.single), isTrue);
      expect(methods, everyElement('GET'));
      session.close();
      repository.close();
    },
  );

  for (final bool failure in <bool>[false, true]) {
    test(
      'a late status ${failure ? 'failure' : 'read'} cannot replace a newer Retry acknowledgement',
      () async {
        final Completer<http.Response> lateStatus = Completer<http.Response>();
        var reads = 0;
        var posts = 0;
        final ApiSpecimenRepository repository = _repository((
          http.Request request,
        ) async {
          if (request.method == 'POST') {
            posts++;
            return _response(
              _summary(status: 'running', actions: <String>[], revision: 3),
            );
          }
          reads++;
          return reads == 1 ? _response(_summary()) : lateStatus.future;
        });
        final IntakeTransferSession session = _session(repository);
        await session.refreshProcessingStatuses();
        final Future<void> oldRead = session.refreshProcessingStatuses();
        await Future<void>.delayed(Duration.zero);
        await session.start(only: session.entries.single);
        expect(session.entries.single.specimen!.revision, 3);

        lateStatus.complete(
          failure ? _response(<String, dynamic>{}, 503) : _response(_summary()),
        );
        await oldRead;

        expect(posts, 1);
        expect(session.entries.single.state, UploadState.processing);
        expect(session.entries.single.specimen!.revision, 3);
        expect(session.canRetryProcessing(session.entries.single), isFalse);
        session.close();
        repository.close();
      },
    );
  }

  testWidgets(
    'Retry processing is single-send, visibly busy, and keeps the saved photo',
    (WidgetTester tester) async {
      final Completer<http.Response> reply = Completer<http.Response>();
      final List<http.Request> posts = <http.Request>[];
      Json current = _summary();
      final ApiSpecimenRepository repository = _repository((
        http.Request request,
      ) async {
        if (request.method == 'POST') {
          posts.add(request);
          expect(
            request.url.path,
            '/v1/organizations/recovery-org/runs/same-run/actions',
          );
          expect(jsonDecode(request.body), <String, dynamic>{
            'expected_revision': 2,
            'action': 'retry',
            'reason': 'Retry processing from Intake.',
          });
          return reply.future;
        }
        return _response(current);
      });
      final IntakeTransferSession session = _session(repository);
      await session.refreshProcessingStatuses();
      await _pumpRecovery(tester, session);
      expect(
        find.textContaining('Your photo and completed work are saved.'),
        findsOneWidget,
      );
      await expectAccessible(tester);

      await tester.tap(uiButton('Retry processing'));
      await tester.tap(uiButton('Retry processing'));
      await tester.pump();

      expect(posts, hasLength(1));
      expect(tester.widget<UiButton>(uiButton('Retrying…')).onPressed, isNull);
      expect(find.text('Stop'), findsNothing);
      expect(session.entries.single.session!['upload_id'], 'same-upload');
      expect(session.entries.single.file, isNull);
      current = _summary(status: 'running', actions: <String>[], revision: 3);
      reply.complete(_response(current));
      await tester.pumpAndSettle();
      expect(find.text('Processing is underway.'), findsOneWidget);
      expect(find.text('Retry processing'), findsNothing);
      current = _summary(
        status: 'completed',
        disposition: 'needs_human_review',
        actions: <String>[],
        revision: 4,
      );
      await session.refreshProcessingStatuses();
      await tester.pumpAndSettle();
      expect(find.text('In main Queue'), findsOneWidget);
      expect(posts, hasLength(1));
      await tester.pumpWidget(const SizedBox());
      session.close();
      repository.close();
    },
  );

  testWidgets('a pending saved photo has an explicit Retry start control', (
    WidgetTester tester,
  ) async {
    var posts = 0;
    final Json pending = _summary(
      status: 'pending',
      actions: <String>['start_processing'],
    );
    final ApiSpecimenRepository repository = _repository((
      http.Request request,
    ) async {
      if (request.method == 'POST') {
        posts++;
        return _response(<String, dynamic>{
          ...pending,
          'dispatch': <String, dynamic>{'status': 'failed'},
        }, 202);
      }
      return _response(pending);
    });
    final IntakeTransferSession session = _session(repository);
    await session.refreshProcessingStatuses();
    await _pumpRecovery(tester, session);
    expect(find.text('Retry start'), findsOneWidget);
    expect(posts, 0);
    await tester.tap(uiButton('Retry start'));
    await tester.pumpAndSettle();
    expect(posts, 1);
    expect(
      find.textContaining('Processing could not be started.'),
      findsOneWidget,
    );
    expect(find.text('In main Queue'), findsNothing);
    await tester.pumpWidget(const SizedBox());
    session.close();
    repository.close();
  });

  // A queued photo waits behind the collection's processing (G13); a start
  // cannot move it forward, so the row is calm and offers no Retry start.
  Json inLine({List<String> actions = const <String>['pause', 'cancel']}) =>
      <String, dynamic>{
        ..._summary(status: 'pending', actions: actions),
        'intake_progress': <String, dynamic>{
          'next_step': 'pin_dependencies',
          'completed_stages': <String>[],
          'waiting_in_line': true,
        },
      };

  for (final ({Size size, TargetPlatform platform}) device
      in <({Size size, TargetPlatform platform})>[
        (size: const Size(390, 844), platform: TargetPlatform.android),
        (size: const Size(834, 1194), platform: TargetPlatform.iOS),
      ]) {
    testWidgets(
      'a photo in line reads as queued without Retry start on ${device.platform.name}',
      (WidgetTester tester) async {
        tester.platformDispatcher.accessibilityFeaturesTestValue =
            const FakeAccessibilityFeatures(disableAnimations: true);
        addTearDown(
          tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
        );
        var posts = 0;
        final ApiSpecimenRepository repository = _repository((
          http.Request request,
        ) async {
          if (request.method == 'POST') posts++;
          return _response(inLine());
        });
        final IntakeTransferSession session = _session(repository);
        await session.refreshProcessingStatuses();
        await _pumpRecovery(
          tester,
          session,
          size: device.size,
          platform: device.platform,
        );
        final ManifestEntry photograph = session.entries.single;
        expect(IntakeProgress.of(photograph).label, IntakeProgress.inLine);
        expect(IntakeProgress.rolls(photograph), isFalse);
        expect(find.text(IntakeProgress.inLine), findsOneWidget);
        expect(find.text(intakeInLineReason), findsOneWidget);
        expect(find.text('Retry start'), findsNothing);
        expect(find.textContaining('Retry start asks'), findsNothing);
        expect(find.text('Waiting for processing to start.'), findsNothing);
        expect(find.text('Needs attention'), findsNothing);
        expect(session.canRetryProcessing(photograph), isFalse);
        expect(photograph.state, UploadState.processing);
        expect(tester.takeException(), isNull);
        await expectAccessible(tester);
        expect(posts, 0);
        await tester.pumpWidget(const SizedBox());
        session.close();
        repository.close();
      },
    );
  }

  test('a start offered beside an in-line report is still withheld', () async {
    final ApiSpecimenRepository repository = _repository(
      (_) async => _response(
        inLine(actions: <String>['pause', 'cancel', 'start_processing']),
      ),
    );
    final IntakeTransferSession session = _session(repository);
    await session.refreshProcessingStatuses();
    expect(intakeProcessingRetryAction(session.entries.single), isNull);
    expect(session.entries.single.reason, intakeInLineReason);
    session.close();
    repository.close();
  });

  test(
    'a start that did not go through yields to the line it joined',
    () async {
      final ApiSpecimenRepository repository = _repository((
        http.Request request,
      ) async {
        if (request.method == 'POST') {
          return _response(<String, dynamic>{
            ...inLine(),
            'dispatch': <String, dynamic>{'status': 'failed'},
          }, 202);
        }
        return _response(
          _summary(status: 'pending', actions: <String>['start_processing']),
        );
      });
      final IntakeTransferSession session = _session(repository);
      await session.refreshProcessingStatuses();
      final ManifestEntry photograph = session.entries.single;
      expect(intakeProcessingRetryAction(photograph), 'start_processing');

      await session.start(only: photograph);

      expect(photograph.reason, intakeInLineReason);
      expect(intakeProcessingRetryAction(photograph), isNull);
      session.close();
      repository.close();
    },
  );

  for (final ({String status, String? blocker, String guidance}) hold
      in <({String status, String? blocker, String guidance})>[
        (
          status: 'processing_blocked',
          blocker: 'external_outcome_unknown',
          guidance: 'An administrator must check',
        ),
        (
          status: 'processing_blocked',
          blocker: 'cost_budget_exhausted',
          guidance: 'cost limit',
        ),
        (
          status: 'processing_blocked',
          blocker: 'sensitive_record_not_processed',
          guidance: 'marked sensitive',
        ),
        (
          status: 'paused',
          blocker: null,
          guidance: 'authorized operator can resume',
        ),
        (
          status: 'cancelled',
          blocker: null,
          guidance: 'will not restart automatically',
        ),
        (
          status: 'retry_scheduled',
          blocker: null,
          guidance: 'retry automatically',
        ),
      ]) {
    for (final ({Size size, TargetPlatform platform}) device
        in <({Size size, TargetPlatform platform})>[
          (size: const Size(390, 844), platform: TargetPlatform.android),
          (size: const Size(834, 1194), platform: TargetPlatform.iOS),
        ]) {
      testWidgets(
        '${hold.blocker ?? hold.status} explains its hold without Retry on ${device.platform.name}',
        (WidgetTester tester) async {
          var posts = 0;
          final ApiSpecimenRepository repository = _repository((
            http.Request request,
          ) async {
            if (request.method == 'POST') posts++;
            return _response(
              _summary(status: hold.status, blocker: hold.blocker),
            );
          });
          final IntakeTransferSession session = _session(repository);
          await session.refreshProcessingStatuses();
          await _pumpRecovery(
            tester,
            session,
            size: device.size,
            platform: device.platform,
          );
          expect(find.textContaining(hold.guidance), findsOneWidget);
          expect(find.text('Retry processing'), findsNothing);
          expect(find.text('Retry start'), findsNothing);
          expect(find.text('In main Queue'), findsNothing);
          expect(tester.takeException(), isNull);
          expect(posts, 0);
          await expectAccessible(tester);
          await tester.pumpWidget(const SizedBox());
          session.close();
          repository.close();
        },
      );
    }
  }
}
