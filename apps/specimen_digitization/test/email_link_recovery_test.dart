import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'login_options_test.dart' show pumpLogin, tapVisible;
import 'magic_link_controller_test.dart'
    show FakeLinkAccess, MemoryLinkStorage, nativeActionLink;

void main() {
  for (final invalid in [
    nativeActionLink.replaceFirst('https:', 'http:'),
    nativeActionLink.replaceFirst('firebaseapp.com/', 'firebaseapp.com:443/'),
    nativeActionLink.replaceFirst('https://', 'https://attacker@'),
    nativeActionLink.replaceFirst('mode=signIn', 'mode=resetPassword'),
    '$nativeActionLink&oobCode=duplicate',
    '$nativeActionLink#fragment',
    nativeActionLink.replaceFirst(
      'https%3A%2F%2Fspecimen-digitization.web.app%2F',
      'https%3A%2F%2Fevil.test%2F',
    ),
  ]) {
    test('copied action cannot relax strict validation: $invalid', () async {
      final access = FakeLinkAccess();
      final controller = MagicLinkController(
        access: access,
        browser: MemoryEmailLinkBrowser(),
        storage: MemoryLinkStorage(),
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(controller.acceptPastedLink(invalid), isFalse);
      expect(access.checked, isEmpty);
      expect(access.completed, isEmpty);
      expect(controller.message, isNot(contains('fixture-action-code')));
    });
  }

  testWidgets(
    'explicit paste completes for the recipient and clears the code',
    (tester) async {
      final access = FakeLinkAccess();
      final storage = MemoryLinkStorage();
      final controller = MagicLinkController(
        access: access,
        browser: MemoryEmailLinkBrowser(),
        storage: storage,
      );
      await controller.initialize();
      await controller.send('researcher@fieldmuseum.org');
      await pumpLogin(
        tester,
        MagicLinkSignInScreen(access: access, controller: controller),
      );
      expect(find.byType(UiField), findsNothing);
      await tapVisible(tester, 'Use email link');
      final field = find.widgetWithText(UiField, 'Paste the full sign-in link');
      await tester.enterText(field, nativeActionLink);
      await tapVisible(tester, 'Sign in');
      await tester.pumpAndSettle();
      expect(access.checked, [nativeActionLink]);
      expect(access.completed, [
        ('researcher@fieldmuseum.org', nativeActionLink),
      ]);
      expect(storage.value.email, isNull);
      expect(find.textContaining('fixture-action-code'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    },
  );

  testWidgets('foreign pasted link preserves recipient and offers a new link', (
    tester,
  ) async {
    final access = FakeLinkAccess();
    final controller = MagicLinkController(
      access: access,
      browser: MemoryEmailLinkBrowser(),
      storage: MemoryLinkStorage(),
    );
    await controller.initialize();
    await controller.send('researcher@fieldmuseum.org');
    await pumpLogin(
      tester,
      MagicLinkSignInScreen(access: access, controller: controller),
    );
    await tapVisible(tester, 'Use email link');
    await tester.enterText(
      find.byType(UiField),
      'https://evil.test/?oobCode=private-code',
    );
    await tapVisible(tester, 'Sign in');
    await tester.pumpAndSettle();
    expect(access.checked, isEmpty);
    expect(access.completed, isEmpty);
    expect(controller.email, 'researcher@fieldmuseum.org');
    expect(find.text('Resend link'), findsOneWidget);
    expect(find.textContaining('private-code'), findsNothing);
    expect(
      tester.widget<UiField>(find.byType(UiField)).controller!.text,
      isEmpty,
    );
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });
}
