import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app/session_notifier.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/firebase_google_sign_in.dart';
import 'package:specimen_digitization/src/google_sign_in.dart';
import 'package:specimen_digitization/src/models.dart';

class GoogleUserFixture implements User {
  GoogleUserFixture({
    this.uid = 'existing-staff-uid',
    this.email = 'staff@fieldmuseum.org',
    this.emailVerified = true,
  });

  @override
  final String uid;
  @override
  final String? email;
  @override
  final bool emailVerified;
  final tokenRequests = <bool>[];

  @override
  Future<String?> getIdToken([bool forceRefresh = false]) async {
    tokenRequests.add(forceRefresh);
    return 'credential-free-token-fixture';
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected user operation: ${invocation.memberName}');
}

class GoogleCredentialFixture implements UserCredential {
  GoogleCredentialFixture(this.user);
  @override
  final User? user;
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected credential operation');
}

/// Deliberately emits an SDK user before the sign-in future has settled.
class GoogleSessionAuthFixture implements FirebaseAuth {
  GoogleSessionAuthFixture({bool synchronousEvents = true})
    : events = StreamController<User?>.broadcast(sync: synchronousEvents);

  final StreamController<User?> events;
  @override
  User? currentUser;
  Completer<UserCredential> popup = Completer<UserCredential>();
  final providers = <AuthProvider>[];
  int signOutCalls = 0;
  bool failSignOut = false;

  void publish(User? user) {
    currentUser = user;
    events.add(user);
  }

  @override
  Stream<User?> userChanges() => events.stream;

