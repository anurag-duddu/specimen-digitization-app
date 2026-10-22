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
  Completer<Json>? pendingCompletion;
  Completer<Json>? pendingStart;
  int completions = 0;
  Object? readError;
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
  ) async {
    completions++;
    return pendingCompletion?.future ?? current;
  }

  @override
  Future<Specimen> intakeProcessingStatus(
    CollectionScope scope,
    String id,
  ) async {
    reads++;
    if (readError != null) throw readError!;
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
    if (pendingStart != null) return pendingStart!.future;
    return {
      ...current,
      'dispatch': {'status': dispatch},
    };
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class LostCompletionRepository extends StartRepository {
  LostCompletionRepository(this.recorded);

  final Json recorded;
  bool committed = false;
  int uploads = 0;
  int resumes = 0;

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async {
    resumes++;
    // GET /uploads/{id} returns the accepted document and its stored summary.
    return {
      'upload_id': id,
      'state': committed ? 'accepted' : 'uploading',
      'offset': 3,
      'revision': committed ? 3 : 2,
      'specimen_id': _id,
      if (committed) 'completion_response': recorded,
    };
  }

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) onProgress,
  ) async {
    uploads++;
    onProgress(1);
  }

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    completions++;
    if (committed) {
      throw const ApiFailure('Completion payload changed.', status: 409);
    }
    committed = true;
    throw const ApiFailure('Response lost after commit.', code: 'network');
  }
}

class AcceptedHandleRepository extends StartRepository {
  AcceptedHandleRepository(this.source);

  final String source;
  final Completer<Json> handle = Completer<Json>();
  int uploads = 0;

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) =>
      source == 'create' ? handle.future : super.createIntake(scope, file, key);

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) => handle.future;

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) onProgress,
  ) async {
    uploads++;
    onProgress(1);
  }
}

class CompletionConflictRepository extends LostCompletionRepository {
  CompletionConflictRepository(super.recorded, {this.accepted = true});

  final bool accepted;

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    completions++;
    // Acceptance becomes visible only after this session's last handle read.
    committed = accepted;
    throw const ApiFailure('Completion payload changed.', status: 409);
  }
}

class LateCompletionRepository extends LostCompletionRepository {
  LateCompletionRepository(super.recorded);

  final Completer<void> retryReply = Completer<void>();

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    completions++;
    if (completions == 2) await retryReply.future;
    throw const ApiFailure('Completion response lost.', code: 'network');
  }
}

class FailingPreferences implements SharedPreferences {
  FailingPreferences(this.delegate);

  final SharedPreferences delegate;
  bool failNextWrite = false;
  int failedWrites = 0;

  @override
  Future<bool> setString(String key, String value) async {
    if (failNextWrite) {
      failNextWrite = false;
      failedWrites++;
      return false;
    }
    return delegate.setString(key, value);
  }

  @override
  String? getString(String key) => delegate.getString(key);

  @override
  Future<void> reload() => delegate.reload();

