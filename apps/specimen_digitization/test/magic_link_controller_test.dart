import 'dart:async';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/email_link_source.dart';
import 'package:specimen_digitization/src/magic_link.dart';

const testLink =
    'https://specimen-digitization.web.app/?mode=signIn&oobCode=fixture-action-code&apiKey=fixture-key';
const nativeActionLink =
    'https://specimen-digitization.firebaseapp.com/__/auth/action?apiKey=fixture-key&mode=signIn&oobCode=fixture-action-code&continueUrl=https%3A%2F%2Fspecimen-digitization.web.app%2F&lang=en';
final nativeTestLink = Uri.https(
  'specimen-digitization.firebaseapp.com',
  '/__/auth/links',
  {'link': nativeActionLink},
).toString();

class MemoryLinkStorage implements EmailLinkStorage {
  RememberedEmailLink value = const RememberedEmailLink();
  bool fail = false;
  int writes = 0;
  @override
  Future<RememberedEmailLink> read() async {
    if (fail) throw StateError('synthetic storage failure');
    return value;
  }

  @override
  Future<void> write(RememberedEmailLink input) async {
    if (fail) throw StateError('synthetic storage failure');
    value = input;
    writes++;
  }
}

class FakeLinkAccess implements EmailLinkAccess {
  final sent = <String>[];
  final checked = <String>[];
  final completed = <(String, String)>[];
  bool linkValid = true;
  Object? sendError, completeError;
  Completer<void>? sendWait, completeWait;
  @override
  bool isSignInWithEmailLink(String link) {
    checked.add(link);
    return linkValid;
  }

  @override
  Future<void> sendSignInLink(String email) async {
    sent.add(email);
    if (sendWait != null) await sendWait!.future;
    if (sendError != null) throw sendError!;
  }

  @override
  Future<void> completeEmailLink(String email, String link) async {
    completed.add((email, link));
    if (completeWait != null) await completeWait!.future;
    if (completeError != null) throw completeError!;
  }
}

class FakeEmailLinkSource implements EmailLinkSource {
  FakeEmailLinkSource({Uri? pending})
    : _pending = pending == null ? null : EmailLinkDelivery(pending);

  final StreamController<EmailLinkDelivery> _events =
      StreamController<EmailLinkDelivery>.broadcast();
  EmailLinkDelivery? _pending;
  final acknowledged = <EmailLinkDelivery>[];

  @override
  EmailLinkDelivery? get pending => _pending;

  @override
  Stream<EmailLinkDelivery> get links => _events.stream;

  void deliver(Uri uri) {
    final delivery = EmailLinkDelivery(uri);
    _pending = delivery;
    _events.add(delivery);
  }

  @override
  void acknowledge(EmailLinkDelivery delivery) {
    acknowledged.add(delivery);
    if (identical(_pending, delivery)) _pending = null;
  }

  @override
  Future<void> close() => _events.close();
}

class RecordingFirebaseAuth implements FirebaseAuth {
  String? email, link;
  ActionCodeSettings? settings;
  int sendCalls = 0, completeCalls = 0;
  @override
  bool isSignInWithEmailLink(String link) => link == testLink;
  @override
  Future<void> sendSignInLinkToEmail({
    required String email,
    required ActionCodeSettings actionCodeSettings,
  }) async {
    sendCalls++;
    this.email = email;
    settings = actionCodeSettings;
  }

