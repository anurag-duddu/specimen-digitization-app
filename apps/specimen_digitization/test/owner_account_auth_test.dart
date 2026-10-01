// Credential-free controls for the exact authorized owner mailbox exception.
// These fixtures do not establish a native UID, membership, or live sign-in.
import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/app_router.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/app/session_notifier.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/email_verification.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

const ownerEmail = 'anurag@infinative.com';
const ownerLinkFixture =
    'https://specimen-digitization.web.app/?mode=signIn&oobCode=owner-action-fixture';

class OwnerUserFixture implements User {
  OwnerUserFixture(this.email, {this.emailVerified = true});
  @override
  final String email;
  @override
  bool emailVerified;
  @override
  String get uid => 'owner-user-fixture';
  int tokenCalls = 0, verificationCalls = 0;
  bool verifyOnReload = false, failForcedRefresh = false;
  @override
  Future<String?> getIdToken([bool forceRefresh = false]) async {
    tokenCalls++;
    if (forceRefresh && failForcedRefresh) {
      throw StateError('Forced token refresh fixture failed');
    }
    return 'owner-token-fixture';
  }

  @override
  Future<void> reload() async {
    if (verifyOnReload) emailVerified = true;
  }

  @override
  Future<void> sendEmailVerification() async {
    verificationCalls++;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected User method in owner auth fixture');
}

class OwnerAuthFixture implements FirebaseAuth {
  OwnerAuthFixture(this.currentUser);
  @override
  final OwnerUserFixture currentUser;
  String? sentEmail, completedEmail, completedLink;
  int sendCalls = 0, completeCalls = 0;
  @override
  Stream<User?> userChanges() => const Stream<User?>.empty();
  @override
  bool isSignInWithEmailLink(String link) => link == ownerLinkFixture;
  @override
  Future<void> sendSignInLinkToEmail({
    required String email,
    required ActionCodeSettings actionCodeSettings,
  }) async {
    sendCalls++;
    sentEmail = email;
  }

  @override
  Future<UserCredential> signInWithEmailLink({
    required String email,
    required String emailLink,
  }) async {
    completeCalls++;
    completedEmail = email;
    completedLink = emailLink;
    return OwnerCredentialFixture();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected Firebase method in owner auth fixture');
}

class OwnerCredentialFixture implements UserCredential {
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unused credential fixture');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final address in [
    ownerEmail,
    'ANURAG@INFINATIVE.COM',
    'AnUrAg@InFiNaTiVe.CoM',
  ]) {
    test('exact owner normalizes and can request a token: $address', () async {
      final user = OwnerUserFixture(address);
      final session = FirebaseSession(OwnerAuthFixture(user));
      final notifier = AppSessionNotifier(session: session);
      addTearDown(notifier.dispose);

      expect(normalizedStaffEmail(address), ownerEmail);
      expect(session.staffEmailAllowed, true);
      expect(session.userId, 'owner-user-fixture');
      expect(notifier.signedIn, true);
      expect(notifier.verified, true);
      expect(await session.token(), 'owner-token-fixture');
      expect(user.tokenCalls, 1);
      expect(user.verificationCalls, 0);
    });
  }

  for (final address in [
    'other@infinative.com',
    'anurag+review@infinative.com',
    'an.urag@infinative.com',
    'anurag@sub.infinative.com',
    'anurag@infinative.com.evil.example',
    'anurag@infinative.com@fieldmuseum.org',
    'anurag@@infinative.com',
    '@infinative.com',
    'anurag@infinative.com.',
    ' anurag@infinative.com',
    'anurag@infinative.com ',
    'anurag @infinative.com',
    'anurag@infinative.com\n',
    'anurag\u0000@infinative.com',
    'anurag\u200b@infinative.com',
    '\u0430nurag@infinative.com',
    'anurag@\u0131nfinative.com',
    'anurag@infinative\uff0ecom',
    'anurag@infinative\u3002com',
    '.anurag@infinative.com',
    'anurag.@infinative.com',
    'anurag..review@infinative.com',
    '"anurag"@infinative.com',
    '${'x' * 65}@infinative.com',
    '${'x' * 255}@infinative.com',
  ]) {
    test('non-owner remains blocked: ${address.codeUnits}', () async {
      final user = OwnerUserFixture(address);
      final session = FirebaseSession(OwnerAuthFixture(user));
      final notifier = AppSessionNotifier(session: session);
      addTearDown(notifier.dispose);

      expect(normalizedStaffEmail(address), isNull);
      expect(session.staffEmailAllowed, false);
      expect(notifier.verified, false);
      await expectLater(
        session.token(),
        throwsA(
          isA<ApiFailure>().having(
            (error) => error.code,
            'code',
            'staff_email_required',
          ),
        ),
      );
      expect(user.tokenCalls, 0);
      expect(user.verificationCalls, 0);
    });
  }

