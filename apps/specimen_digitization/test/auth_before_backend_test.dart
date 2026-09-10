import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/workspace.dart';

// Local fake only: no Firebase initialization, account lookup, mail, or API.
class AuthOnlySession implements SessionAccess, VerifiedEmailAccess {
  AuthOnlySession({this.signedIn = false, this.emailVerified = false});

  @override
  bool signedIn;
  @override
  bool emailVerified;
  final controller = StreamController<bool>.broadcast();
  int tokenCalls = 0;
  int verificationRequests = 0;
  int refreshes = 0;
  bool failRefresh = false;
  @override
  Stream<bool> get changes => controller.stream;
  @override
  String get userId => 'local-test-user';
  @override
  String get displayName => 'Local test account';
  @override
  Future<String?> token() async {
    tokenCalls++;
    throw StateError('Auth-only UI must not request a collection token');
  }

  @override
  Future<void> signIn(String email, String password) async {
    signedIn = true;
    controller.add(true);
  }

  @override
  Future<void> signOut() async {
    signedIn = false;
    controller.add(false);
  }

  @override
  Future<void> resetPassword(String email) async {}
  @override
  Future<void> sendVerification() async {
    verificationRequests++;
  }

  @override
  Future<void> refreshVerification() async {
    refreshes++;
    emailVerified = true;
    if (failRefresh) throw StateError('Local test refresh failure');
  }
}

const backendPending = 'The application API is not configured.';

void main() {
  testWidgets('configured Firebase session can sign in without API', (
    tester,
  ) async {
    final session = AuthOnlySession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, setupMessage: backendPending),
    );
    expect(find.byType(CollectionWorkspace), findsNothing);
    expect(session.tokenCalls, 0);
    expect(session.verificationRequests, 0);
    expect(find.byType(SignInScreen), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
  });

  testWidgets('unverified account can explicitly verify without API', (
    tester,
  ) async {
    final session = AuthOnlySession(signedIn: true);
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, setupMessage: backendPending),
    );
    expect(find.byType(CollectionWorkspace), findsNothing);
    expect(session.tokenCalls, 0);
    expect(session.verificationRequests, 0);
    expect(find.text('Send verification email'), findsOneWidget);
    expect(find.text('I verified my email — check again'), findsOneWidget);
    await tester.tap(find.text('Send verification email'));
    await tester.pumpAndSettle();
    expect(session.verificationRequests, 1);
    expect(session.refreshes, 0);
    expect(session.tokenCalls, 0);
    expect(find.byType(CollectionWorkspace), findsNothing);
  });

  testWidgets('CONTROL: missing Firebase session stays in setup', (
    tester,
  ) async {
    await tester.pumpWidget(
      const SpecimenDigitizationApp(setupMessage: backendPending),
    );
    expect(find.text('Collection connection required'), findsOneWidget);
    expect(find.byType(SignInScreen), findsNothing);
    expect(find.byType(CollectionWorkspace), findsNothing);
  });

  testWidgets('CONTROL: verified account without API stays out of collection', (
    tester,
  ) async {
    final session = AuthOnlySession(signedIn: true, emailVerified: true);
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, setupMessage: backendPending),
    );
    expect(find.text('Collection connection required'), findsOneWidget);
    expect(find.text(backendPending), findsOneWidget);
    expect(find.byType(CollectionWorkspace), findsNothing);
    expect(session.tokenCalls, 0);
    expect(session.verificationRequests, 0);
  });

  testWidgets('auth-only login, verification, pending setup and sign-out', (
    tester,
  ) async {
    final session = AuthOnlySession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, setupMessage: backendPending),
    );
    await tester.enterText(
      find.byType(TextFormField).at(0),
      'test@example.test',
    );
    await tester.enterText(find.byType(TextFormField).at(1), 'local-test-only');
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Verify your account'), findsOneWidget);
    expect(session.verificationRequests, 0);
    expect(session.tokenCalls, 0);
    expect(find.byType(CollectionWorkspace), findsNothing);
    await tester.tap(find.text('Send verification email'));
    await tester.pumpAndSettle();
    expect(session.verificationRequests, 1);
    await tester.tap(find.text('I verified my email — check again'));
    await tester.pumpAndSettle();
    expect(session.refreshes, 1);
    expect(find.text(backendPending), findsOneWidget);
    expect(find.byType(CollectionWorkspace), findsNothing);
    expect(session.tokenCalls, 0);
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(session.signedIn, false);
    expect(find.byType(SignInScreen), findsOneWidget);
    expect(find.byType(CollectionWorkspace), findsNothing);
  });

  testWidgets('auth-only failed refresh keeps verification gate locked', (
    tester,
  ) async {
    final session = AuthOnlySession(signedIn: true)..failRefresh = true;
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, setupMessage: backendPending),
    );
    await tester.tap(find.text('I verified my email — check again'));
    await tester.pumpAndSettle();
    expect(session.refreshes, 1);
    expect(find.text('Verify your account'), findsOneWidget);
    expect(find.text(backendPending), findsNothing);
    expect(find.byType(CollectionWorkspace), findsNothing);
    expect(session.tokenCalls, 0);
  });

  testWidgets('already verified account can sign out from pending setup', (
    tester,
  ) async {
    final session = AuthOnlySession(signedIn: true, emailVerified: true);
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, setupMessage: backendPending),
    );
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(session.signedIn, false);
    expect(find.byType(SignInScreen), findsOneWidget);
    expect(session.tokenCalls, 0);
    expect(find.byType(CollectionWorkspace), findsNothing);
  });
}
