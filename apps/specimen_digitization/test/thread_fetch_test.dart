// The record screen fetches its thread (UI.md T2.6).
//
// Three layers, each with its own way to fail: the repository asks the route
// S5's #171 serves and reads its answers; the workspace controller asks once
// per record version and keeps the thread with the open record; the
// workbench hands what the controller holds to the segments that draw it.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/thread/thread.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'golden/golden_harness.dart';
import 'widget_test.dart' show TestRepository, TestSession, fixture;

/// S5's canonical thread (#171 at `c149115`).
Json canonical() =>
    jsonDecode(File('test/fixtures/thread-example.json').readAsStringSync())
        as Json;

/// The canonical thread's specimen, which tells a fetched thread apart.
const String canonicalSpecimen = '00000000-0000-4000-8000-000000000003';

const CollectionScope scope = CollectionScope(
  organizationId: 'org-1',
  collectionId: 'insects',
  name: 'Insects',
  permissions: <String>['reviewer'],
);

/// An error body as the API's handler writes it.
String refusal(String code) => jsonEncode(<String, dynamic>{
  'error': <String, dynamic>{
    'code': code,
    'category': 'test',
    'message': 'Refused by the test.',
    'retryable': code == 'runtime_unavailable',
    'request_id': 'request-1',
    'details': <String, dynamic>{},
  },
});

/// Lets the controller's fetch, and the answer it waits for, finish.
Future<void> settle() => Future<void>.delayed(Duration.zero);

/// A collection whose open record's thread answers as a test says.
class ThreadRepository extends TestRepository {
  /// The record the workspace serves. A test moves its version.
  Specimen record = fixture;

  /// The records whose thread was asked for, in order.
  final List<String> asked = <String>[];

  /// How each thread request is answered: the canonical thread unless a
  /// test says otherwise.
  Future<SpecimenThread?> Function(String specimenId) answer = (String _) =>
      Future<SpecimenThread?>.value(SpecimenThread.fromJson(canonical()));

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async =>
      id == record.id
      ? record
      : Specimen(<String, dynamic>{...record.data, 'specimen_id': id});

  @override
  Future<SpecimenThread?> thread(
    CollectionScope scope,
    String specimenId, {
    String? runId,
  }) {
    asked.add(specimenId);
    return answer(specimenId);
  }
}

