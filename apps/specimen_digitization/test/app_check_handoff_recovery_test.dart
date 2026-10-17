@TestOn('vm')
library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/app_reload.dart';
import 'package:specimen_digitization/src/google_sign_in.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'magic_link_app_test.dart' show LinkSession;
import 'magic_link_controller_test.dart'
    show FakeEmailLinkSource, MemoryLinkStorage, testLink;
import 'widget_test.dart' show TestRepository;

const appCheckFailure = ApiFailure(
  'App verification stopped before collection access was checked. '
  'Reload or reopen the app to start it again.',
  status: 403,
  code: 'app_check_unavailable',
);
const intendedRoute = '/c/museum%2Finsects/queue/fixture%20record';

class RecoverySession extends LinkSession implements GoogleSignInAccess {
  String address = 'staff@fieldmuseum.org';
  String identity = 'staff-fixture';
  int googleCalls = 0;

  @override
  String get displayName => address;
  @override
  String get userId => signedIn ? identity : '';
  @override
  bool get googleSignInAvailable => true;

  void restore({bool verified = true}) {
    signedIn = true;
    emailVerified = verified;
    controller.add(true);
  }

  @override
  Future<GoogleSignInOutcome> signInWithGoogle({String? emailHint}) async {
    googleCalls++;
    restore();
    return GoogleSignInOutcome.signedIn;
  }
}

class RecoveryRepository extends TestRepository implements AccessFailureSource {
  Object? failure = appCheckFailure;
  Completer<void>? scopeGate;
  List<CollectionScope>? scopesOverride;
  int scopeCalls = 0;
  final failures = StreamController<ApiFailure>.broadcast(sync: true);

  @override
  Stream<ApiFailure> get accessFailures => failures.stream;

  @override
  Future<List<CollectionScope>> scopes() async {
    scopeCalls++;
    await scopeGate?.future;
    final error = failure;
    if (error != null) {
      if (error is ApiFailure) failures.add(error);
      throw error;
    }
    return scopesOverride ?? await super.scopes();
  }
}

class RecordingReload implements AppReload {
  final locations = <String>[];
  Object? failure;

  @override
  Future<void> reload(String location) async {
    locations.add(location);
    if (failure case final Object error) throw error;
  }
}

class DelayedCleanupStorage extends MemoryLinkStorage {
  final started = Completer<void>();
  final release = Completer<void>();

  @override
  Future<void> write(RememberedEmailLink value) async {
    if (value.email == null) {
      if (!started.isCompleted) started.complete();
      await release.future;
    }
    await super.write(value);
  }
}

class RecoveryFixture {
  RecoveryFixture(this.session, this.repository, this.reload, this.link);
  final RecoverySession session;
  final RecoveryRepository repository;
  final RecordingReload? reload;
  final MagicLinkController? link;
}

