import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/screens/intake/intake_status.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_digitization/src/workspace.dart';

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
  int summaryUnavailableFailures = 0;
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
    if (summaryUnavailableFailures > 0) {
      summaryUnavailableFailures--;
      throw const ApiFailure('Status service unavailable.', status: 503);
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

class QueueTransferRepository extends TransferRepository {
  final List<Map<String, String>> queueReads = <Map<String, String>>[];

  @override
  Future<List<CollectionScope>> scopes() async => <CollectionScope>[scope];

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    if (filters.containsKey('specimen_id')) {
      return super.specimenPage(scope, filters: filters, cursor: cursor);
    }
    queueReads.add(Map<String, String>.from(filters));
    return SpecimenPage(
      summaries.values
          .where((Specimen item) => item.disposition == filters['disposition'])
          .toList(),
    );
  }
}

/// The Queue list as the server pages it: oldest first, two to a page.
class PagedQueueTransferRepository extends QueueTransferRepository {
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    final SpecimenPage all = await super.specimenPage(
      scope,
      filters: filters,
      cursor: cursor,
    );
    if (filters.containsKey('specimen_id')) return all;
    final int start = cursor == null
        ? 0
        : all.items.indexWhere((Specimen s) => 'after:${s.id}' == cursor) + 1;
    final List<Specimen> page = all.items.skip(start).take(2).toList();
    return SpecimenPage(
      page,
      nextCursor: page.length == 2 ? 'after:${page.last.id}' : null,
    );
  }
}

class QueueTestSession implements SessionAccess {
  @override
  bool get signedIn => true;

  @override
  String get userId => 'queue-test-operator';

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Specimen processingSpecimen(
  String id, {
  String status = 'running',
  String? blocker,
  String? disposition,
  List<String> actions = const <String>[],
  int revision = 1,
}) => Specimen(<String, dynamic>{
  'specimen_id': id,
  'status': status,
  'blocker': ?blocker,
  'disposition': disposition,
  'revision': revision,
  'available_actions': actions,
});

ManifestEntry trackedPhotograph(String id) => ManifestEntry.tracking(
  digest: id.padRight(64, 'a'),
  name: '$id.jpg',
  handle: <String, dynamic>{'upload_id': 'upload-$id'},
  specimenId: id,
);

class RetryTransferRepository extends TransferRepository {
  final List<Object> failures = [];
  final List<Object> createFailures = [];
  Completer<void>? failureGate;
  final List<int> offsets = [];
  final List<String> createKeys = [];
  final List<String> completeKeys = [];
  Object? accessFailure;
  String failAt = 'create';
  int serverOffset = 0;
  int failureOffset = 1;
  bool reportFailureProgress = true;

  void checkAccess(String point) {
    if (point != failAt || accessFailure == null) return;
    final Object error = accessFailure!;
    accessFailure = null;
    throw error;
  }

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    createKeys.add(key);
    if (createFailures.isNotEmpty) throw createFailures.removeAt(0);
    checkAccess('create');
    return super.createIntake(scope, file, key);
  }