  test('owner link adapters normalize but do not admit other mailboxes', () async {
    final auth = OwnerAuthFixture(OwnerUserFixture(ownerEmail));
    final session = FirebaseSession(auth);

    await session.sendSignInLink('ANURAG@INFINATIVE.COM');
    await session.completeEmailLink('AnUrAg@InFiNaTiVe.CoM', ownerLinkFixture);
    expect(auth.sentEmail, ownerEmail);
    expect(auth.completedEmail, ownerEmail);
    expect(auth.completedLink, ownerLinkFixture);
    for (final email in ['other@infinative.com', 'anurag+review@infinative.com']) {
      await expectLater(session.sendSignInLink(email), throwsFormatException);
      await expectLater(
        session.completeEmailLink(email, ownerLinkFixture),
        throwsFormatException,
      );
    }
    expect(auth.sendCalls, 1);
    expect(auth.completeCalls, 1);
  });

  test('unverified owner remains gated before token access', () async {
    final user = OwnerUserFixture(ownerEmail, emailVerified: false);
    final session = FirebaseSession(OwnerAuthFixture(user));
    final notifier = AppSessionNotifier(session: session);
    addTearDown(notifier.dispose);

    expect(session.staffEmailAllowed, true);
    expect(notifier.verified, false);
    await expectLater(
      session.token(),
      throwsA(
        isA<ApiFailure>().having((error) => error.code, 'code', 'email_unverified'),
      ),
    );
    expect(user.tokenCalls, 0);
  });

  test('owner verification still waits for a successful token refresh', () async {
    final user = OwnerUserFixture(ownerEmail, emailVerified: false)
      ..verifyOnReload = true
      ..failForcedRefresh = true;
    final session = FirebaseSession(OwnerAuthFixture(user));
    final notifier = AppSessionNotifier(session: session);
    addTearDown(notifier.dispose);

    await expectLater(notifier.refreshVerification(), throwsStateError);
    expect(session.emailVerified, true);
    expect(notifier.verified, false);
    user.failForcedRefresh = false;
    await notifier.refreshVerification();
    expect(notifier.verified, true);
    expect(user.tokenCalls, 2);
  });

  for (final (email, verified, expectedRoute) in [
    (ownerEmail, true, AppRoutes.setup),
    ('ANURAG@INFINATIVE.COM', true, AppRoutes.setup),
    (ownerEmail, false, AppRoutes.verify),
    ('other@infinative.com', true, AppRoutes.verify),
    ('anurag+review@infinative.com', true, AppRoutes.verify),
  ]) {
    testWidgets('router gates $email verified=$verified', (tester) async {
      final user = OwnerUserFixture(email, emailVerified: verified);
      final session = FirebaseSession(OwnerAuthFixture(user));
      final notifier = AppSessionNotifier(session: session);
      final router = buildAppRouter(
        sessionNotifier: notifier,
        initialLocation: AppRoutes.verify,
      );
      addTearDown(notifier.dispose);
      addTearDown(router.dispose);

      await tester.pumpWidget(
        MaterialApp.router(theme: AppTheme.light(), routerConfig: router),
      );
      await tester.pumpAndSettle();

      expect(router.routerDelegate.currentConfiguration.uri.path, expectedRoute);
      if (expectedRoute == AppRoutes.setup) {
        // Email admission does not provide a collection/controller.
        expect(find.text('Collection connection required'), findsOneWidget);
        expect(find.text('Use a Field Museum account'), findsNothing);
      }
      expect(user.tokenCalls, 0);
      expect(user.verificationCalls, 0);
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets('verified owner passes the existing email verification gate', (
    tester,
  ) async {
    final user = OwnerUserFixture(ownerEmail);
    final session = FirebaseSession(OwnerAuthFixture(user));

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: EmailVerificationGate(
          session: session,
          child: const Text('owner collection fixture'),
        ),
      ),
    );

    expect(find.text('owner collection fixture'), findsOneWidget);
    expect(find.text('Use a Field Museum account'), findsNothing);
    expect(user.tokenCalls, 0);
    expect(user.verificationCalls, 0);
  });
}
