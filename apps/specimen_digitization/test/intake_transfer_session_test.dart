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
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

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

  test('completion copy does not mistake missing status for no processing', () {
    expect(
      intakeCompletionReason(<String, dynamic>{}),
      'Uploaded to the collection. Check the queue for processing status.',
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
