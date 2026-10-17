import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';

import 'google_sign_in.dart';
import 'magic_link.dart';
import 'native_google_sign_in.dart';

/// Requests Google authentication without admitting an app session.
///
/// The caller must quarantine Firebase auth events until the returned and
/// current identities have passed its verified-email and account checks.
class GoogleFirebaseSignInAdapter {
  GoogleFirebaseSignInAdapter({
    required FirebaseAuth auth,
    bool enabled = false,
    bool? web,
    TargetPlatform? platform,
    bool nativeConfigured = false,
    NativeGoogleSignIn? nativeSignIn,
  }) : _auth = auth,
       _enabled = enabled,
       _web = web ?? kIsWeb,
       _platform = platform ?? defaultTargetPlatform,
       _nativeConfigured = nativeConfigured,
       _nativeSignIn = nativeSignIn;

  final FirebaseAuth _auth;
  final bool _enabled;
  final bool _web;
  final TargetPlatform _platform;
  final bool _nativeConfigured;
  NativeGoogleSignIn? _nativeSignIn;

  bool get available =>
      _enabled &&
      (_web ||
          (_nativeConfigured &&
              (_platform == TargetPlatform.iOS ||
                  _platform == TargetPlatform.android)));

  /// An email hint is a convenience, never an account restriction or proof.
  Future<UserCredential?> authenticate([String? emailHint]) async {
    if (!available) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.unavailable);
    }
    try {
      if (_web) {
        final hint = normalizedStaffEmail(emailHint?.trim() ?? '');
        final provider = GoogleAuthProvider()
          ..setCustomParameters({
            'prompt': 'select_account',
            'login_hint': ?hint,
          });
        // No await before opening the popup: preserve browser user activation.
        return await _auth.signInWithPopup(provider);
      }
      final native = _nativeSignIn ??= GoogleSdkNativeSignIn.instance;
      final idToken = await native.authenticate();
      if (idToken == null) return null;
      if (idToken.isEmpty) {
        throw const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
      }
      return await _auth.signInWithCredential(
        GoogleAuthProvider.credential(idToken: idToken),
      );
    } on FirebaseAuthException catch (error) {
      if (error.code == 'popup-closed-by-user' ||
          error.code == 'cancelled-popup-request' ||
          error.code == 'web-context-cancelled') {
        return null;
      }
      throw GoogleSignInFailure(switch (error.code) {
        'popup-blocked' => GoogleSignInFailureKind.popupBlocked,
        'network-request-failed' => GoogleSignInFailureKind.network,
        'operation-not-allowed' ||
        'unauthorized-domain' ||
        'invalid-api-key' ||
        'app-not-authorized' => GoogleSignInFailureKind.unavailable,
        'account-exists-with-different-credential' ||
        'credential-already-in-use' ||
        'email-already-in-use' => GoogleSignInFailureKind.accountConflict,
        'admin-restricted-operation' ||
        'user-disabled' => GoogleSignInFailureKind.policyBlocked,
        _ => GoogleSignInFailureKind.unknown,
      });
    } on GoogleSignInFailure {
      rethrow;
    } catch (_) {
      throw const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
    }
  }

  /// Clears only this app's initialized native Google session.
  Future<void> signOut() async {
    if (!_web) await _nativeSignIn?.signOut();
  }
}