  @override
  Future<bool> remove(String key) => delegate.remove(key);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

IntakeTransferSession automaticSession(
  StartRepository repository, {
  Duration delay = const Duration(seconds: 60),
  Duration pollInterval = Duration.zero,
  Future<void> Function()? beforePersist,
  SharedPreferences? preferences,
}) {
  final IntakeTransferSession session = IntakeTransferSession(
    repository,
    _scope,
    'auto',
    processingPollInterval: pollInterval,
    automaticStartDelay: delay,
    beforePersist: beforePersist,
    preferences: preferences,
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

  for (final String status in ['running', 'pending']) {
    testWidgets('H1 completion conflict reconciles accepted $status', (
      tester,
    ) async {
      final CompletionConflictRepository repository =
          CompletionConflictRepository(_summary(status: status));
      final IntakeTransferSession session = automaticSession(repository);
      addTearDown(session.close);
      final ManifestEntry photo = session.entries.single;
      await session.start();
      await tester.pump();
      expect(
        intakeStatus(photo).status,
        status == 'running' ? 'Sent' : 'Starting',
      );
      expect(photo.file, isNull);
      expect(repository.resumes, 2);
      expect(repository.uploads, 1);
      expect(repository.completions, 1);
      expect(session.needsProcessingPoll, status == 'pending');
      if (status == 'running') {
        expect(session.entries, isEmpty);
        expect(session.sentCount, 1);
        final SharedPreferences prefs = await SharedPreferences.getInstance();
        expect(
          jsonDecode(prefs.getString('upload-handles-v1:auto:${_scope.key}')!),
          isEmpty,
        );
      } else {
        expect(session.entries, [photo]);
        expect(repository.reads, 1);
      }
      await tester.pump(const Duration(seconds: 120));
      expect(repository.completions, 1);
      expect(repository.uploads, 1);
    });
  }

  testWidgets('H1 unexplained completion conflict stays Not sent', (
    tester,
  ) async {
    final CompletionConflictRepository repository =
        CompletionConflictRepository(
          _summary(status: 'running'),
          accepted: false,
        );
    final IntakeTransferSession session = automaticSession(repository);
    addTearDown(session.close);
    final ManifestEntry photo = session.entries.single;
    await session.start();
    expect(intakeStatus(photo).status, 'Not sent');
    expect(intakeStatus(photo).action, IntakeAction.remove);
    expect(photo.file, isNotNull);
    expect(session.needsProcessingPoll, isFalse);
    expect(repository.resumes, 2);
    await tester.pump(const Duration(seconds: 120));
    expect(repository.completions, 1);
    expect(repository.uploads, 1);
    expect(session.entries, [photo]);
    expect(session.sentCount, 0);
  });

  testWidgets('H1 late commit after retry read recovers on a later retry', (
    tester,
  ) async {
    final LateCompletionRepository repository = LateCompletionRepository(
      _summary(status: 'running'),
    );
    final IntakeTransferSession session = automaticSession(repository);
    addTearDown(session.close);
    final ManifestEntry photo = session.entries.single;
    await session.start();
    expect(intakeStatus(photo).status, 'Retrying');
    expect(repository.committed, isFalse);
    await tester.pump(const Duration(seconds: 5));
    expect(repository.completions, 2);
    expect(repository.resumes, 3);
    expect(repository.committed, isFalse);
    // The original server operation commits after both reads by this retry.
    // Its pending completion response is also lost; the next retry must recover.
    repository.committed = true;
    repository.retryReply.complete();
    await tester.pump();
    expect(intakeStatus(photo).status, 'Retrying');
    await tester.pump(const Duration(seconds: 14));
    expect(repository.resumes, 3);
    await tester.pump(const Duration(seconds: 1));
    expect(intakeStatus(photo).status, 'Sent');
    expect(session.entries, isEmpty);
    expect(session.sentCount, 1);
    expect(session.needsProcessingPoll, isFalse);
    expect(photo.file, isNull);
    expect(repository.resumes, 4);
    expect(repository.completions, 2);
    expect(repository.uploads, 2);
    await tester.pump(const Duration(seconds: 120));
    expect(repository.completions, 2);
  });

  for (final String opportunity in ['read', 'foreground']) {
    testWidgets('H2 failed attempt write waits for next $opportunity', (
      tester,
    ) async {
      final FailingPreferences prefs = FailingPreferences(
        await SharedPreferences.getInstance(),
      );
      final StartRepository repository = StartRepository();
      final IntakeTransferSession session = automaticSession(
        repository,
        preferences: prefs,
      );
      addTearDown(() {
        session.close();
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
      });
      await session.start();
      final ManifestEntry photo = session.entries.single;
      prefs.failNextWrite = true;
      await tester.pump(const Duration(seconds: 60));
      expect(repository.keys, isEmpty);
      expect(prefs.failedWrites, 1);
      expect(photo.automaticStartAttempted, isFalse);
      expect(session.busy, isFalse);
      await prefs.reload();
      final List<dynamic> rows =
          jsonDecode(prefs.getString('upload-handles-v1:auto:${_scope.key}')!)
              as List<dynamic>;
      expect(rows.single['automatic_start_attempted'], isFalse);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(repository.keys, isEmpty);
      expect(prefs.failedWrites, 1);
      // Keep the re-armed timer overdue without depending on wall-clock time.
      photo.savedAt = DateTime.utc(2000);
      if (opportunity == 'read') {
        await session.refreshProcessingStatuses();
      } else {
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
      }
      await tester.pump();
      await tester.pump(Duration.zero);
      expect(repository.keys, hasLength(1));
      expect(repository.persistedAttempts, [true]);
      expect(photo.automaticStartAttempted, isTrue);
      await session.refreshProcessingStatuses();
      await tester.pump(const Duration(seconds: 120));
      expect(repository.keys, hasLength(1));
    });
  }

  testWidgets('H2 ordinary failed write does not throw from persist', (
    tester,
  ) async {
    final FailingPreferences prefs = FailingPreferences(
      await SharedPreferences.getInstance(),
    );
    final IntakeTransferSession session = automaticSession(
      StartRepository(),
      preferences: prefs,
    );
    try {
      await session.start();
      prefs.failNextWrite = true;
      await expectLater(session.persist(), completes);
      expect(prefs.failedWrites, 1);
      expect(session.entries.single.automaticStartAttempted, isFalse);
    } finally {
      session.close();
    }
  });

  for (final String result in ['running', 'pending', 'duplicate', 'legacy']) {
    testWidgets(
      'G2 lost completion recovers $result without completing twice',
      (tester) async {
        final Json recorded = switch (result) {
          'duplicate' => {..._summary(), 'upload_state': 'duplicate'},
          'legacy' => <String, dynamic>{'status': 'pending'},
          _ => _summary(status: result),
        };
        final LostCompletionRepository repository = LostCompletionRepository(
          recorded,
        )..current = _summary();
        final IntakeTransferSession session = automaticSession(repository);
        addTearDown(session.close);
        final ManifestEntry photo = session.entries.single;
        await session.start();
        expect(intakeStatus(photo).status, 'Retrying');
        expect(repository.completions, 1);
        await tester.pump(const Duration(seconds: 4));
        expect(repository.resumes, 1);
        await tester.pump(const Duration(seconds: 1));
        expect(repository.completions, 1);
        expect(repository.uploads, 1);
        expect(repository.resumes, 2);
        expect(photo.file, isNull);
        expect(intakeStatus(photo).status, switch (result) {
          'running' => 'Sent',
          'duplicate' => 'Duplicate',
          'legacy' => 'Saved',
          _ => 'Starting',
        });
        if (result == 'running' || result == 'duplicate') {
          expect(session.entries, isEmpty);
          expect(session.sentCount, result == 'running' ? 1 : 0);
          expect(session.duplicateCount, result == 'duplicate' ? 1 : 0);
          expect(session.needsProcessingPoll, isFalse);
          final SharedPreferences prefs = await SharedPreferences.getInstance();
          expect(
            jsonDecode(
              prefs.getString('upload-handles-v1:auto:${_scope.key}')!,
            ),
            isEmpty,
          );
        } else if (result == 'pending') {
          expect(repository.reads, 1);
          expect(session.needsProcessingPoll, isTrue);
          await tester.pump(const Duration(seconds: 60));
          expect(repository.keys, hasLength(1));
        } else {
          expect(intakeStatus(photo).action, IntakeAction.dismiss);
          expect(session.needsProcessingPoll, isFalse);
        }
        await tester.pump(const Duration(seconds: 120));
        expect(repository.completions, 1);
      },
    );
  }

  for (final bool readCrossesBackground in [false, true]) {
    testWidgets(
      'G3 in-flight completion refreshes without listeners (read crosses background=$readCrossesBackground)',
      (tester) async {
        final Completer<Json> completion = Completer<Json>();
        final Completer<Specimen> freshRead = Completer<Specimen>();
        final StartRepository repository = StartRepository()
          ..pendingCompletion = completion
          ..pendingRead = freshRead;
        final IntakeTransferSession session = automaticSession(repository);
        addTearDown(() {
          session.close();
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.resumed,
          );
        });
        int notifications = 0;
        void listener() => notifications++;
        session.addListener(listener);
        final ManifestEntry photo = session.entries.single;
        final Future<void> sending = session.start();
        await tester.pump();
        expect(repository.completions, 1);
        session.removeListener(listener);
        final int notificationsBeforeRemoval = notifications;
        session.changed();
        expect(notifications, notificationsBeforeRemoval);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        await tester.pump(const Duration(seconds: 61));
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        expect(repository.reads, 0);
        completion.complete(_summary());
        await sending;
        await tester.pump();
        expect(intakeStatus(photo).status, 'Starting');
        expect(repository.reads, 1);
        expect(photo.startOfferCurrent, isFalse);
        await tester.pump(const Duration(seconds: 61));
        expect(repository.keys, isEmpty);
        if (readCrossesBackground) {
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.paused,
          );
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.resumed,
          );
          repository.pendingRead = null;
          repository.current = _summary(status: 'running');
          freshRead.complete(Specimen(_summary()));
        } else {
          freshRead.complete(Specimen(_summary(status: 'running')));
        }
        await tester.pump();
        expect(repository.reads, readCrossesBackground ? 2 : 1);
        expect(repository.keys, isEmpty);
        expect(session.entries, isEmpty);
        expect(session.summary, '1 sent');
      },
    );
  }

  for (final String source in ['create', 'resume', 'post-upload resume']) {
    testWidgets(
      'G3 accepted $source refreshes after resume without listeners',
      (tester) async {
        final AcceptedHandleRepository repository = AcceptedHandleRepository(
          source,
        );
        final IntakeTransferSession session = automaticSession(repository);
        addTearDown(() {
          session.close();
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.resumed,
          );
        });
        if (source == 'resume') {
          session.entries.single.session = {'upload_id': 'same-upload'};
        }
        final Future<void> sending = session.start();
        await tester.pump();
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        repository.current = _summary(status: 'running');
        repository.handle.complete({
          'upload_id': 'same-upload',
          'state': 'accepted',
          'specimen_id': _id,
          'completion_response': _summary(),
        });
        await sending;
        await tester.pump();
        expect(repository.completions, 0);
        expect(repository.uploads, source == 'post-upload resume' ? 1 : 0);
        expect(repository.reads, 1);
        expect(repository.keys, isEmpty);
        expect(session.entries, isEmpty);
        expect(session.summary, '1 sent');
      },
    );
  }

  testWidgets('G3 in-flight start refreshes after resume without listeners', (
    tester,
  ) async {
    final Completer<Json> reply = Completer<Json>();
    final StartRepository repository = StartRepository()..pendingStart = reply;
    final IntakeTransferSession session = automaticSession(repository);
    addTearDown(() {
      session.close();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    });
    await session.start();
    await tester.pump(const Duration(seconds: 60));
    expect(repository.keys, hasLength(1));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    repository.current = _summary(status: 'running');
    reply.complete({
      ..._summary(),
      'dispatch': {'status': 'failed'},
    });
    await tester.pump();
    expect(repository.reads, 1);
    expect(repository.keys, hasLength(1));
    expect(session.entries, isEmpty);
    expect(session.summary, '1 sent');
  });

  testWidgets('G4 Stop during a start allows Start after a failed reply', (
    tester,
  ) async {
    final Completer<Json> reply = Completer<Json>();
    final StartRepository repository = StartRepository()..pendingStart = reply;
    final IntakeTransferSession session = automaticSession(repository);
    addTearDown(session.close);
    await session.start();
    final ManifestEntry photo = session.entries.single;
    await tester.pump(const Duration(seconds: 60));
    expect(repository.keys, hasLength(1));
    expect(session.busy, isTrue);
    session.stop();
    expect(session.stopping, isTrue);
    reply.complete({
      ..._summary(),
      'dispatch': {'status': 'failed'},
    });
    await tester.pump();
    expect(session.busy, isFalse);
    expect(intakeStatus(photo).action, IntakeAction.start);
    repository.pendingStart = null;
    await session.retryProcessing(photo);
    expect(repository.keys, hasLength(2));
    expect(session.stopping, isFalse);
  });

  for (final bool manual in [false, true]) {
    testWidgets(
      'G4 idle Stop does not block ${manual ? 'manual' : 'automatic'} Start',
      (tester) async {
        final StartRepository repository = StartRepository()
          ..dispatch = 'failed';
        final IntakeTransferSession session = automaticSession(repository);
        addTearDown(session.close);
        await session.start();
        final ManifestEntry photo = session.entries.single;
        if (manual) await tester.pump(const Duration(seconds: 60));
        expect(session.busy, isFalse);
        session.stop();
        if (manual) {
          expect(intakeStatus(photo).action, IntakeAction.start);
          await session.retryProcessing(photo);
        } else {
          await tester.pump(const Duration(seconds: 60));
        }
        expect(repository.keys, hasLength(manual ? 2 : 1));
        expect(session.stopping, isFalse);
      },
    );
  }

  testWidgets('F1 resume reads status before using an overdue start offer', (
    tester,
  ) async {
    final StartRepository repository = StartRepository();
    final IntakeTransferSession session = automaticSession(
      repository,
      pollInterval: const Duration(seconds: 5),
    );
    addTearDown(() {
      session.close();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    });
    await session.start();
    session.addListener(() {});
    await tester.pump();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 61));
    final int readsBeforeResume = repository.reads;
    final Completer<Specimen> read = Completer<Specimen>();
    repository.pendingRead = read;
    repository.current = _summary(status: 'running');
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(repository.keys, isEmpty);
    expect(repository.reads, readsBeforeResume + 1);
    read.complete(Specimen(repository.current));
    await tester.pump();
    expect(repository.keys, isEmpty);
    expect(session.entries, isEmpty);
    expect(session.summary, '1 sent');
  });

  testWidgets(
    'F1 a read begun before background cannot renew the start offer',
    (tester) async {
      final StartRepository repository = StartRepository();
      final IntakeTransferSession session = automaticSession(repository);
      addTearDown(() {
        session.close();
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
      });
      await session.start();
      final Completer<Specimen> oldRead = Completer<Specimen>();
      repository.pendingRead = oldRead;
      final Future<void> reading = session.refreshProcessingStatuses();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(seconds: 61));
      repository.pendingRead = null;
      repository.current = _summary(status: 'running');
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      oldRead.complete(Specimen(_summary()));
      await reading;
      await tester.pump();
      expect(repository.keys, isEmpty);
      expect(repository.reads, 2);
      expect(session.entries, isEmpty);
      expect(session.summary, '1 sent');
    },
  );

  for (final String guard in [
    'background',
    'Stop',
    'sign-in',
    'changed offer',
  ]) {
    testWidgets('F2 $guard during start persistence prevents dispatch', (
      tester,
    ) async {
      final StartRepository repository = StartRepository();
      final Completer<void> write = Completer<void>();
      bool holdWrite = false;
      final IntakeTransferSession session = automaticSession(
        repository,
        beforePersist: () async {
          if (holdWrite) await write.future;
        },
      );
      addTearDown(() {
        session.close();
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
      });
      await session.start();
      final ManifestEntry photo = session.entries.single;
      holdWrite = true;
      await tester.pump(const Duration(seconds: 60));
      expect(session.busy, isTrue);
      expect(repository.keys, isEmpty);
      switch (guard) {
        case 'background':
          tester.binding.handleAppLifecycleStateChanged(
            AppLifecycleState.paused,
          );
        case 'Stop':
          session.stop();
        case 'sign-in':
          session.signInRequired = true;
        case 'changed offer':
          photo.specimen = Specimen(_summary(actions: []));
      }
      write.complete();
      await tester.pump();
      expect(repository.keys, isEmpty);
      // The saved decision stays consumed: local storage cannot safely undo
      // another session's attempt, even when this session sent no request.
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final List<dynamic> rows =
          jsonDecode(prefs.getString('upload-handles-v1:auto:${_scope.key}')!)
              as List<dynamic>;
      expect(rows.single['automatic_start_attempted'], isTrue);
      expect(photo.automaticStartAttempted, isTrue);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await session.resumeAfterSignIn();
      await tester.pump(const Duration(seconds: 120));
      expect(repository.keys, isEmpty);
      expect(intakeStatus(photo).status, 'Starting');
      expect(intakeStatus(photo).action, isNull);
    });
  }

  for (final bool saveFirst in [false, true]) {
    testWidgets(
      'F3 a restored session respects another session start attempt (save=$saveFirst)',
      (tester) async {
        final StartRepository repository = StartRepository();
        final IntakeTransferSession first = automaticSession(repository);
        addTearDown(first.close);
        await first.start();
        final IntakeTransferSession second = IntakeTransferSession(
          repository,
          _scope,
          'auto',
          processingPollInterval: Duration.zero,
          automaticStartDelay: const Duration(seconds: 61),
        );
        addTearDown(second.close);
        await second.restore();
        expect(second.entries.single.automaticStartAttempted, isFalse);
        await tester.pump(const Duration(seconds: 60));
        expect(repository.keys, hasLength(1));
        // A stale session's ordinary save must not erase the other attempt.
        if (saveFirst) await second.persist();
        await tester.pump(const Duration(seconds: 2));
        expect(repository.keys, hasLength(1));
        expect(second.entries.single.automaticStartAttempted, isTrue);
      },
    );
  }

  for (final String blocker in [
    'sensitive_record_not_processed',
    'collection_processing_unconfigured',
    'program_allowance_unavailable',
  ]) {
    testWidgets('F7 $blocker survives a 503 summary', (tester) async {
      final StartRepository repository = StartRepository()
        ..current = _summary(status: 'processing_blocked', blocker: blocker);
      final IntakeTransferSession session = automaticSession(repository);
      addTearDown(session.close);
      await session.start();
      final ManifestEntry photo = session.entries.single;
      final IntakeStatus confirmed = intakeStatus(photo);
      repository.readError = const ApiFailure('outage', status: 503);
      await session.refreshProcessingStatuses();
      expect(intakeStatus(photo).status, confirmed.status);
      expect(intakeStatus(photo).reason, confirmed.reason);
      expect(intakeStatus(photo).action, IntakeAction.dismiss);
      expect(
        session.summary,
        blocker == 'sensitive_record_not_processed' ? '1 held' : '1 to fix',
      );
      await tester.pump(const Duration(seconds: 120));
      expect(repository.keys, isEmpty);
      session.remove(photo);
      expect(session.entries, isEmpty);
    });
  }

  for (final bool failedDispatch in [false, true]) {
    testWidgets(
      'F7 stale ${failedDispatch ? 'manual' : 'automatic'} start offer stays disabled until a successful read',
      (tester) async {
        final StartRepository repository = StartRepository();
        if (failedDispatch) {
          repository.current = {
            ..._summary(),
            'dispatch': {'status': 'failed'},
          };
        }
        final IntakeTransferSession session = automaticSession(repository);
        addTearDown(session.close);
        await session.start();
        final ManifestEntry photo = session.entries.single;
        repository.readError = const ApiFailure('outage', status: 503);
        await session.refreshProcessingStatuses();
        expect(photo.specimen, isNotNull);
        expect(intakeStatus(photo).action, isNull);
        await session.retryProcessing(photo);
        await tester.pump(const Duration(seconds: 60));
        expect(repository.keys, isEmpty);
        repository.readError = null;
        await session.refreshProcessingStatuses();
        await tester.pump();
        expect(repository.keys, hasLength(1));
      },
    );
  }

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
