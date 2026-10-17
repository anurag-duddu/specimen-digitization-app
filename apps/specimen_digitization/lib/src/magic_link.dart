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
const emailLinkSentMessage =
    'Check your inbox and spam folder. Open the link to sign in.';
const _emailLinkWebHost = 'specimen-digitization.web.app';
const _emailLinkNativeHost = 'specimen-digitization.firebaseapp.com';
const _emailLinkNativePath = '/__/auth/links';
const _emailLinkNativeActionPath = '/__/auth/action';

bool _hasExactAuthority(Uri uri, String host) {
  final value = uri.toString();
  const prefix = 'https://';
  if (!value.startsWith(prefix)) return false;
  final separator = value.indexOf(RegExp(r'[/?#]'), prefix.length);
  final end = separator < 0 ? value.length : separator;
  return value.substring(prefix.length, end) == host;
}

String? _trustedEmailLink(Uri uri, Map<String, List<String>> parameters) {
  if (uri.scheme != 'https' ||
      uri.hasPort ||
      uri.userInfo.isNotEmpty ||
      uri.fragment.isNotEmpty ||
      uri.toString().length > 8192 ||
      parameters.values.any((values) => values.length != 1)) {
    return null;
  }

  if (uri.host == _emailLinkWebHost &&
      _hasExactAuthority(uri, _emailLinkWebHost) &&
      (uri.path == '/' || uri.path.isEmpty)) {
    return parameters['mode']?.singleOrNull == 'signIn' &&
            (parameters['oobCode']?.singleOrNull?.isNotEmpty ?? false)
        ? uri.toString()
        : null;
  }

  if (uri.host != _emailLinkNativeHost ||
      !_hasExactAuthority(uri, _emailLinkNativeHost) ||
      uri.path != _emailLinkNativePath ||
      parameters.length != 1) {
    return null;
  }

  // Firebase Hosting wraps the action URL in one `link` parameter for native
  // delivery. Constrain both URLs so the trusted Hosting origin cannot become
  // an open redirect, then give Firebase Auth only the validated action URL to
  // parse and verify.
  final String? actionValue = parameters['link']?.singleOrNull;
  if (actionValue == null || actionValue.isEmpty) return null;
  final Uri? action = Uri.tryParse(actionValue);
  if (action == null ||
      action.scheme != 'https' ||
      action.host != _emailLinkNativeHost ||
      action.hasPort ||
      action.userInfo.isNotEmpty ||
      !_hasExactAuthority(action, _emailLinkNativeHost) ||
      action.path != _emailLinkNativeActionPath ||
      action.fragment.isNotEmpty) {
    return null;
  }
  final actionParameters = action.queryParametersAll;
  if (actionParameters.values.any((values) => values.length != 1) ||
      actionParameters['mode']?.singleOrNull != 'signIn' ||
      !(actionParameters['oobCode']?.singleOrNull?.isNotEmpty ?? false) ||
      actionParameters['continueUrl']?.singleOrNull != emailLinkReturnUrl) {
    return null;
  }
  return action.toString();
}

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
  int _sendEpoch = 0;
  Future<void> _storageWrites = Future<void>.value();
  String email = '';
  String? _emailSentInThisPage;
  int _handoffGeneration = 0;

  /// Changes when a new request, local link or alternate sign-in supersedes
  /// the request that could have completed in another tab.
  int get handoffGeneration => _handoffGeneration;

  /// Called synchronously before dispatching another provider's sign-in.
  void beginAlternateSignIn() {
    _emailSentInThisPage = null;
    _handoffGeneration++;
    _changed();
  }

  /// A successful request made by this controller, never restored preferences.
  /// This is a recovery hint, not proof of authentication or collection access.
  String? get emailSentInThisPage => _emailSentInThisPage;
  String? message;

  /// A failed request can coexist with a previously sent link.
  bool get hasError => message != null && message != emailLinkSentMessage;
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

  /// Accepts a link the person explicitly pasted, through the same strict
  /// origin, shape and Firebase checks as a browser or native delivery.
  /// The action code remains in memory only and the clipboard is unchanged.
  bool acceptPastedLink(String rawLink) {
    if (_disposed || !initialized || busy) return false;
    final String value = rawLink.trim();
    final Uri? uri = value.isEmpty ? null : Uri.tryParse(value);
    if (uri == null) {
      message =
          'No usable sign-in link was found. Copy the full link from the email and try again.';
      _changed();
      return false;
    }
    final String? previousMessage = message;
    // A copied email button can contain the direct action URL rather than the
    // native Hosting envelope. Reuse the envelope validator for its exact
    // origin, path, unique parameters and continuation; Firebase still verifies
    // the action code. This normalization applies only to an explicit paste.
    final Uri candidate =
        uri.host == _emailLinkNativeHost &&
            uri.path == _emailLinkNativeActionPath &&
            value.startsWith(
              'https://$_emailLinkNativeHost$_emailLinkNativeActionPath?',
            )
        ? Uri.https(_emailLinkNativeHost, _emailLinkNativePath, {'link': value})
        : uri;
    final bool accepted = _ingestLink(candidate, () {});
    if (!accepted && _link == null && message == previousMessage) {
      message =
          'This sign-in link cannot be used. Copy the full link from the email or request a new one.';
    }
    _changed();
    if (accepted && email.isNotEmpty) unawaited(complete(email));
    return accepted;
  }

  Future<void> _remember({bool clearEmail = false}) {
    final value = RememberedEmailLink(
      email: clearEmail || email.isEmpty ? null : email,
      retryAt: _retryAt,
    );
    // A session can complete in another browser tab while a previous local
    // write is pending. Preserve write order so cleanup is the final value.
    _storageWrites = _storageWrites.then((_) async {
      try {
        await storage.write(value);
      } catch (_) {
        // Storage may be disabled in private browsing. Cross-browser
        // confirmation remains available; no account data is logged.
      }
    });
    return _storageWrites;
  }

  /// Clears a sent request completed by a matching, verified session event.
  ///
  /// The application must establish signed-in and verified state before
  /// calling this method. An incoming link still owns its explicit confirmation
  /// and cleanup, even if Firebase publishes a session before it completes.
  Future<void> reconcileVerifiedSession(String verifiedEmail) async {
    final normalized = normalizedStaffEmail(verifiedEmail);
    if (_disposed ||
        !initialized ||
        normalized == null ||
        normalized != email ||
        _link != null ||
        _inFlight != null) {
      return;
    }
    _sendEpoch++;
    _emailSentInThisPage = null;
    email = '';
    sent = false;
    busy = false;
    message = null;
    _changed();
    await _remember(clearEmail: true);
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
        final value = _trustedEmailLink(uri, parameters);
        if (value != null && access.isSignInWithEmailLink(value)) {
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
          _handoffGeneration++;
          _emailSentInThisPage = null;
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
    final int epoch = ++_sendEpoch;
    _handoffGeneration++;
    _emailSentInThisPage = null;
    final previousLink = _link;
    busy = true;
    message = null;
    _retryAt = now().add(emailLinkCooldown);
    _changed();
    // Persist before dispatch so a refresh or uncertain response retains the
    // same address/cooldown. No automatic SDK retry is scheduled by this UI.
    await _remember();
    if (_disposed || epoch != _sendEpoch) return;
    try {
      await access.sendSignInLink(email);
      if (_disposed || epoch != _sendEpoch) return;
      sent = true;
      _emailSentInThisPage = normalized;
      message = emailLinkSentMessage;
    } catch (error) {
      if (!_disposed && epoch == _sendEpoch) {
        message = emailLinkError(error);
      }
    } finally {
      if (epoch == _sendEpoch) {
        busy = false;
        _changed();
        if (!_disposed && _link != null && !identical(_link, previousLink)) {
          unawaited(complete(email));
        }
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
    _handoffGeneration++;
    _emailSentInThisPage = null;
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
    _handoffGeneration++;
    _emailSentInThisPage = null;
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
