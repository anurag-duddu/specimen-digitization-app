import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart' as sdk;

import 'google_sign_in.dart';

/// The native SDK returns an ID token for Firebase to verify, or cancellation.
abstract interface class NativeGoogleSignIn {
  Future<String?> authenticate();
  Future<void> signOut();
}

/// Official Google SDK bridge for configured iOS and Android applications.
///
/// The shared instance initializes the SDK exactly once. Client IDs may come
/// from real platform configuration or explicit build values; there are no
/// substitute IDs. iOS still requires its reversed-client callback URL scheme.
class GoogleSdkNativeSignIn implements NativeGoogleSignIn {
  GoogleSdkNativeSignIn._({
    required sdk.GoogleSignIn google,
    String? clientId,
    String? serverClientId,
  }) : _google = google,
       _clientId = clientId?.isEmpty == true ? null : clientId,
       _serverClientId = serverClientId?.isEmpty == true
           ? null
           : serverClientId;

  @visibleForTesting
  GoogleSdkNativeSignIn.forTesting({
    required sdk.GoogleSignIn google,
    String? clientId,
    String? serverClientId,
  }) : this._(
         google: google,
         clientId: clientId,
         serverClientId: serverClientId,
       );

  static final GoogleSdkNativeSignIn instance = GoogleSdkNativeSignIn._(
    google: sdk.GoogleSignIn.instance,
    clientId: const String.fromEnvironment('SPECIMEN_GOOGLE_NATIVE_CLIENT_ID'),
    serverClientId: const String.fromEnvironment(
      'SPECIMEN_GOOGLE_SERVER_CLIENT_ID',
    ),
  );

  final sdk.GoogleSignIn _google;
  final String? _clientId;
  final String? _serverClientId;
  Future<void>? _initialization;

  Future<void> _initialize() => _initialization ??= _google.initialize(
    clientId: _clientId,
    serverClientId: _serverClientId,
  );

  @override
  Future<String?> authenticate() async {
    try {
      await _initialize();
      if (!_google.supportsAuthenticate()) {
        throw const GoogleSignInFailure(GoogleSignInFailureKind.unavailable);
      }
      // Clear the SDK's previous app account before explicit account selection.
      // This does not disconnect the device's Google account or revoke consent.
      await _google.signOut();
      final account = await _google.authenticate();
      final token = account.authentication.idToken;
      if (token == null || token.isEmpty) {
        throw const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
      }
      return token;
    } on sdk.GoogleSignInException catch (error) {
      if (error.code == sdk.GoogleSignInExceptionCode.canceled) return null;
      throw GoogleSignInFailure(switch (error.code) {
        sdk.GoogleSignInExceptionCode.clientConfigurationError ||
        sdk.GoogleSignInExceptionCode.providerConfigurationError =>
          GoogleSignInFailureKind.unavailable,
        _ => GoogleSignInFailureKind.unknown,
      });
    } on GoogleSignInFailure {
      rethrow;
    } catch (_) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
    }
  }

  @override
  Future<void> signOut() async {
    // Email-only sessions must not initialize an unconfigured Google SDK.
    if (_initialization == null) return;
    try {
      await _initialization;
      await _google.signOut();
    } catch (_) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
    }
  }
}
