// Compiled browser fixture for the real production popup adapter. Synthetic
// messages only: no Firebase, provider, API, or credential is used here.
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:specimen_digitization/src/screens/intake/intake_auth_session_web.dart';
import 'package:web/web.dart' as web;

void main() {
  if (Uri.base.scheme != 'http' || Uri.base.host != '127.0.0.1') {
    throw StateError('The browser fixture is restricted to loopback.');
  }
  IntakeAuthSession? session;
  var state = <String, dynamic>{'status': 'idle', 'barrier': 0};
  globalContext.setProperty(
    'intakeAuthBrowserState'.toJS,
    (() => jsonEncode(state)).toJS,
  );
  globalContext.setProperty(
    'intakeAuthBrowserStart'.toJS,
    ((String authorizationUrl, bool keepOpen) {
      final url = Uri.parse(authorizationUrl);
      if (url.scheme != 'http' || url.host != '127.0.0.1') {
        throw StateError('The callback fixture is restricted to loopback.');
      }
      session?.close();
      state = {'status': 'pending', 'barrier': 0};
      final current = session = IntakeAuthSession();
      current
          .authenticate(authorizationUrl, keepOpen: keepOpen)
          .then(
            (response) {
              state['status'] = 'completed';
              state['response'] = response;
            },
            onError: (Object error) {
              state['status'] = 'failed';
              state['errorType'] = error.runtimeType.toString();
            },
          );
    }).toJS,
  );
  globalContext.setProperty(
    'intakeAuthBrowserClose'.toJS,
    (() => session?.close()).toJS,
  );
  // A barrier is posted immediately after each invalid message. Browser task
  // ordering lets the driver assert rejection without sleeping for a timeout.
  web.window.addEventListener(
    'message',
    ((web.MessageEvent event) {
      final data = event.data.dartify();
      if (data is Map && data['fixtureBarrier'] is int) {
        state['barrier'] = data['fixtureBarrier'];
      }
    }).toJS,
  );
}