  @override
  Future<UserCredential> signInWithEmailLink({
    required String email,
    required String emailLink,
  }) async {
    completeCalls++;
    this.email = email;
    link = emailLink;
    return EmptyCredential();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected Firebase invocation');
}

class EmptyCredential implements UserCredential {
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unused credential fixture');
}

void main() {
  for (final address in [
    'a@fieldmuseum.org',
    'FIRST.LAST@FIELDMUSEUM.ORG',
    'a+labels@fieldmuseum.org',
    "o'brien@fieldmuseum.org",
  ]) {
    test(
      'accept exact staff mailbox $address',
      () => expect(normalizedStaffEmail(address), address.toLowerCase()),
    );
  }
  for (final address in [
    '',
    'staff@sub.fieldmuseum.org',
    'staff@fieldmuseum.org.evil.test',
    'staff@fieldmuseum.org@evil.test',
    'staff@@fieldmuseum.org',
    '@fieldmuseum.org',
    'staff@fieldmuseum.org.',
    ' staff@fieldmuseum.org',
    'staff@fieldmuseum.org ',
    'staff\n@fieldmuseum.org',
    'staff@fieldmuseum.org\r\n',
    'sta ff@fieldmuseum.org',
    'staff\u200b@fieldmuseum.org',
    'staff@fieldmuseuｍ.org',
    'staff@fieldmuseum。org',
    'staff@fieldmuseum.org\u0000',
    'a..b@fieldmuseum.org',
    '.a@fieldmuseum.org',
    'a.@fieldmuseum.org',
    '"staff"@fieldmuseum.org',
  ]) {
    test(
      'reject malformed or foreign staff mailbox ${address.codeUnits}',
      () => expect(normalizedStaffEmail(address), isNull),
    );
  }

  late FakeLinkAccess access;
  late MemoryLinkStorage storage;
  late MemoryEmailLinkBrowser browser;
  late DateTime clock;
  MagicLinkController controller({String? link}) {
    browser = MemoryEmailLinkBrowser(
      uri: link == null ? null : Uri.parse(link),
    );
    final c = MagicLinkController(
      access: access,
      storage: storage,
      browser: browser,
      now: () => clock,
    );
    addTearDown(c.dispose);
    return c;
  }

  setUp(() {
    access = FakeLinkAccess();
    storage = MemoryLinkStorage();
    clock = DateTime.utc(2026, 9, 10);
  });

  test('email-link settings select only the registered native app', () {
    final android = emailLinkActionCodeSettings(
      web: false,
      platform: TargetPlatform.android,
    );
    expect(android.url, emailLinkReturnUrl);
    expect(android.handleCodeInApp, true);
    expect(android.androidPackageName, emailLinkAndroidPackageName);
    expect(android.androidInstallApp, false);
    expect(android.androidMinimumVersion, isNull);
    expect(android.iOSBundleId, isNull);
    expect(android.linkDomain, isNull);

    final ios = emailLinkActionCodeSettings(
      web: false,
      platform: TargetPlatform.iOS,
    );
    expect(ios.url, emailLinkReturnUrl);
    expect(ios.handleCodeInApp, true);
    expect(ios.androidPackageName, isNull);
    expect(ios.iOSBundleId, emailLinkIosBundleId);
    expect(ios.linkDomain, isNull);
  });

  test('web email-link settings retain the hosted-only flow', () {
    for (final platform in TargetPlatform.values) {
      final settings = emailLinkActionCodeSettings(
        web: true,
        platform: platform,
      );
      expect(settings.url, emailLinkReturnUrl);
      expect(settings.handleCodeInApp, true);
      expect(settings.androidPackageName, isNull);
      expect(settings.iOSBundleId, isNull);
      expect(settings.linkDomain, isNull);
    }
  });

  test(
    'adapter sends the Android app settings with the fixed HTTPS return URL',
    () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      final auth = RecordingFirebaseAuth();
      final session = FirebaseSession(auth);
      await session.sendSignInLink('STAFF@FIELDMUSEUM.ORG');
      expect(auth.email, 'staff@fieldmuseum.org');
      expect(auth.settings!.url, emailLinkReturnUrl);
      expect(auth.settings!.handleCodeInApp, true);
      expect(auth.settings!.linkDomain, isNull);
      expect(auth.settings!.androidPackageName, emailLinkAndroidPackageName);
      expect(auth.settings!.iOSBundleId, isNull);
      await session.completeEmailLink('STAFF@FIELDMUSEUM.ORG', testLink);
      expect(auth.completeCalls, 1);
      expect(auth.link, testLink);
      await expectLater(
        session.sendSignInLink('staff@other.org'),
        throwsFormatException,
      );
      await expectLater(
        session.completeEmailLink('staff@other.org', testLink),
        throwsFormatException,
      );
      await expectLater(
        session.completeEmailLink('staff@fieldmuseum.org', 'invalid'),
        throwsA(isA<FirebaseAuthException>()),
      );
      expect(auth.sendCalls, 1);
      expect(auth.completeCalls, 1);
      await expectLater(
        session.signIn('staff@fieldmuseum.org', 'unused'),
        throwsUnsupportedError,
      );
      await expectLater(
        session.resetPassword('staff@fieldmuseum.org'),
        throwsUnsupportedError,
      );
    },
  );

  test(
    'send waits for initialization, rejects bad address and cannot double-dispatch',
    () async {
      final c = controller();
      await c.send('staff@fieldmuseum.org');
      expect(access.sent, isEmpty);
      await c.initialize();
      await c.send('staff@foreign.org');
      expect(access.sent, isEmpty);
      access.sendWait = Completer<void>();
      final future = c.send('STAFF@FIELDMUSEUM.ORG');
      await Future<void>.delayed(Duration.zero);
      await c.send('another@fieldmuseum.org');
      expect(access.sent, ['staff@fieldmuseum.org']);
      expect(storage.value.email, 'staff@fieldmuseum.org');
      expect(c.busy, true);
      access.sendWait!.complete();
      await future;
      expect(c.sent, true);
      expect(c.cooldownSeconds, 60);
    },
  );

