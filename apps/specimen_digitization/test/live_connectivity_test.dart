// Every way the collection service can fail a live reviewer, and the screen
// each one gets (07 section 11; slot B3, item 4).
//
// 07 section 11 puts an error at one of three surfaces and gives each failure
// class its own recovery: validation at the field, a failed action beside the
// control that was pressed, and a loss of access or of connectivity at the
// screen. The screen surface is the one a live pilot meets first, so it is the
// one measured here, and it is measured through the whole stack: a real
// `ApiSpecimenRepository` over a transport that fails, a real
// `WorkspaceController` above it, and the sentence and the recovery the
// reviewer is left holding.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestSession;

/// The checked in wire contract, which answers the calls that must succeed
/// before the call under test can fail.
final Json wireContract =
    jsonDecode(
          File('test/fixtures/backend-wire-examples.json').readAsStringSync(),
        )
        as Json;

/// How a transport or a service fails.
typedef Failure = Future<http.Response> Function(http.Request request);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  final Json session = wireContract['session'] as Json;

  /// A repository that answers the session and the collections, and then
  /// fails the queue the way [failure] says.
  ApiSpecimenRepository failing(Failure failure) => ApiSpecimenRepository(
    baseUrl: Uri.parse('https://api.example.org'),
    token: () async => 'connectivity-token',
    client: MockClient((http.Request request) async {
      if (request.url.path == '/v1/session') {
        return http.Response(jsonEncode(session), 200);
      }
      if (request.url.path.endsWith('/collections')) {
        return http.Response(
          jsonEncode(<String, dynamic>{
            'items': <Json>[
              <String, dynamic>{
                'collection_id':
                    (session['memberships'] as List).first['collection_id'],
                'display_name': 'Entomology',
              },
            ],
          }),
          200,
        );
      }
      return failure(request);
    }),
  );

  /// Opens a collection, then lets the queue fail.
  Future<WorkspaceController> failedQueue(Failure failure) async {
    final ApiSpecimenRepository repository = failing(failure);
    addTearDown(repository.close);
    final TestSession testSession = TestSession();
    addTearDown(testSession.controller.close);
    final WorkspaceController controller = WorkspaceController(
      repository: repository,
      session: testSession,
    );
    addTearDown(controller.dispose);
    await controller.checkAccess();
    return controller;
  }

  /// An error body the service returns.
  String error(String code, String message) => jsonEncode(<String, dynamic>{
    'error': <String, dynamic>{'code': code, 'message': message},
  });

  group('a failure of the connection', () {
    test('offline names the connection and offers Retry', () async {
      final WorkspaceController controller = await failedQueue(
        (http.Request request) =>
            throw http.ClientException('Failed host lookup', request.url),
      );
      final WorkspaceError failure = controller.error!;
      expect(failure.message, contains('Connection interrupted.'));
      expect(failure.actionLabel, 'Retry');
      expect(failure.clearsAccess, isFalse);

      // 07 section 11: the banner names the last successful sync, so the
      // records already on screen are not mistaken for current ones.
      expect(
        failure.message,
        anyOf(
          contains('last loaded'),
          contains('No records have been loaded yet.'),
        ),
      );
    });

    test('a timeout says the server may already have the work', () async {
      final WorkspaceController controller = await failedQueue(
        (http.Request request) => throw TimeoutException('too slow'),
      );
      final WorkspaceError failure = controller.error!;
      expect(failure.message, contains('The request timed out.'));
      expect(
        failure.message,
        contains('reconcile'),
        reason:
            'a timed out write may have landed, and the reviewer is owed '
            'that difference rather than a bare failure',
      );
      expect(failure.actionLabel, 'Retry');
    });

    test('a 5xx is unreachable, not a refusal', () async {
      final WorkspaceController controller = await failedQueue(
        (http.Request request) async => http.Response(
          error('internal', 'The service is unavailable.'),
          503,
        ),
      );
      final WorkspaceError failure = controller.error!;
      expect(failure.actionLabel, 'Retry');
      expect(failure.clearsAccess, isFalse);
      expect(
        failure.message,
        anyOf(
          contains('last loaded'),
          contains('No records have been loaded yet.'),
        ),
      );
    });
  });

  group('a refusal by the service', () {
    test('a 401 clears the workspace and asks for a fresh check', () async {
      final WorkspaceController controller = await failedQueue(
        (http.Request request) async => http.Response(
          error('unauthenticated', 'Your session expired.'),
          401,
        ),
      );
      final WorkspaceError failure = controller.error!;
      expect(failure.clearsAccess, isTrue);
      expect(failure.actionLabel, 'Check access again');
      expect(failure.message, contains('could not be verified'));

      // Nothing editable survives a denial.
      expect(controller.items, isEmpty);
      expect(controller.scope, isNull);
    });

    test(
      'an unverified address is refused with the recheck that resolves it',
      () async {
        // `docs/execution/LIVE_API.md`: the production API answers 403
        // `email_verification_required` for a cryptographically verified
        // identity whose address is not verified. The client normally never
        // reaches this, because `auth.dart` gates on the local flag before it
        // calls the API at all; it reaches it when that flag is stale. The
        // banner does not say "verify your address" in so many words, and its
        // recovery is the access recheck, which refreshes the user and routes
        // to the verification screen. Recorded rather than reworded here: the
        // sentence is the entry screens' to own.
        final WorkspaceController controller = await failedQueue(
          (http.Request request) async => http.Response(
            error(
              'email_verification_required',
              'Verify your museum address before continuing.',
            ),
            403,
          ),
        );
        final WorkspaceError failure = controller.error!;
        expect(failure.clearsAccess, isTrue);
        expect(failure.actionLabel, 'Check access again');
        expect(
          failure.message,
          contains('Verify your museum address before continuing.'),
          reason: 'the service said what was wrong and the banner dropped it',
        );
      },
    );

    test('a 403 gets the same screen, because the record is as gone', () async {
      final WorkspaceController controller = await failedQueue(
        (http.Request request) async => http.Response(
          error('access_denied', 'Collection access was withdrawn.'),
          403,
        ),
      );
      final WorkspaceError failure = controller.error!;
      expect(failure.clearsAccess, isTrue);
      expect(failure.actionLabel, 'Check access again');
      expect(controller.items, isEmpty);
    });
  });

  group('a save against a version that moved', () {
    Future<WorkspaceController> staleSave(int status) async {
      final Json workspace = wireContract['workspace_response'] as Json;
      final ApiSpecimenRepository repository = ApiSpecimenRepository(
        baseUrl: Uri.parse('https://api.example.org'),
        token: () async => 'connectivity-token',
        client: MockClient((http.Request request) async {
          if (request.url.path == '/v1/session') {
            return http.Response(jsonEncode(session), 200);
          }
          if (request.url.path.endsWith('/collections')) {
            return http.Response(
              jsonEncode(<String, dynamic>{
                'items': <Json>[
                  <String, dynamic>{
                    'collection_id':
                        (session['memberships'] as List).first['collection_id'],
                    'display_name': 'Entomology',
                  },
                ],
              }),
              200,
            );
          }
          if (request.method == 'POST') {
            return http.Response(
              error('revision_conflict', 'This record has a newer version.'),
              status,
            );
          }
          if (request.url.path.endsWith('/content')) {
            return http.Response.bytes(<int>[1, 2, 3], 200);
          }
          if (request.url.path.endsWith('/specimens')) {
            return http.Response(
              jsonEncode(<String, dynamic>{
                'items': <Json>[workspace],
              }),
              200,
            );
          }
          return http.Response(jsonEncode(workspace), 200);
        }),
      );
      addTearDown(repository.close);
      final TestSession testSession = TestSession();
      addTearDown(testSession.controller.close);
      final WorkspaceController controller = WorkspaceController(
        repository: repository,
        session: testSession,
      );
      addTearDown(controller.dispose);
      await controller.checkAccess();
      await controller.openSpecimen(workspace['specimen_id'] as String);
      await controller.mutate(<String, dynamic>{
        'kind': 'coverage',
        'reason': 'Every label read',
      }, null);
      return controller;
    }

    test(
      'a 409 says another reviewer saved, and offers the comparison',
      () async {
        final WorkspaceController controller = await staleSave(409);
        final WorkspaceError failure = controller.error!;
        expect(
          failure.message,
          contains(
            'Another reviewer saved a new version while you were working.',
          ),
        );
        expect(
          failure.message,
          contains('Your decision was not saved.'),
          reason:
              'a stale save that does not say it did not save is a save the '
              'reviewer believes they made',
        );
        expect(failure.actionLabel, 'Refresh and compare');
        expect(failure.clearsAccess, isFalse);
      },
    );

    test('a 412 is the same failure and gets the same screen', () async {
      final WorkspaceController controller = await staleSave(412);
      expect(controller.error!.actionLabel, 'Refresh and compare');
    });
  });

  group('every screen failure carries a recovery', () {
    test('no failure class leaves the reviewer without an action', () async {
      final List<Failure> classes = <Failure>[
        (http.Request request) =>
            throw http.ClientException('Failed host lookup', request.url),
        (http.Request request) => throw TimeoutException('too slow'),
        (http.Request request) async =>
            http.Response(error('unauthenticated', 'Expired.'), 401),
        (http.Request request) async =>
            http.Response(error('access_denied', 'Withdrawn.'), 403),
        (http.Request request) async =>
            http.Response(error('internal', 'Unavailable.'), 503),
        (http.Request request) async =>
            http.Response(error('bad_gateway', 'Unavailable.'), 502),
      ];
      for (final Failure failure in classes) {
        final WorkspaceController controller = await failedQueue(failure);
        final WorkspaceError reported = controller.error!;
        expect(reported.message.trim(), isNotEmpty);
        expect(reported.actionLabel.trim(), isNotEmpty);
        expect(
          reported.actionLabel.split(' ').length,
          inInclusiveRange(1, 4),
          reason:
              'a recovery is a verb phrase of two to four words '
              '(02 section 4.3): "${reported.actionLabel}"',
        );
      }
    });
  });

  group('the elapsed time the wire waits is named where the policy lives', () {
    test('one request timeout covers the whole wire', () {
      expect(apiRequestTimeout, const Duration(seconds: 30));
    });

    test('the wire writes that duration down exactly once', () {
      // 10 section 8, the fit amendment: an elapsed time is a named constant
      // in the file that owns the policy, not a motion token and not a digit
      // repeated at each call site. Seven call sites read one constant, so a
      // reviewer waiting on the sign in refresh, on a JSON request, on the
      // evidence stream or on the photograph waits the same declared time.
      final String source = File(
        'lib/src/api_repository.dart',
      ).readAsStringSync();
      expect(
        RegExp(r'Duration\(').allMatches(source).length,
        1,
        reason:
            'api_repository.dart writes an elapsed time as a literal '
            'somewhere other than the declaration of apiRequestTimeout',
      );
      expect(
        RegExp(r'\bapiRequestTimeout\b').allMatches(source).length,
        greaterThanOrEqualTo(8),
        reason: 'the seven waits and the declaration',
      );
    });
  });
}
