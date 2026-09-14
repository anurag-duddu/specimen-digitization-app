/// The session facts the router redirects on (screen blueprints, 1.1).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../auth.dart';

/// Tracks whether there is a session, whether it is signed in, and whether its
/// address is verified, and remembers where the window was trying to go.
class AppSessionNotifier extends ChangeNotifier {
  AppSessionNotifier({this.session}) {
    final SessionAccess? access = session;
    _signedIn = access?.signedIn ?? false;
    _userId = access?.userId;
    if (access != null) {
      _changes = access.changes.listen((bool signedIn) {
        if (_disposed) return;
        final String identity = access.userId;
        if (!signedIn || identity != _userId) {
          pendingLocation = null;
          _verificationBlocked = false;
          _verificationEpoch++;
        }
        _userId = identity;
        _signedIn = signedIn;
        notifyListeners();
      });
    }
  }

  /// The session, or null in a build with no sign-in configured.
  final SessionAccess? session;

  StreamSubscription<bool>? _changes;
  bool _signedIn = false;
  String? _userId;
  bool _verificationBlocked = false;
  int _verificationEpoch = 0;
  bool _disposed = false;

  /// The location the window asked for before it was sent to an entry screen.
  String? pendingLocation;

  /// True when this build has a session at all.
  bool get configured => session != null;

  /// True when someone is signed in.
  bool get signedIn => _signedIn;

  /// True when the address behind the session is verified, and when the
  /// session does not carry verification at all.
  bool get verified {
    if (_verificationBlocked) return false;
    final SessionAccess? access = session;
    if (access is FirebaseSession && !access.staffEmailAllowed) return false;
    if (access is! VerifiedEmailAccess) return true;
    // `VerifiedEmailAccess` is not a subtype of `SessionAccess`, so the type
    // test above narrows nothing and the cast is the only way through.
    return (access as VerifiedEmailAccess).emailVerified;
  }

  /// A reload can emit a verified user before the forced token refresh
  /// finishes. Keep routing and collection loading gated until both succeed.
  Future<void> refreshVerification() async {
    final SessionAccess? access = session;
    if (access is! VerifiedEmailAccess) return;
    final int epoch = ++_verificationEpoch;
    _verificationBlocked = true;
    notifyListeners();
    try {
      await (access as VerifiedEmailAccess).refreshVerification();
      if (!_disposed && epoch == _verificationEpoch) {
        _verificationBlocked = false;
      }
    } finally {
      if (!_disposed && epoch == _verificationEpoch) notifyListeners();
    }
  }

  /// Re-runs every redirect, after something the router cannot observe.
  void refresh() => notifyListeners();

  @override
  void dispose() {
    _disposed = true;
    _verificationEpoch++;
    unawaited(_changes?.cancel());
    super.dispose();
  }
}