  test(
    'remembered email and cooldown survive controller refresh, including change email',
    () async {
      final first = controller();
      await first.initialize();
      await first.send('STAFF@FIELDMUSEUM.ORG');
      clock = clock.add(const Duration(seconds: 15));
      final next = controller();
      await next.initialize();
      expect(next.email, 'staff@fieldmuseum.org');
      expect(next.cooldownSeconds, 45);
      await next.send('staff@fieldmuseum.org');
      expect(access.sent.length, 1);
      await next.changeEmail();
      expect(storage.value.email, isNull);
      expect(next.cooldownSeconds, 45);
      clock = clock.add(const Duration(seconds: 46));
      await next.send('other@fieldmuseum.org');
      expect(access.sent.length, 2);
    },
  );

  test(
    'same browser completes once and removes URL code plus remembered email',
    () async {
      storage.value = RememberedEmailLink(
        email: 'STAFF@FIELDMUSEUM.ORG',
        retryAt: clock.add(emailLinkCooldown),
      );
      final c = controller(link: testLink);
      await c.initialize();
      await c.initialize();
      expect(access.checked, [testLink]);
      expect(access.completed, [('staff@fieldmuseum.org', testLink)]);
      expect(c.handlingLink, false);
      expect(browser.clearCount, 1);
      expect(storage.value.email, isNull);
      expect(c.cooldownSeconds, 60);
    },
  );

  test(
    'Android cold delivery accepts the exact Firebase Hosting envelope',
    () async {
      storage.value = const RememberedEmailLink(email: 'staff@fieldmuseum.org');
      final source = FakeEmailLinkSource(pending: Uri.parse(nativeTestLink));
      addTearDown(source.close);
      final c = MagicLinkController(
        access: access,
        storage: storage,
        browser: MemoryEmailLinkBrowser(),
        linkSource: source,
        now: () => clock,
      );
      addTearDown(c.dispose);

      await c.initialize();

      expect(access.checked, [nativeActionLink]);
      expect(access.completed, [('staff@fieldmuseum.org', nativeActionLink)]);
      expect(source.pending, isNull);
      expect(source.acknowledged, hasLength(1));
      expect(c.handlingLink, false);
    },
  );

  test(
    'iOS warm delivery passes the validated inner action to Firebase Auth',
    () async {
      storage.value = const RememberedEmailLink(email: 'staff@fieldmuseum.org');
      final source = FakeEmailLinkSource();
      addTearDown(source.close);
      final c = MagicLinkController(
        access: access,
        storage: storage,
        browser: MemoryEmailLinkBrowser(),
        linkSource: source,
        now: () => clock,
      );
      addTearDown(c.dispose);
      await c.initialize();

      source.deliver(Uri.parse(nativeTestLink));
      await pumpEventQueue();

      expect(access.checked, [nativeActionLink]);
      expect(access.completed, [('staff@fieldmuseum.org', nativeActionLink)]);
      expect(source.pending, isNull);
      expect(source.acknowledged, hasLength(1));
      expect(c.handlingLink, false);
    },
  );

  test(
    'successful completion cleans URL and storage after controller disposal',
    () async {
      storage.value = const RememberedEmailLink(email: 'staff@fieldmuseum.org');
      access.completeWait = Completer<void>();
      final currentBrowser = MemoryEmailLinkBrowser(uri: Uri.parse(testLink));
      final c = MagicLinkController(
        access: access,
        storage: storage,
        browser: currentBrowser,
        now: () => clock,
      );
      final pending = c.initialize();
      await Future<void>.delayed(Duration.zero);
      expect(access.completed.length, 1);
      c.dispose(); // Firebase userChanges may rebuild/unmount while SDK resolves.
      access.completeWait!.complete();
      await pending;
      expect(currentBrowser.clearCount, 1);
      expect(storage.value.email, isNull);
    },
  );

  test(
    'other browser asks for email and never trusts email URL parameters',
    () async {
      final link = '$testLink&email=attacker%40fieldmuseum.org';
      final c = controller(link: link);
      await c.initialize();
      expect(c.handlingLink, true);
      expect(c.email, isEmpty);
      expect(access.completed, isEmpty);
      await c.complete('staff@evil.org');
      expect(access.completed, isEmpty);
      await c.complete('USER@FIELDMUSEUM.ORG');
      expect(access.completed, [('user@fieldmuseum.org', link)]);
      expect(browser.clearCount, 1);
      expect(storage.value.email, isNull);
    },
  );