Future<RecoveryFixture> mountRecovery(
  WidgetTester tester, {
  RecoverySession? session,
  RecoveryRepository? repository,
  MemoryLinkStorage? storage,
  RecordingReload? reload,
  bool native = false,
  String? incoming,
  FakeEmailLinkSource? source,
}) async {
  final activeSession = session ?? RecoverySession();
  final activeRepository = repository ?? RecoveryRepository();
  final activeReload = native ? null : reload ?? RecordingReload();
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox());
    await activeRepository.failures.close();
    await activeSession.controller.close();
  });
  await tester.pumpWidget(
    SpecimenDigitizationApp(
      session: activeSession,
      repository: activeRepository,
      initialLocation: intendedRoute,
      appReload: activeReload,
      emailLinkStorage: storage ?? MemoryLinkStorage(),
      emailLinkBrowser: MemoryEmailLinkBrowser(
        uri: incoming == null ? null : Uri.parse(incoming),
      ),
      emailLinkSource: source,
    ),
  );
  await tester.pumpAndSettle();
  final finder = find.byType(MagicLinkSignInScreen);
  return RecoveryFixture(
    activeSession,
    activeRepository,
    activeReload,
    finder.evaluate().isEmpty
        ? null
        : tester.widget<MagicLinkSignInScreen>(finder).controller,
  );
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('matching cross-tab handoff reloads once at the intended route', (
    tester,
  ) async {
    final storage = MemoryLinkStorage();
    final fixture = await mountRecovery(tester, storage: storage);
    await fixture.link!.send('STAFF@FIELDMUSEUM.ORG');
    final cooldown = storage.value.retryAt;
    fixture.session.restore();
    await tester.pumpAndSettle();

    expect(fixture.reload!.locations, [intendedRoute]);
    expect(fixture.repository.scopeCalls, 1);
    expect(fixture.link!.sent, isFalse);
    expect(fixture.link!.email, isEmpty);
    expect(storage.value.email, isNull);
    expect(storage.value.retryAt, cooldown);
    expect(find.byType(AppShell), findsNothing);
    // Synchronous denial, thrown denial and repeat identity events are one
    // outcome, not three reloads or an authorization bypass.
    fixture.repository.failures.add(appCheckFailure);
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, [intendedRoute]);
    await tester.pumpWidget(const SizedBox());
    storage.value = const RememberedEmailLink(email: 'staff@fieldmuseum.org');
    await tester.pumpWidget(
      SpecimenDigitizationApp(
        session: fixture.session,
        repository: fixture.repository,
        appReload: fixture.reload,
        emailLinkStorage: storage,
        initialLocation: intendedRoute,
      ),
    );
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, [intendedRoute]);
  });

  for (final intervening in [
    'verified-other-account',
    'unverified-matching-account',
  ]) {
    testWidgets(
      'intervening $intervening then sign-out cannot reuse an old send',
      (tester) async {
        final fixture = await mountRecovery(tester);
        await fixture.link!.send('staff@fieldmuseum.org');
        if (intervening == 'verified-other-account') {
          fixture.session.address = 'another@fieldmuseum.org';
          fixture.session.identity = 'another-fixture';
          fixture.session.restore();
        } else {
          fixture.session.restore(verified: false);
        }
        await tester.pumpAndSettle();
        expect(fixture.reload!.locations, isEmpty);
        await fixture.session.signOut();
        await tester.pumpAndSettle();
        fixture.session.address = 'staff@fieldmuseum.org';
        fixture.session.identity = 'staff-fixture';
        fixture.session.restore();
        await tester.pumpAndSettle();
        expect(fixture.reload!.locations, isEmpty);
        expect(fixture.link!.emailSentInThisPage, isNull);
        expect(find.text('Reload app'), findsOneWidget);
        expect(find.byType(AppShell), findsNothing);
      },
    );
  }

  testWidgets(
    'initial duplicate signed-out events retain the current email request',
    (tester) async {
      final fixture = await mountRecovery(tester);
      await fixture.link!.send('staff@fieldmuseum.org');
      // Firebase may repeat its still-signed-out initial state while the user
      // opens email. This is not a transition out of an established session.
      fixture.session.controller.add(false);
      fixture.session.controller.add(false);
      await tester.pumpAndSettle();
      expect(fixture.link!.emailSentInThisPage, 'staff@fieldmuseum.org');
      fixture.session.restore();
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, [intendedRoute]);
    },
  );

  testWidgets(
    'an established identity change invalidates pending email provenance',
    (tester) async {
      final fixture = await mountRecovery(tester);
      await fixture.link!.send('staff@fieldmuseum.org');
      fixture.session.restore(verified: false);
      await tester.pumpAndSettle();
      expect(fixture.link!.emailSentInThisPage, 'staff@fieldmuseum.org');
      fixture.session.identity = 'another-fixture';
      fixture.session.address = 'another@fieldmuseum.org';
      fixture.session.restore(verified: false);
      await tester.pumpAndSettle();
      expect(fixture.link!.emailSentInThisPage, isNull);
      expect(fixture.reload!.locations, isEmpty);
    },
  );

  testWidgets('cleanup is awaited despite repeated verified notifications', (
    tester,
  ) async {
    final storage = DelayedCleanupStorage();
    final fixture = await mountRecovery(tester, storage: storage);
    await fixture.link!.send('staff@fieldmuseum.org');
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(storage.started.isCompleted, isTrue);
    expect(fixture.reload!.locations, isEmpty);
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(fixture.repository.scopeCalls, 1);
    expect(fixture.reload!.locations, isEmpty);
    storage.release.complete();
    await tester.pumpAndSettle();
    expect(storage.value.email, isNull);
    expect(fixture.reload!.locations, [intendedRoute]);
  });

  for (final change in [
    'sign-out',
    'identity',
    'cancel',
    'google',
    'incoming',
  ]) {
    testWidgets('$change while cleanup waits cancels automatic reload', (
      tester,
    ) async {
      final storage = DelayedCleanupStorage();
      final source = FakeEmailLinkSource();
      final fixture = await mountRecovery(
        tester,
        storage: storage,
        source: source,
      );
      await fixture.link!.send('staff@fieldmuseum.org');
      fixture.session.restore();
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
      switch (change) {
        case 'sign-out':
          await fixture.session.signOut();
        case 'identity':
          fixture.session.identity = 'another-fixture';
          fixture.session.restore();
        case 'cancel':
          unawaited(fixture.link!.changeEmail());
        case 'google':
          fixture.link!.beginAlternateSignIn();
        case 'incoming':
          fixture.session.completeWait = Completer<void>();
          source.deliver(Uri.parse(testLink));
      }
      await tester.pumpAndSettle();
      storage.release.complete();
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
      fixture.session.completeWait?.complete();
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
    });
  }

  for (final error in <Object>[
    const ApiFailure('Membership refused.', status: 403, code: 'forbidden'),
    const ApiFailure('Sign in again.', status: 401, code: 'unauthenticated'),
    StateError('synthetic network failure'),
  ]) {
    final kind = error is ApiFailure ? error.code : 'network';
    testWidgets('unrelated $kind outcome disarms recovery', (tester) async {
      final fixture = await mountRecovery(
        tester,
        repository: RecoveryRepository()..failure = error,
      );
      await fixture.link!.send('staff@fieldmuseum.org');
      fixture.session.restore();
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
      expect(find.text('Reload app'), findsNothing);
      expect(find.text('Check access again'), findsOneWidget);
      fixture.repository.failures.add(appCheckFailure);
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
    });
  }

  testWidgets('successful access disarms before a later App Check failure', (
    tester,
  ) async {
    final fixture = await mountRecovery(
      tester,
      repository: RecoveryRepository()..failure = null,
    );
    await fixture.link!.send('staff@fieldmuseum.org');
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(find.byType(AppShell), findsOneWidget);
    fixture.repository.failures.add(appCheckFailure);
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, isEmpty);
    expect(find.byType(AppShell), findsNothing);
    expect(find.text('Reload app'), findsOneWidget);
  });

  testWidgets(
    'an authoritative empty collection result also disarms recovery',
    (tester) async {
      final fixture = await mountRecovery(
        tester,
        repository: RecoveryRepository()
          ..failure = null
          ..scopesOverride = <CollectionScope>[],
      );
      await fixture.link!.send('staff@fieldmuseum.org');
      fixture.session.restore();
      await tester.pumpAndSettle();
      expect(find.text('You have no collection assigned'), findsOneWidget);
      fixture.repository.failures.add(appCheckFailure);
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
    },
  );

  testWidgets('an unsuccessful email request cannot arm recovery', (
    tester,
  ) async {
    final fixture = await mountRecovery(tester);
    fixture.session.sendError = StateError('synthetic send failure');
    await fixture.link!.send('staff@fieldmuseum.org');
    expect(fixture.link!.emailSentInThisPage, isNull);
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, isEmpty);
  });

  testWidgets('different or unverified account cannot arm recovery', (
    tester,
  ) async {
    final fixture = await mountRecovery(tester);
    await fixture.link!.send('staff@fieldmuseum.org');
    fixture.session.restore(verified: false);
    await tester.pumpAndSettle();
    expect(fixture.repository.scopeCalls, 0);
    fixture.session.address = 'another@fieldmuseum.org';
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, isEmpty);
  });

  testWidgets(
    'remembered email and already-restored launch never auto reload',
    (tester) async {
      final storage = MemoryLinkStorage()
        ..value = const RememberedEmailLink(email: 'staff@fieldmuseum.org');
      final fixture = await mountRecovery(tester, storage: storage);
      expect(fixture.link!.sent, isTrue);
      expect(fixture.link!.emailSentInThisPage, isNull);
      fixture.session.restore();
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
      // Reconstruct the app as a reload would. Even stale optional preferences
      // cannot arm another automatic reload without a new request in this page.
      await tester.pumpWidget(const SizedBox());
      storage.value = const RememberedEmailLink(email: 'staff@fieldmuseum.org');
      await tester.pumpWidget(
        SpecimenDigitizationApp(
          session: fixture.session,
          repository: fixture.repository,
          appReload: fixture.reload,
          emailLinkStorage: storage,
        ),
      );
      await tester.pumpAndSettle();
      expect(fixture.reload!.locations, isEmpty);
      expect(find.text('Reload app'), findsOneWidget);
    },
  );

  testWidgets('an incoming local link does not arm cross-tab recovery', (
    tester,
  ) async {
    final fixture = await mountRecovery(tester, incoming: testLink);
    await fixture.link!.complete('staff@fieldmuseum.org');
    await tester.pumpAndSettle();
    expect(fixture.session.completed, hasLength(1));
    expect(fixture.reload!.locations, isEmpty);
    expect(find.text('Reload app'), findsOneWidget);
  });

  testWidgets('Google dispatch invalidates the page email handoff hint', (
    tester,
  ) async {
    final fixture = await mountRecovery(tester);
    await fixture.link!.send('staff@fieldmuseum.org');
    await fixture.link!.changeEmail();
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Sign in with Google'));
    await tester.pump();
    await tester.tap(find.text('Sign in with Google'));
    await tester.pumpAndSettle();
    expect(fixture.session.googleCalls, 1);
    expect(fixture.link!.emailSentInThisPage, isNull);
    expect(fixture.reload!.locations, isEmpty);
  });

  testWidgets('explicit web fallback performs a real reload request', (
    tester,
  ) async {
    final fixture = await mountRecovery(tester);
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, isEmpty);
    final before = fixture.repository.scopeCalls;
    await tester.ensureVisible(find.text('Reload app'));
    await tester.pump();
    await tester.tap(find.text('Reload app'));
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, [intendedRoute]);
    expect(fixture.repository.scopeCalls, before);
  });

  testWidgets('a web workspace denial action also invokes reload', (
    tester,
  ) async {
    final session = RecoverySession()..restore();
    final repository = RecoveryRepository();
    var reloads = 0;
    final workspace = WorkspaceController(
      session: session,
      repository: repository,
      reloadApp: () async {
        reloads++;
      },
    );
    addTearDown(() async {
      await repository.failures.close();
      await session.controller.close();
    });
    try {
      workspace.start();
      await tester.pumpAndSettle();
      expect(workspace.error?.actionLabel, 'Reload app');
      expect(workspace.scopesVerified, isFalse);
      await workspace.error!.action();
      expect(reloads, 1);
      expect(repository.scopeCalls, 1);
      expect(workspace.scopesVerified, isFalse);
    } finally {
      workspace.dispose();
    }
  });

  testWidgets('native App Check error retains the supported access retry', (
    tester,
  ) async {
    final fixture = await mountRecovery(tester, native: true);
    await fixture.link!.send('staff@fieldmuseum.org');
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(find.text('Reload app'), findsNothing);
    expect(find.text('Check access again'), findsOneWidget);
    final before = fixture.repository.scopeCalls;
    await tester.ensureVisible(find.text('Check access again'));
    await tester.pump();
    await tester.tap(find.text('Check access again'));
    await tester.pumpAndSettle();
    expect(fixture.repository.scopeCalls, before + 1);
  });

  testWidgets('a failed automatic browser reload keeps an explicit fallback', (
    tester,
  ) async {
    final fixture = await mountRecovery(
      tester,
      reload: RecordingReload()
        ..failure = StateError('synthetic reload failure'),
    );
    await fixture.link!.send('staff@fieldmuseum.org');
    fixture.session.restore();
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, hasLength(1));
    expect(find.text('Reload app'), findsOneWidget);
    fixture.repository.failures.add(appCheckFailure);
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, hasLength(1));
    await tester.ensureVisible(find.text('Reload app'));
    await tester.pump();
    await tester.tap(find.text('Reload app'));
    await tester.pumpAndSettle();
    expect(fixture.reload!.locations, hasLength(2));
    expect(
      find.textContaining('Use your browser’s Reload button'),
      findsOneWidget,
    );
  });

  test(
    'reload route stays internal and preserves encoded scope and record',
    () {
      expect(appReloadLocation(intendedRoute), intendedRoute);
      expect(
        appReloadLocation('/c/museum/insects/queue'),
        '/c/museum%2Finsects/queue',
      );
      expect(
        appReloadLocation('/c/museum%2Finsects/intake/sources/fixture'),
        '/c/museum%2Finsects/intake/sources/fixture',
      );
      for (final value in <String?>[
        null,
        'https://outside.example/',
        '//outside.example/',
        '/\\outside.example/',
        '/unknown',
        '/c/key',
        '/c/%FF/queue',
        '/c/key/intake/unknown',
        '/setup#mode=signIn',
        '/setup?oobCode=fixture-action',
        '/setup?mode=signIn',
        '/setup?link=fixture',
        '/setup?%FF=invalid',
      ]) {
        expect(appReloadLocation(value), AppRoutes.setup, reason: '$value');
      }
      final url = appReloadUrl(
        Uri.parse(
          'https://specimen-digitization.web.app/'
          '?mode=signIn&oobCode=fixture-action#/setup',
        ),
        intendedRoute,
      );
      expect(url, 'https://specimen-digitization.web.app/#$intendedRoute');
      expect(Uri.parse(url).hasQuery, isFalse);
    },
  );
}
