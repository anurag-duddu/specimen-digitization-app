// An idle tab lost its collection after one refused request, and checking
// access again never recovered it. These tests hold the client to what the
// live API saw on 2026-10-11: one read refused with 403 in the middle of a
// queue poll, then nothing from that tab for hours.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestSession;

final Json _session =
    (jsonDecode(
              File(
                'test/fixtures/backend-wire-examples.json',
              ).readAsStringSync(),
            )
            as Json)['session']
        as Json;

final String _collectionId =
    ((_session['memberships'] as List).single as Map)['collection_id']
        as String;

final CollectionScope _scope = CollectionScope(
  organizationId:
      ((_session['memberships'] as List).single as Map)['organization_id']
          as String,
  collectionId: _collectionId,
  name: 'Pilot collection',
);

http.Response _refused() => http.Response(
  jsonEncode({
    'error': {'code': 'access_denied', 'message': 'Access denied'},
  }),
  403,
);

/// A collection API with one assigned collection and an empty queue.
class _Server {
  final List<http.Request> sent = <http.Request>[];

  /// Answers a request before the ordinary routes do, when it returns one.
  Future<http.Response?> Function(http.Request request)? intercept;

  late final MockClient client = MockClient((http.Request request) async {
    sent.add(request);
    final http.Response? answer = await intercept?.call(request);
    if (answer != null) return answer;
    final String path = request.url.path;
    if (path == '/v1/session') {
      return http.Response(jsonEncode(_session), 200);
    }
    if (path.endsWith('/collections')) {
      return http.Response(
        jsonEncode({
          'items': [
            {'collection_id': _collectionId, 'display_name': 'Pilot'},
          ],
        }),
        200,
      );
    }
    if (path.endsWith('/specimens')) {
      return http.Response(jsonEncode({'items': [], 'next_cursor': null}), 200);
    }
    return http.Response(jsonEncode({'error': {}}), 404);
  });

  int count(String path) =>
      sent.where((http.Request r) => r.url.path.endsWith(path)).length;
}

/// A token source that keeps one token until asked to mint another, the way
/// Firebase Auth and App Check do.
class _Tokens {
  _Tokens(this.name);
  final String name;
  int minted = 0;

  /// When set, reading the cached token throws this.
  Object? readError;

  /// When set, minting a token throws this.
  Object? mintError;

  String get current => '$name-$minted';

  Future<String?> read() async {
    if (readError != null) throw readError!;
    return current;
  }

  Future<String?> mint() async {
    if (mintError != null) throw mintError!;
    minted++;
    return current;
  }
}

ApiSpecimenRepository _repository(_Server server, _Tokens id, _Tokens check) =>
    ApiSpecimenRepository(
      baseUrl: Uri.parse('http://localhost:8000'),
      token: id.read,
      freshToken: id.mint,
      appCheckToken: check.read,
      freshAppCheckToken: check.mint,
      client: server.client,
    );