  test(
    'an explicitly pasted link uses the strict path and is never persisted',
    () async {
      final c = controller();
      await c.initialize();

      expect(c.acceptPastedLink('  $testLink\n'), isTrue);

      expect(access.checked, [testLink]);
      expect(access.completed, isEmpty);
      expect(c.handlingLink, isTrue);
      expect(browser.clearCount, 0);
      expect(storage.writes, 0);
      expect(storage.value.email, isNull);
    },
  );

  test('a pasted foreign link is rejected without reaching Firebase', () async {
    final c = controller();
    await c.initialize();

    expect(
      c.acceptPastedLink(
        'https://evil.test/?mode=signIn&oobCode=private-action-code',
      ),
      isFalse,
    );

    expect(access.checked, isEmpty);
    expect(access.completed, isEmpty);
    expect(c.handlingLink, isFalse);
    expect(c.message, contains('cannot be used'));
    expect(c.message, isNot(contains('private-action-code')));
    expect(storage.writes, 0);
  });

  for (final link in [
    'http://specimen-digitization.web.app/?mode=signIn&oobCode=x',
    'https://other.test/?mode=signIn&oobCode=x',
    'https://specimen-digitization.web.app/?mode=signIn&oobCode=x&oobCode=y',
    'https://specimen-digitization.web.app/?mode=resetPassword&oobCode=x',
    'https://specimen-digitization.web.app/?mode=signIn&oobCode=',
    'https://specimen-digitization.web.app/#oobCode=x',
    'https://specimen-digitization.web.app/?link=x',
  ]) {
    test('malformed callback is cleaned without sign-in: $link', () async {
      final c = controller(link: link);
      await c.initialize();
      expect(access.completed, isEmpty);
      expect(c.handlingLink, false);
      expect(browser.clearCount, 1);
      expect(c.message, contains('cannot be used'));
    });
  }