void main() {
  group('the repository asks the route #171 serves', () {
    late List<http.Request> sent;

    ApiSpecimenRepository answering(http.Response Function() respond) {
      sent = <http.Request>[];
      final ApiSpecimenRepository repository = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8000'),
        token: () async => 'test-only-token',
        client: MockClient((http.Request request) async {
          sent.add(request);
          return respond();
        }),
      );
      addTearDown(repository.close);
      return repository;
    }

    test("the active run's thread, read as a typed thread", () async {
      final ApiSpecimenRepository repository = answering(
        () => http.Response(jsonEncode(canonical()), 200),
      );

      final SpecimenThread? thread = await repository.thread(scope, 'sp/1');

      expect(sent, hasLength(1));
      expect(sent.single.method, 'GET');
      expect(
        sent.single.url.path,
        '/v1/organizations/org-1/specimens/sp%2F1/thread',
      );
      expect(sent.single.url.hasQuery, isFalse);
      expect(thread?.specimenId, canonicalSpecimen);
      expect(thread?.regions, hasLength(2));
    });

    test('a previous run is named by its id', () async {
      final ApiSpecimenRepository repository = answering(
        () => http.Response(jsonEncode(canonical()), 200),
      );

      await repository.thread(scope, 'sp-1', runId: 'run-2');

      expect(sent.single.url.queryParameters, <String, String>{
        'run_id': 'run-2',
      });
    });

    test('a run the server keeps no thread for is no thread (404)', () async {
      final ApiSpecimenRepository repository = answering(
        () => http.Response(refusal('not_found'), 404),
      );

      expect(await repository.thread(scope, 'sp-1'), isNull);
      expect(sent, hasLength(1));
    });

    for (final (int status, String code) in <(int, String)>[
      (413, 'thread_limit_exceeded'),
      (503, 'runtime_unavailable'),
    ]) {
      test('$status is a refusal the record screen names', () async {
        final ApiSpecimenRepository repository = answering(
          () => http.Response(refusal(code), status),
        );

        await expectLater(
          repository.thread(scope, 'sp-1'),
          throwsA(
            isA<ApiFailure>()
                .having((ApiFailure f) => f.status, 'status', status)
                .having((ApiFailure f) => f.code, 'code', code),
          ),
        );
      });
    }
  });

  group('the controller keeps the thread with the open record', () {
    late ThreadRepository repository;
    late WorkspaceController controller;

    setUp(() async {
      repository = ThreadRepository();
      final TestSession session = TestSession();
      controller = WorkspaceController(
        repository: repository,
        session: session,
      );
      addTearDown(() {
        controller.dispose();
        session.controller.close();
      });
      await controller.checkAccess();
    });

    test('a record that opens asks for its thread, once a version', () async {
      await controller.openSpecimen(fixture.id);
      await settle();

      expect(repository.asked, <String>[fixture.id]);
      expect(controller.thread?.specimenId, canonicalSpecimen);
      expect(controller.threadGap, isNull);

      await controller.refresh(quiet: true);
      await settle();

      expect(
        repository.asked,
        hasLength(1),
        reason: 'a poll that brings the same version asks for nothing',
      );
    });

    test('a new version asks again and keeps the thread on screen until '
        'the new one arrives', () async {
      await controller.openSpecimen(fixture.id);
      await settle();
      final SpecimenThread? first = controller.thread;
      expect(first, isNotNull);

      final Completer<SpecimenThread?> pending = Completer<SpecimenThread?>();
      repository.answer = (String _) => pending.future;
      repository.record = Specimen(<String, dynamic>{
        ...fixture.data,
        'revision': fixture.revision + 1,
      });
      await controller.refresh(quiet: true);
      await settle();

      expect(repository.asked, hasLength(2));
      expect(
        controller.thread,
        same(first),
        reason: 'the Readings segment does not rebuild while it is asked',
      );

      final SpecimenThread second = SpecimenThread.fromJson(canonical());
      pending.complete(second);
      await settle();

      expect(controller.thread, same(second));
    });

    test("another record never shows the last one's thread", () async {
      await controller.openSpecimen(fixture.id);
      await settle();
      expect(controller.thread, isNotNull);

      final Map<String, Completer<SpecimenThread?>> answers =
          <String, Completer<SpecimenThread?>>{};
      repository.answer = (String id) =>
          (answers[id] = Completer<SpecimenThread?>()).future;
      await controller.openSpecimen('fixture-002');
      await settle();

      expect(controller.selected?.id, 'fixture-002');
      expect(controller.thread, isNull);

      await controller.openSpecimen('fixture-003');
      await settle();
      answers['fixture-002']!.complete(SpecimenThread.fromJson(canonical()));
      answers['fixture-003']!.complete(null);
      await settle();

      expect(repository.asked, <String>[
        fixture.id,
        'fixture-002',
        'fixture-003',
      ]);
      expect(
        controller.thread,
        isNull,
        reason: 'an answer for a record no longer open is dropped',
      );
    });

    test('a 404 is no thread, and nothing is said', () async {
      repository.answer = (String _) => Future<SpecimenThread?>.value();
      await controller.openSpecimen(fixture.id);
      await settle();

      expect(controller.thread, isNull);
      expect(controller.threadGap, isNull);
    });

    test('a 413 is named, and not asked again for that version', () async {
      repository.answer = (String _) => Future<SpecimenThread?>.error(
        const ApiFailure(
          'Refused by the test.',
          code: 'thread_limit_exceeded',
          status: 413,
        ),
      );
      await controller.openSpecimen(fixture.id);
      await settle();

      expect(controller.thread, isNull);
      expect(controller.threadGap, ThreadGap.tooLarge);
      expect(controller.error, isNull, reason: 'the record itself is fine');

      await controller.refresh(quiet: true);
      await settle();

      expect(repository.asked, hasLength(1));
      expect(controller.threadGap, ThreadGap.tooLarge);
    });

    for (final (String name, Object failure) in <(String, Object)>[
      (
        'a 503',
        const ApiFailure(
          'Refused by the test.',
          code: 'runtime_unavailable',
          status: 503,
        ),
      ),
      (
        'a failed connection',
        const ApiFailure('Connection interrupted.', code: 'network'),
      ),
    ]) {
      test('$name is named, and the next refresh asks again', () async {
        repository.answer = (String _) =>
            Future<SpecimenThread?>.error(failure);
        await controller.openSpecimen(fixture.id);
        await settle();

        expect(controller.thread, isNull);
        expect(controller.threadGap, ThreadGap.unreadable);
        expect(controller.error, isNull, reason: 'the record itself is fine');
        expect(repository.asked, hasLength(1));

        repository.answer = (String _) =>
            Future<SpecimenThread?>.value(SpecimenThread.fromJson(canonical()));
        await controller.refresh(quiet: true);
        await settle();

        expect(repository.asked, hasLength(2));
        expect(controller.thread?.specimenId, canonicalSpecimen);
        expect(controller.threadGap, isNull);
      });
    }
  });

  group('the workbench draws what the controller fetched', () {
    setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

    Future<void> pumpRecord(
      WidgetTester tester,
      ThreadRepository repository,
    ) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1440, 900);
      addTearDown(tester.view.reset);
      final TestSession session = TestSession();
      addTearDown(session.controller.close);
      await tester.pumpWidget(
        SpecimenDigitizationApp(
          session: session,
          repository: repository,
          initialLocation: goldenSpecimenLocation,
          motionPreferences: MemoryMotionPreferenceStore(),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('the fetched thread reaches the segments', (
      WidgetTester tester,
    ) async {
      final ThreadRepository repository = ThreadRepository();
      await pumpRecord(tester, repository);

      final ReviewWorkbench workbench = tester.widget<ReviewWorkbench>(
        find.byType(ReviewWorkbench),
      );
      expect(repository.asked, <String>[goldenSpecimenId]);
      expect(workbench.thread?.specimenId, canonicalSpecimen);
      expect(workbench.threadGap, isNull);

      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a refused thread reaches the Processing disclosure', (
      WidgetTester tester,
    ) async {
      final ThreadRepository repository = ThreadRepository()
        ..answer = (String _) => Future<SpecimenThread?>.error(
          const ApiFailure(
            'Refused by the test.',
            code: 'thread_limit_exceeded',
            status: 413,
          ),
        );
      await pumpRecord(tester, repository);

      final ReviewWorkbench workbench = tester.widget<ReviewWorkbench>(
        find.byType(ReviewWorkbench),
      );
      expect(workbench.thread, isNull);
      expect(workbench.threadGap, ThreadGap.tooLarge);

      await tester.pumpWidget(const SizedBox());
    });
  });
}
