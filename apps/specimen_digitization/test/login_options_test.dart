import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart'
    show debugDefaultTargetPlatformOverride;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/google_sign_in.dart';
import 'package:specimen_digitization/src/google_sign_in_option.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'magic_link_controller_test.dart'
    show FakeLinkAccess, MemoryLinkStorage, FakeEmailLinkSource, testLink;

class FakeGoogleAccess implements GoogleSignInAccess {
  @override
  bool googleSignInAvailable = true;
  int attempts = 0;
  Completer<GoogleSignInOutcome>? pending;
  GoogleSignInFailure? failure;
  GoogleSignInOutcome outcome = GoogleSignInOutcome.cancelled;

  @override
  Future<GoogleSignInOutcome> signInWithGoogle({String? emailHint}) async {
    attempts++;
    if (pending != null) return pending!.future;
    if (failure != null) throw failure!;
    return outcome;
  }
}

Future<void> pumpLogin(
  WidgetTester tester,
  Widget child, {
  Size size = const Size(390, 844),
  double scale = 1,
  double keyboard = 0,
  bool dark = false,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: dark ? AppTheme.dark() : AppTheme.light(),
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          textScaler: TextScaler.linear(scale),
          viewInsets: EdgeInsets.only(bottom: keyboard),
        ),
        child: child!,
      ),
      home: child,
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> tapVisible(WidgetTester tester, String label) async {
  final target = find.text(label);
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pump();
}

MagicLinkController emailController(
  FakeLinkAccess access, {
  DateTime Function()? now,
}) => MagicLinkController(
  access: access,
  browser: MemoryEmailLinkBrowser(),
  storage: MemoryLinkStorage(),
  now: now,
);

