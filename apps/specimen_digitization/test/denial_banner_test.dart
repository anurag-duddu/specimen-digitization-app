// The banner a refusal leaves on the setup screen, rendered through the whole
// stack: a real `ApiSpecimenRepository` over a transport that refuses, the
// app's own `WorkspaceController`, and the screen the router sends a refusal
// to.
//
// The setup screen's title already says collection access could not be
// verified, so the banner carries only the cause and its fix. Each banner is
// pinned word for word and held to the writing guidelines (02 section 6,
// items 6, 9 and 10, and section 7's banner budget).

import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/app/setup_screen.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'widget_test.dart' show TestSession;

/// One way the collection service refuses, and the banner it must leave.
class Refusal {
  const Refusal(
    this.name, {
    required this.banner,
    this.token = _signedIn,
    this.appCheck,
    this.answer = _offline,
  });

  final String name;

  /// The banner text, exactly.
  final String banner;

  /// The sign-in token the repository reads.
  final Future<String?> Function() token;

  /// The App Check token the repository reads, when the build has one.
  final Future<String?> Function()? appCheck;

  /// How the service answers the access check.
  final Future<http.Response> Function(http.Request request) answer;
}

Future<String?> _signedIn() async => 'denial-token';

Future<http.Response> _offline(http.Request request) =>
    throw http.ClientException('Failed host lookup', request.url);

String _error(String code, String message) => jsonEncode(<String, dynamic>{
  'error': <String, dynamic>{'code': code, 'message': message},
});

final List<Refusal> refusals = <Refusal>[
  const Refusal(
    'an access check that stops',
    banner:
        'The access check stopped. Check access again, or ask an administrator.',
  ),
  Refusal(
    'a sign-in that cannot be refreshed',
    banner:
        'The sign-in could not be refreshed. Check the connection, or sign in '
        'again.',
    token: () async => throw StateError('token refresh failed'),
  ),
  Refusal(
    'app verification that cannot finish',
    banner:
        'App verification stopped before collection access was checked. '
        'Reload or reopen the app to start it again.',
    appCheck: () async => throw StateError('throttled'),
  ),
  Refusal(
    'an expired session',
    banner: 'The session expired. Sign in again.',
    token: () async => null,
  ),
  Refusal(
    "the server's bare refusal",
    banner: serverRefusalMessage,
    answer: (http.Request request) async =>
        http.Response(_error('access_denied', 'Access denied'), 403),
  ),
  Refusal(
    'a refusal the server words as a code',
    banner: serverRefusalMessage,
    answer: (http.Request request) async =>
        http.Response(_error('http_error', 'research_access_required'), 401),
  ),
  Refusal(
    'a front door that refuses with a page instead of JSON',
    banner: serverRefusalMessage,
    answer: (http.Request request) async =>
        http.Response('<html><body>Error: Forbidden</body></html>', 403),
  ),
];

/// The words section 6 item 6 bans, and the second person that section 2.4
/// bans from an operational error.
final RegExp _banned = RegExp(
  r'\b(invalid|illegal|failed to|an error occurred|something went wrong|oops|'
  r'please wait|simply|just|easily|unfortunately|sorry|we|our|delightful|'
  r'seamless|you|your)\b',
  caseSensitive: false,
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final Refusal refusal in refusals) {
    testWidgets('${refusal.name} leaves its banner alone', (
      WidgetTester tester,
    ) async {
      final TestSession session = TestSession();
      addTearDown(session.controller.close);
      final ApiSpecimenRepository repository = ApiSpecimenRepository(
        baseUrl: Uri.parse('https://api.example.org'),
        token: refusal.token,
        appCheckToken: refusal.appCheck,
        client: MockClient(refusal.answer),
      );
      addTearDown(repository.close);
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: repository),
      );
      await tester.pumpAndSettle();

      expect(find.byType(SetupScreen), findsOneWidget);
      expect(find.text(refusal.banner), findsOneWidget);
      final WorkspaceError error = tester
          .widget<SetupScreen>(find.byType(SetupScreen))
          .controller!
          .error!;
      expect(error.message, refusal.banner);
      expect(error.actionLabel, 'Check access again');
      expect(error.clearsAccess, isTrue);

      final String banner = refusal.banner;
      expect(banner.length, lessThanOrEqualTo(120), reason: 'banner budget');
      expect(
        RegExp(r'[.?!](\s|$)').allMatches(banner).length,
        lessThanOrEqualTo(2),
        reason: 'two sentences at most',
      );
      expect(banner, endsWith('.'), reason: 'an error message takes a period');
      expect(_banned.firstMatch(banner)?.group(0), isNull);
      expect(
        banner,
        isNot(contains('could not be verified')),
        reason: 'the screen title already says it',
      );
      await tester.pumpWidget(const SizedBox());
    });
  }
}
