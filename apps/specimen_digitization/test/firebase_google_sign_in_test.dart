import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/firebase_google_sign_in.dart';
import 'package:specimen_digitization/src/google_sign_in.dart';
import 'package:specimen_digitization/src/native_google_sign_in.dart';

class AuthFixture implements FirebaseAuth {
  AuthProvider? provider;
  AuthCredential? credential;
  int popupCalls = 0, credentialCalls = 0;
  Object? failure;
  final result = CredentialFixture();

  @override
  Future<UserCredential> signInWithPopup(AuthProvider provider) async {
    this.provider = provider;
    popupCalls++;
    if (failure case final Object error) throw error;
    return result;
  }

  @override
  Future<UserCredential> signInWithCredential(AuthCredential credential) async {
    this.credential = credential;
    credentialCalls++;
    if (failure case final Object error) throw error;
    return result;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected Firebase call: ${invocation.memberName}');
}

class CredentialFixture implements UserCredential {
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unused credential fixture');
}

class NativeFixture implements NativeGoogleSignIn {
  String? token = 'native-id-token-fixture';
  int calls = 0, signOutCalls = 0;
  @override
  Future<String?> authenticate() async {
    calls++;
    return token;
  }

  @override
  Future<void> signOut() async => signOutCalls++;
}

Matcher failureKind(GoogleSignInFailureKind kind) => throwsA(
  isA<GoogleSignInFailure>().having((failure) => failure.kind, 'kind', kind),
);

void main() {
  test('disabled provider cannot invoke Firebase or native SDK', () async {
    final auth = AuthFixture();
    final native = NativeFixture();
    final adapter = GoogleFirebaseSignInAdapter(
      auth: auth,
      web: true,
      nativeSignIn: native,
    );
    expect(adapter.available, false);
    await expectLater(
      adapter.authenticate(),
      failureKind(GoogleSignInFailureKind.unavailable),
    );
    expect(auth.popupCalls, 0);
    expect(native.calls, 0);
  });

  test(
    'web opens Google popup immediately with no added data scopes',
    () async {
      final auth = AuthFixture();
      final adapter = GoogleFirebaseSignInAdapter(
        auth: auth,
        enabled: true,
        web: true,
      );
      final attempt = adapter.authenticate();
      expect(auth.popupCalls, 1);
      expect(await attempt, same(auth.result));
      final provider = auth.provider as GoogleAuthProvider;
      expect(provider.providerId, 'google.com');
      expect(provider.scopes, isEmpty);
      expect(provider.parameters, {'prompt': 'select_account'});
      expect(auth.credentialCalls, 0);
    },
  );

  test(
    'optional allowed hint normalizes; invalid hint does not restrict login',
    () async {
      final auth = AuthFixture();
      final adapter = GoogleFirebaseSignInAdapter(
        auth: auth,
        enabled: true,
        web: true,
      );
      for (final hint in [' STAFF@FIELDMUSEUM.ORG ', 'ANURAG@INFINATIVE.COM']) {
        await adapter.authenticate(hint);
        expect((auth.provider as GoogleAuthProvider).parameters, {
          'prompt': 'select_account',
          'login_hint': hint.trim().toLowerCase(),
        });
      }
      await adapter.authenticate('staff@fieldmuseum.org.evil.example');
      expect((auth.provider as GoogleAuthProvider).parameters, {
        'prompt': 'select_account',
      });
    },
  );

  test(
    'native registration gate and platform gate prevent SDK calls',
    () async {
      final auth = AuthFixture();
      final native = NativeFixture();
      for (final platform in TargetPlatform.values) {
        final adapter = GoogleFirebaseSignInAdapter(
          auth: auth,
          enabled: true,
          web: false,
          platform: platform,
          nativeSignIn: native,
        );
        expect(adapter.available, false);
        await expectLater(
          adapter.authenticate(),
          failureKind(GoogleSignInFailureKind.unavailable),
        );
      }
      final desktop = GoogleFirebaseSignInAdapter(
        auth: auth,
        enabled: true,
        web: false,
        nativeConfigured: true,
        platform: TargetPlatform.macOS,
        nativeSignIn: native,
      );
      expect(desktop.available, false);
      expect(native.calls, 0);
      expect(auth.popupCalls + auth.credentialCalls, 0);
    },
  );

  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    test(
      'configured $platform exchanges native ID token with Firebase',
      () async {
        final auth = AuthFixture();
        final native = NativeFixture();
        final adapter = GoogleFirebaseSignInAdapter(
          auth: auth,
          enabled: true,
          web: false,
          nativeConfigured: true,
          platform: platform,
          nativeSignIn: native,
        );
        expect(adapter.available, true);
        expect(await adapter.authenticate(), same(auth.result));
        final credential = auth.credential as OAuthCredential;
        expect(credential.providerId, 'google.com');
        expect(credential.idToken, native.token);
        expect(credential.accessToken, isNull);
        expect(auth.popupCalls, 0);
        await adapter.signOut();
        expect(native.signOutCalls, 1);
      },
    );
  }