void main() {
  // The faces, Google Sans among them, are loaded by `flutter_test_config.dart`
  // through `UiFonts.loadForTest`: the font belongs to specimen_ui now.
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'Google does not request an email and releases busy after cancellation',
    (tester) async {
      final google = FakeGoogleAccess()
        ..pending = Completer<GoogleSignInOutcome>();
      final changes = <bool>[];
      await pumpLogin(
        tester,
        Center(
          child: SizedBox(
            width: 320,
            child: GoogleSignInOption(
              access: google,
              onBusyChanged: changes.add,
            ),
          ),
        ),
      );
      expect(find.byType(UiField), findsNothing);
      final RenderParagraph providerLabel = tester.renderObject(
        find.text('Sign in with Google'),
      );
      expect(find.byType(UiGoogleSignInButton), findsOneWidget);
      expect(
        providerLabel.text.style!.fontFamily,
        GoogleSignInBrand.prefixedFontFamily,
      );
      expect(providerLabel.text.style!.fontWeight, FontWeight.w500);
      await tapVisible(tester, 'Sign in with Google');
      expect(changes, <bool>[true]);
      expect(google.attempts, 1);
      expect(find.text('Opening Google…'), findsOneWidget);
      await tester.tap(find.text('Sign in with Google'));
      expect(google.attempts, 1);
      google.pending!.complete(GoogleSignInOutcome.cancelled);
      await tester.pumpAndSettle();
      expect(changes, <bool>[true, false]);
      expect(
        find.text(
          'Google sign-in cancelled. You can try again or use an email link.',
        ),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      expect(changes, <bool>[true, false]);
    },
  );

  testWidgets('the option draws the same button on every platform', (
    tester,
  ) async {
    // The padding and the icon gap used to differ on iOS. The option offers the
    // design system's button now, which reads no platform.
    final sizes = <TargetPlatform, Size>{};
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    for (final platform in TargetPlatform.values) {
      debugDefaultTargetPlatformOverride = platform;
      await pumpLogin(
        tester,
        Center(child: GoogleSignInOption(access: FakeGoogleAccess())),
      );
      expect(find.byType(UiGoogleSignInButton), findsOneWidget);
      sizes[platform] = tester.getSize(find.byType(UiGoogleSignInButton));
    }
    debugDefaultTargetPlatformOverride = null;
    expect(sizes.values.toSet(), hasLength(1), reason: '$sizes');
    expect(sizes.values.first.height, UiDensity.hitBox);
  });

  testWidgets('disposing during Google sign-in never calls parent again', (
    tester,
  ) async {
    final google = FakeGoogleAccess()
      ..pending = Completer<GoogleSignInOutcome>();
    final changes = <bool>[];
    await pumpLogin(
      tester,
      GoogleSignInOption(access: google, onBusyChanged: changes.add),
    );
    await tapVisible(tester, 'Sign in with Google');
    await tester.pumpWidget(const SizedBox.shrink());
    google.pending!.complete(GoogleSignInOutcome.cancelled);
    await tester.pump();
    expect(changes, <bool>[true]);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'replacement provider uses its new controller and ignores old completion',
    (tester) async {
      final first = FakeGoogleAccess()
        ..pending = Completer<GoogleSignInOutcome>();
      final second = FakeGoogleAccess()
        ..pending = Completer<GoogleSignInOutcome>();
      final changes = <bool>[];
      Widget option(FakeGoogleAccess access) =>
          GoogleSignInOption(access: access, onBusyChanged: changes.add);
      await pumpLogin(tester, option(first));
      await tapVisible(tester, 'Sign in with Google');
      await pumpLogin(tester, option(second));
      expect(changes, <bool>[true, false]);
      await tapVisible(tester, 'Sign in with Google');
      first.pending!.complete(GoogleSignInOutcome.cancelled);
      await tester.pump();
      expect(changes, <bool>[true, false, true]);
      expect(second.attempts, 1);
      second.pending!.complete(GoogleSignInOutcome.cancelled);
      await tester.pumpAndSettle();
      expect(changes, <bool>[true, false, true, false]);
    },
  );

  testWidgets(
    'sent email is recognized without an editable field or duplicate prose',
    (tester) async {
      final access = FakeLinkAccess();
      final controller = emailController(access);
      addTearDown(controller.dispose);
      await controller.initialize();
      await pumpLogin(
        tester,
        MagicLinkSignInScreen(
          access: access,
          controller: controller,
          google: FakeGoogleAccess(),
        ),
      );
      await tester.enterText(find.byType(UiField), 'STAFF@FIELDMUSEUM.ORG');
      await tapVisible(tester, 'Send link');
      await tester.pumpAndSettle();
      expect(find.text('staff@fieldmuseum.org'), findsOneWidget);
      expect(find.byType(UiField), findsNothing);
      expect(find.text(emailLinkSentMessage), findsNothing);
      expect(find.text('Sign in with Google'), findsNothing);
      expect(find.widgetWithText(UiButton, 'Resend link'), findsOneWidget);
      expect(
        tester
            .widget<UiButton>(find.widgetWithText(UiButton, 'Resend link'))
            .variant,
        UiButtonVariant.secondary,
      );
      await tapVisible(tester, 'Change email');
      await tester.pumpAndSettle();
      expect(find.byType(UiField), findsOneWidget);
      expect(
        tester.widget<UiField>(find.byType(UiField)).controller!.text,
        isEmpty,
      );
      expect(find.text('Sign in with Google'), findsOneWidget);
      expect(controller.cooldownSeconds, greaterThan(0));
    },
  );

  testWidgets(
    'failed resend stays visible alongside recipient and retains cooldown',
    (tester) async {
      final access = FakeLinkAccess();
      var now = DateTime.utc(2026, 10, 17);
      final controller = emailController(access, now: () => now);
      addTearDown(controller.dispose);
      await controller.initialize();
      await controller.send('staff@fieldmuseum.org');
      now = now.add(const Duration(seconds: 61));
      access.sendError = FirebaseAuthException(code: 'network-request-failed');
      await pumpLogin(
        tester,
        MagicLinkSignInScreen(access: access, controller: controller),
      );
      await tapVisible(tester, 'Resend link');
      await tester.pumpAndSettle();
      expect(controller.sent, isTrue);
      expect(controller.hasError, isTrue);
      expect(find.text(controller.message!), findsOneWidget);
      expect(find.text('staff@fieldmuseum.org'), findsOneWidget);
      expect(controller.cooldownSeconds, 60);
      expect(
        tester
            .widget<UiButton>(find.widgetWithText(UiButton, 'Resend link'))
            .onPressed,
        isNull,
      );
    },
  );

  testWidgets('warm link during Google cancel releases confirmation controls', (
    tester,
  ) async {
    final google = FakeGoogleAccess()
      ..pending = Completer<GoogleSignInOutcome>();
    final access = FakeLinkAccess();
    final source = FakeEmailLinkSource();
    final controller = MagicLinkController(
      access: access,
      browser: MemoryEmailLinkBrowser(),
      storage: MemoryLinkStorage(),
      linkSource: source,
    );
    addTearDown(controller.dispose);
    addTearDown(source.close);
    await controller.initialize();
    await pumpLogin(
      tester,
      MagicLinkSignInScreen(
        access: access,
        controller: controller,
        google: google,
      ),
    );
    await tester.enterText(find.byType(UiField), 'staff@fieldmuseum.org');
    await tapVisible(tester, 'Sign in with Google');
    source.deliver(Uri.parse(testLink));
    await tester.pump();
    expect(find.text('Confirm your email'), findsOneWidget);
    expect(tester.widget<UiField>(find.byType(UiField)).enabled, isFalse);
    google.pending!.complete(GoogleSignInOutcome.cancelled);
    await tester.pumpAndSettle();
    expect(find.text('Sign in with Google'), findsNothing);
    expect(tester.widget<UiField>(find.byType(UiField)).enabled, isTrue);
    expect(
      tester
          .widget<UiButton>(find.widgetWithText(UiButton, 'Sign in'))
          .onPressed,
      isNotNull,
    );
    await tapVisible(tester, 'Sign in');
    await tester.pumpAndSettle();
    expect(access.completed.single.$1, 'staff@fieldmuseum.org');
  });

  for (final dark in <bool>[false, true]) {
    for (final size in <Size>[
      const Size(320, 568),
      const Size(390, 844),
      const Size(768, 1024),
      const Size(1024, 768),
      const Size(1440, 900),
    ]) {
      testWidgets(
        'email and Google errors wrap at 200 percent on $size dark=$dark',
        (tester) async {
          final access = FakeLinkAccess();
          var now = DateTime.utc(2026, 10, 17);
          final controller = emailController(access, now: () => now);
          addTearDown(controller.dispose);
          await controller.initialize();
          final google = FakeGoogleAccess()
            ..failure = const GoogleSignInFailure(
              GoogleSignInFailureKind.popupBlocked,
            );
          await pumpLogin(
            tester,
            MagicLinkSignInScreen(
              access: access,
              controller: controller,
              google: google,
            ),
            size: size,
            scale: 2,
            dark: dark,
            keyboard: size.width < 600 ? 280 : 0,
          );
          await tapVisible(tester, 'Sign in with Google');
          await tester.pumpAndSettle();
          final error = find.byKey(const ValueKey<String>('google-feedback'));
          await tester.ensureVisible(error);
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          final RenderParagraph paragraph = tester.renderObject(error);
          expect(paragraph.didExceedMaxLines, isFalse);
          expect(paragraph.maxLines, isNull);
          expect(paragraph.text.toPlainText(), google.failure!.message);
          final button = tester.renderObject<RenderParagraph>(
            find.text('Sign in with Google'),
          );
          expect(button.didExceedMaxLines, isFalse);
          expect(button.maxLines, isNull);
          await controller.send('long.staff.address@fieldmuseum.org');
          await tester.pumpAndSettle();
          final recipient = find.byKey(
            const ValueKey<String>('email-link-recipient'),
          );
          await tester.ensureVisible(recipient);
          expect(tester.takeException(), isNull);
          expect(
            tester.renderObject<RenderParagraph>(recipient).didExceedMaxLines,
            isFalse,
          );
          now = now.add(const Duration(seconds: 61));
          access.sendError = FirebaseAuthException(
            code: 'network-request-failed',
          );
          await controller.send('long.staff.address@fieldmuseum.org');
          await tester.pumpAndSettle();
          final emailError = find.byKey(
            const ValueKey<String>('email-link-error'),
          );
          await tester.ensureVisible(emailError);
          final RenderParagraph emailParagraph = tester.renderObject(
            emailError,
          );
          expect(emailParagraph.maxLines, isNull);
          expect(emailParagraph.didExceedMaxLines, isFalse);
          expect(emailParagraph.text.toPlainText(), controller.message);
          for (final label in <String>[
            'Resend link',
            'Change email',
            'Sign-in help',
          ]) {
            final RenderParagraph action = tester.renderObject(
              find.text(label),
            );
            expect(action.didExceedMaxLines, isFalse, reason: label);
          }
          await tester.pumpWidget(const SizedBox.shrink());
        },
      );
    }
  }
}
