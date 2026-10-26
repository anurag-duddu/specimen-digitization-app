import 'dart:async';
import 'dart:math';

import 'package:flutter/services.dart';

import '../../models.dart';
import 'intake_timing.dart';

/// A system authentication sheet/tab; provider credentials stay on the server.
class IntakeAuthSession {
  IntakeAuthSession({
    MethodChannel channel = const MethodChannel('specimen/intake_auth'),
    Duration timeout = intakeAuthorizationTimeout,
  }) : _channel = channel,
       _timeout = timeout;

  final MethodChannel _channel;
  final Duration _timeout;
  final String _id = List.generate(
    16,
    (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
  Completer<Json>? _result;
  Timer? _timer;
  bool _closed = false;

  String? get returnOrigin => null;

  // Native Google selection uses trigger_onepick in the authenticated flow.
  // Loading the web JavaScript Picker in a native WebView is unsupported.
  Future<void> openPicker(String url) async => throw const ApiFailure(
    'Choose Google Drive photos through the account connection.',
    code: 'picker_unsupported',
  );

  Future<Json> authenticate(String authorizationUrl, {bool keepOpen = false}) {
    if (_closed) return Future.error(_cancelled);
    if (_result != null) {
      return Future.error(
        const ApiFailure(
          'This connection is already open.',
          code: 'connection_busy',
        ),
      );
    }
    final uri = Uri.tryParse(authorizationUrl);
    final states = uri?.queryParametersAll['state'];
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        states == null ||
        states.length != 1 ||
        states.single.isEmpty) {
      return Future.error(_invalidCallback);
    }
    final expected = states.single;
    final result = _result = Completer<Json>();
    _timer = Timer(_timeout, () {
      _fail(
        const ApiFailure(
          'Connection expired. Connect again to finish authorizing this account.',
          code: 'connection_expired',
          details: {'action': 'connect'},
        ),
      );
      _cancelNative();
    });
    unawaited(
      _channel
          .invokeMethod<String>('authenticate', {
            'id': _id,
            'url': authorizationUrl,
            'state': expected,
          })
          .then<void>(
            (value) {
              if (result.isCompleted) return;
              try {
                final callback = value == null ? null : Uri.tryParse(value);
                if (callback == null ||
                    callback.scheme != 'specimenintake' ||
                    callback.host != 'oauth' ||
                    callback.path != '/callback' ||
                    callback.userInfo.isNotEmpty ||
                    callback.hasPort ||
                    callback.hasQuery) {
                  throw _invalidCallback;
                }
                final fields = Uri(query: callback.fragment).queryParametersAll;
                if (fields.values.any((values) => values.length != 1) ||
                    fields['state']?.single != expected ||
                    fields.keys.any(
                      (key) => !const {
                        'state',
                        'code',
                        'error',
                        'picked_file_ids',
                      }.contains(key),
                    ) ||
                    ((fields['code']?.single.isNotEmpty ?? false) ==
                        (fields['error']?.single.isNotEmpty ?? false))) {
                  throw _invalidCallback;
                }
                _timer?.cancel();
                result.complete({
                  for (final field in fields.entries)
                    field.key: field.value.single,
                });
              } catch (_) {
                _fail(_invalidCallback);
              }
            },
            onError: (Object error) {
              if (result.isCompleted) return;
              _fail(switch (error) {
                PlatformException(code: 'cancelled') => _cancelled,
                PlatformException(code: 'invalid_callback') => _invalidCallback,
                PlatformException(code: 'busy') => const ApiFailure(
                  'Another account connection is open. Finish it before trying again.',
                  code: 'connection_busy',
                  details: {'action': 'connect'},
                ),
                _ => const ApiFailure(
                  'The account connection could not open. Try again.',
                  code: 'browser_unavailable',
                  details: {'action': 'connect'},
                ),
              });
            },
          ),
    );
    return result.future;
  }

  static const _cancelled = ApiFailure(
    'Connection cancelled.',
    code: 'authorization_cancelled',
  );
  static const _invalidCallback = ApiFailure(
    'Could not verify this connection. Connect again.',
    code: 'invalid_callback',
    details: {'action': 'connect'},
  );

  void _fail(ApiFailure error) {
    _timer?.cancel();
    final result = _result;
    if (result != null && !result.isCompleted) result.completeError(error);
  }

  void _cancelNative() {
    unawaited(
      _channel
          .invokeMethod<void>('cancel', {'id': _id})
          .catchError((Object _) {}),
    );
  }

  void close() {
    if (_closed) return;
    _closed = true;
    final pending = _result != null && !_result!.isCompleted;
    _fail(_cancelled);
    if (pending) _cancelNative();
  }
}
