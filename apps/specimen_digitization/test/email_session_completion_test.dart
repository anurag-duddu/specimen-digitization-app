import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'magic_link_app_test.dart' show LinkSession;
import 'magic_link_controller_test.dart'
    show FakeLinkAccess, MemoryLinkStorage, testLink;

class DelayedLinkStorage extends MemoryLinkStorage {
  final started = Completer<void>();
  final release = Completer<void>();

  @override
  Future<void> write(RememberedEmailLink value) async {
    if (!started.isCompleted) {
      started.complete();
      await release.future;
    }
    await super.write(value);
  }
}

class PendingSendAccess extends FakeLinkAccess {
  final started = Completer<void>();

  @override
  Future<void> sendSignInLink(String email) {
    started.complete();
    return super.sendSignInLink(email);
  }
}

class RestoredEmailSession extends LinkSession {
  String address = 'staff@fieldmuseum.org';

  @override
  String get displayName => address;

  void restore({required bool verified}) {
    signedIn = true;
    emailVerified = verified;
    controller.add(true);
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
    'matching verified session clears sent state and preserves cooldown',
    () async {
      final storage = MemoryLinkStorage();
      final controller = MagicLinkController(
        access: FakeLinkAccess(),
        browser: MemoryEmailLinkBrowser(),
        storage: storage,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.send('staff@fieldmuseum.org');
      final deadline = storage.value.retryAt;

      await controller.reconcileVerifiedSession('another@fieldmuseum.org');
      expect(controller.sent, isTrue);
      await controller.reconcileVerifiedSession('not an email');
      expect(controller.sent, isTrue);
      await controller.reconcileVerifiedSession('STAFF@FIELDMUSEUM.ORG');

      expect(controller.sent, isFalse);
      expect(controller.email, isEmpty);
      expect(controller.message, isNull);
      expect(storage.value.email, isNull);
      expect(storage.value.retryAt, deadline);
      expect(controller.cooldownSeconds, greaterThan(0));
    },
  );

  test('a late send failure cannot restore an authenticated request', () async {
    final access = PendingSendAccess()
      ..sendWait = Completer<void>()
      ..sendError = FirebaseAuthException(code: 'network-request-failed');
    final controller = MagicLinkController(
      access: access,
      browser: MemoryEmailLinkBrowser(),
      storage: MemoryLinkStorage(),
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    final sending = controller.send('staff@fieldmuseum.org');
    await access.started.future;
    await controller.reconcileVerifiedSession('staff@fieldmuseum.org');
    access.sendWait!.complete();
    await sending;

    expect(controller.busy, isFalse);
    expect(controller.sent, isFalse);
    expect(controller.email, isEmpty);
    expect(controller.message, isNull);
  });

  test(
    'cleanup follows an older pending preference write and prevents dispatch',
    () async {
      final storage = DelayedLinkStorage();
      final access = FakeLinkAccess();
      final controller = MagicLinkController(
        access: access,
        browser: MemoryEmailLinkBrowser(),
        storage: storage,
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      final sending = controller.send('staff@fieldmuseum.org');
      await storage.started.future;
      final clearing = controller.reconcileVerifiedSession(
        'staff@fieldmuseum.org',
      );
      storage.release.complete();
      await sending;
      await clearing;

      expect(access.sent, isEmpty);
      expect(storage.value.email, isNull);
      expect(storage.value.retryAt, isNotNull);
      expect(controller.sent, isFalse);
      expect(controller.email, isEmpty);
    },
  );

  test(
    'verified event cannot cancel an incoming link still completing',
    () async {
      final access = FakeLinkAccess()..completeWait = Completer<void>();
      final browser = MemoryEmailLinkBrowser(uri: Uri.parse(testLink));
      final controller = MagicLinkController(
        access: access,
        browser: browser,
        storage: MemoryLinkStorage(),
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      final completion = controller.complete('staff@fieldmuseum.org');
      await controller.reconcileVerifiedSession('staff@fieldmuseum.org');

      expect(controller.handlingLink, isTrue);
      expect(controller.busy, isTrue);
      expect(controller.email, 'staff@fieldmuseum.org');
      expect(browser.clearCount, 0);
      access.completeWait!.complete();
      await completion;
      expect(controller.handlingLink, isFalse);
      expect(browser.clearCount, 1);
    },
  );

  testWidgets(
    'external verified session advances and does not restore stale sent state',
    (tester) async {
      final session = RestoredEmailSession();
      addTearDown(session.controller.close);
      await tester.pumpWidget(SpecimenDigitizationApp(session: session));
      await tester.pumpAndSettle();
      final controller = tester
          .widget<MagicLinkSignInScreen>(find.byType(MagicLinkSignInScreen))
          .controller!;
      await controller.send('staff@fieldmuseum.org');
      await tester.pumpAndSettle();
      expect(find.text('Open Gmail'), findsOneWidget);

      session.restore(verified: true);
      await tester.pumpAndSettle();
      expect(find.text('Collection connection required'), findsOneWidget);
      expect(controller.email, isEmpty);
      expect(controller.sent, isFalse);
      expect(controller.cooldownSeconds, greaterThan(0));
      await session.signOut();
      await tester.pumpAndSettle();
      expect(find.text('Send link'), findsOneWidget);
      expect(find.text('Open Gmail'), findsNothing);
      expect(
        tester.widget<UiField>(find.byType(UiField)).controller!.text,
        isEmpty,
      );
      expect(session.completed, isEmpty);
    },
  );

  testWidgets('an unverified restored session keeps the pending request', (
    tester,
  ) async {
    final session = RestoredEmailSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(SpecimenDigitizationApp(session: session));
    await tester.pumpAndSettle();
    final controller = tester
        .widget<MagicLinkSignInScreen>(find.byType(MagicLinkSignInScreen))
        .controller!;
    await controller.send('staff@fieldmuseum.org');

    session.restore(verified: false);
    await tester.pumpAndSettle();
    expect(find.text('Verify your account'), findsOneWidget);
    expect(controller.sent, isTrue);
    expect(controller.email, 'staff@fieldmuseum.org');
    session.restore(verified: true);
    await tester.pumpAndSettle();
    expect(controller.sent, isFalse);
  });

  testWidgets(
    'already restored session clears preferences after initialization',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        PreferencesEmailLinkStorage.emailKey: 'staff@fieldmuseum.org',
      });
      final session = RestoredEmailSession()
        ..signedIn = true
        ..emailVerified = true;
      addTearDown(session.controller.close);
      await tester.pumpWidget(SpecimenDigitizationApp(session: session));
      await tester.pumpAndSettle();
      expect(
        (await SharedPreferences.getInstance()).getString(
          PreferencesEmailLinkStorage.emailKey,
        ),
        isNull,
      );
      await session.signOut();
      await tester.pumpAndSettle();
      expect(find.text('Send link'), findsOneWidget);
      expect(find.text('Open Gmail'), findsNothing);
    },
  );
}
