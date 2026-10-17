import 'package:flutter/foundation.dart';

/// Google sign-in, separate from email-link delivery.
///
/// Implementations must not expose an authenticated app session until the
/// returned identity has passed their account checks. An optional email hint is
/// never proof of identity or collection permission.
abstract interface class GoogleSignInAccess {
  bool get googleSignInAvailable;

  Future<GoogleSignInOutcome> signInWithGoogle({String? emailHint});
}

enum GoogleSignInOutcome { signedIn, cancelled }

enum GoogleSignInFailureKind {
  unavailable,
  popupBlocked,
  network,
  accountNotAllowed,
  unverifiedEmail,
  accountConflict,
  policyBlocked,
  unknown,
}

/// A bounded outcome whose UI never displays raw provider exceptions or URLs.
class GoogleSignInFailure implements Exception {
  const GoogleSignInFailure(this.kind);

  final GoogleSignInFailureKind kind;

  String get message => switch (kind) {
    GoogleSignInFailureKind.unavailable =>
      'Google sign-in is not available. Use an email link or get sign-in help.',
    GoogleSignInFailureKind.popupBlocked =>
      'Your browser blocked the sign-in window. Allow pop-ups for this site, then try again.',
    GoogleSignInFailureKind.network =>
      'Could not reach the sign-in service. Check your connection and try again.',
    GoogleSignInFailureKind.accountNotAllowed =>
      'Choose your Field Museum account or another approved account.',
    GoogleSignInFailureKind.unverifiedEmail =>
      'Google did not verify this email address. Use an email link or get sign-in help.',
    GoogleSignInFailureKind.accountConflict =>
      'This account uses another sign-in method. Use your existing email link or get sign-in help.',
    GoogleSignInFailureKind.policyBlocked =>
      'Your organization has not allowed this sign-in. Contact your sign-in administrator.',
    GoogleSignInFailureKind.unknown =>
      'Sign-in did not finish. Try again or get sign-in help.',
  };

  @override
  String toString() => 'GoogleSignInFailure(${kind.name})';
}

/// Owns one Google sign-in attempt without making permission decisions.
class GoogleSignInController extends ChangeNotifier {
  GoogleSignInController({required this.access});

  final GoogleSignInAccess access;
  GoogleSignInFailure? _failure;
  GoogleSignInOutcome? _lastOutcome;
  bool _busy = false;
  bool _disposed = false;
  int _epoch = 0;

  GoogleSignInFailure? get failure => _failure;
  GoogleSignInOutcome? get lastOutcome => _lastOutcome;
  bool get busy => _busy;

  /// Returns null for failure or an ignored duplicate attempt.
  Future<GoogleSignInOutcome?> signIn({String? emailHint}) async {
    if (_disposed || _busy) return null;
    _failure = null;
    _lastOutcome = null;
    if (!access.googleSignInAvailable) {
      _failure = const GoogleSignInFailure(GoogleSignInFailureKind.unavailable);
      notifyListeners();
      return null;
    }

    final epoch = ++_epoch;
    _busy = true;
    notifyListeners();
    try {
      final outcome = await access.signInWithGoogle(emailHint: emailHint);
      if (_disposed || epoch != _epoch) return null;
      _lastOutcome = outcome;
      return outcome;
    } on GoogleSignInFailure catch (failure) {
      if (!_disposed && epoch == _epoch) _failure = failure;
      return null;
    } catch (_) {
      if (!_disposed && epoch == _epoch) {
        _failure = const GoogleSignInFailure(GoogleSignInFailureKind.unknown);
      }
      return null;
    } finally {
      if (!_disposed && epoch == _epoch) {
        _busy = false;
        notifyListeners();
      }
    }
  }

  /// Clears idle feedback; it cannot cancel a provider window.
  void reset() {
    if (_disposed || _busy) return;
    _epoch++;
    _failure = null;
    _lastOutcome = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _epoch++;
    super.dispose();
  }
}
