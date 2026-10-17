import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/firebase_google_sign_in.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'firebase_google_session_test.dart'
    show GoogleCredentialFixture, GoogleSessionAuthFixture, GoogleUserFixture;
import 'magic_link_controller_test.dart'
    show FakeEmailLinkSource, MemoryLinkStorage, testLink;

class DispatchAuthFixture extends GoogleSessionAuthFixture {
  final sent = <String>[];
  final completed = <(String, String)>[];
  Completer<void>? sendGate;
  Object? sendFailure;

  @override
  bool isSignInWithEmailLink(String link) => link == testLink;

  @override
  Future<void> sendSignInLinkToEmail({
    required String email,
    required ActionCodeSettings actionCodeSettings,
  }) async {
    sent.add(email);
    await sendGate?.future;
    if (sendFailure case final Object failure) throw failure;
  }

  @override
  Future<UserCredential> signInWithEmailLink({
    required String email,
    required String emailLink,
  }) async {
    completed.add((email, emailLink));
    final user = GoogleUserFixture(email: email);
    publish(user);
    return GoogleCredentialFixture(user);
  }
}

void main() {
  late DispatchAuthFixture auth;
  MagicLinkController? link;

  setUp(() {
    link = null;
  });

  tearDown(() async {
    link?.dispose();
    await auth.events.close();
  });

  Future<void> mount(
    WidgetTester tester, {
    bool google = true,
    String? incoming,
    FakeEmailLinkSource? source,
  }) async {
    // The provider completion belongs to the widget test's fake-async zone.
    auth = DispatchAuthFixture();
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(800, 1100);
    addTearDown(tester.view.reset);
    final session = FirebaseSession(
      auth,
      google: GoogleFirebaseSignInAdapter(
        auth: auth,
        enabled: google,
        web: true,
      ),
    );
    link = MagicLinkController(
      access: session,
      browser: MemoryEmailLinkBrowser(
        uri: incoming == null ? null : Uri.parse(incoming),
      ),
      storage: MemoryLinkStorage(),
      linkSource: source,
    );
    await link!.initialize();
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: SignInScreen(session: session, magicLink: link),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> unmount(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox());
    await tester.pumpAndSettle();
  }

  testWidgets('disabled Google preserves production email-link entry', (
    tester,
  ) async {
    await mount(tester, google: false);
    expect(find.byType(MagicLinkSignInScreen), findsOneWidget);
    expect(find.text('Send link'), findsOneWidget);
    expect(find.text('Sign in with Google'), findsNothing);
    expect(find.text('Password'), findsNothing);
    await tester.enterText(find.byType(UiField), 'staff@fieldmuseum.org');
    await tester.tap(find.text('Send link'));
    await tester.pumpAndSettle();
    expect(auth.sent, ['staff@fieldmuseum.org']);
    expect(auth.providers, isEmpty);
    expect(find.text('Check your email'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('Google is secondary and needs no typed email', (tester) async {
    await mount(tester);
    final emailButton = find.text('Send link');
    final googleButton = find.text('Sign in with Google');
    expect(emailButton, findsOneWidget);
    expect(googleButton, findsOneWidget);
    expect(
      tester.getTopLeft(emailButton).dy,
      lessThan(tester.getTopLeft(googleButton).dy),
    );
    expect(
      tester.widget<EditableText>(find.byType(EditableText)).controller.text,
      isEmpty,
    );
    await tester.tap(googleButton);
    await tester.pump();
    expect(auth.providers, hasLength(1));
    expect(auth.sent, isEmpty);
    auth.popup.completeError(
      FirebaseAuthException(code: 'popup-closed-by-user'),
    );
    await tester.pumpAndSettle();
    expect(find.text('Send link'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('Google cancellation preserves typed email for fallback', (
    tester,
  ) async {
    await mount(tester);
    await tester.enterText(find.byType(UiField), 'Staff@FieldMuseum.org');
    await tester.tap(find.text('Sign in with Google'));
    await tester.pump();
    expect(tester.widget<UiField>(find.byType(UiField)).enabled, isFalse);
    await tester.tap(find.text('Send link'));
    expect(auth.sent, isEmpty);
    auth.popup.completeError(
      FirebaseAuthException(code: 'popup-closed-by-user'),
    );
    await tester.pumpAndSettle();
    expect(
      tester.widget<EditableText>(find.byType(EditableText)).controller.text,
      'Staff@FieldMuseum.org',
    );
    expect(tester.widget<UiField>(find.byType(UiField)).enabled, isTrue);
    await tester.tap(find.text('Send link'));
    await tester.pumpAndSettle();
    expect(auth.sent, ['staff@fieldmuseum.org']);
    expect(find.text('Check your email'), findsOneWidget);
    expect(find.text('Sign in with Google'), findsNothing);
    await unmount(tester);
  });

  testWidgets('sending an email link excludes parallel Google dispatch', (
    tester,
  ) async {
    await mount(tester);
    auth.sendGate = Completer<void>();
    await tester.enterText(find.byType(UiField), 'staff@fieldmuseum.org');
    await tester.tap(find.text('Send link'));
    await tester.pump();
    await tester.tap(find.text('Sign in with Google'));
    await tester.pump();
    expect(auth.providers, isEmpty);
    expect(auth.sent, ['staff@fieldmuseum.org']);
    auth.sendGate!.complete();
    await tester.pumpAndSettle();
    expect(find.text('Sign in with Google'), findsNothing);
    await unmount(tester);
  });

  testWidgets('received email link takes priority over optional Google', (
    tester,
  ) async {
    await mount(tester, incoming: testLink);
    expect(find.text('Confirm your email'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Sign in with Google'), findsNothing);
    expect(auth.completed, isEmpty);
    await tester.enterText(find.byType(UiField), 'staff@fieldmuseum.org');
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(auth.completed, [('staff@fieldmuseum.org', testLink)]);
    expect(auth.providers, isEmpty);
    await unmount(tester);
  });

  testWidgets('warm link cannot dispatch Firebase completion during Google', (
    tester,
  ) async {
    final source = FakeEmailLinkSource();
    addTearDown(source.close);
    await mount(tester, source: source);
    auth.sendFailure = FirebaseAuthException(code: 'network-request-failed');
    await tester.enterText(find.byType(UiField), 'staff@fieldmuseum.org');
    await tester.tap(find.text('Send link'));
    await tester.pumpAndSettle();
    expect(link!.email, 'staff@fieldmuseum.org');
    expect(link!.sent, isFalse);

    await tester.tap(find.text('Sign in with Google'));
    await tester.pump();
    source.deliver(Uri.parse(testLink));
    await tester.pump();
    expect(link!.handlingLink, isTrue);
    expect(link!.hasError, isTrue);
    expect(auth.completed, isEmpty);
    expect(tester.widget<UiField>(find.byType(UiField)).enabled, isFalse);

    auth.popup.completeError(
      FirebaseAuthException(code: 'popup-closed-by-user'),
    );
    await tester.pumpAndSettle();
    expect(find.text('Sign in with Google'), findsNothing);
    expect(tester.widget<UiField>(find.byType(UiField)).enabled, isTrue);
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(auth.completed, [('staff@fieldmuseum.org', testLink)]);
    expect(auth.currentUser?.email, 'staff@fieldmuseum.org');
    await unmount(tester);
  });
}
