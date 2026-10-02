import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'email_link_source.dart';

const staffEmailMessage = 'Use your fieldmuseum.org email address.';
const emailLinkReturnUrl = 'https://specimen-digitization.web.app/';
const emailLinkCooldown = Duration(seconds: 60);

/// ASCII mailbox syntax, the museum domain or exact authorized owner mailbox,
/// and no whitespace/control characters.
/// We accept case differences, not Unicode/lookalike or subdomain addresses.
String? normalizedStaffEmail(String raw) {
  if (raw.length > 254 || raw.contains(RegExp(r'[^\x21-\x7e]'))) return null;
  final parts = raw.split('@');
  if (parts.length != 2 ||
      (parts[1].toLowerCase() != 'fieldmuseum.org' &&
          raw.toLowerCase() != 'anurag@infinative.com')) {
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

class _IncomingEmailLink {
  _IncomingEmailLink(
    this.value,
    this.digest,
    VoidCallback acknowledge,
    Object deliveryIdentity,
  ) {
    acknowledgements[deliveryIdentity] = acknowledge;
  }
  final String value;
  final String digest;
  final Map<Object, VoidCallback> acknowledgements =
      Map<Object, VoidCallback>.identity();
  bool retryable = false;
}

/// Stores the requested address and cooldown only. Action codes stay in memory
/// and the active address bar until completion/cancel; never in preferences.
class MagicLinkController extends ChangeNotifier {
  MagicLinkController({
    required this.access,
    required this.browser,
    this.linkSource,
    EmailLinkStorage? storage,
    DateTime Function()? now,
  }) : storage = storage ?? PreferencesEmailLinkStorage(),
       now = now ?? DateTime.now;
  final EmailLinkAccess access;
  final EmailLinkBrowser browser;

  /// Optional cold/warm delivery source, owned by the application. The
  /// controller owns only its subscription. Without it, the existing browser
  /// snapshot remains the input.
  final EmailLinkSource? linkSource;
  final EmailLinkStorage storage;
  final DateTime Function() now;
  bool initialized = false, busy = false, sent = false;
  bool _disposed = false;
  bool _initializing = false;
  String email = '';
  String? message;
  _IncomingEmailLink? _link;
  _IncomingEmailLink? _inFlight;
  StreamSubscription<EmailLinkDelivery>? _linkSubscription;
  // A canceled or transiently failed link can be explicitly delivered again.
  // Retain only hashes of links confirmed consumed or terminally rejected.
  final Set<String> _consumedLinks = <String>{};
  // Snapshot/stream notification copies are the same delivery, even after
  // cancellation. Expando does not keep old delivery objects or URIs alive.
  final Expando<bool> _receivedDeliveries = Expando<bool>();
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
    final source = linkSource;
    if (source != null) {
      _linkSubscription = source.links.listen(
        _receiveDelivery,
        onError: (Object _) {
          // Platform errors can contain the action URL. Never expose them.
          if (!_disposed && _link == null) {
            message = 'The sign-in link could not be opened. Try again.';
            _changed();
          }
        },
      );
      final pending = source.pending;
      if (pending != null) _receiveDelivery(pending);
    }
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
    if (source == null) _ingestLink(browser.initialUri, browser.clearLink);
    initialized = true;
    _changed();
    if (_link != null && email.isNotEmpty) await complete(email);
  }

  void _receiveDelivery(EmailLinkDelivery delivery) {
    if (_disposed) return;
    final source = linkSource;
    if (source == null) return;
    if (_receivedDeliveries[delivery] == true) return;
    _receivedDeliveries[delivery] = true;
    final accepted = _ingestLink(
      delivery.uri,
      () => source.acknowledge(delivery),
      deliveryIdentity: delivery,
    );
    _changed();
    if (accepted && initialized && !busy && email.isNotEmpty) {
      unawaited(complete(email));
    }
  }

  bool _ingestLink(
    Uri uri,
    VoidCallback acknowledge, {
    Object? deliveryIdentity,
  }) {
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
          final value = uri.toString();
          final digest = crypto.sha256.convert(utf8.encode(value)).toString();
          if (_consumedLinks.contains(digest)) {
            _acknowledge(acknowledge);
            return false;
          }
          final active = _inFlight?.digest == digest
              ? _inFlight
              : _link?.digest == digest
              ? _link
              : null;
          if (active != null && !active.retryable) {
            active.acknowledgements[deliveryIdentity ?? Object()] = acknowledge;
            return false;
          }
          final superseded = _link;
          if (superseded != null && !identical(superseded, _inFlight)) {
            _acknowledgeLink(superseded);
          }
          _link = _IncomingEmailLink(
            value,
            digest,
            acknowledge,
            deliveryIdentity ?? Object(),
          );
          message = null;
          return true;
        } else {
          _rejectLink(acknowledge);
        }
      } else if (linkSource != null) {
        // Unrelated native events are not retained and do not cancel a
        // previously accepted sign-in link.
        _acknowledge(acknowledge);
      }
    } catch (_) {
      _rejectLink(acknowledge);
    }
    return false;
  }

  void _acknowledge(VoidCallback acknowledge) {
    try {
      acknowledge();
    } catch (_) {
      /* Never log a URL-bearing error. */
    }
  }

  void _rejectLink(VoidCallback acknowledge) {
    _acknowledge(acknowledge);
    if (_link == null) {
      message = 'This sign-in link cannot be used. Request a new link.';
    }
  }

  void _clearLink([_IncomingEmailLink? expected]) {
    final target = expected ?? _link;
    if (target == null) return;
    _acknowledgeLink(target);
    if (identical(_link, target)) _link = null;
  }

  void _acknowledgeLink(_IncomingEmailLink target) {
    final acknowledgements = target.acknowledgements.values.toList();
    target.acknowledgements.clear();
    for (final acknowledge in acknowledgements) {
      _acknowledge(acknowledge);
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
    final previousLink = _link;
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
      if (!_disposed && _link != null && !identical(_link, previousLink)) {
        unawaited(complete(email));
      }
    }
  }

  Future<void> complete(String rawEmail) async {
    if (busy || !initialized || _link == null || _disposed) return;
    final normalized = normalizedStaffEmail(rawEmail);
    if (normalized == null) {
      message = staffEmailMessage;
      _changed();
      return;
    }
    email = normalized;
    final target = _link!;
    target.retryable = false;
    _inFlight = target;
    busy = true;
    message = null;
    _changed();
    try {
      await access.completeEmailLink(normalized, target.value);
      // Firebase can emit userChanges before this Future resolves. Terminal
      // cleanup must survive disposal; only UI notifications depend on life.
      _consumedLinks.add(target.digest);
      _clearLink(target);
      if (_link == null) {
        sent = false;
        await _remember(clearEmail: true);
        if (_link == null) {
          email = '';
        } else {
          // A newer delivery arrived while the old storage clear was pending.
          // Keep its confirmation address and restore that remembered state.
          await _remember();
        }
      }
    } catch (error) {
      if (!_disposed && identical(_link, target)) {
        message = emailLinkError(error);
      }
      if (error is FirebaseAuthException &&
          [
            'expired-action-code',
            'invalid-action-code',
            'invalid-credential',
            'user-disabled',
          ].contains(error.code)) {
        _consumedLinks.add(target.digest);
        _clearLink(target);
        if (_link == null) sent = false;
      } else {
        // Keep the current link for the explicit retry button. Release injected
        // deliveries so a new user-initiated delivery can also retry; preserve
        // a browser URL so refreshing still permits retry after network errors.
        // No retry is scheduled merely because this request failed.
        target.retryable = true;
        if (linkSource != null) _acknowledgeLink(target);
      }
    } finally {
      if (identical(_inFlight, target)) _inFlight = null;
      busy = false;
      _changed();
      if (!_disposed && _link != null && !identical(_link, target)) {
        unawaited(complete(email));
      }
    }
  }

  Future<void> changeEmail() async {
    if (busy || !initialized || _disposed) return;
    busy = true;
    if (_link != null) _clearLink();
    email = '';
    sent = false;
    message = null;
    _changed();
    try {
      await _remember(clearEmail: true);
    } finally {
      busy = false;
      _changed();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(_linkSubscription?.cancel());
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
        'Email-link sign-in is not available yet. Ask your administrator.',
      'user-disabled' => 'This account cannot sign in. Ask your administrator.',
      'invalid-email' => staffEmailMessage,
      _ => 'Sign-in could not be completed. Request a new link or try again.',
    };
  }
  return 'Sign-in could not be completed. Check your connection and try again.';
}
