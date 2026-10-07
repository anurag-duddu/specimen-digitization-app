import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/research/research_host.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'research_fixture.dart';
import 'research_host_test.dart' as host;

Json thread(String name, int revision) {
  final json = researchFixture(name)..['scope'] = host.trusted.json;
  json['canonical_revision'] = revision;
  for (final field in json['fields'] as List) {
    if (field['checkpoint'] != null) {
      field['checkpoint']['scope'] = host.trusted.json;
    }
  }
  return json;
}

Future<void> pump(
  WidgetTester tester,
  host.HostApi api, {
  int epoch = 0,
  int revision = 1,
  bool enabled = true,
  void Function(Object, bool)? onPaused,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: ResearchHost(
          repository: api,
          collection: host.collection,
          specimen: host.item(null, revision),
          refreshEpoch: epoch,
          refreshEnabled: enabled,
          onPollingPaused: onPaused,
          builder: (context, forField) => forField('taxon', null),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

ResearchThreadCard card(WidgetTester tester) =>
    tester.widget<ResearchThreadCard>(find.byType(ResearchThreadCard));
int reads(host.HostApi api) =>
    api.paths.where((path) => path.endsWith('/thread')).length;
void main() {
  testWidgets(
    'verified same-revision ticks refresh opened research but preserve lazy reads',
    (tester) async {
      var name = 'failed-thread';
      final api = host.HostApi(
        (path) async => path.endsWith('/research/current')
            ? host.discovery()
            : thread(name, 1),
      );
      addTearDown(api.close);
      await pump(tester, api);
      expect(reads(api), 0);
      await pump(tester, api, epoch: 1);
      expect(reads(api), 0);
      card(tester).onLoad?.call();
      await tester.pumpAndSettle();
      expect(reads(api), 1);
      name = 'queued-thread';
      await pump(tester, api, epoch: 2);
      expect(reads(api), 2);
      expect(card(tester).field?.workState, ResearchWorkState.retryScheduled);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets('canonical version change reloads an already opened disclosure', (
    tester,
  ) async {
    var revision = 1;
    final api = host.HostApi(
      (path) async => path.endsWith('/research/current')
          ? host.discovery(null, revision)
          : thread('queued-thread', revision),
    );
    addTearDown(api.close);
    await pump(tester, api);
    card(tester).onLoad?.call();
    await tester.pumpAndSettle();
    revision = 2;
    await pump(tester, api, revision: 2, epoch: 1);
    expect(reads(api), 2);
    expect(card(tester).recordRevision, 2);
    expect(card(tester).networkState, ResearchNetworkState.ready);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('inactive refresh epochs issue no research requests', (
    tester,
  ) async {
    final api = host.HostApi(
      (path) async => path.endsWith('/research/current')
          ? host.discovery()
          : thread('failed-thread', 1),
    );
    addTearDown(api.close);
    await pump(tester, api);
    card(tester).onLoad?.call();
    await tester.pumpAndSettle();
    final before = api.paths.length;
    await pump(tester, api, epoch: 1, enabled: false);
    expect(api.paths.length, before);
    await pump(tester, api, epoch: 2);
    expect(reads(api), 2);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
    'research submission pauses record polling and cannot overlap a refresh tick',
    (tester) async {
      final held = Completer<Json>();
      final pauses = <bool>[];
      var name = 'failed-thread';
      final api = host.HostApi((path) async {
        if (path.endsWith('/research/current')) return host.discovery();
        if (path.endsWith('/retry')) return held.future;
        return thread(name, 1);
      });
      addTearDown(api.close);
      void onPaused(Object owner, bool value) => pauses.add(value);
      await pump(tester, api, onPaused: onPaused);
      card(tester).onLoad?.call();
      await tester.pumpAndSettle();
      card(tester).onRetry?.call();
      await tester.pump();
      expect(pauses, [true]);
      final before = api.paths.length;
      await pump(tester, api, epoch: 1, onPaused: onPaused);
      expect(api.paths.length, before);
      name = 'queued-thread';
      held.complete(researchFixture('queued-retry'));
      await tester.pumpAndSettle();
      expect(pauses, [true, false]);
      expect(card(tester).field?.workState, ResearchWorkState.retryScheduled);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