  test('native cancellation and missing token never call Firebase', () async {
    final auth = AuthFixture();
    final native = NativeFixture()..token = null;
    final adapter = GoogleFirebaseSignInAdapter(
      auth: auth,
      enabled: true,
      web: false,
      nativeConfigured: true,
      platform: TargetPlatform.iOS,
      nativeSignIn: native,
    );
    expect(await adapter.authenticate(), isNull);
    native.token = '';
    await expectLater(
      adapter.authenticate(),
      failureKind(GoogleSignInFailureKind.unknown),
    );
    expect(auth.credentialCalls, 0);
  });

  test('popup cancellation is a neutral result and can retry', () async {
    final auth = AuthFixture();
    final adapter = GoogleFirebaseSignInAdapter(
      auth: auth,
      enabled: true,
      web: true,
    );
    for (final code in [
      'popup-closed-by-user',
      'cancelled-popup-request',
      'web-context-cancelled',
    ]) {
      auth.failure = FirebaseAuthException(code: code);
      expect(await adapter.authenticate(), isNull);
    }
    auth.failure = null;
    expect(await adapter.authenticate(), same(auth.result));
  });

  test('provider failures have bounded recovery categories', () async {
    final auth = AuthFixture();
    final adapter = GoogleFirebaseSignInAdapter(
      auth: auth,
      enabled: true,
      web: true,
    );
    final cases = {
      'popup-blocked': GoogleSignInFailureKind.popupBlocked,
      'network-request-failed': GoogleSignInFailureKind.network,
      'operation-not-allowed': GoogleSignInFailureKind.unavailable,
      'unauthorized-domain': GoogleSignInFailureKind.unavailable,
      'account-exists-with-different-credential':
          GoogleSignInFailureKind.accountConflict,
      'credential-already-in-use': GoogleSignInFailureKind.accountConflict,
      'admin-restricted-operation': GoogleSignInFailureKind.policyBlocked,
      'user-disabled': GoogleSignInFailureKind.policyBlocked,
      'future-provider-error': GoogleSignInFailureKind.unknown,
    };
    for (final entry in cases.entries) {
      auth.failure = FirebaseAuthException(
        code: entry.key,
        message: 'private-provider-detail',
      );
      await expectLater(adapter.authenticate(), failureKind(entry.value));
    }
    auth.failure = StateError('private-provider-detail');
    await expectLater(
      adapter.authenticate(),
      failureKind(GoogleSignInFailureKind.unknown),
    );
  });

  test('web signout never signs out the native SDK', () async {
    final native = NativeFixture();
    final adapter = GoogleFirebaseSignInAdapter(
      auth: AuthFixture(),
      enabled: true,
      web: true,
      nativeSignIn: native,
    );
    await adapter.signOut();
    expect(native.signOutCalls, 0);
  });
}
