import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

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
import 'package:specimen_digitization/src/screens/intake/intake_status.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';

import 'widgets/harness.dart';

const CollectionScope _scope = CollectionScope(
  organizationId: 'recovery-org',
  collectionId: 'recovery-collection',
  name: 'Recovery fixture',
);
const String _id = 'saved-photo';
const String _detail = '/v1/organizations/recovery-org/specimens/saved-photo';

Json _summary({
  String status = 'pending',
  String? blocker,
  String? disposition,
  List<String> actions = const <String>['start_processing'],
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

class StartRepository
    implements SpecimenRepository, IntakeProcessingRepository {
  Json current = _summary();
  String dispatch = 'requested';
  final List<String> keys = [];
  int reads = 0;
  Object? startError;
  Completer<Specimen>? pendingRead;
  final List<bool> persistedAttempts = [];

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => {'upload_id': 'same-upload', 'state': 'ready'};
  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async => {
    'upload_id': id,
    'state': 'ready',
  };
  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) onProgress,
  ) async => onProgress(1);
  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => current;
  @override
  Future<Specimen> intakeProcessingStatus(
    CollectionScope scope,
    String id,
  ) async {
    reads++;
    return pendingRead?.future ?? Specimen(current);
  }

  @override
  Future<Json> startIntakeProcessing(
    CollectionScope scope,
    Specimen specimen,
    String key,
  ) async {
    keys.add(key);
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final List<dynamic> rows =
        jsonDecode(
              prefs.getString('upload-handles-v1:auto:${_scope.key}') ?? '[]',
            )
            as List<dynamic>;
    persistedAttempts.add(
      rows.isNotEmpty && rows.first['automatic_start_attempted'] == true,
    );
    if (startError != null) throw startError!;
    return {
      ...current,
      'dispatch': {'status': dispatch},
    };
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

IntakeTransferSession automaticSession(
  StartRepository repository, {
  Duration delay = const Duration(seconds: 60),
}) {
  final IntakeTransferSession session = IntakeTransferSession(
    repository,
    _scope,
    'auto',
    processingPollInterval: Duration.zero,
    automaticStartDelay: delay,
  );
  session.entries.add(
    ManifestEntry(
      digest: 'a' * 64,
      name: 'photo.jpg',
      state: UploadState.ready,
      file: IntakeFile(
        name: 'photo.jpg',
        bytes: Uint8List.fromList([1, 2, 3]),
        mimeType: 'image/jpeg',
        sha256: 'a' * 64,
        method: 'camera',
        sensitive: false,
      ),
    ),
  );
  return session;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets(
    'pending saved photo starts once at 60 seconds with no early button',
    (tester) async {
      final StartRepository repository = StartRepository();
      final IntakeTransferSession session = automaticSession(repository);
      await session.start();
      final ManifestEntry photograph = session.entries.single;
      expect(photograph.file, isNull);
      await pumpComponent(
        tester,
        AnimatedBuilder(
          animation: session,
          builder: (context, child) => IntakeManifest(
            entries: session.entries,
            busy: session.busy,
            stopping: session.stopping,
            onStop: session.stop,
            onRemove: session.remove,
            onServerCheck: (_) {},
            onRetry: (entry) => unawaited(session.start(only: entry)),
          ),
        ),
      );
      expect(find.text('Retry start'), findsNothing);
      expect(intakeStatus(photograph).action, isNull);
      await tester.pump(const Duration(seconds: 59));
      expect(repository.keys, isEmpty);
      await tester.pump(const Duration(seconds: 1));
      expect(repository.keys, ['intake-start-${photograph.digest}-2']);
      expect(repository.persistedAttempts, [true]);
      expect(intakeStatus(photograph).status, 'Starting');
      await session.refreshProcessingStatuses();
      await tester.pump(const Duration(minutes: 3));
      expect(repository.keys, hasLength(1));
      await tester.pumpWidget(const SizedBox());
      session.close();
    },
  );

  for (final String dispatch in ['requested', 'failed', 'unconfigured']) {
    testWidgets(
      'automatic start maps reported dispatch $dispatch and never repeats',
      (tester) async {
        final StartRepository repository = StartRepository()
          ..dispatch = dispatch;
        final IntakeTransferSession session = automaticSession(
          repository,
          delay: const Duration(seconds: 2),
        );
        await session.start();
        final ManifestEntry photograph = session.entries.single;
        await tester.pump(const Duration(seconds: 1));
        expect(repository.keys, isEmpty);
        expect(session.canRetryProcessing(photograph), isFalse);
        await tester.pump(const Duration(seconds: 1));
        expect(repository.keys, hasLength(1));
        await session.refreshProcessingStatuses();
        final IntakeStatus status = intakeStatus(photograph);
        expect(
          status.status,
          dispatch == 'requested' ? 'Starting' : 'Not started',
        );
        expect(status.reason, switch (dispatch) {
          'failed' => 'Processing did not start. Photo saved.',
          'unconfigured' => 'Not set up for processing. Ask an admin.',
          _ => null,
        });
        expect(status.action, switch (dispatch) {
          'failed' => IntakeAction.start,
          'unconfigured' => IntakeAction.dismiss,
          _ => null,
        });
        await tester.pump(const Duration(minutes: 3));
        expect(repository.keys, hasLength(1));
        if (dispatch == 'unconfigured') {
          session.remove(photograph);
          expect(session.entries, isEmpty);
        }
        session.close();
      },
    );
  }

  testWidgets('failed start permits one manual Start with the existing key', (
    tester,
  ) async {
    final StartRepository repository = StartRepository()..dispatch = 'failed';
    final IntakeTransferSession session = automaticSession(repository);
    await session.start();
    final ManifestEntry photograph = session.entries.single;
    await tester.pump(const Duration(seconds: 60));
    repository.current = _summary(status: 'running');
    repository.dispatch = 'requested';
    await session.start(only: photograph);
    expect(repository.keys, [
      'intake-start-${photograph.digest}-2',
      'intake-start-${photograph.digest}-2',
    ]);
    expect(session.entries, isEmpty);
    expect(session.sentCount, 1);
    expect(session.needsProcessingPoll, isFalse);
    session.close();
  });

  testWidgets(
    'unconfirmed start reads status without inventing failure or repeating start',
    (tester) async {
      final StartRepository repository = StartRepository()
        ..startError = const ApiFailure('lost', code: 'network');
      final IntakeTransferSession session = automaticSession(repository);
      await session.start();
      final ManifestEntry photograph = session.entries.single;
      await tester.pump(const Duration(seconds: 60));
      expect(photograph.specimen, isNull);
      expect(intakeStatus(photograph).status, 'Starting');
      expect(session.canRetryProcessing(photograph), isFalse);
      await session.refreshProcessingStatuses();
      await tester.pump(const Duration(seconds: 120));
      expect(repository.keys, hasLength(1));
      repository.current = _summary(status: 'running');
      await session.refreshProcessingStatuses();
      expect(session.entries, isEmpty);
      session.close();
    },
  );

  testWidgets(
    'in-line and running summaries cancel a pending automatic start',
    (tester) async {
      for (final bool inLine in [true, false]) {
        final StartRepository repository = StartRepository();
        final IntakeTransferSession session = automaticSession(repository);
        await session.start();
        repository.current = inLine
            ? {
                ..._summary(),
                'intake_progress': {'waiting_in_line': true},
              }
            : _summary(status: 'running');
        await session.refreshProcessingStatuses();
        expect(session.entries, isEmpty);
        expect(session.needsProcessingPoll, isFalse);
        await tester.pump(const Duration(minutes: 3));
        expect(repository.keys, isEmpty);
        expect(session.sentCount, 1);
        session.close();
      }
    },
  );

  testWidgets(
    'start waits for a server offer and foreground without resetting the delay',
    (tester) async {
      final StartRepository repository = StartRepository()
        ..current = _summary(actions: []);
      final IntakeTransferSession session = automaticSession(repository);
      await session.start();
      await tester.pump(const Duration(seconds: 60));
      expect(repository.keys, isEmpty);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      repository.current = _summary();
      await tester.pump(const Duration(seconds: 60));
      expect(repository.keys, isEmpty);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await session.refreshProcessingStatuses();
      await tester.pump();
      expect(repository.keys, hasLength(1));
      session.close();
    },
  );

  testWidgets('restoring an attempted automatic start cannot submit it again', (
    tester,
  ) async {
    final StartRepository repository = StartRepository();
    final IntakeTransferSession first = automaticSession(repository);
    await first.start();
    await tester.pump(const Duration(seconds: 60));
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String stored = prefs.getString(
      'upload-handles-v1:auto:${_scope.key}',
    )!;
    first.close();
    await tester.pump();
    SharedPreferences.setMockInitialValues({
      'upload-handles-v1:auto:${_scope.key}': stored,
    });
    final IntakeTransferSession restored = IntakeTransferSession(
      repository,
      _scope,
      'auto',
      processingPollInterval: Duration.zero,
    );
    await restored.restore();
    await tester.pump(const Duration(minutes: 3));
    expect(repository.keys, hasLength(1));
    expect(restored.entries.single.automaticStartAttempted, isTrue);
    expect(restored.entries.single.file, isNull);
    restored.close();
  });

  for (final bool failure in [false, true]) {
    testWidgets(
      'a late status ${failure ? 'failure' : 'read'} cannot undo a newer start hand-off',
      (tester) async {
        final StartRepository repository = StartRepository()
          ..dispatch = 'failed';
        final IntakeTransferSession session = automaticSession(repository);
        await session.start();
        await tester.pump(const Duration(seconds: 60));
        final ManifestEntry photograph = session.entries.single;
        final Completer<Specimen> pending = Completer<Specimen>();
        repository.pendingRead = pending;
        final Future<void> oldRead = session.refreshProcessingStatuses();
        repository.current = _summary(status: 'running', revision: 3);
        repository.dispatch = 'requested';
        await session.start(only: photograph);
        expect(session.entries, isEmpty);
        if (failure) {
          pending.completeError(const ApiFailure('outage', status: 503));
        } else {
          pending.complete(Specimen(_summary()));
        }
        await oldRead;
        expect(session.entries, isEmpty);
        expect(photograph.specimen!.revision, 3);
        expect(session.sentCount, 1);
        session.close();
      },
    );
  }

  for (final String blocker in [
    'sensitive_record_not_processed',
    'collection_processing_unconfigured',
    'program_allowance_unavailable',
  ]) {
    testWidgets('$blocker stays visible without start or pipeline retry', (
      tester,
    ) async {
      final StartRepository repository = StartRepository()
        ..current = _summary(
          status: 'processing_blocked',
          blocker: blocker,
          actions: ['retry'],
        );
      final IntakeTransferSession session = automaticSession(repository);
      await session.start();
      final ManifestEntry photograph = session.entries.single;
      expect(
        intakeStatus(photograph).status,
        blocker == 'sensitive_record_not_processed' ? 'Held' : 'Not started',
      );
      expect(session.canRetryProcessing(photograph), isFalse);
      expect(session.needsProcessingPoll, isTrue);
      await tester.pump(const Duration(seconds: 120));
      expect(repository.keys, isEmpty);
      expect(session.entries, [photograph]);
      session.close();
    });
  }

  for (final String field in [
    'specimen_id',
    'organization_id',
    'collection_id',
  ]) {
    test(
      'a status response with the wrong $field cannot start or claim hand-off',
      () async {
        final ApiSpecimenRepository repository = _repository(
          (_) async =>
              _response({..._summary(status: 'running'), field: 'different'}),
        );
        final IntakeTransferSession session = _session(repository);
        await session.refreshProcessingStatuses();
        expect(session.entries.single.specimen, isNull);
        expect(session.canRetryProcessing(session.entries.single), isFalse);
        expect(session.entries.single.specimenId, _id);
        expect(session.movedToQueue, 0);
        session.close();
        repository.close();
      },
    );
  }

  testWidgets(
    'automatic start uses the existing scoped HTTP route and idempotency key',
    (tester) async {
      final List<http.Request> posts = [];
      final ApiSpecimenRepository repository = _repository((request) async {
        if (request.method == 'POST') {
          posts.add(request);
          return _response({
            ..._summary(),
            'dispatch': {'status': 'failed'},
          }, 202);
        }
        expect(request.url.path, _detail);
        return _response(_summary());
      });
      final IntakeTransferSession session = _session(repository);
      await session.refreshProcessingStatuses();
      expect(session.canRetryProcessing(session.entries.single), isFalse);
      await tester.pump(const Duration(seconds: 60));
      expect(posts, hasLength(1));
      expect(posts.single.url.path, '$_detail/process');
      expect(posts.single.body, isEmpty);
      expect(
        posts.single.headers['Idempotency-Key'],
        'intake-start-${'a' * 64}-2',
      );
      expect(
        intakeStatus(session.entries.single).reason,
        'Processing did not start. Photo saved.',
      );
      session.close();
      repository.close();
    },
  );
  testWidgets(
    'a hand-off refusal leaves when the server later reports recovery',
    (tester) async {
      final StartRepository repository = StartRepository()
        ..current = _summary(
          status: 'processing_blocked',
          blocker: 'collection_processing_unconfigured',
        );
      final IntakeTransferSession session = automaticSession(repository);
      await session.start();
      expect(intakeStatus(session.entries.single).status, 'Not started');
      repository.current = _summary(status: 'running', revision: 3);
      await session.refreshProcessingStatuses();
      expect(session.entries, isEmpty);
      expect(session.needsProcessingPoll, isFalse);
      expect(session.sentCount, 1);
      expect(repository.keys, isEmpty);
      session.close();
    },
  );
}