  @override
  Future<UserCredential> signInWithPopup(AuthProvider provider) {
    providers.add(provider);
    return popup.future;
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
    if (failSignOut) throw StateError('Cleanup failed fixture');
    publish(null);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected auth operation: ${invocation.memberName}');
}

Future<void> flushEvents() => Future<void>.delayed(Duration.zero);

Matcher googleFailure(GoogleSignInFailureKind kind) =>
    isA<GoogleSignInFailure>().having((e) => e.kind, 'kind', kind);

void main() {
  late GoogleSessionAuthFixture auth;
  late FirebaseSession session;
  late AppSessionNotifier notifier;
  late StreamSubscription<bool> subscription;
  late List<bool> events;

  setUp(() {
    auth = GoogleSessionAuthFixture();
    session = FirebaseSession(
      auth,
      google: GoogleFirebaseSignInAdapter(auth: auth, enabled: true, web: true),
    );
    notifier = AppSessionNotifier(session: session);
    events = <bool>[];
    subscription = session.changes.listen(events.add);
  });

  tearDown(() async {
    notifier.dispose();
    await subscription.cancel();
    await auth.events.close();
  });

  Future<void> expectBlocked(GoogleUserFixture user) async {
    expect(session.signedIn, isFalse);
    expect(session.userId, isEmpty);
    expect(session.displayName, isEmpty);
    expect(session.staffEmailAllowed, isFalse);
    expect(session.emailVerified, isFalse);
    expect(notifier.signedIn, isFalse);
    await expectLater(session.token(), throwsA(isA<ApiFailure>()));
    await expectLater(session.freshToken(), throwsA(isA<ApiFailure>()));
    expect(user.tokenRequests, isEmpty);
    expect(events, isNot(contains(true)));
  }

  test('raw SDK identity remains private until checked success', () async {
    final user = GoogleUserFixture();
    notifier.pendingLocation = '/c/org/plants/queue/record-1';
    final signingIn = session.signInWithGoogle();
    expect(auth.providers, hasLength(1));
    auth.publish(user);
    await flushEvents();
    await expectBlocked(user);

    auth.popup.complete(GoogleCredentialFixture(user));
    expect(await signingIn, GoogleSignInOutcome.signedIn);
    await flushEvents();
    expect(events, <bool>[true]);
    expect(notifier.signedIn, isTrue);
    expect(notifier.verified, isTrue);
    expect(notifier.pendingLocation, '/c/org/plants/queue/record-1');
    expect(session.userId, 'existing-staff-uid');
    expect(session.displayName, 'staff@fieldmuseum.org');
    expect(await session.token(), 'credential-free-token-fixture');
    expect(await session.freshToken(), 'credential-free-token-fixture');
    expect(user.tokenRequests, <bool>[false, true]);
    expect(auth.signOutCalls, 0);
  });

  for (final email in <String?>[
    'outside@@example.org',
    'staff@sub..fieldmuseum.org',
    'staff@fieldmuseum.org.example.org.',
    'staff@fіeldmuseum.org',
    'other@infinative.com ',
    null,
  ]) {
    test('rejected returned email never emits authenticated: $email', () async {
      final user = GoogleUserFixture(email: email);
      final signingIn = session.signInWithGoogle();
      auth.publish(user);
      await flushEvents();
      await expectBlocked(user);
      final rejected = expectLater(
        signingIn,
        throwsA(googleFailure(GoogleSignInFailureKind.accountNotAllowed)),
      );
      auth.popup.complete(GoogleCredentialFixture(user));
      await rejected;
      await flushEvents();
      expect(auth.currentUser, isNull);
      expect(auth.signOutCalls, 1);
      expect(events, isNot(contains(true)));
      expect(user.tokenRequests, isEmpty);
    });
  }

  test('unverified staff cannot expose a session or token', () async {
    final user = GoogleUserFixture(emailVerified: false);
    final signingIn = session.signInWithGoogle();
    auth.publish(user);
    final rejected = expectLater(
      signingIn,
      throwsA(googleFailure(GoogleSignInFailureKind.unverifiedEmail)),
    );
    auth.popup.complete(GoogleCredentialFixture(user));
    await rejected;
    await flushEvents();
    expect(events, isNot(contains(true)));
    expect(notifier.verified, isFalse);
    expect(user.tokenRequests, isEmpty);
  });

  for (final mismatchedUid in <bool>[true, false]) {
    test(
      'returned/current identity mismatch is rejected: uid=$mismatchedUid',
      () async {
        final returned = GoogleUserFixture();
        final current = GoogleUserFixture(
          uid: mismatchedUid ? 'other-uid' : returned.uid,
          email: mismatchedUid ? returned.email : 'other@fieldmuseum.org',
        );
        final signingIn = session.signInWithGoogle();
        auth.publish(current);
        final rejected = expectLater(
          signingIn,
          throwsA(googleFailure(GoogleSignInFailureKind.accountNotAllowed)),
        );
        auth.popup.complete(GoogleCredentialFixture(returned));
        await rejected;
        await flushEvents();
        expect(events, isNot(contains(true)));
        expect(current.tokenRequests, isEmpty);
      },
    );
  }

  test(
    'optional email hint does not restrict actual allowed account',
    () async {
      final user = GoogleUserFixture(email: 'another@fieldmuseum.org');
      final signingIn = session.signInWithGoogle(
        emailHint: 'first@fieldmuseum.org',
      );
      auth.publish(user);
      auth.popup.complete(GoogleCredentialFixture(user));
      expect(await signingIn, GoogleSignInOutcome.signedIn);
      expect(session.displayName, 'another@fieldmuseum.org');
    },
  );

  test('exact approved owner retains the actual Firebase UID', () async {
    final user = GoogleUserFixture(
      uid: 'existing-owner-uid',
      email: 'ANURAG@INFINATIVE.COM',
    );
    final signingIn = session.signInWithGoogle();
    auth.publish(user);
    auth.popup.complete(GoogleCredentialFixture(user));
    expect(await signingIn, GoogleSignInOutcome.signedIn);
    expect(session.userId, 'existing-owner-uid');
    expect(session.staffEmailAllowed, isTrue);
    expect(await session.token(), 'credential-free-token-fixture');
  });

  test(
    'verified external identity reaches the ordinary server admission check',
    () async {
      final user = GoogleUserFixture(email: 'tester.external@gmail.com');
      final signingIn = session.signInWithGoogle();
      auth.publish(user);
      await flushEvents();
      await expectBlocked(user);
      auth.popup.complete(GoogleCredentialFixture(user));
      expect(await signingIn, GoogleSignInOutcome.signedIn);
      expect(await session.token(), 'credential-free-token-fixture');
      // No collection or role is created by the Firebase adapter.
      expect(session.userId, user.uid);
      expect(auth.signOutCalls, 0);
    },
  );

  test(
    'cleanup failure quarantines rejected user until explicit cleanup retry',
    () async {
      final user = GoogleUserFixture(email: 'outside@@example.org');
      auth.failSignOut = true;
      final signingIn = session.signInWithGoogle();
      auth.publish(user);
      final rejected = expectLater(
        signingIn,
        throwsA(googleFailure(GoogleSignInFailureKind.accountNotAllowed)),
      );
      auth.popup.complete(GoogleCredentialFixture(user));
      await rejected;
      auth.publish(user);
      await flushEvents();
      await expectBlocked(user);

      auth.failSignOut = false;
      await expectLater(
        session.signInWithGoogle(),
        throwsA(googleFailure(GoogleSignInFailureKind.unknown)),
      );
      expect(auth.currentUser, isNull);
      expect(auth.providers, hasLength(1));
      expect(session.signedIn, isFalse);

      auth.popup = Completer<UserCredential>();
      final allowed = GoogleUserFixture();
      final retry = session.signInWithGoogle();
      auth.publish(allowed);
      auth.popup.complete(GoogleCredentialFixture(allowed));
      expect(await retry, GoogleSignInOutcome.signedIn);
      expect(auth.providers, hasLength(2));
      expect(session.userId, allowed.uid);
    },
  );

  test('explicit sign-out invalidates a late provider success', () async {
    final signingIn = session.signInWithGoogle();
    await session.signOut();
    final user = GoogleUserFixture();
    auth.publish(user);
    await flushEvents();
    await expectBlocked(user);
    final rejected = expectLater(
      signingIn,
      throwsA(googleFailure(GoogleSignInFailureKind.unknown)),
    );
    auth.popup.complete(GoogleCredentialFixture(user));
    await rejected;
    await flushEvents();
    expect(auth.currentUser, isNull);
    expect(events, isNot(contains(true)));
    expect(auth.signOutCalls, 2);
  });

  test('provider cancellation cleans any intermediate SDK identity', () async {
    final user = GoogleUserFixture();
    final signingIn = session.signInWithGoogle();
    auth.publish(user);
    auth.popup.completeError(
      FirebaseAuthException(code: 'popup-closed-by-user'),
    );
    expect(await signingIn, GoogleSignInOutcome.cancelled);
    await flushEvents();
    expect(auth.currentUser, isNull);
    expect(events, isNot(contains(true)));
  });

  test(
    'queued raw SDK events report current state rather than stale user',
    () async {
      final queuedAuth = GoogleSessionAuthFixture(synchronousEvents: false);
      final queuedSession = FirebaseSession(queuedAuth);
      final observed = <bool>[];
      final listener = queuedSession.changes.listen(observed.add);
      queuedAuth.publish(GoogleUserFixture());
      queuedAuth.publish(null);
      await flushEvents();
      expect(observed, isNot(contains(true)));
      expect(queuedSession.signedIn, isFalse);
      await listener.cancel();
      await queuedAuth.events.close();
    },
  );
}
