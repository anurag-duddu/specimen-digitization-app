import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_host.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_repository.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'research_fixture.dart';

class _FieldHostApi extends ApiSpecimenRepository {
  _FieldHostApi(this.respond)
    : super(
        baseUrl: Uri.parse('https://api.example.test'),
        token: () async => 'test-only-token',
      );
  final Future<Json> Function(String path) respond;
  final paths = <String>[];
  final failures = StreamController<ApiFailure>.broadcast(sync: true);
  @override
  Stream<ApiFailure> get accessFailures => failures.stream;
  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    String? key,
    Map<String, String>? query,
    dynamic bytes,
    Map<String, String>? headers,
    int? verificationEpoch,
  }) {
    paths.add('$method $path');
    return respond(path);
  }

  @override
  void close() {
    failures.close();
    super.close();
  }
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('field-scoped research shares one lazy record read', (
    tester,
  ) async {
    final scope = trustedResearchScope();
    final collection = CollectionScope(
      organizationId: scope.organizationId,
      collectionId: scope.collectionId,
      name: 'Fixture collection',
    );
    final specimen = Specimen({
      'specimen_id': scope.specimenId,
      'revision': 1,
      'record_version_id': 'fixture-host:1',
      'sensitive': scope.sensitive,
    });
    final read = Completer<Json>();
    final api = _FieldHostApi((path) async {
      if (path.endsWith('/research/current')) {
        return {
          'contract_version': 'canonical-binding/v2',
          'canonical': {
            'organization_id': collection.organizationId,
            'collection_id': collection.collectionId,
            'specimen_id': specimen.id,
            'record_revision': specimen.revision,
            'host_record_version_id': specimen.recordVersionId,
            'sensitive': scope.sensitive,
          },
          'scope': scope.json,
          'capabilities': {'read': true},
        };
      }
      if (path.endsWith('/research/derivations/capability')) {
        return {
          'contract_version': 'research-derivation-capability/v1',
          'available': false,
          'blocked_reason': 'worker_unavailable',
          'canonical_revision': specimen.revision,
          'eligible_fields': <String>[],
        };
      }
      if (path.endsWith('/thread')) return read.future;
      throw StateError('Unexpected research path: $path');
    });
    addTearDown(api.close);
    await _pump(
      tester,
      ResearchHost(
        repository: api,
        collection: collection,
        specimen: specimen,
        builder: (context, researchForField) => Column(
          children: [
            researchForField('country', null),
            researchForField('taxon', null),
          ],
        ),
      ),
    );
    expect(find.byType(ResearchThreadCard), findsNWidgets(2));
    expect(find.text('Field research'), findsNothing);
    expect(api.paths, hasLength(1));
    await tester.tap(find.text('Research').first);
    await tester.pump();
    await tester.tap(find.text('Research').last);
    await tester.pump();
    expect(api.paths, hasLength(3));
    expect(
      api.paths.where((path) => path.endsWith('/research/current')),
      hasLength(1),
    );
    expect(
      api.paths.where(
        (path) => path.endsWith('/research/derivations/capability'),
      ),
      hasLength(1),
    );
    expect(api.paths.where((path) => path.endsWith('/thread')), hasLength(1));
    read.complete(researchFixture('failed-thread'));
    await tester.pumpAndSettle();
    expect(api.paths, hasLength(3));
    expect(find.byType(ResearchThreadCard), findsNWidgets(2));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('field research gives one value and discloses provenance', (
    tester,
  ) async {
    final json = researchFixture('failed-thread');
    final raw = fixtureField(json, 'country');
    final value = <String, dynamic>{
      ...raw['value'] as Map<String, dynamic>,
      'literal': 'Written country',
      'parsed': 'Interpreted country',
      'normalized': 'Canonical country',
    };
    raw['value'] = value;
    raw['checkpoint']['resolution']['value'] = value;
    raw['checkpoint']['resolution']['reason'] = 'internal_reason_code';
    final field = ResearchThread.fromJson(
      json,
      expectedScope: trustedResearchScope(),
    ).field('country');
    await _pump(
      tester,
      ResearchThreadCard(
        scope: trustedResearchScope(),
        recordRevision: 1,
        fieldKey: 'country',
        fieldLabel: 'Country',
        field: field,
        fieldCentered: true,
        networkState: ResearchNetworkState.ready,
        onRefresh: () {},
      ),
    );
    await tester.tap(find.text('Research'));
    await tester.pumpAndSettle();
    expect(find.text('Canonical country'), findsOneWidget);
    expect(find.text('As written'), findsNothing);
    expect(find.text('internal_reason_code'), findsNothing);
    expect(find.widgetWithText(UiButton, 'Accept proposal'), findsNothing);
    expect(
      find.widgetWithText(UiButton, 'Fill remaining fields'),
      findsNothing,
    );
    final provenanceHeader = find
        .descendant(
          of: find.byWidgetPredicate(
            (widget) =>
                widget is UiDisclosure && widget.title == 'Value provenance',
          ),
          matching: find.byType(Pressable),
        )
        .first;
    await tester.ensureVisible(provenanceHeader);
    await tester.pumpAndSettle();
    expect(provenanceHeader.hitTestable(), findsOneWidget);
    await tester.tap(provenanceHeader);
    await tester.pumpAndSettle();
    expect(find.text('Written country'), findsOneWidget);
    expect(find.text('Interpreted country'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('unavailable research does not guess a network failure', () {
    const unavailable = ResearchFailure(ResearchFailureKind.unavailable);
    expect(unavailable.message, isNot(contains('connection')));
    expect(
      const ResearchFailure(ResearchFailureKind.unauthenticated).message,
      contains('Sign in'),
    );
    expect(
      const ResearchFailure(ResearchFailureKind.forbidden).message,
      contains('collection'),
    );
  });
}
