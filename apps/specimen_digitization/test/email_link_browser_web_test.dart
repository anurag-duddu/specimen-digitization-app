@TestOn('browser')
library;

import 'dart:js_interop';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/email_link_browser_web.dart';

@JS('window.history.replaceState')
external void _replaceState(JSAny? state, String title, String url);

@JS('window.history.state')
external JSAny? get _historyState;

Uri installCallback() {
  final original = Uri.base;
  final originalState = _historyState;
  addTearDown(() => _replaceState(originalState, '', original.toString()));
  final callback = original.replace(
    // Invented values only. No Firebase request is made by these tests.
    query: 'mode=signIn&oobCode=fixture-old&apiKey=fixture-key',
    fragment: '',
  );
  _replaceState(null, '', callback.toString());
  return Uri.base;
}

void main() {
  test('web adapter clears callback after a real history hash change', () {
    final callback = installCallback();
    final browser = createEmailLinkBrowser();
    final routeState = {'fixtureRoute': 'setup', 'fixtureDepth': 2};
    _replaceState(
      routeState.jsify(),
      '',
      callback.replace(fragment: '/setup').toString(),
    );

    browser.clearLink();

    expect(Uri.base.hasQuery, isFalse);
    expect(Uri.base.fragment, '/setup');
    expect(Uri.base.origin, callback.origin);
    expect(Uri.base.path, callback.path);
    expect(_historyState?.dartify(), routeState);
  });

  test('web adapter leaves a newer callback and route untouched', () {
    final callback = installCallback();
    final browser = createEmailLinkBrowser();
    final newer = callback.replace(
      query: 'mode=signIn&oobCode=fixture-new&apiKey=fixture-key',
      fragment: '/sign-in',
    );
    _replaceState(null, '', newer.toString());

    browser.clearLink();

    expect(Uri.base, newer);
  });

  test('web adapter clears an unchanged malformed callback fragment', () {
    final callback = installCallback();
    _replaceState(
      null,
      '',
      callback.replace(fragment: 'oobCode=fixture-malformed').toString(),
    );
    final browser = createEmailLinkBrowser();

    browser.clearLink();

    expect(Uri.base.hasQuery, isFalse);
    expect(Uri.base.hasFragment, isFalse);
    expect(Uri.base.path, callback.path);
  });
}