  @override
  Future<Json> resumeIntake(CollectionScope scope, String id) async {
    checkAccess('resume');
    return {'upload_id': id, 'state': 'ready', 'offset': serverOffset};
  }

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async {
    checkAccess('upload');
    offsets.add((session['offset'] as int?) ?? 0);
    if (failures.isNotEmpty) {
      await failureGate?.future;
      serverOffset = failureOffset;
      if (reportFailureProgress) progress(serverOffset / file.bytes.length);
      throw failures.removeAt(0);
    }
    await super.upload(scope, session, file, progress);
  }

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async {
    completeKeys.add(key);
    checkAccess('complete');
    return super.completeIntake(scope, id, key);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
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
      expect(queuedEntry.reason, 'Saved. Start not confirmed.');

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
      expect(sensitiveEntry.reason, 'Saved. Start not confirmed.');
      queued.close();
      sensitive.close();
    },
  );

  test('pending completion persists only safe restart identifiers', () async {
    final TransferRepository repository = TransferRepository()
      ..holdFirst = false
      ..completionResponse = <String, dynamic>{
        'specimen_id': 'specimen-1',
        'status': 'pending',
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
  });

  test('refresh hands a running record to Specimens', () async {
    final TransferRepository repository = TransferRepository()
      ..holdFirst = false
      ..completionResponse = <String, dynamic>{
        'specimen_id': 'specimen-2',
        'status': 'pending',
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
      status: 'running',
      revision: 2,
    );

    await session.refreshProcessingStatuses();

    expect(repository.summaryRequests, <String>['specimen-2']);
    expect(photograph.state, UploadState.inMainQueue);
    expect(photograph.reason, isNull);
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

  test('handoff refresh loads the real Needs review Queue list', () async {
    final QueueTransferRepository repository = QueueTransferRepository();
    final WorkspaceController workspace = WorkspaceController(
      repository: repository,
      session: QueueTestSession(),
    );
    await workspace.checkAccess();
    expect(workspace.items, isEmpty);
    expect(workspace.disposition, 'needs_human_review');
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'queue-test-operator',
      processingPollInterval: Duration.zero,
    );
    session.entries.add(trackedPhotograph('real-queue-handoff'));
    final List<Future<void>> workspaceRefreshes = <Future<void>>[];
    // This is the same read-only refresh contract wired by _IntakeRoute.
    session.attachHandoff(() {
      workspaceRefreshes.add(workspace.refresh(quiet: true));
    });
    repository.summaries['real-queue-handoff'] = processingSpecimen(
      'real-queue-handoff',
      status: 'pending',
    );
    await session.refreshProcessingStatuses();
    expect(workspaceRefreshes, isEmpty);
    expect(workspace.items, isEmpty);
    repository.summaries['real-queue-handoff'] = processingSpecimen(
      'real-queue-handoff',
      status: 'completed',
      disposition: 'needs_human_review',
    );

    await session.refreshProcessingStatuses();
    await Future.wait(workspaceRefreshes);

    expect(workspaceRefreshes, hasLength(1));
    expect(workspace.items.map((Specimen item) => item.id), <String>[
      'real-queue-handoff',
    ]);
    expect(workspace.needsReview, 1);
    expect(workspace.selected, isNull);
    expect(repository.queueReads, <Map<String, String>>[
      <String, String>{'disposition': 'needs_human_review'},
      <String, String>{'disposition': 'needs_human_review'},
    ]);
    expect(repository.started, isEmpty);
    expect(repository.retryRequests, isEmpty);
    session.close();
    workspace.dispose();
  });

  test(
    'handoff refresh adds the photograph to a paginated Queue without dropping loaded pages',
    () async {
      final PagedQueueTransferRepository repository =
          PagedQueueTransferRepository();
      for (final String id in <String>['older-1', 'older-2', 'older-3']) {
        repository.summaries[id] = processingSpecimen(
          id,
          status: 'completed',
          disposition: 'needs_human_review',
        );
      }
      final WorkspaceController workspace = WorkspaceController(
        repository: repository,
        session: QueueTestSession(),
      );
      await workspace.checkAccess();
      await workspace.loadMore();
      expect(workspace.items.map((Specimen item) => item.id), <String>[
        'older-1',
        'older-2',
        'older-3',
      ]);
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'queue-test-operator',
        processingPollInterval: Duration.zero,
      );
      session.entries.add(trackedPhotograph('paged-handoff'));
      final List<Future<void>> workspaceRefreshes = <Future<void>>[];
      // The refresh _IntakeRoute wires to Intake's handoff (app_router.dart).
      session.attachHandoff(() {
        workspaceRefreshes.add(workspace.refresh(quiet: true));
      });
      repository.summaries['paged-handoff'] = processingSpecimen(
        'paged-handoff',
        status: 'completed',
        disposition: 'needs_human_review',
      );

      await session.refreshProcessingStatuses();
      await Future.wait(workspaceRefreshes);

      expect(workspaceRefreshes, hasLength(1));
      expect(workspace.items.map((Specimen item) => item.id), <String>[
        'older-1',
        'older-2',
        'older-3',
        'paged-handoff',
      ]);
      expect(workspace.error, isNull);
      session.close();
      workspace.dispose();
    },
  );

  test(
    'a shared callback reports upload and a later handoff separately',
    () async {
      final TransferRepository repository = TransferRepository()
        ..holdFirst = false
        ..completionResponse = <String, dynamic>{
          'specimen_id': 'specimen-later',
          'status': 'pending',
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

  testWidgets(
    'processing polling pauses without observers and resumes on attach',
    (tester) async {
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
      await tester.pump(const Duration(milliseconds: 35));
      expect(repository.summaryRequests, isEmpty);

      session.addListener(observer);
      await tester.pump(const Duration(milliseconds: 35));
      expect(repository.summaryRequests, <String>['specimen-observed']);
      // In the main Queue, the photo leaves Intake (owner, 2026-10-12).
      expect(session.entries, isEmpty);
      expect(session.movedToQueue, 1);
      session.removeListener(observer);
      session.close();
    },
  );

  testWidgets('reattaching stays paused until sign-in resumes the session', (
    tester,
  ) async {
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
    await tester.pump(const Duration(milliseconds: 35));
    expect(repository.summaryRequests, <String>['specimen-access']);
    expect(session.entries.single.state, UploadState.processing);

    session.removeListener(observer);
    session.addListener(observer);
    await tester.pump(const Duration(milliseconds: 35));
    expect(repository.summaryRequests, <String>['specimen-access']);
    await session.resumeAfterSignIn();
    expect(repository.summaryRequests, <String>[
      'specimen-access',
      'specimen-access',
    ]);
    expect(session.entries, isEmpty);
    expect(session.movedToQueue, 1);
    session.removeListener(observer);
    session.close();
  });

  for (final String status in <String>[
    'running',
    'retry_scheduled',
    'paused',
    'cancelled',
    'completed',
  ]) {
    test(
      '$status removes the photo and stops polling without a disposition',
      () async {
        final TransferRepository repository = TransferRepository();
        final IntakeTransferSession session = IntakeTransferSession(
          repository,
          scope,
          'handoff-$status',
          processingPollInterval: Duration.zero,
        );
        final ManifestEntry photograph = trackedPhotograph('handoff');
        session.entries.add(photograph);
        repository.summaries['handoff'] = processingSpecimen(
          'handoff',
          status: status,
        );
        await session.refreshProcessingStatuses();
        expect(session.entries, isEmpty);
        expect(photograph.state, UploadState.inMainQueue);
        expect(session.needsProcessingPoll, isFalse);
        expect(session.movedToQueue, 1);
        await session.refreshProcessingStatuses();
        expect(repository.summaryRequests, ['handoff']);
        expect(repository.started, isEmpty);
        expect(repository.retryRequests, isEmpty);
        session.close();
      },
    );
  }

  for (final String blocker in [
    'sensitive_record_not_processed',
    'collection_processing_unconfigured',
    'program_allowance_unavailable',
  ]) {
    testWidgets('F7 $blocker survives a missing summary', (tester) async {
      final TransferRepository repository = TransferRepository();
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'missing',
        processingPollInterval: Duration.zero,
      );
      addTearDown(session.close);
      final ManifestEntry photo = trackedPhotograph('missing');
      session.entries.add(photo);
      repository.summaries['missing'] = processingSpecimen(
        'missing',
        status: 'processing_blocked',
        blocker: blocker,
      );
      await session.refreshProcessingStatuses();
      final IntakeStatus confirmed = intakeStatus(photo);
      repository.summaries.clear();
      await session.refreshProcessingStatuses();
      expect(intakeStatus(photo).status, confirmed.status);
      expect(intakeStatus(photo).reason, confirmed.reason);
      expect(intakeStatus(photo).action, IntakeAction.dismiss);
      expect(
        session.summary,
        blocker == 'sensitive_record_not_processed' ? '1 held' : '1 to fix',
      );
      expect(session.canRetryProcessing(photo), isFalse);
      await tester.pump(const Duration(seconds: 120));
      expect(repository.retryRequests, isEmpty);
      session.remove(photo);
      expect(session.entries, isEmpty);
    });
  }

  test(
    'status outage preserves a pending record until read recovery',
    () async {
      final TransferRepository repository = TransferRepository();
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'outage-operator',
        processingPollInterval: Duration.zero,
      );
      final ManifestEntry photograph = trackedPhotograph('outage');
      session.entries.add(photograph);
      repository.summaries['outage'] = processingSpecimen(
        'outage',
        status: 'pending',
      );
      await session.refreshProcessingStatuses();
      repository.summaryUnavailableFailures = 1;

      await session.refreshProcessingStatuses();

      expect(photograph.state, UploadState.processing);
      expect(photograph.reason, isNull);
      expect(session.needsProcessingPoll, isTrue);
      repository.summaries['outage'] = processingSpecimen(
        'outage',
        status: 'completed',
        disposition: 'needs_human_review',
      );
      await session.refreshProcessingStatuses();
      expect(photograph.state, UploadState.inMainQueue);
      expect(repository.started, isEmpty);
      expect(repository.completions, 0);
      expect(repository.retryRequests, isEmpty);
      session.close();
    },
  );

  testWidgets('route reattach immediately checks a pending summary', (
    tester,
  ) async {
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'reattach-blocked-operator',
      processingPollInterval: const Duration(hours: 1),
    );
    final ManifestEntry photograph = trackedPhotograph('reattach-blocked');
    session.entries.add(photograph);
    repository.summaries['reattach-blocked'] = processingSpecimen(
      'reattach-blocked',
      status: 'pending',
    );
    await session.refreshProcessingStatuses();
    void observer() {}
    session.addListener(observer);
    session.removeListener(observer);
    repository.summaries['reattach-blocked'] = processingSpecimen(
      'reattach-blocked',
      status: 'completed',
      disposition: 'needs_human_review',
    );

    session.addListener(observer);
    await tester.pump(const Duration(milliseconds: 1));

    expect(repository.summaryRequests, hasLength(2));
    expect(photograph.state, UploadState.inMainQueue);
    expect(repository.started, isEmpty);
    expect(repository.retryRequests, isEmpty);
    session.removeListener(observer);
    session.close();
  });

  testWidgets('background pauses reads and sign-in recovery resumes them', (
    tester,
  ) async {
    final TestWidgetsFlutterBinding binding =
        TestWidgetsFlutterBinding.ensureInitialized();
    final TransferRepository repository = TransferRepository()
      ..summaryAccessFailures = 1;
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'resumed-operator',
      processingPollInterval: const Duration(milliseconds: 10),
    );
    final ManifestEntry photograph = trackedPhotograph('resumed');
    session.entries.add(photograph);
    repository.summaries['resumed'] = processingSpecimen(
      'resumed',
      status: 'completed',
      disposition: 'needs_human_review',
    );
    void observer() {}
    try {
      session.addListener(observer);
      await tester.pump(const Duration(milliseconds: 35));
      expect(repository.summaryRequests, hasLength(1));
      expect(photograph.state, UploadState.processing);

      binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(milliseconds: 35));
      expect(repository.summaryRequests, hasLength(1));

      binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(repository.summaryRequests, hasLength(1));
      await session.resumeAfterSignIn();
      expect(repository.summaryRequests, hasLength(2));
      expect(photograph.state, UploadState.inMainQueue);
      expect(repository.started, isEmpty);
      expect(repository.completions, 0);
      expect(repository.retryRequests, isEmpty);
    } finally {
      session.removeListener(observer);
      session.close();
      binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    }
  });

  test('a cancelled run has been handed off and leaves Intake', () async {
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'cancelled-operator',
      processingPollInterval: Duration.zero,
    );
    session.entries.add(trackedPhotograph('cancelled'));
    repository.summaries['cancelled'] = processingSpecimen(
      'cancelled',
      status: 'cancelled',
    );
    var handoffs = 0;
    session.attachHandoff(() => handoffs++);

    await session.refreshProcessingStatuses();

    expect(session.entries, isEmpty);
    expect(session.needsProcessingPoll, isFalse);
    expect(handoffs, 1);
    session.close();
  });

  test(
    'detached handoff survives a route that leaves before delivery',
    () async {
      final TransferRepository repository = TransferRepository();
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'detached-handoff-operator',
        processingPollInterval: Duration.zero,
      );
      session.entries.add(trackedPhotograph('detached-handoff'));
      repository.summaries['detached-handoff'] = processingSpecimen(
        'detached-handoff',
        status: 'completed',
        disposition: 'needs_human_review',
      );
      await session.refreshProcessingStatuses();
      var refreshes = 0;
      void refreshQueue() => refreshes++;

      session.attachHandoff(refreshQueue);
      session.detachHandoff(refreshQueue);
      await Future<void>.delayed(Duration.zero);
      expect(refreshes, 0);

      session.attachHandoff(refreshQueue);
      await Future<void>.delayed(Duration.zero);
      expect(refreshes, 1);
      session.detachHandoff(refreshQueue);
      session.attachHandoff(refreshQueue);
      await Future<void>.delayed(Duration.zero);
      expect(refreshes, 1);
      session.close();
    },
  );

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
        status: 'pending',
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

  test('post-hand-off blockers never offer pipeline retry in Intake', () async {
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'retry-operator',
      processingPollInterval: Duration.zero,
    );
    final ManifestEntry photograph = trackedPhotograph('blocked');
    photograph.specimen = processingSpecimen(
      'blocked',
      status: 'processing_blocked',
      actions: ['retry'],
    );
    photograph.state = UploadState.processingBlocked;
    session.entries.add(photograph);
    expect(session.canRetryProcessing(photograph), isFalse);
    await session.retryProcessing(photograph);
    expect(repository.retryRequests, isEmpty);
    session.close();
  });

  test('rate-limited processing leaves Intake for Specimens', () async {
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'rate-limited-operator',
      processingPollInterval: Duration.zero,
    );
    final ManifestEntry photograph = ManifestEntry.tracking(
      digest: List<String>.filled(64, 'r').join(),
      name: 'rate-limited.jpg',
      handle: <String, dynamic>{'upload_id': 'upload-rate-limited'},
      specimenId: 'specimen-rate-limited',
    );
    session.entries.add(photograph);
    repository.summaries['specimen-rate-limited'] = processingSpecimen(
      'specimen-rate-limited',
      status: 'retry_scheduled',
      blocker: 'model_rate_limited',
    );

    await session.refreshProcessingStatuses();

    expect(photograph.state, UploadState.inMainQueue);
    expect(photograph.reason, isNull);
    expect(session.entries, isEmpty);
    expect(session.needsProcessingPoll, isFalse);
    session.close();
  });

  test('completion copy does not mistake missing status for no processing', () {
    expect(
      intakeCompletionReason(<String, dynamic>{}),
      'Saved. Start not confirmed.',
    );
    expect(
      intakeCompletionReason(<String, dynamic>{
        'stage': 'processing_blocked',
        'blocker': 'collection_processing_unconfigured',
      }),
      'Saved. Start not confirmed.',
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
    'permission denial leaves Ready and sign-in resumes without a Send tap',
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
      expect(first.state, UploadState.ready);
      expect(first.reason, isNull);
      expect(session.busy, isFalse);
      expect(session.entries.last.state, UploadState.ready);
      expect(repository.started, isEmpty);
      await session.resumeAfterSignIn();
      expect(first.state, UploadState.accepted);
      expect(repository.started, ['first.jpg', 'second.jpg']);
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

  for (final ApiFailure failure in <ApiFailure>[
    const ApiFailure('lost', code: 'network'),
    const ApiFailure('timed out', code: 'timeout'),
    for (final int status in <int>[408, 429, 500, 503])
      ApiFailure('unavailable', status: status),
  ]) {
    testWidgets(
      'transfer ${failure.code}/${failure.status} retries from the server offset without a tap',
      (tester) async {
        final RetryTransferRepository repository = RetryTransferRepository()
          ..holdFirst = false
          ..completionResponse = {'specimen_id': 'sent', 'status': 'running'}
          ..failures.add(failure);
        final IntakeTransferSession session = IntakeTransferSession(
          repository,
          scope,
          'retry',
        );
        final ManifestEntry photograph = entry('retry');
        session.entries.add(photograph);
        await session.start();
        expect(intakeStatus(photograph).status, 'Retrying');
        expect(session.busy, isFalse);
        expect(photograph.progress, 1 / 3);
        await tester.pump(const Duration(seconds: 4));
        expect(repository.offsets, [0]);
        await tester.pump(const Duration(seconds: 1));
        expect(repository.offsets, [0, 1]);
        expect(session.entries, isEmpty);
        expect(session.sentCount, 1);
        expect(session.summary, '1 sent');
        expect(repository.createKeys, ['intake-${photograph.digest}']);
        expect(repository.completeKeys, ['complete-${photograph.digest}']);
        session.close();
      },
    );
  }

  for (final bool reportProgress in [true, false]) {
    testWidgets(
      'F6 ${reportProgress ? 'progress' : 'server offset'} restarts retry backoff at five seconds',
      (tester) async {
        final RetryTransferRepository repository = RetryTransferRepository()
          ..holdFirst = false
          ..failureOffset = 0
          ..reportFailureProgress = reportProgress
          ..failures.addAll(
            List.filled(4, const ApiFailure('lost', code: 'network')),
          );
        final IntakeTransferSession session = IntakeTransferSession(
          repository,
          scope,
          'progress',
        );
        addTearDown(session.close);
        final ManifestEntry photo = entry('progress');
        session.entries.add(photo);
        await session.start();
        await tester.pump(const Duration(seconds: 4));
        expect(repository.offsets, [0]);
        await tester.pump(const Duration(seconds: 1));
        expect(repository.offsets, [0, 0]);
        await tester.pump(const Duration(seconds: 14));
        expect(repository.offsets, [0, 0]);
        // The third attempt advances, through progress or a fresh server offset.
        repository.failureOffset = 2;
        if (!reportProgress) repository.serverOffset = 2;
        await tester.pump(const Duration(seconds: 1));
        expect(repository.offsets, hasLength(3));
        await tester.pump(const Duration(seconds: 4));
        expect(repository.offsets, hasLength(3));
        await tester.pump(const Duration(seconds: 1));
        expect(repository.offsets, hasLength(4));
        // No further progress: the next failure backs off to 15 seconds.
        await tester.pump(const Duration(seconds: 14));
        expect(repository.offsets, hasLength(4));
        await tester.pump(const Duration(seconds: 1));
        expect(repository.offsets, hasLength(5));
        expect(photo.state, UploadState.accepted);
      },
    );
  }

  for (final ApiFailure refusal in [
    const ApiFailure('refused', status: 422),
    const ApiFailure('image_codec_disabled', status: 503),
    const ApiFailure('different setting', code: 'intake_sensitivity_mismatch'),
  ]) {
    testWidgets('F4 Stop preserves earlier ${refusal.message} refusal', (
      tester,
    ) async {
      final RetryTransferRepository repository = RetryTransferRepository()
        ..holdFirst = false
        ..failures.add(refusal);
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'stop-refusal',
      );
      addTearDown(session.close);
      final ManifestEntry refused = entry('refused');
      session.entries.add(refused);
      await session.start();
      final IntakeStatus confirmed = intakeStatus(refused);
      final String? detail = refused.why;
      final Completer<void> inFlight = Completer<void>();
      repository.failureGate = inFlight;
      repository.failures.add(const ApiFailure('lost', code: 'network'));
      session.entries.add(entry('second'));
      final Future<void> sending = session.start();
      await tester.pump();
      expect(repository.offsets, hasLength(2));
      session.stop();
      inFlight.complete();
      await sending;
      expect(refused.state, UploadState.failed);
      expect(intakeStatus(refused).status, confirmed.status);
      expect(intakeStatus(refused).reason, confirmed.reason);
      expect(intakeStatus(refused).action, confirmed.action);
      expect(refused.why, detail);
      await session.start();
      expect(repository.offsets, hasLength(3));
      expect(refused.state, UploadState.failed);
    });
  }

  for (final int status in [401, 403]) {
    testWidgets('F5 Stop before $status prevents sign-in resuming transfers', (
      tester,
    ) async {
      final Completer<void> inFlight = Completer<void>();
      final RetryTransferRepository repository = RetryTransferRepository()
        ..holdFirst = false
        ..failureGate = inFlight
        ..failures.add(ApiFailure('signed out', status: status));
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'stop-auth',
      );
      addTearDown(session.close);
      final List<ManifestEntry> photos = [entry('first'), entry('second')];
      session.entries.addAll(photos);
      final Future<void> sending = session.start();
      await tester.pump();
      expect(repository.offsets, [0]);
      session.stop();
      inFlight.complete();
      await sending;
      expect(session.signInRequired, isTrue);
      await session.resumeAfterSignIn();
      await tester.pump(const Duration(seconds: 90));
      expect(repository.offsets, [0]);
      expect(photos.map((p) => p.state), everyElement(UploadState.ready));
      expect(photos.map((p) => intakeStatus(p).status), everyElement('Ready'));
      expect(
        photos.map((p) => p.reason),
        everyElement('Stopped. Send to continue.'),
      );
    });
  }

  testWidgets('retry delays are 5, 15, 60 then 60 seconds', (tester) async {
    final RetryTransferRepository repository = RetryTransferRepository()
      ..holdFirst = false
      ..failures.addAll(
        List.filled(4, const ApiFailure('lost', code: 'network')),
      );
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'delays',
    );
    session.entries.add(entry('delays'));
    await session.start();
    var attempts = 1;
    for (final int seconds in [5, 15, 60, 60]) {
      await tester.pump(Duration(seconds: seconds - 1));
      expect(repository.offsets, hasLength(attempts));
      await tester.pump(const Duration(seconds: 1));
      expect(repository.offsets, hasLength(++attempts));
    }
    expect(session.entries.single.state, UploadState.accepted);
    session.close();
  });

  testWidgets('retry waits in the background and resumes in the foreground', (
    tester,
  ) async {
    final RetryTransferRepository repository = RetryTransferRepository()
      ..holdFirst = false
      ..failures.add(const ApiFailure('lost', code: 'network'));
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'foreground',
    );
    session.entries.add(entry('foreground'));
    await session.start();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 65));
    expect(repository.offsets, [0]);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(repository.offsets, [0, 1]);
    session.close();
  });

  testWidgets('a batch keeps sending while the app is only inactive', (
    tester,
  ) async {
    // On the web `inactive` is a window or tab without input focus; on phones
    // it is a notification shade or a permission sheet. Neither may pause the
    // primary action between two photos.
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'inactive-batch',
    );
    session.entries.addAll(<ManifestEntry>[
      entry('one'),
      entry('two'),
      entry('three'),
    ]);
    try {
      final Future<void> run = session.start();
      await tester.pump();
      expect(repository.started, ['one.jpg']);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      repository.firstUpload.complete();
      await run;
      expect(repository.started, ['one.jpg', 'two.jpg', 'three.jpg']);
      expect(repository.completions, 3);
      expect(session.busy, isFalse);
    } finally {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      session.close();
    }
  });

  testWidgets('a batch pauses between photos in the background and resumes', (
    tester,
  ) async {
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'paused-batch',
    );
    session.entries.addAll(<ManifestEntry>[
      entry('one'),
      entry('two'),
      entry('three'),
    ]);
    try {
      final Future<void> run = session.start();
      await tester.pump();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      repository.firstUpload.complete();
      await run;
      expect(repository.started, ['one.jpg']);
      expect(repository.completions, 1);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(repository.started, ['one.jpg', 'two.jpg', 'three.jpg']);
      expect(repository.completions, 3);
    } finally {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      session.close();
    }
  });

  testWidgets(
    'Retry now cancels the scheduled retry and keeps its server handle',
    (tester) async {
      final RetryTransferRepository repository = RetryTransferRepository()
        ..holdFirst = false
        ..failures.add(const ApiFailure('lost', code: 'network'));
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'now',
      );
      final ManifestEntry photograph = entry('now');
      session.entries.add(photograph);
      await session.start();
      await tester.pump(const Duration(seconds: 1));
      expect(repository.offsets, [0]);
      await session.start(only: photograph);
      expect(repository.offsets, [0, 1]);
      await tester.pump(const Duration(seconds: 90));
      expect(repository.offsets, [0, 1]);
      expect(repository.createKeys, hasLength(1));
      session.close();
    },
  );

  testWidgets('removing or stopping a waiting retry prevents later sending', (
    tester,
  ) async {
    for (final bool remove in [true, false]) {
      final RetryTransferRepository repository = RetryTransferRepository()
        ..holdFirst = false
        ..failures.add(const ApiFailure('lost', code: 'network'));
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'stop-$remove',
      );
      final ManifestEntry photograph = entry('stop-$remove');
      session.entries.add(photograph);
      await session.start();
      if (remove) {
        session.remove(photograph);
      } else {
        session.stop();
        expect(photograph.state, UploadState.ready);
        expect(intakeStatus(photograph).reason, 'Stopped. Send to continue.');
      }
      await tester.pump(const Duration(seconds: 90));
      expect(repository.offsets, [0]);
      session.close();
    }
  });

  for (final int status in [401, 403]) {
    for (final String point in ['create', 'upload', 'resume', 'complete']) {
      testWidgets(
        '$status at $point leaves rows Ready and sign-in resumes sending',
        (tester) async {
          final RetryTransferRepository repository = RetryTransferRepository()
            ..holdFirst = false
            ..completionResponse = {'specimen_id': 'sent', 'status': 'running'}
            ..failAt = point
            ..accessFailure = ApiFailure(
              'private server message',
              status: status,
            );
          final IntakeTransferSession session = IntakeTransferSession(
            repository,
            scope,
            'auth-$point-$status',
          );
          final List<ManifestEntry> photographs = [
            entry('first'),
            entry('second'),
          ];
          session.entries.addAll(photographs);
          await session.start();
          expect(
            photographs.map((e) => e.state),
            everyElement(UploadState.ready),
          );
          expect(photographs.map((e) => e.reason), everyElement(isNull));
          expect(session.busy, isFalse);
          expect(session.signInRequired, isTrue);
          await tester.pump(const Duration(seconds: 90));
          expect(repository.completions, 0);
          await session.start();
          expect(repository.completions, 0);
          await session.resumeAfterSignIn();
          expect(session.signInRequired, isFalse);
          expect(session.entries, isEmpty);
          expect(session.sentCount, 2);
          session.close();
        },
      );
    }
  }

  testWidgets(
    'a transient failure after Stop stays Ready without automatic retry',
    (tester) async {
      final Completer<void> gate = Completer<void>();
      final RetryTransferRepository repository = RetryTransferRepository()
        ..holdFirst = false
        ..failureGate = gate
        ..failures.add(const ApiFailure('lost', code: 'network'));
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'stop-flight',
      );
      final ManifestEntry photograph = entry('stop-flight');
      session.entries.add(photograph);
      final Future<void> send = session.start();
      await tester.pump();
      session.stop();
      gate.complete();
      await send;
      expect(photograph.state, UploadState.ready);
      expect(photograph.reason, 'Stopped. Send to continue.');
      await tester.pump(const Duration(seconds: 90));
      expect(repository.offsets, [0]);
      session.close();
    },
  );

  for (final ApiFailure failure in [
    const ApiFailure('image_codec_disabled', status: 503),
    const ApiFailure('detail', code: 'intake_sensitivity_mismatch'),
    const ApiFailure('detail', status: 422),
  ]) {
    testWidgets(
      '${failure.message}/${failure.code}/${failure.status} retains the photo without automatic transfer retry',
      (tester) async {
        final RetryTransferRepository repository = RetryTransferRepository()
          ..holdFirst = false
          ..failures.add(failure);
        final IntakeTransferSession session = IntakeTransferSession(
          repository,
          scope,
          'refusal',
        );
        final ManifestEntry photograph = entry('refusal');
        session.entries.add(photograph);
        await session.start();
        expect(photograph.state, UploadState.failed);
        expect(photograph.file, isNotNull);
        expect(photograph.session?['upload_id'], photograph.digest);
        await tester.pump(const Duration(seconds: 120));
        expect(repository.offsets, [0]);
        expect(intakeStatus(photograph).status, 'Not sent');
        session.close();
      },
    );
  }

  for (final String saved in ['not json', '{"unexpected":true}', '[17]']) {
    test('G1 sends a new photo after restoring $saved', () async {
      final String storageKey = 'upload-handles-v1:broken:${scope.key}';
      SharedPreferences.setMockInitialValues({storageKey: saved});
      final TransferRepository repository = TransferRepository()
        ..holdFirst = false
        ..completionResponse = {
          'specimen_id': 'new-photo',
          'status': 'pending',
        };
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'broken',
      );
      addTearDown(session.close);
      await session.restore();
      expect(session.restoreError, 'Earlier photos could not be restored.');
      expect(session.entries, isEmpty);

      final ManifestEntry photo = entry('new-photo');
      session.entries.add(photo);
      Object? sendError;
      try {
        await session.start();
      } catch (error) {
        sendError = error;
      }
      expect(repository.started, ['new-photo.jpg']);
      expect(sendError, isNull);
      expect(repository.completions, 1);
      expect(photo.file, isNull);
      expect(intakeStatus(photo).status, 'Starting');
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final dynamic rewritten = jsonDecode(prefs.getString(storageKey)!);
      expect(rewritten, isA<List<dynamic>>());
      expect(rewritten, hasLength(1));
      expect(rewritten.single['specimen_id'], 'new-photo');
      expect(rewritten.single['upload_id'], photo.digest);
    });
  }

  test('an unreadable saved list uses the short restore banner', () async {
    SharedPreferences.setMockInitialValues({
      'upload-handles-v1:broken:${scope.key}': 'not json',
    });
    final TransferRepository repository = TransferRepository();
    final IntakeTransferSession session = IntakeTransferSession(
      repository,
      scope,
      'broken',
    );
    await session.restore();
    expect(session.restoreError, 'Earlier photos could not be restored.');
    expect(session.entries, isEmpty);
    expect(repository.started, isEmpty);
    session.close();
  });

  test(
    'resuming sign-in does not retry an earlier permanent rejection',
    () async {
      final RetryTransferRepository repository = RetryTransferRepository()
        ..holdFirst = false
        ..createFailures.addAll([
          const ApiFailure('refused', status: 422),
          const ApiFailure('sign in', status: 401),
        ]);
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'resume-rejections',
      );
      final ManifestEntry refused = entry('refused');
      final ManifestEntry paused = entry('paused');
      session.entries.addAll([refused, paused]);
      await session.start();
      expect(refused.state, UploadState.failed);
      expect(paused.state, UploadState.ready);
      await session.resumeAfterSignIn();
      expect(refused.state, UploadState.failed);
      expect(paused.state, UploadState.accepted);
      expect(repository.createKeys, [
        'intake-${refused.digest}',
        'intake-${paused.digest}',
        'intake-${paused.digest}',
      ]);
      session.close();
    },
  );

  test(
    'sending a newly added photo does not retry a prior permanent rejection',
    () async {
      final RetryTransferRepository repository = RetryTransferRepository()
        ..holdFirst = false
        ..createFailures.add(const ApiFailure('refused', status: 422));
      final IntakeTransferSession session = IntakeTransferSession(
        repository,
        scope,
        'new-after-refusal',
      );
      final ManifestEntry refused = entry('refused');
      session.entries.add(refused);
      await session.start();
      final ManifestEntry added = entry('added');
      session.entries.add(added);
      await session.start();
      expect(refused.state, UploadState.failed);
      expect(added.state, UploadState.accepted);
      expect(repository.createKeys, [
        'intake-${refused.digest}',
        'intake-${added.digest}',
      ]);
      session.close();
    },
  );

  for (final bool atCreate in [true, false]) {
    testWidgets(
      'duplicate ${atCreate ? 'at creation' : 'at completion'} leaves and is counted separately',
      (tester) async {
        final TransferRepository repository = atCreate
            ? DuplicateTransferRepository()
            : (TransferRepository()
                ..completionResponse = {'upload_state': 'duplicate'});
        repository.holdFirst = false;
        final IntakeTransferSession session = IntakeTransferSession(
          repository,
          scope,
          'duplicate-$atCreate',
        );
        session.entries.add(entry('duplicate'));
        await session.start();
        expect(session.entries, isEmpty);
        expect(session.duplicateCount, 1);
        expect(session.sentCount, 0);
        expect(session.departureCount, 1);
        expect(session.summary, '1 duplicate');
        expect(session.needsProcessingPoll, isFalse);
        session.close();
      },
    );
  }
}

class DuplicateTransferRepository extends TransferRepository {
  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => {'upload_id': 'duplicate', 'state': 'duplicate'};
}
