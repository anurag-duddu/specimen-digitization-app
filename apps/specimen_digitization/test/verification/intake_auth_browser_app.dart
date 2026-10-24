// Compiled browser fixture for production OAuth and inline Picker adapters. Synthetic
// messages only: no Firebase, provider, API, or credential is used here.
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_auth_session_web.dart';
import 'package:specimen_digitization/src/screens/intake/intake_picker_bridge_web.dart';
import 'package:web/web.dart' as web;

void main() {
  if (Uri.base.scheme != 'http' || Uri.base.host != '127.0.0.1') {
    throw StateError('The browser fixture is restricted to loopback.');
  }
  IntakeAuthSession? session;
  IntakePickerBridge? picker;
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
              if (error is ApiFailure) {
                state['errorCode'] = error.code;
                state['errorMessage'] = error.message;
                state['recoveryAction'] = error.details['action'];
              }
            },
          );
    }).toJS,
  );
  globalContext.setProperty(
    'intakeAuthBrowserClose'.toJS,
    (() => session?.close()).toJS,
  );
  globalContext.setProperty(
    'intakePickerBrowserStart'.toJS,
    ((String url, String pickerId) {
      final uri = Uri.parse(url);
      if (uri.scheme != 'http' || uri.host != '127.0.0.1') {
        throw StateError('The Picker fixture is restricted to loopback.');
      }
      picker?.dispose();
      state['pickerActions'] = <String>[];
      picker = IntakePickerBridge(
        url: url,
        pickerId: pickerId,
        onEvent: (action) {
          (state['pickerActions'] as List<String>).add(action);
        },
      );
      picker!.frame.id = 'intake-picker-fixture';
      web.document.body!.append(picker!.frame);
    }).toJS,
  );
  globalContext.setProperty(
    'intakePickerBrowserClose'.toJS,
    (() => picker?.dispose()).toJS,
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
