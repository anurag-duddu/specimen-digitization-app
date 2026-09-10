import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

const staffEmailMessage = 'Use your fieldmuseum.org email address.';
const emailLinkReturnUrl = 'https://specimen-digitization.web.app/';
const emailLinkCooldown = Duration(seconds: 60);

/// ASCII mailbox syntax, an exact domain, and no whitespace/control characters.
/// We accept case differences, not Unicode/lookalike or subdomain addresses.
String? normalizedStaffEmail(String raw) {
  if (raw.length > 254 || raw.contains(RegExp(r'[^\x21-\x7e]'))) return null;
  final parts = raw.split('@');
  if (parts.length != 2 || parts[1].toLowerCase() != 'fieldmuseum.org') {
    return null;
  }
  final local = parts[0];
  if (local.isEmpty ||
      local.length > 64 ||
      local.startsWith('.') ||
      local.endsWith('.') ||
      local.contains('..') ||
      !RegExp(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$").hasMatch(local)) {
    return null;
  }
  return raw.toLowerCase();
}

abstract class EmailLinkAccess {
  bool isSignInWithEmailLink(String link);
  Future<void> sendSignInLink(String email);
  Future<void> completeEmailLink(String email, String link);
}

abstract class EmailLinkBrowser {
  Uri get initialUri;
  void clearLink();
}

class MemoryEmailLinkBrowser implements EmailLinkBrowser {
  MemoryEmailLinkBrowser({Uri? uri})
    : initialUri = uri ?? Uri.parse(emailLinkReturnUrl);
  @override
  final Uri initialUri;
  int clearCount = 0;
  @override
  void clearLink() {
    clearCount++;
  }
}

class RememberedEmailLink {
  const RememberedEmailLink({this.email, this.retryAt});
  final String? email;
  final DateTime? retryAt;
}

abstract class EmailLinkStorage {
  Future<RememberedEmailLink> read();
  Future<void> write(RememberedEmailLink value);
}

class PreferencesEmailLinkStorage implements EmailLinkStorage {
  static const emailKey = 'specimen.emailLink.email';
  static const retryKey = 'specimen.emailLink.retryAt';
  @override
  Future<RememberedEmailLink> read() async {
    final preferences = await SharedPreferences.getInstance();
    final at = preferences.getInt(retryKey);
    return RememberedEmailLink(
      email: preferences.getString(emailKey),
      retryAt: at == null
          ? null
          : DateTime.fromMillisecondsSinceEpoch(at, isUtc: true),
    );
  }

  @override
  Future<void> write(RememberedEmailLink value) async {
    final preferences = await SharedPreferences.getInstance();
    final ok = value.email == null
        ? await preferences.remove(emailKey)
        : await preferences.setString(emailKey, value.email!);
    if (!ok) throw StateError('Local sign-in storage unavailable');
    if (value.retryAt != null &&
        !await preferences.setInt(
          retryKey,
          value.retryAt!.millisecondsSinceEpoch,
        )) {
      throw StateError('Local sign-in storage unavailable');
    }
  }
}

/// Stores the requested address and cooldown only. Action codes stay in memory
/// and the active address bar until completion/cancel; never in preferences.
class MagicLinkController extends ChangeNotifier {
  MagicLinkController({
    required this.access,
    required this.browser,
    EmailLinkStorage? storage,
    DateTime Function()? now,
  }) : storage = storage ?? PreferencesEmailLinkStorage(),
       now = now ?? DateTime.now;
  final EmailLinkAccess access;
  final EmailLinkBrowser browser;
  final EmailLinkStorage storage;
  final DateTime Function() now;
  bool initialized = false, busy = false, sent = false;
  bool _disposed = false;
  bool _initializing = false;
  String email = '';
  String? message;
  String? _link;
  DateTime? _retryAt;
  bool get handlingLink => _link != null;
  int get cooldownSeconds {
    final milliseconds = (_retryAt?.difference(now()).inMilliseconds ?? 0);
    return milliseconds <= 0 ? 0 : (milliseconds / 1000).ceil();
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> _remember({bool clearEmail = false}) async {
    try {
      await storage.write(
        RememberedEmailLink(
          email: clearEmail || email.isEmpty ? null : email,
          retryAt: _retryAt,
        ),
      );
    } catch (_) {
      // Storage may be disabled in private browsing. Cross-browser confirmation
      // remains available; no raw exception or account data is logged.
    }
  }

  Future<void> initialize() async {
    if (initialized || _initializing || _disposed) return;
    _initializing = true;
    try {
      final saved = await storage.read();
      if (_disposed) return;
      email = normalizedStaffEmail(saved.email ?? '') ?? '';
      final retry = saved.retryAt;
      // Corrupt/future local timestamps cannot lock out sign-in indefinitely.
      if (retry != null &&
          retry.isAfter(now()) &&
          retry.difference(now()) <= emailLinkCooldown) {
        _retryAt = retry;
      }
      sent = email.isNotEmpty;
    } catch (_) {
      /* Local storage is optional. */
    }
    if (_disposed) return;
    final uri = browser.initialUri;
    // Percent escapes can parse as a Uri yet fail UTF-8 query decoding.
    // Keep shape parsing inside the same recoverable invalid-link boundary.
    try {
      final parameters = uri.queryParametersAll;
      final candidate =
          parameters.containsKey('oobCode') ||
          parameters.containsKey('mode') ||
          uri.fragment.contains('oobCode') ||
          parameters.containsKey('link');
      if (candidate) {
        final validShape =
            uri.scheme == 'https' &&
            uri.host == 'specimen-digitization.web.app' &&
            !uri.hasPort &&
            uri.userInfo.isEmpty &&
            (uri.path == '/' || uri.path.isEmpty) &&
            uri.fragment.isEmpty &&
            parameters['mode']?.singleOrNull == 'signIn' &&
            (parameters['oobCode']?.singleOrNull?.isNotEmpty ?? false) &&
            uri.toString().length <= 8192 &&
            parameters.values.every((values) => values.length == 1);
        if (validShape && access.isSignInWithEmailLink(uri.toString())) {
          _link = uri.toString();
        } else {
          _clearLink();
          message = 'This sign-in link is invalid. Request a new link.';
        }
      }
    } catch (_) {
      _clearLink();
      message = 'This sign-in link is invalid. Request a new link.';
    }
    initialized = true;
    _changed();
    if (_link != null && email.isNotEmpty) await complete(email);
  }

  void _clearLink() {
    _link = null;
    try {
      browser.clearLink();
    } catch (_) {
      /* Never log a URL-bearing error. */
    }
  }

  Future<void> send(String rawEmail) async {
    if (busy || !initialized || cooldownSeconds > 0 || _disposed) return;
    final normalized = normalizedStaffEmail(rawEmail);
    if (normalized == null) {
      message = staffEmailMessage;
      _changed();
      return;
    }
    email = normalized;
    busy = true;
    message = null;
    _retryAt = now().add(emailLinkCooldown);
    _changed();
    // Persist before dispatch so a refresh or uncertain response retains the
    // same address/cooldown. No automatic SDK retry is scheduled by this UI.
    await _remember();
    if (_disposed) return;
    try {
      await access.sendSignInLink(email);
      if (_disposed) return;
      sent = true;
      message = 'Check your inbox and spam folder. Open the link to sign in.';
    } catch (error) {
      if (!_disposed) message = emailLinkError(error);
    } finally {
      busy = false;
      _changed();
    }
  }

  Future<void> complete(String rawEmail) async {
    if (busy || _link == null || _disposed) return;
    final normalized = normalizedStaffEmail(rawEmail);
    if (normalized == null) {
      message = staffEmailMessage;
      _changed();
      return;
    }
    email = normalized;
    busy = true;
    message = null;
    _changed();
    try {
      await access.completeEmailLink(email, _link!);
      // Firebase can emit userChanges before this Future resolves. Terminal
      // cleanup must survive disposal; only UI notifications depend on life.
      _clearLink();
      sent = false;
      await _remember(clearEmail: true);
      email = '';
    } catch (error) {
      if (!_disposed) message = emailLinkError(error);
      if (error is FirebaseAuthException &&
          [
            'expired-action-code',
            'invalid-action-code',
            'invalid-credential',
            'user-disabled',
          ].contains(error.code)) {
        _clearLink();
        sent = false;
      }
    } finally {
      busy = false;
      _changed();
    }
  }

  Future<void> changeEmail() async {
    if (busy || _disposed) return;
    if (_link != null) _clearLink();
    email = '';
    sent = false;
    message = null;
    await _remember(clearEmail: true);
    _changed();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

String emailLinkError(Object error) {
  if (error is FirebaseAuthException) {
    return switch (error.code) {
      'expired-action-code' || 'invalid-action-code' || 'invalid-credential' =>
        'This sign-in link has expired or was already used. Request a new link.',
      'network-request-failed' =>
        'Could not reach the sign-in service. Check your connection and try again.',
      'too-many-requests' =>
        'Too many attempts. Wait a few minutes before trying again.',
      'operation-not-allowed' ||
      'unauthorized-continue-uri' ||
      'invalid-continue-uri' =>
        'Email-link sign-in is not available yet. Contact your administrator.',
      'user-disabled' =>
        'This account cannot sign in. Contact your administrator.',
      'invalid-email' => staffEmailMessage,
      _ => 'Sign-in could not be completed. Request a new link or try again.',
    };
  }
  return 'Sign-in could not be completed. Check your connection and try again.';
}