  for (final link in [
    nativeTestLink.replaceFirst('https:', 'http:'),
    nativeTestLink.replaceFirst(
      'specimen-digitization.firebaseapp.com',
      'other.firebaseapp.com',
    ),
    nativeTestLink.replaceFirst('/__/auth/links?', '/__/auth/links/extra?'),
    nativeTestLink.replaceFirst(
      'https://specimen-digitization.firebaseapp.com',
      'https://attacker@specimen-digitization.firebaseapp.com',
    ),
    nativeTestLink.replaceFirst(
      'specimen-digitization.firebaseapp.com/',
      'specimen-digitization.firebaseapp.com:444/',
    ),
    '$nativeTestLink#fragment',
    '$nativeTestLink&ofl=https%3A%2F%2Fevil.test%2F',
    '$nativeTestLink&link=${Uri.encodeQueryComponent(nativeActionLink)}',
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link':
          'https://evil.test/__/auth/action?mode=signIn&oobCode=fixture-action-code&continueUrl=https%3A%2F%2Fspecimen-digitization.web.app%2F',
    }).toString(),
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link': nativeActionLink.replaceFirst(
        '/__/auth/action?',
        '/__/auth/handler?',
      ),
    }).toString(),
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link': nativeActionLink.replaceFirst(
        'https://specimen-digitization.firebaseapp.com',
        'http://specimen-digitization.firebaseapp.com',
      ),
    }).toString(),
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link': nativeActionLink.replaceFirst(
        'specimen-digitization.firebaseapp.com/',
        'attacker@specimen-digitization.firebaseapp.com/',
      ),
    }).toString(),
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link': nativeActionLink.replaceFirst(
        'specimen-digitization.firebaseapp.com/',
        'specimen-digitization.firebaseapp.com:444/',
      ),
    }).toString(),
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link': nativeActionLink.replaceFirst(
        'mode=signIn',
        'mode=resetPassword',
      ),
    }).toString(),
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link': '$nativeActionLink&oobCode=other-action-code',
    }).toString(),
    Uri.https('specimen-digitization.firebaseapp.com', '/__/auth/links', {
      'link': nativeActionLink.replaceFirst(
        'https%3A%2F%2Fspecimen-digitization.web.app%2F',
        'https%3A%2F%2Fevil.test%2F',
      ),
    }).toString(),
  ]) {
    test(
      'untrusted native envelope is cleaned without sign-in: $link',
      () async {
        final c = controller(link: link);
        await c.initialize();
        expect(access.completed, isEmpty);
        expect(access.checked, isEmpty);
        expect(c.handlingLink, false);
        expect(browser.clearCount, 1);
        expect(c.message, contains('cannot be used'));
      },
    );
  }
  test('SDK rejects malformed link even if URL shape is valid', () async {
    access.linkValid = false;
    final c = controller(link: testLink);
    await c.initialize();
    expect(c.handlingLink, false);
    expect(browser.clearCount, 1);
    expect(access.completed, isEmpty);
  });

  for (final encoded in ['%FF', '%C0%AF', '%E2%82']) {
    test(
      'malformed UTF-8 callback $encoded finishes initialization safely',
      () async {
        final c = controller(
          link:
              'https://specimen-digitization.web.app/?mode=signIn&oobCode=$encoded',
        );
        await expectLater(c.initialize(), completes);
        expect(c.initialized, true);
        expect(c.busy, false);
        expect(c.handlingLink, false);
        expect(
          c.message,
          'This sign-in link cannot be used. Request a new link.',
        );
        expect(browser.clearCount, 1);
        expect(access.completed, isEmpty);
        await c.send('staff@fieldmuseum.org');
        expect(access.sent, ['staff@fieldmuseum.org']);
      },
    );
  }

  for (final encoded in ['%ZZ', '%']) {
    test(
      'permissive percent parse $encoded still requires SDK validation',
      () async {
        access.linkValid = false;
        final c = controller(
          link:
              'https://specimen-digitization.web.app/?mode=signIn&oobCode=$encoded',
        );
        await c.initialize();
        expect(c.initialized, true);
        expect(c.handlingLink, false);
        expect(
          c.message,
          'This sign-in link cannot be used. Request a new link.',
        );
        expect(browser.clearCount, 1);
        expect(access.completed, isEmpty);
      },
    );
  }

  for (final code in [
    'expired-action-code',
    'invalid-action-code',
    'invalid-credential',
  ]) {
    test(
      'expired/reused code $code is terminal, cleaned and not automatically replayed',
      () async {
        access.completeError = FirebaseAuthException(
          code: code,
          message: 'PRIVATE RAW ERROR',
        );
        final c = controller(link: testLink);
        await c.initialize();
        await c.complete('staff@fieldmuseum.org');
        expect(c.message, contains('expired or was already used'));
        expect(c.message, isNot(contains('PRIVATE')));
        expect(c.handlingLink, false);
        expect(browser.clearCount, 1);
        await c.complete('staff@fieldmuseum.org');
        expect(access.completed.length, 1);
      },
    );
  }
  test(
    'network failure permits explicit retry while preserving cooldown and hides error data',
    () async {
      access.sendError = FirebaseAuthException(
        code: 'network-request-failed',
        message: testLink,
      );
      final c = controller();
      await c.initialize();
      await c.send('staff@fieldmuseum.org');
      expect(c.message, contains('connection'));
      expect(c.message, isNot(contains('fixture-action-code')));
      expect(c.cooldownSeconds, 60);
      await c.send('staff@fieldmuseum.org');
      expect(access.sent.length, 1);
      clock = clock.add(const Duration(seconds: 61));
      access.sendError = null;
      await c.send('staff@fieldmuseum.org');
      expect(access.sent.length, 2);
    },
  );
  test('cross-browser cancel clears link without authenticating', () async {
    final c = controller(link: testLink);
    await c.initialize();
    await c.changeEmail();
    expect(c.handlingLink, false);
    expect(browser.clearCount, 1);
    expect(access.completed, isEmpty);
  });
  test(
    'unavailable storage still permits send and explicit confirmation',
    () async {
      storage.fail = true;
      final c = controller();
      await c.initialize();
      await c.send('staff@fieldmuseum.org');
      expect(access.sent.length, 1);
      expect(c.sent, true);
    },
  );
  test(
    'SharedPreferences roundtrip persists address/cooldown and never action code',
    () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = PreferencesEmailLinkStorage();
      await prefs.write(
        RememberedEmailLink(email: 'staff@fieldmuseum.org', retryAt: clock),
      );
      final value = await prefs.read();
      expect(value.email, 'staff@fieldmuseum.org');
      expect(value.retryAt, clock);
      final raw = await SharedPreferences.getInstance();
      expect(raw.getKeys(), {
        PreferencesEmailLinkStorage.emailKey,
        PreferencesEmailLinkStorage.retryKey,
      });
      await prefs.write(RememberedEmailLink(retryAt: clock));
      expect((await prefs.read()).email, isNull);
    },
  );
}