void main() {
  group('tokens', () {
    late _Server server;
    late _Tokens id;
    late _Tokens check;
    late ApiSpecimenRepository repository;
    late List<ApiFailure> denials;

    setUp(() {
      server = _Server();
      id = _Tokens('id');
      check = _Tokens('check');
      repository = _repository(server, id, check);
      denials = <ApiFailure>[];
      repository.accessFailures.listen(denials.add);
    });

    test('a refused read is sent again on minted tokens', () async {
      server.intercept = (http.Request r) async =>
          r.headers['X-Firebase-AppCheck'] == 'check-0' ? _refused() : null;
      final SpecimenPage page = await repository.specimenPage(_scope);
      expect(page.items, isEmpty);
      expect(
        server.sent.map((http.Request r) => r.headers['X-Firebase-AppCheck']),
        <String>['check-0', 'check-1'],
      );
      expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
      expect(denials, isEmpty);
    });

    test('a read refused on minted tokens is a denial', () async {
      server.intercept = (http.Request r) async => _refused();
      await expectLater(
        repository.specimenPage(_scope),
        throwsA(isA<ApiFailure>().having((f) => f.status, 'status', 403)),
      );
      expect(server.count('/specimens'), 2);
      expect(denials, hasLength(1));
    });

    test('a refused write is not sent again', () async {
      server.intercept = (http.Request r) async => _refused();
      await expectLater(
        repository.request('POST', '/v1/anything', body: const {}),
        throwsA(isA<ApiFailure>()),
      );
      expect(server.sent, hasLength(1));
      expect(id.minted, 0);
    });

    test('a cached token that cannot be read is minted first', () async {
      id.readError = StateError('token refresh did not reach the network');
      await repository.specimenPage(_scope);
      expect(server.sent.single.headers['Authorization'], 'Bearer id-1');
      expect(denials, isEmpty);
    });

    test('a mint that throws falls back to the cached token', () async {
      // App Check on the web throws from a forced refresh it cannot finish,
      // even while it still holds a valid token.
      check.mintError = StateError('exchange throttled');
      server.intercept = (http.Request r) async =>
          r.headers['Authorization'] == 'Bearer id-0' ? _refused() : null;
      await repository.specimenPage(_scope);
      expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
      expect(server.sent.last.headers['X-Firebase-AppCheck'], 'check-0');
      expect(denials, isEmpty);
    });

    test('checking access after a refusal mints before it sends', () async {
      server.intercept = (http.Request r) async => _refused();
      await expectLater(
        repository.specimenPage(_scope),
        throwsA(isA<ApiFailure>()),
      );
      // The service is back. Every token minted before now has expired.
      final Set<String> expired = {'Bearer id-0', 'Bearer id-1'};
      server.intercept = (http.Request r) async =>
          expired.contains(r.headers['Authorization']) ? _refused() : null;
      server.sent.clear();
      final List<CollectionScope> scopes = await repository.scopes();
      expect(scopes.single.collectionId, _collectionId);
      expect(server.count('/v1/session'), 1);
      expect(server.sent.first.headers['Authorization'], 'Bearer id-2');
      expect(server.sent.first.headers['X-Firebase-AppCheck'], 'check-2');
      // The collection list after it reads the token just minted.
      expect(server.sent.last.headers['Authorization'], 'Bearer id-2');
      expect(id.minted, 2);
    });
  });

  testWidgets('a first access check that fails can be run again', (
    tester,
  ) async {
    final server = _Server();
    var offline = true;
    server.intercept = (http.Request request) async {
      if (offline && request.url.path == '/v1/session') {
        throw http.ClientException('offline');
      }
      return null;
    };
    final session = TestSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(
        session: session,
        repository: ApiSpecimenRepository(
          baseUrl: Uri.parse('http://localhost:8000'),
          token: session.token,
          client: server.client,
        ),
      ),
    );
    await tester.pumpAndSettle();
    // The check ended. The screen must say so and offer the retry, rather
    // than wait on a check that is no longer running.
    expect(
      find.text('Collection access could not be verified'),
      findsOneWidget,
    );
    offline = false;
    await tester.tap(find.text('Check access again'));
    await tester.pumpAndSettle();
    expect(server.count('/v1/session'), 2);
    expect(find.byType(AppShell), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a poll read on an expired token keeps the collection open', (
    tester,
  ) async {
    final server = _Server();
    final id = _Tokens('id');
    final session = TestSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(
        session: session,
        repository: ApiSpecimenRepository(
          baseUrl: Uri.parse('http://localhost:8000'),
          token: id.read,
          freshToken: id.mint,
          client: server.client,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(AppShell), findsOneWidget);
    final int before = server.count('/specimens');
    // The token the client still holds has expired at the server.
    server.intercept = (http.Request request) async =>
        request.headers['Authorization'] == 'Bearer id-0' ? _refused() : null;
    await tester.pump(queuePollInterval);
    await tester.pumpAndSettle();
    expect(server.count('/specimens'), before + 2);
    expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
    expect(find.byType(AppShell), findsOneWidget);
    expect(find.textContaining('could not be verified'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
