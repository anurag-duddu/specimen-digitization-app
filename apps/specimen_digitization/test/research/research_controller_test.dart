import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart' show ApiFailure;
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_repository.dart';

import 'research_fixture.dart';

class ControlledRepository implements ResearchRepository {
  int reads = 0;
  final retries = <(String, int)>[];
  Future<ResearchThread> Function(ResearchScope)? onRead;
  Future<ResearchRetryAck> Function(ResearchScope, String, int)? onRetry;
  @override
  Future<ResearchThread> read(ResearchScope scope) async {
    reads++;
    return onRead == null ? boundThread(scope) : await onRead!(scope);
  }

  @override
  Future<ResearchRetryAck> retry(
    ResearchScope scope,
    String fieldKey, {
    required int expectedCheckpointRevision,
  }) async {
    retries.add((fieldKey, expectedCheckpointRevision));
    return onRetry == null
        ? ResearchRetryAck.fromJson(
            researchFixture('queued-retry'),
            expectedScope: scope,
            expectedFieldKey: fieldKey,
            expectedCheckpointRevision: expectedCheckpointRevision,
          )
        : await onRetry!(scope, fieldKey, expectedCheckpointRevision);
  }
}

ResearchThread boundThread(
  ResearchScope scope, [
  String name = 'failed-thread',
]) {
  final json = researchFixture(name);
  json['scope'] = scope.json;
  for (final field in json['fields'] as List) {
    if (field['checkpoint'] != null) field['checkpoint']['scope'] = scope.json;
  }
  return ResearchThread.fromJson(json, expectedScope: scope);
}

ResearchController controllerFor(
  ControlledRepository repository, {
  bool readOnly = false,
  Stream<ApiFailure>? accessFailures,
}) => ResearchController(
  repository: repository,
  scope: trustedResearchScope(),
  recordRevision: 100,
  readOnly: readOnly,
  accessFailures: accessFailures,
);

