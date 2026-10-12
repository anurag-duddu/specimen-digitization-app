// An idle tab lost its collection after one refused request, and checking
// access again never recovered it. These tests hold the client to what the
// live API saw on 2026-10-11: one read refused with 403 in the middle of a
// queue poll, then nothing from that tab for hours.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
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

final Json _wire =
    jsonDecode(
          File('test/fixtures/backend-wire-examples.json').readAsStringSync(),
        )
        as Json;

final Json _session = _wire['session'] as Json;

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

/// A raw reading, as the evidence route returns it.
final List<int> _raw = utf8.encode('Raw reading, as the model returned it.');

final Specimen _record = const Specimen({
  'specimen_id': 'sample',
  'revision': 1,
});

final ArtifactRequest _reading = ArtifactRequest(
  ArtifactKind.observationRaw,
  'reading',
  sha256: sha256.convert(_raw).toString(),
);

/// When a late refusal arrives: halfway through the one wait a request has.
final Duration _late = apiRequestTimeout ~/ 2;

/// Refuses the first read of [path] late, on the token the client holds, and
/// never answers the resend on minted tokens.
Future<http.Response?> Function(http.Request) _refusedLateThenSilent(
  String path,
) => (http.Request r) async {
  if (!r.url.path.endsWith(path)) return null;
  if (r.headers['Authorization'] != 'Bearer id-0') {
    return Completer<http.Response>().future;
  }
  await Future<void>.delayed(_late);
  return _refused();
};

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

    test('a refused source image is sent again on minted tokens', () async {
      // The record answers, and the token expires before its image is read.
      server.intercept = (http.Request r) async {
        if (r.url.path.endsWith('/workspace')) {
          return http.Response(jsonEncode(_wire['workspace_response']), 200);
        }
        if (r.url.path.endsWith('/content')) {
          return r.headers['Authorization'] == 'Bearer id-0'
              ? _refused()
              : http.Response.bytes(<int>[1, 2, 3], 200);
        }
        return null;
      };
      final Specimen record = await repository.specimen(_scope, 'sample');
      expect(record.assets.single['preview_bytes'], <int>[1, 2, 3]);
      expect(server.count('/content'), 2);
      expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
      expect(denials, isEmpty);
    });

    test('refused raw evidence is sent again on minted tokens', () async {
      server.intercept = (http.Request r) async {
        if (!r.url.path.endsWith('/observations/reading/raw')) return null;
        return r.headers['Authorization'] == 'Bearer id-0'
            ? _refused()
            : http.Response.bytes(_raw, 200);
      };
      final Json evidence = await repository.artifact(
        _scope,
        _record,
        _reading,
      );
      expect(utf8.encode(evidence['text'] as String), _raw);
      expect(evidence['sha256'], _reading.sha256);
      expect(server.count('/raw'), 2);
      expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
      expect(server.sent.last.headers['X-Firebase-AppCheck'], 'check-1');
      expect(denials, isEmpty);
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

    /// Starts [read] against a late refusal whose resend never answers, and
    /// returns what it came to one [apiRequestTimeout] after its first send.
    Future<Object?> outcomeAtTimeout(
      WidgetTester tester,
      Future<Object?> Function() read,
    ) async {
      Object? outcome;
      var settled = false;
      unawaited(
        read().then(
          (Object? value) {
            outcome = value;
            settled = true;
          },
          onError: (Object error) {
            outcome = error;
            settled = true;
          },
        ),
      );
      await tester.pump(_late);
      expect(settled, isFalse);
      await tester.pump(apiRequestTimeout - _late);
      expect(
        settled,
        isTrue,
        reason: 'the refusal, the minting and the resend share one wait',
      );
      // The abandoned resend's own timeout.
      await tester.pump(apiRequestTimeout);
      return outcome;
    }

    testWidgets('a resend that cannot answer in time is a timeout', (
      tester,
    ) async {
      server.intercept = _refusedLateThenSilent('/specimens');
      final Object? outcome = await outcomeAtTimeout(
        tester,
        () => repository.specimenPage(_scope),
      );
      expect(
        outcome,
        isA<ApiFailure>().having((f) => f.code, 'code', 'timeout'),
      );
      expect(server.count('/specimens'), 2);
      expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
      expect(denials, isEmpty);
    });

    testWidgets('a source image resend ends at the same wait', (tester) async {
      final refuse = _refusedLateThenSilent('/content');
      server.intercept = (http.Request r) async =>
          r.url.path.endsWith('/workspace')
          ? http.Response(jsonEncode(_wire['workspace_response']), 200)
          : refuse(r);
      final Object? outcome = await outcomeAtTimeout(
        tester,
        () => repository.specimen(_scope, 'sample'),
      );
      expect(
        outcome,
        isA<Specimen>().having(
          (s) => s.assets.single['preview_error'],
          'preview error',
          'Image request interrupted. Refresh to retry.',
        ),
      );
      expect(server.count('/content'), 2);
      expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
      expect(denials, isEmpty);
    });

    testWidgets('a raw evidence resend ends at the same wait', (tester) async {
      server.intercept = _refusedLateThenSilent('/raw');
      final Object? outcome = await outcomeAtTimeout(
        tester,
        () => repository.artifact(_scope, _record, _reading),
      );
      expect(
        outcome,
        isA<ApiFailure>().having((f) => f.code, 'code', 'timeout'),
      );
      expect(server.count('/raw'), 2);
      expect(server.sent.last.headers['Authorization'], 'Bearer id-1');
      expect(denials, isEmpty);
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

  testWidgets('app verification that cannot finish says to reload', (
    tester,
  ) async {
    final server = _Server();
    final check = _Tokens('check')
      ..readError = StateError('throttled')
      ..mintError = StateError('throttled');
    final session = TestSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(
        session: session,
        repository: _repository(server, _Tokens('id'), check),
      ),
    );
    await tester.pumpAndSettle();
    const String message =
        'App verification stopped before collection access was checked. '
        'Reload or reopen the app to start it again.';
    // The banner holds this message alone, inside its 120-character budget.
    expect(find.text(message), findsOneWidget);
    expect(message.length, lessThanOrEqualTo(120));
    expect(server.sent, isEmpty);
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
