import 'package:flutter_test/flutter_test.dart';
import 'package:google_sign_in/google_sign_in.dart' as sdk;
import 'package:specimen_digitization/src/google_sign_in.dart';
import 'package:specimen_digitization/src/native_google_sign_in.dart';

class SdkFixture implements sdk.GoogleSignIn {
  final calls = <String>[];
  String? clientId, serverClientId, hostedDomain, nonce;
  List<String>? scopes;
  bool supports = true;
  String? token = 'sdk-id-token-fixture';
  Object? failure;
  Object? initializationFailure;

  @override
  Future<void> initialize({
    String? clientId,
    String? serverClientId,
    String? nonce,
    String? hostedDomain,
  }) async {
    calls.add('initialize');
    this.clientId = clientId;
    this.serverClientId = serverClientId;
    this.nonce = nonce;
    this.hostedDomain = hostedDomain;
    if (initializationFailure case final Object error) throw error;
  }

  @override
  bool supportsAuthenticate() => supports;

  @override
  Future<sdk.GoogleSignInAccount> authenticate({
    List<String> scopeHint = const [],
  }) async {
    calls.add('authenticate');
    scopes = scopeHint;
    if (failure case final Object error) throw error;
    return AccountFixture(token);
  }

  @override
  Future<void> signOut() async => calls.add('signOut');

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected SDK call: ${invocation.memberName}');
}

class AccountFixture implements sdk.GoogleSignInAccount {
  AccountFixture(this.token);
  final String? token;
  @override
  sdk.GoogleSignInAuthentication get authentication =>
      sdk.GoogleSignInAuthentication(idToken: token);
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected account field: ${invocation.memberName}');
}

Matcher failureKind(GoogleSignInFailureKind kind) => throwsA(
  isA<GoogleSignInFailure>().having((failure) => failure.kind, 'kind', kind),
);

void main() {
  test(
    'initializes once, clears old app account, and requests no extra scopes',
    () async {
      final google = SdkFixture();
      final bridge = GoogleSdkNativeSignIn.forTesting(
        google: google,
        clientId: 'actual-client-id-fixture',
        serverClientId: 'actual-server-id-fixture',
      );
      expect(await bridge.authenticate(), google.token);
      expect(await bridge.authenticate(), google.token);
      expect(google.calls, [
        'initialize',
        'signOut',
        'authenticate',
        'signOut',
        'authenticate',
      ]);
      expect(google.clientId, 'actual-client-id-fixture');
      expect(google.serverClientId, 'actual-server-id-fixture');
      expect(google.scopes, isEmpty);
      expect(google.hostedDomain, isNull);
      expect(google.nonce, isNull);
    },
  );

  test('platform configuration receives no fabricated client IDs', () async {
    final google = SdkFixture();
    final bridge = GoogleSdkNativeSignIn.forTesting(
      google: google,
      clientId: '',
      serverClientId: '',
    );
    await bridge.signOut();
    expect(google.calls, isEmpty);
    await bridge.authenticate();
    expect(google.clientId, isNull);
    expect(google.serverClientId, isNull);
    await bridge.signOut();
    expect(google.calls.last, 'signOut');
  });

  test('SDK cancellation is neutral and a later attempt can succeed', () async {
    final google = SdkFixture()
      ..failure = const sdk.GoogleSignInException(
        code: sdk.GoogleSignInExceptionCode.canceled,
      );
    final bridge = GoogleSdkNativeSignIn.forTesting(google: google);
    expect(await bridge.authenticate(), isNull);
    google.failure = null;
    expect(await bridge.authenticate(), google.token);
    expect(google.calls.where((call) => call == 'initialize').length, 1);
  });

  test('unsupported interactive SDK never opens account selection', () async {
    final google = SdkFixture()..supports = false;
    final bridge = GoogleSdkNativeSignIn.forTesting(google: google);
    await expectLater(
      bridge.authenticate(),
      failureKind(GoogleSignInFailureKind.unavailable),
    );
    expect(google.calls, ['initialize']);
  });

  test(
    'missing ID token cannot be returned as successful authentication',
    () async {
      final google = SdkFixture();
      final bridge = GoogleSdkNativeSignIn.forTesting(google: google);
      for (final token in [null, '']) {
        google.token = token;
        await expectLater(
          bridge.authenticate(),
          failureKind(GoogleSignInFailureKind.unknown),
        );
      }
    },
  );

  test(
    'SDK failures are bounded with default handling for future codes',
    () async {
      final google = SdkFixture();
      final bridge = GoogleSdkNativeSignIn.forTesting(google: google);
      for (final code in sdk.GoogleSignInExceptionCode.values) {
        if (code == sdk.GoogleSignInExceptionCode.canceled) continue;
        google.failure = sdk.GoogleSignInException(
          code: code,
          description: 'private-provider-detail',
        );
        final configuration =
            code == sdk.GoogleSignInExceptionCode.clientConfigurationError ||
            code == sdk.GoogleSignInExceptionCode.providerConfigurationError;
        await expectLater(
          bridge.authenticate(),
          failureKind(
            configuration
                ? GoogleSignInFailureKind.unavailable
                : GoogleSignInFailureKind.unknown,
          ),
        );
      }
      google.failure = StateError('private-provider-detail');
      await expectLater(
        bridge.authenticate(),
        failureKind(GoogleSignInFailureKind.unknown),
      );
    },
  );

  test('failed initialization is not called twice on singleton SDK', () async {
    final google = SdkFixture()
      ..initializationFailure = const sdk.GoogleSignInException(
        code: sdk.GoogleSignInExceptionCode.clientConfigurationError,
      );
    final bridge = GoogleSdkNativeSignIn.forTesting(google: google);
    for (var attempt = 0; attempt < 2; attempt++) {
      await expectLater(
        bridge.authenticate(),
        failureKind(GoogleSignInFailureKind.unavailable),
      );
    }
    expect(google.calls, ['initialize']);
  });
}
