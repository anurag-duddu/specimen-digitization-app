import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart' show ApiFailure;
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_repository.dart';

import 'probe_helpers.dart';

class ProbeRepository implements ResearchRepository {
  int reads = 0;
  int posts = 0;

  @override
  Future<ResearchThread> read(ResearchScope scope) async {
    reads++;
    return probeThread(posts == 0 ? 'failed-thread' : 'queued-thread');
  }

  @override
  Future<ResearchRetryAck> retry(
    ResearchScope scope,
    String fieldKey, {
    required int expectedCheckpointRevision,
  }) async {
    posts++;
    return ResearchRetryAck.fromJson(
      probeFixture('queued-retry'),
      expectedScope: scope,
      expectedFieldKey: fieldKey,
      expectedCheckpointRevision: expectedCheckpointRevision,
    );
  }
}

void main() {
  test('positive control: an unchanged advertised retry sends once', () async {
    final repository = ProbeRepository();
    final controller = ResearchController(
      repository: repository,
      scope: probeScope(),
      recordRevision: 100,
    );
    addTearDown(controller.dispose);
    await controller.ensureLoaded();
    await controller.retryField('taxon');
    expect(repository.posts, 1);
    expect(repository.reads, 2);
    expect(
      controller.thread!.field('taxon')!.workState,
      ResearchWorkState.retryScheduled,
    );
  });

  for (final action in ['record', 'generation', 'readOnly', 'denial']) {
    test(
      'synchronous $action during retry notification prevents old POST',
      () async {
        final repository = ProbeRepository();
        final access = StreamController<ApiFailure>.broadcast(sync: true);
        addTearDown(access.close);
        final controller = ResearchController(
          repository: repository,
          scope: probeScope(),
          recordRevision: 100,
          accessFailures: access.stream,
        );
        addTearDown(controller.dispose);
        await controller.ensureLoaded();
        var invalidated = false;
        controller.addListener(() {
          if (invalidated ||
              controller.networkState != ResearchNetworkState.submitting) {
            return;
          }
          invalidated = true;
          switch (action) {
            case 'record':
              controller.bind(scope: controller.scope, recordRevision: 101);
            case 'generation':
              controller.bind(
                scope: ResearchScope.fromJson({
                  ...controller.scope.json,
                  'generation': 2,
                }),
                recordRevision: 100,
              );
            case 'readOnly':
              controller.bind(
                scope: controller.scope,
                recordRevision: 100,
                readOnly: true,
              );
            case 'denial':
              access.add(
                const ApiFailure('Synthetic revoked access', status: 403),
              );
          }
        });
        await controller.retryField('taxon');
        expect(invalidated, isTrue);
        expect(
          repository.posts,
          0,
          reason: 'A discarded ACK cannot undo a stale external dispatch.',
        );
        expect(repository.reads, 1);
      },
    );
  }

  for (final action in ['record', 'generation', 'readOnly', 'denial']) {
    test(
      'synchronous $action during load notification prevents old GET',
      () async {
        final repository = ProbeRepository();
        final access = StreamController<ApiFailure>.broadcast(sync: true);
        addTearDown(access.close);
        final controller = ResearchController(
          repository: repository,
          scope: probeScope(),
          recordRevision: 100,
          accessFailures: access.stream,
        );
        addTearDown(controller.dispose);
        var invalidated = false;
        controller.addListener(() {
          if (invalidated ||
              controller.networkState != ResearchNetworkState.loading) {
            return;
          }
          invalidated = true;
          switch (action) {
            case 'record':
              controller.bind(scope: controller.scope, recordRevision: 101);
            case 'generation':
              controller.bind(
                scope: ResearchScope.fromJson({
                  ...controller.scope.json,
                  'generation': 2,
                }),
                recordRevision: 100,
              );
            case 'readOnly':
              controller.bind(
                scope: controller.scope,
                recordRevision: 100,
                readOnly: true,
              );
            case 'denial':
              access.add(
                const ApiFailure('Synthetic revoked access', status: 401),
              );
          }
        });
        await controller.ensureLoaded();
        expect(invalidated, isTrue);
        expect(repository.reads, 0);
        expect(repository.posts, 0);
        expect(controller.thread, isNull);
      },
    );
  }
}