void main() {
  test('construction is lazy and concurrent reveal starts one read', () async {
    final repository = ControlledRepository();
    final held = Completer<ResearchThread>();
    repository.onRead = (_) => held.future;
    final controller = controllerFor(repository);
    addTearDown(controller.dispose);
    expect(repository.reads, 0);
    final first = controller.ensureLoaded();
    final second = controller.ensureLoaded();
    expect(repository.reads, 1);
    held.complete(fixtureThread());
    await Future.wait([first, second]);
    expect(controller.canRetry('taxon'), isTrue);
  });

  for (final change in [
    'record',
    'generation',
    'input',
    'profile',
    'sensitive',
    'job',
    'specimen',
  ]) {
    test(
      'late read cannot restore content after binding change: $change',
      () async {
        final repository = ControlledRepository();
        final held = Completer<ResearchThread>();
        repository.onRead = (_) => held.future;
        final controller = controllerFor(repository);
        addTearDown(controller.dispose);
        final pending = controller.ensureLoaded();
        final original = controller.scope;
        final next = ResearchScope.fromJson({
          ...original.json,
          if (change == 'generation') 'generation': 2,
          if (change == 'input') 'input_digest': 'b' * 64,
          if (change == 'profile') 'profile_digest': 'c' * 64,
          if (change == 'sensitive') 'sensitive': true,
          if (change == 'job') 'job_id': 'other-job',
          if (change == 'specimen') 'specimen_id': 'other-specimen',
        });
        controller.bind(
          scope: next,
          recordRevision: change == 'record' ? 101 : 100,
        );
        held.complete(fixtureThread());
        await pending;
        expect(controller.thread, isNull);
        expect(controller.networkState, ResearchNetworkState.idle);
        repository.onRead = (scope) async => boundThread(scope);
        await controller.ensureLoaded();
        expect(controller.thread!.scope.matches(next), isTrue);
      },
    );
  }

  test(
    'queued acknowledgment rereads without changing values or record revision',
    () async {
      final repository = ControlledRepository();
      final freshRead = Completer<ResearchThread>();
      final started = Completer<void>();
      repository.onRead = (scope) {
        if (repository.reads == 1) return Future.value(boundThread(scope));
        started.complete();
        return freshRead.future;
      };
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.ensureLoaded();
      final retry = controller.retryField('taxon');
      await started.future;
      expect(repository.retries, [('taxon', 1)]);
      expect(controller.recordRevision, 100);
      expect(controller.queuedAck, isNotNull);
      expect(controller.thread, isNull);
      expect(controller.networkState, ResearchNetworkState.loading);
      expect(controller.message, contains('queued'));
      freshRead.complete(fixtureThread('queued-thread'));
      await retry;
      expect(repository.reads, 2);
      expect(
        controller.thread!.field('taxon')!.workState,
        ResearchWorkState.retryScheduled,
      );
      expect(
        controller.thread!.field('country')!.value.literal,
        'Synthetic country',
      );
      expect(controller.canRetry('taxon'), isFalse);
    },
  );

  test(
    'conflict performs one fresh GET without resubmitting the new revision',
    () async {
      final repository = ControlledRepository();
      repository.onRetry = (_, _, _) async =>
          throw const ResearchFailure(ResearchFailureKind.conflict);
      repository.onRead = (scope) async {
        final json = researchFixture('failed-thread');
        if (repository.reads > 1) {
          fixtureField(json, 'taxon')['checkpoint']['revision'] = 2;
        }
        return ResearchThread.fromJson(json, expectedScope: scope);
      };
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.ensureLoaded();
      await controller.retryField('taxon');
      expect(repository.retries, [('taxon', 1)]);
      expect(repository.reads, 2);
      expect(controller.thread!.field('taxon')!.checkpoint!.revision, 2);
      expect(controller.message, contains('changed'));
    },
  );

  test(
    'late queued ACK after record change does not trigger a fresh read',
    () async {
      final repository = ControlledRepository();
      final held = Completer<ResearchRetryAck>();
      repository.onRetry = (_, _, _) => held.future;
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.ensureLoaded();
      final pending = controller.retryField('taxon');
      controller.bind(scope: controller.scope, recordRevision: 101);
      held.complete(
        ResearchRetryAck.fromJson(
          researchFixture('queued-retry'),
          expectedScope: trustedResearchScope(),
          expectedFieldKey: 'taxon',
          expectedCheckpointRevision: 1,
        ),
      );
      await pending;
      expect(controller.thread, isNull);
      expect(controller.queuedAck, isNull);
      expect(repository.reads, 1);
    },
  );

  for (final kind in [
    ResearchFailureKind.unauthenticated,
    ResearchFailureKind.forbidden,
  ]) {
    test(
      'access denial clears cached content and requires host recheck: ${kind.name}',
      () async {
        final repository = ControlledRepository();
        final controller = controllerFor(repository);
        addTearDown(controller.dispose);
        await controller.ensureLoaded();
        repository.onRead = (_) async => throw ResearchFailure(kind);
        await controller.refresh();
        expect(controller.thread, isNull);
        expect(controller.queuedAck, isNull);
        expect(controller.networkState, ResearchNetworkState.denied);
        await controller.refresh();
        controller.bind(scope: controller.scope, recordRevision: 101);
        await controller.ensureLoaded();
        expect(repository.reads, 2);
        expect(controller.canRetry('taxon'), isFalse);
      },
    );
  }

  test(
    'existing access failure stream rejects a pending success after revocation',
    () async {
      final access = StreamController<ApiFailure>.broadcast(sync: true);
      addTearDown(access.close);
      final repository = ControlledRepository();
      final held = Completer<ResearchThread>();
      repository.onRead = (_) => held.future;
      final controller = controllerFor(
        repository,
        accessFailures: access.stream,
      );
      addTearDown(controller.dispose);
      final pending = controller.ensureLoaded();
      access.add(const ApiFailure('RAW PRIVATE', status: 403));
      held.complete(fixtureThread());
      await pending;
      expect(controller.thread, isNull);
      expect(controller.networkState, ResearchNetworkState.denied);
      expect(controller.message, isNot(contains('RAW')));
    },
  );

  test(
    'disposed controller rejects late results without notification or content',
    () async {
      final repository = ControlledRepository();
      final held = Completer<ResearchThread>();
      repository.onRead = (_) => held.future;
      final controller = controllerFor(repository);
      final pending = controller.ensureLoaded();
      controller.dispose();
      held.complete(fixtureThread());
      await pending;
      expect(controller.thread, isNull);
      expect(controller.queuedAck, isNull);
    },
  );

  test('read-only view and missing capabilities never post', () async {
    final repository = ControlledRepository();
    final controller = controllerFor(repository, readOnly: true);
    addTearDown(controller.dispose);
    await controller.ensureLoaded();
    await controller.retryField('taxon');
    expect(repository.retries, isEmpty);
    controller.bind(
      scope: controller.scope,
      recordRevision: 100,
      readOnly: false,
    );
    repository.onRead = (scope) async {
      final json = researchFixture('failed-thread');
      fixtureField(json, 'taxon')['actions'] = [];
      return ResearchThread.fromJson(json, expectedScope: scope);
    };
    await controller.ensureLoaded();
    await controller.retryField('taxon');
    expect(repository.retries, isEmpty);
  });

  test(
    'unconfirmed retry clears stale capability and never retries automatically',
    () async {
      final repository = ControlledRepository();
      repository.onRetry = (_, _, _) async => throw StateError('PRIVATE TOKEN');
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.ensureLoaded();
      await controller.retryField('taxon');
      expect(controller.thread, isNull);
      expect(controller.canRetry('taxon'), isFalse);
      expect(controller.message, isNot(contains('PRIVATE')));
      expect(repository.retries, hasLength(1));
      expect(repository.reads, 1);
    },
  );
}
