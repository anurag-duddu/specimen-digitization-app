import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/magic_link.dart';

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
}
