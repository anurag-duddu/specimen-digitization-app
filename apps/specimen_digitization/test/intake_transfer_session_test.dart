import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';

const CollectionScope scope = CollectionScope(
  organizationId: 'fixture-org',
  collectionId: 'fixture-collection',
  name: 'Fixture',
);

ManifestEntry entry(String name) => ManifestEntry(
  digest: name.padRight(64, 'a'),
  name: '$name.jpg',
  file: IntakeFile(
    name: '$name.jpg',
    bytes: Uint8List.fromList(<int>[1, 2, 3]),
    mimeType: 'image/jpeg',
    sha256: name.padRight(64, 'a'),
    method: 'camera',
    sensitive: true,
  ),
  state: UploadState.ready,
);

class TransferRepository implements SpecimenRepository {
  final Completer<void> firstUpload = Completer<void>();
  final List<String> started = <String>[];
  bool holdFirst = true;
  bool denyNext = false;
  int completions = 0;
  Json completionResponse = <String, dynamic>{'status': 'pending'};
  final Map<String, Specimen> summaries = <String, Specimen>{};
  final List<String> summaryRequests = <String>[];
  int summaryAccessFailures = 0;
  final List<String> retryRequests = <String>[];
  Specimen? retryResponse;

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    if (denyNext) {
      denyNext = false;
      throw const ApiFailure('Collection access denied.', status: 403);
    }
    return <String, dynamic>{'upload_id': file.sha256, 'state': 'ready'};
  }

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
    started.add(file.name);
    if (holdFirst && started.length == 1) await firstUpload.future;
    progress(1);
  }

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    completions++;
    return <String, dynamic>{'upload_id': id, ...completionResponse};
  }

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    final String id = filters['specimen_id'] ?? '';
    summaryRequests.add(id);
    if (summaryAccessFailures > 0) {
      summaryAccessFailures--;
      throw const ApiFailure('Processing access expired.', status: 401);
    }
    final Specimen? specimen = summaries[id];
    return SpecimenPage(<Specimen>[?specimen]);
  }

  @override
  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  ) async {
    retryRequests.add(specimen.id);
    return retryResponse ?? specimen;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Specimen processingSpecimen(
  String id, {
  String status = 'running',
  String? disposition,
  List<String> actions = const <String>[],
  int revision = 1,
}) => Specimen(<String, dynamic>{
  'specimen_id': id,
  'status': status,
  'disposition': disposition,
  'revision': revision,
  'available_actions': actions,
});

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test(
    'completion snapshot distinguishes queued and sensitive uploads',
    () async {
      final TransferRepository queuedRepository = TransferRepository()
        ..holdFirst = false;
      final IntakeTransferSession queued = IntakeTransferSession(
        queuedRepository,
        scope,
        'queued-operator',
      );
      final ManifestEntry queuedEntry = entry('queued');
      queued.entries.add(queuedEntry);
      await queued.start();
      expect(queuedEntry.state, UploadState.accepted);
      expect(
        queuedEntry.reason,
        'Uploaded to the collection. Processing is queued.',
      );

      final TransferRepository sensitiveRepository = TransferRepository()
        ..holdFirst = false
        ..completionResponse = <String, dynamic>{
          'status': 'processing_blocked',
          'blocker': 'sensitive_record_not_processed',
        };
      final IntakeTransferSession sensitive = IntakeTransferSession(
        sensitiveRepository,
        scope,
        'sensitive-operator',
      );
      final ManifestEntry sensitiveEntry = entry('sensitive');
      sensitive.entries.add(sensitiveEntry);
      await sensitive.start();
      expect(sensitiveEntry.state, UploadState.accepted);
      expect(
        sensitiveEntry.reason,
        'Uploaded to the collection. Sensitive records are held from processing.',
      );
      queued.close();
      sensitive.close();
    },
  );

  test(
    'completion enters Intake processing and persists safe restart identifiers',
    () async {
      final TransferRepository repository = TransferRepository()
        ..holdFirst = false
        ..completionResponse = <String, dynamic>{
          'specimen_id': 'specimen-1',
          'status': 'running',
          'revision': 1,
          'available_actions': <String>[],
        };
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'tracking-operator',
        processingPollInterval: Duration.zero,
      );
      final ManifestEntry photograph = entry('tracking');
      session.entries.add(photograph);

      await session.start();

      expect(photograph.state, UploadState.processing);
      expect(photograph.specimenId, 'specimen-1');
      expect(photograph.file, isNull);
      expect(session.needsProcessingPoll, isTrue);
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String saved = prefs.getString(
        'upload-handles-v1:tracking-operator:${scope.key}',
      )!;
      expect(saved, contains('"upload_id"'));
      expect(saved, contains('"specimen_id":"specimen-1"'));
      expect(saved, isNot(contains('tracking.jpg')));
      session.close();
    },
  );

  test('refresh hands a completed record to the existing main Queue', () async {
    final TransferRepository repository = TransferRepository()
      ..holdFirst = false
      ..completionResponse = <String, dynamic>{
        'specimen_id': 'specimen-2',
        'status': 'running',
        'revision': 1,
        'available_actions': <String>[],
      };
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'handoff-operator',
      processingPollInterval: Duration.zero,
    );
    final ManifestEntry photograph = entry('handoff');
    session.entries.add(photograph);
    await session.start();
    var handoffs = 0;
    session.attachHandoff(() => handoffs++);
    repository.summaries['specimen-2'] = processingSpecimen(
      'specimen-2',
      status: 'completed',
      disposition: 'needs_human_review',
      revision: 2,
    );

    await session.refreshProcessingStatuses();

    expect(repository.summaryRequests, <String>['specimen-2']);
    expect(photograph.state, UploadState.inMainQueue);
    expect(
      photograph.reason,
      'Processing finished. This photograph is now in the main Queue.',
    );
    expect(session.needsProcessingPoll, isFalse);
    expect(handoffs, 1);
    await session.refreshProcessingStatuses();
    expect(handoffs, 1);
    session.close();
  });

  test('one shared callback reports immediate handoff only once', () async {
    final TransferRepository repository = TransferRepository()
      ..holdFirst = false
      ..completionResponse = <String, dynamic>{
        'specimen_id': 'specimen-immediate',
        'status': 'completed',
        'disposition': 'needs_human_review',
        'revision': 1,
        'available_actions': <String>[],
      };
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'immediate-handoff-operator',
      processingPollInterval: Duration.zero,
    );
    final ManifestEntry photograph = entry('immediate');
    session.entries.add(photograph);
    var refreshes = 0;
    void refresh() => refreshes++;
    session.attachComplete(refresh);
    session.attachHandoff(refresh);

    await session.start();

    expect(photograph.state, UploadState.inMainQueue);
    expect(refreshes, 1);
    session.close();
  });

  test(
    'a shared callback reports upload and a later handoff separately',
    () async {
      final TransferRepository repository = TransferRepository()
        ..holdFirst = false
        ..completionResponse = <String, dynamic>{
          'specimen_id': 'specimen-later',
          'status': 'running',
          'revision': 1,
          'available_actions': <String>[],
        };
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'later-handoff-operator',
        processingPollInterval: Duration.zero,
      );
      final ManifestEntry photograph = entry('later');
      session.entries.add(photograph);
      var refreshes = 0;
      void refresh() => refreshes++;
      session.attachComplete(refresh);
      session.attachHandoff(refresh);

      await session.start();
      expect(refreshes, 1);
      repository.summaries['specimen-later'] = processingSpecimen(
        'specimen-later',
        status: 'completed',
        disposition: 'needs_human_review',
        revision: 2,
      );

      await session.refreshProcessingStatuses();

      expect(photograph.state, UploadState.inMainQueue);
      expect(refreshes, 2);
      session.close();
    },
  );

  test(
    'processing polling pauses without observers and resumes on attach',
    () async {
      final TransferRepository repository = TransferRepository();
      repository.summaries['specimen-observed'] = processingSpecimen(
        'specimen-observed',
        status: 'completed',
        disposition: 'needs_human_review',
      );
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'observed-operator',
        processingPollInterval: const Duration(milliseconds: 10),
      );
      session.entries.add(
        ManifestEntry.tracking(
          digest: List<String>.filled(64, 'o').join(),
          name: 'observed.jpg',
          handle: <String, dynamic>{'upload_id': 'upload-observed'},
          specimenId: 'specimen-observed',
        ),
      );
      void observer() {}

      session.addListener(observer);
      session.removeListener(observer);
      await Future<void>.delayed(const Duration(milliseconds: 35));
      expect(repository.summaryRequests, isEmpty);

      session.addListener(observer);
      await Future<void>.delayed(const Duration(milliseconds: 35));
      expect(repository.summaryRequests, <String>['specimen-observed']);
      expect(session.entries.single.state, UploadState.inMainQueue);
      session.removeListener(observer);
      session.close();
    },
  );

  test('reattaching restarts polling after an access failure', () async {
    final TransferRepository repository = TransferRepository()
      ..summaryAccessFailures = 1;
    repository.summaries['specimen-access'] = processingSpecimen(
      'specimen-access',
      status: 'completed',
      disposition: 'needs_human_review',
    );
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'access-operator',
      processingPollInterval: const Duration(milliseconds: 10),
    );
    session.entries.add(
      ManifestEntry.tracking(
        digest: List<String>.filled(64, 'x').join(),
        name: 'access.jpg',
        handle: <String, dynamic>{'upload_id': 'upload-access'},
        specimenId: 'specimen-access',
      ),
    );
    void observer() {}

    session.addListener(observer);
    await Future<void>.delayed(const Duration(milliseconds: 35));
    expect(repository.summaryRequests, <String>['specimen-access']);
    expect(session.entries.single.state, UploadState.processing);

    session.removeListener(observer);
    session.addListener(observer);
    await Future<void>.delayed(const Duration(milliseconds: 35));
    expect(repository.summaryRequests, <String>[
      'specimen-access',
      'specimen-access',
    ]);
    expect(session.entries.single.state, UploadState.inMainQueue);
    session.removeListener(observer);
    session.close();
  });

  test(
    'restores a processing record and refreshes it without image bytes',
    () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'upload-handles-v1:restored-operator:${scope.key}':
            '[{"digest":"aaaaaaaaaaaaaaaa","upload_id":"upload-1",'
            '"specimen_id":"specimen-3","state":"processing"}]',
      });
      final TransferRepository repository = TransferRepository();
      repository.summaries['specimen-3'] = processingSpecimen(
        'specimen-3',
        status: 'running',
      );
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'restored-operator',
        processingPollInterval: Duration.zero,
      );

      await session.restore();

      expect(session.entries, hasLength(1));
      expect(session.entries.single.file, isNull);
      expect(session.entries.single.specimenId, 'specimen-3');
      expect(session.entries.single.state, UploadState.processing);
      expect(repository.summaryRequests, <String>['specimen-3']);
      session.close();
    },
  );

  test(
    'blocked processing retries only when the server offers retry',
    () async {
      final TransferRepository repository = TransferRepository();
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'retry-operator',
        processingPollInterval: Duration.zero,
      );
      final ManifestEntry photograph = ManifestEntry.tracking(
        digest: List<String>.filled(64, 'b').join(),
        name: 'blocked.jpg',
        handle: <String, dynamic>{'upload_id': 'upload-2'},
        specimenId: 'specimen-4',
        state: UploadState.processingBlocked,
      );
      photograph.specimen = processingSpecimen(
        'specimen-4',
        status: 'processing_blocked',
        actions: <String>['retry'],
      );
      session.entries.add(photograph);
      repository.retryResponse = processingSpecimen(
        'specimen-4',
        status: 'running',
        revision: 2,
      );

      expect(session.canRetryProcessing(photograph), isTrue);
      await session.retryProcessing(photograph);

      expect(repository.retryRequests, <String>['specimen-4']);
      expect(photograph.state, UploadState.processing);
      expect(photograph.reason, 'Processing is underway.');
      expect(session.needsProcessingPoll, isTrue);
      session.close();
    },
  );

  test('completion copy does not mistake missing status for no processing', () {
    expect(
      intakeCompletionReason(<String, dynamic>{}),
      'Uploaded to Intake. Processing status is not available yet.',
    );
    expect(
      intakeCompletionReason(<String, dynamic>{
        'stage': 'processing_blocked',
        'blocker': 'collection_processing_unconfigured',
      }),
      'Uploaded to the collection. Processing awaits collection setup.',
    );
  });

  test(
    'an accepted camera photo uploads while more photos enter the same queue',
    () async {
      final TransferRepository repository = TransferRepository();
      final IntakeTransferSession session = intakeTransferSession(
        repository,
        scope,
        'operator',
      );
      session.entries.add(entry('first'));
      final Future<void> pumping = session.start();
      await Future<void>.delayed(Duration.zero);
      expect(repository.started, <String>['first.jpg']);
      expect(session.busy, isTrue);

      // The intake route may unmount and reacquire this session during a transfer.
      final IntakeTransferSession reopened = intakeTransferSession(
        repository,
        scope,
        'operator',
      );
      expect(identical(reopened, session), isTrue);
      reopened.entries.add(entry('second'));
      reopened.changed();
      repository.firstUpload.complete();
      await pumping;

      expect(repository.started, <String>['first.jpg', 'second.jpg']);
      expect(
        session.entries.every((item) => item.state == UploadState.accepted),
        isTrue,
      );
      expect(session.entries.every((item) => item.file == null), isTrue);
      forgetIntakeTransfers(repository, 'operator');
    },
  );

  test('stop leaves queued files ready, then retry sends them', () async {
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = intakeTransferSession(
      repository,
      scope,
      'operator',
    );
    session.entries.addAll(<ManifestEntry>[entry('first'), entry('second')]);
    final Future<void> pumping = session.start();
    await Future<void>.delayed(Duration.zero);
    session.stop();
    repository.firstUpload.complete();
    await pumping;
    expect(repository.started, <String>['first.jpg']);
    expect(session.entries.last.state, UploadState.ready);
    await session.start();
    expect(repository.started, <String>['first.jpg', 'second.jpg']);
    forgetIntakeTransfers(repository, 'operator');
  });

  test(
    'permission denial stops the queue and an explicit retry can resume',
    () async {
      final TransferRepository repository = TransferRepository()
        ..holdFirst = false
        ..denyNext = true;
      final IntakeTransferSession session = intakeTransferSession(
        repository,
        scope,
        'operator',
      );
      final ManifestEntry first = entry('first');
      session.entries.addAll(<ManifestEntry>[first, entry('second')]);
      await session.start();
      expect(first.state, UploadState.failed);
      expect(session.entries.last.state, UploadState.ready);
      expect(repository.started, isEmpty);
      await session.start(only: first);
      expect(first.state, UploadState.accepted);
      forgetIntakeTransfers(repository, 'operator');
    },
  );

  test(
    'sign-out releases bytes and skips completion of an in-flight upload',
    () async {
      final TransferRepository repository = TransferRepository();
      final IntakeTransferSession session = intakeTransferSession(
        repository,
        scope,
        'operator',
      );
      session.entries.add(entry('first'));
      final Future<void> pumping = session.start();
      await Future<void>.delayed(Duration.zero);
      expect(repository.started, <String>['first.jpg']);
      forgetIntakeTransfers(repository, 'operator');
      repository.firstUpload.complete();
      await pumping;
      expect(repository.completions, 0);
      expect(session.entries, isEmpty);
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      expect(
        prefs.getString('upload-handles-v1:operator:${scope.key}'),
        isNull,
      );
    },
  );

  test(
    'sign-out during a delayed handle write cannot start the upload',
    () async {
      final TransferRepository repository = TransferRepository()
        ..holdFirst = false;
      final Completer<void> allowPersist = Completer<void>();
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'operator',
        beforePersist: () => allowPersist.future,
      );
      session.entries.add(entry('first'));
      final Future<void> pumping = session.start();
      await Future<void>.delayed(Duration.zero);
      session.close();
      allowPersist.complete();
      await pumping;
      expect(repository.started, isEmpty);
      expect(repository.completions, 0);
    },
  );
}
