import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'magic_link_controller_test.dart'
    show FakeLinkAccess, MemoryLinkStorage, testLink;

class LinkSession extends FakeLinkAccess
    implements SessionAccess, VerifiedEmailAccess {
  @override
  bool signedIn = false;
  @override
  bool emailVerified = false;
  final controller = StreamController<bool>.broadcast();
  int tokenCalls = 0, verificationCalls = 0;
  @override
  Stream<bool> get changes => controller.stream;
  @override
  String get userId => 'local-staff-fixture';
  @override
  String get displayName => 'Staff fixture';
  @override
  Future<String?> token() async {
    tokenCalls++;
    throw StateError('No API configured');
  }

  @override
  Future<void> completeEmailLink(String email, String link) async {
    signedIn = true;
    emailVerified = true;
    controller.add(true);
    await super.completeEmailLink(email, link);
  }

  @override
  Future<void> signOut() async {
    signedIn = false;
    controller.add(false);
  }

  @override
  Future<void> signIn(String email, String password) async =>
      throw StateError('No password route');
  @override
  Future<void> resetPassword(String email) async =>
      throw StateError('No reset route');
  @override
  Future<void> refreshVerification() async {}
  @override
  Future<void> sendVerification() async {
    verificationCalls++;
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets(
    'cross-browser magic link verifies account before pending API, then sign out',
    (tester) async {
      final session = LinkSession()..completeWait = Completer<void>();
      addTearDown(session.controller.close);
      final browser = MemoryEmailLinkBrowser(
        uri: Uri.parse('$testLink&email=untrusted%40fieldmuseum.org'),
      );
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, emailLinkBrowser: browser),
      );
      await tester.pumpAndSettle();
      expect(find.text('Confirm your email'), findsOneWidget);
      expect(session.completed, isEmpty);
      expect(
        tester
            .widget<TextFormField>(find.byType(TextFormField))
            .controller!
            .text,
        isEmpty,
      );
      await tester.enterText(
        find.byType(TextFormField),
        'STAFF@FIELDMUSEUM.ORG',
      );
      await tester.tap(find.text('Confirm and sign in'));
      await tester.pump();
      expect(find.text('Signing in…'), findsOneWidget);
      expect(find.byType(CollectionWorkspace), findsNothing);
      expect(find.text('Collection connection required'), findsNothing);
      session.completeWait!.complete();
      await tester.pumpAndSettle();
      expect(find.text('Collection connection required'), findsOneWidget);
      expect(session.emailVerified, true);
      expect(session.verificationCalls, 0);
      expect(session.tokenCalls, 0);
      expect(browser.clearCount, 1);
      await tester.tap(find.text('Sign out'));
      await tester.pumpAndSettle();
      expect(find.text('Send sign-in link'), findsOneWidget);
      expect(find.text('Reset password'), findsNothing);
    },
  );

  testWidgets(
    'same-browser remembered email completes without typing or extra email',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        PreferencesEmailLinkStorage.emailKey: 'staff@fieldmuseum.org',
      });
      final session = LinkSession();
      addTearDown(session.controller.close);
      final browser = MemoryEmailLinkBrowser(uri: Uri.parse(testLink));
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, emailLinkBrowser: browser),
      );
      await tester.pumpAndSettle();
      expect(session.completed, [('staff@fieldmuseum.org', testLink)]);
      expect(session.sent, isEmpty);
      expect(find.text('Collection connection required'), findsOneWidget);
      expect(browser.clearCount, 1);
      expect(
        (await SharedPreferences.getInstance()).getString(
          PreferencesEmailLinkStorage.emailKey,
        ),
        isNull,
      );
    },
  );

  testWidgets(
    'resend cooldown, loading and change-email states are actionable',
    (tester) async {
      final access = FakeLinkAccess()..sendWait = Completer<void>();
      final storage = MemoryLinkStorage();
      var now = DateTime.utc(2026, 9, 10);
      final controller = MagicLinkController(
        access: access,
        storage: storage,
        browser: MemoryEmailLinkBrowser(),
        now: () => now,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await tester.pumpWidget(
        MaterialApp(
          home: MagicLinkSignInScreen(access: access, controller: controller),
        ),
      );
      await tester.enterText(
        find.byType(TextFormField),
        'staff@fieldmuseum.org',
      );
      await tester.tap(find.text('Send sign-in link'));
      await tester.pump();
      expect(find.text('Sending link…'), findsOneWidget);
      expect(
        tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNull,
      );
      access.sendWait!.complete();
      await tester.pumpAndSettle();
      expect(find.text('Resend sign-in link'), findsOneWidget);
      expect(
        tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNull,
      );
      expect(find.text('You can request another link in 60s.'), findsOneWidget);
      now = now.add(const Duration(seconds: 61));
      await tester.pump(const Duration(seconds: 1));
      expect(
        tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNotNull,
      );
      await tester.tap(find.text('Use a different email'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextFormField>(find.byType(TextFormField))
            .controller!
            .text,
        isEmpty,
      );
      expect(storage.value.email, isNull);
    },
  );
}
