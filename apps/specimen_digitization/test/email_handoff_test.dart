import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/email_handoff.dart';
import 'package:url_launcher/url_launcher.dart';

void main() {
  test(
    'opens the fixed inbox externally in the original user gesture',
    () async {
      final result = Completer<bool>();
      var calls = 0;
      Uri? launchedUrl;
      LaunchMode? launchedMode;
      String? launchedWindow;
      final launcher = UrlEmailInboxLauncher(
        launch: (url, {required mode, required webOnlyWindowName}) {
          calls++;
          launchedUrl = url;
          launchedMode = mode;
          launchedWindow = webOnlyWindowName;
          return result.future;
        },
      );

      final opening = launcher.openInbox();

      // These assertions run before any await: browser launch has already begun.
      expect(calls, 1);
      expect(launchedUrl.toString(), 'https://mail.google.com/mail/');
      expect(launchedUrl?.scheme, 'https');
      expect(launchedUrl?.userInfo, isEmpty);
      expect(launchedUrl?.query, isEmpty);
      expect(launchedUrl?.fragment, isEmpty);
      expect(launchedMode, LaunchMode.externalApplication);
      expect(launchedWindow, '_blank');
      result.complete(true);
      expect(await opening, isTrue);
    },
  );

  test('reports a declined launch without retrying it', () async {
    var calls = 0;
    final launcher = UrlEmailInboxLauncher(
      launch: (url, {required mode, required webOnlyWindowName}) async {
        calls++;
        return false;
      },
    );

    expect(await launcher.openInbox(), isFalse);
    expect(calls, 1);
  });

  test('contains a synchronous platform exception', () async {
    final launcher = UrlEmailInboxLauncher(
      launch: (url, {required mode, required webOnlyWindowName}) {
        throw StateError('private-platform-detail');
      },
    );

    expect(await launcher.openInbox(), isFalse);
  });

  test('contains an asynchronous platform exception', () async {
    final launcher = UrlEmailInboxLauncher(
      launch: (url, {required mode, required webOnlyWindowName}) async {
        throw StateError('private-platform-detail');
      },
    );

    expect(await launcher.openInbox(), isFalse);
  });
}
