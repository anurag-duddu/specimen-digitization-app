import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_auth_session_io.dart';

const _channel = MethodChannel('specimen/intake_auth');
const _url = 'https://provider.example/authorize?state=expected-state';

void main() {
  late List<MethodCall> calls;
  late List<Completer<String?>> launches;

  setUp(() {
    calls = [];
    launches = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, (call) {
          calls.add(call);
          if (call.method == 'cancel') return null;
          final launch = Completer<String?>();
          launches.add(launch);
          return launch.future;
        });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, null);
  });

  testWidgets('valid callback returns server-bound fields', (tester) async {
    final session = IntakeAuthSession();
    final future = session.authenticate(_url);
    await tester.pump();
    expect(calls.single.method, 'authenticate');
    final args = Map<String, String>.from(calls.single.arguments as Map);
    expect(args['state'], 'expected-state');
    expect(args['url'], _url);
    expect(args['id'], matches(RegExp(r'^[0-9a-f]{32}$')));
    launches.single.complete(
      'specimenintake://oauth/callback#state=expected-state&code=abc&picked_file_ids=file-1',
    );
    await tester.pump();
    expect(await future, {
      'state': 'expected-state',
      'code': 'abc',
      'picked_file_ids': 'file-1',
    });
    session.close();
  });

  testWidgets('close settles immediately and ignores a late callback', (
    tester,
  ) async {
    final session = IntakeAuthSession();
    final future = session.authenticate(_url);
    final failure = expectLater(
      future,
      throwsA(
        isA<ApiFailure>().having(
          (e) => e.code,
          'code',
          'authorization_cancelled',
        ),
      ),
    );
    await tester.pump();
    final oldId = (calls.single.arguments as Map)['id'];
    session.close();
    await tester.pump();
    await failure;
    expect(calls.last.method, 'cancel');
    expect((calls.last.arguments as Map)['id'], oldId);
    launches.single.complete(
      'specimenintake://oauth/callback#state=expected-state&code=stale',
    );
    await tester.pump();
    final retry = IntakeAuthSession();
    final next = retry.authenticate(_url);
    await tester.pump();
    expect((calls.last.arguments as Map)['id'], isNot(oldId));
    launches.last.complete(
      'specimenintake://oauth/callback#state=expected-state&code=fresh',
    );
    await tester.pump();
    expect((await next)['code'], 'fresh');
    retry.close();
  });

  testWidgets('native dismissal becomes authorization_cancelled', (
    tester,
  ) async {
    final session = IntakeAuthSession();
    final future = session.authenticate(_url);
    final failure = expectLater(
      future,
      throwsA(
        isA<ApiFailure>().having(
          (e) => e.code,
          'code',
          'authorization_cancelled',
        ),
      ),
    );
    await tester.pump();
    launches.single.completeError(PlatformException(code: 'cancelled'));
    await tester.pump();
    await failure;
    session.close();
  });

  testWidgets('launch failure settles without waiting for expiry', (
    tester,
  ) async {
    final session = IntakeAuthSession();
    final future = session.authenticate(_url);
    final failure = expectLater(
      future,
      throwsA(
        isA<ApiFailure>().having((e) => e.code, 'code', 'browser_unavailable'),
      ),
    );
    await tester.pump();
    launches.single.completeError(PlatformException(code: 'unavailable'));
    await tester.pump();
    await failure;
    session.close();
  });

  testWidgets('expired attempt cancels native tab and permits fresh retry', (
    tester,
  ) async {
    final session = IntakeAuthSession(timeout: const Duration(seconds: 1));
    final future = session.authenticate(_url);
    final failure = expectLater(
      future,
      throwsA(
        isA<ApiFailure>().having((e) => e.code, 'code', 'connection_expired'),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await failure;
    expect(calls.last.method, 'cancel');
    launches.single.complete(
      'specimenintake://oauth/callback#state=expected-state&code=too-late',
    );
    await tester.pump();
    session.close();
    final retry = IntakeAuthSession();
    final next = retry.authenticate(_url);
    await tester.pump();
    launches.last.complete(
      'specimenintake://oauth/callback#state=expected-state&error=access_denied',
    );
    await tester.pump();
    expect((await next)['error'], 'access_denied');
    retry.close();
  });

  for (final callback in [
    'specimenintake://other/callback#state=expected-state&code=abc',
    'specimenintake://oauth/other#state=expected-state&code=abc',
    'specimenintake://oauth/callback?code=abc#state=expected-state',
    'specimenintake://oauth/callback#state=wrong&code=abc',
    'specimenintake://oauth/callback#state=expected-state&state=expected-state&code=abc',
    'specimenintake://oauth/callback#state=expected-state&code=',
    'specimenintake://oauth/callback#state=expected-state&code=abc&error=denied',
    'specimenintake://oauth/callback#state=expected-state&code=abc&unexpected=1',
  ]) {
    testWidgets('rejects malformed callback: $callback', (tester) async {
      final session = IntakeAuthSession();
      final future = session.authenticate(_url);
      final failure = expectLater(
        future,
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'invalid_callback'),
        ),
      );
      await tester.pump();
      launches.single.complete(callback);
      await tester.pump();
      await failure;
      session.close();
    });
  }
}
