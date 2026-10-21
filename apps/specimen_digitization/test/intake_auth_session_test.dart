import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_auth_session_io.dart';

void main() {
  testWidgets(
    'expired native consent releases links and permits a fresh retry',
    (tester) async {
      const links = MethodChannel('com.llfbandit.app_links/events');
      const launcher = MethodChannel('plugins.flutter.io/url_launcher');
      final messenger = tester.binding.defaultBinaryMessenger;
      final linkCalls = <String>[];
      final launched = <String>[];
      messenger.setMockMethodCallHandler(links, (call) async {
        linkCalls.add(call.method);
        return null;
      });
      messenger.setMockMethodCallHandler(launcher, (call) async {
        expect(call.method, 'launch');
        launched.add((call.arguments as Map)['url'] as String);
        return true;
      });
      addTearDown(() {
        messenger.setMockMethodCallHandler(links, null);
        messenger.setMockMethodCallHandler(launcher, null);
      });

      final expired = IntakeAuthSession();
      Object? failure;
      Json? response;
      expired
          .authenticate(
            'https://provider.example/authorize?state=expired-state',
          )
          .then(
            (value) {
              response = value;
            },
            onError: (Object error) {
              failure = error;
            },
          );
      await tester.pump();
      await tester.pump();
      expect(linkCalls, ['listen']);
      await tester.pump(const Duration(minutes: 9, seconds: 59));
      expect(failure, isNull);
      expect(response, isNull);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      // Platform-channel cancellation completes outside the fake timer zone.
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      await tester.pump();
      expect(linkCalls, ['listen', 'cancel']);
      expect(failure, isA<ApiFailure>());
      final problem = failure! as ApiFailure;
      expect(problem.code, 'connection_expired');
      expect(
        problem.message,
        'Connection expired. Connect again to finish authorizing this account.',
      );
      expect(problem.details['action'], 'connect');
      expect(linkCalls, ['listen', 'cancel']);
      expired.close();
      await tester.pump();

      final retry = IntakeAuthSession();
      failure = null;
      retry
          .authenticate('https://provider.example/authorize?state=retry-state')
          .then(
            (value) {
              response = value;
            },
            onError: (Object error) {
              failure = error;
            },
          );
      await tester.pump();
      expect(linkCalls, ['listen', 'cancel', 'listen']);
      expect(launched, hasLength(2));
      void callback(String state, String code) =>
          tester.binding.channelBuffers.push(
            links.name,
            const StandardMethodCodec().encodeSuccessEnvelope(
              'specimenintake://oauth/callback#state=$state&code=$code',
            ),
            (_) {},
          );
      callback('expired-state', 'stale-code');
      await tester.pump();
      expect(response, isNull);
      callback('retry-state', 'retry-code');
      await tester.pump();
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      await tester.pump();
      expect(failure, isNull);
      expect(response, {'state': 'retry-state', 'code': 'retry-code'});
      expect(linkCalls, ['listen', 'cancel', 'listen', 'cancel']);
      retry.close();
      await tester.pump();
    },
  );
}
