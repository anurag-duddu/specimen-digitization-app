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
    if (access != null) {
      _changes = access.changes.listen((bool signedIn) {
        if (_signedIn == signedIn) return;
        _signedIn = signedIn;
        if (!signedIn) pendingLocation = null;
        notifyListeners();
      });
    }
  }

  /// The session, or null in a build with no sign-in configured.
  final SessionAccess? session;

  StreamSubscription<bool>? _changes;
  bool _signedIn = false;

  /// The location the window asked for before it was sent to an entry screen.
  String? pendingLocation;

  /// True when this build has a session at all.
  bool get configured => session != null;

  /// True when someone is signed in.
  bool get signedIn => _signedIn;

  /// True when the address behind the session is verified, and when the
  /// session does not carry verification at all.
  bool get verified {
    final SessionAccess? access = session;
    if (access is FirebaseSession && !access.staffEmailAllowed) return false;
    if (access is! VerifiedEmailAccess) return true;
    // `VerifiedEmailAccess` is not a subtype of `SessionAccess`, so the type
    // test above narrows nothing and the cast is the only way through.
    return (access as VerifiedEmailAccess).emailVerified;
  }

  /// Re-runs every redirect, after something the router cannot observe.
  void refresh() => notifyListeners();

  @override
  void dispose() {
    unawaited(_changes?.cancel());
    super.dispose();
  }
}
