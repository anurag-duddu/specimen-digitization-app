import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('iOS declares the Firebase Hosting universal-link entitlement', () {
    final String entitlements = File(
      'ios/Runner/Runner.entitlements',
    ).readAsStringSync();
    final String project = File(
      'ios/Runner.xcodeproj/project.pbxproj',
    ).readAsStringSync();

    expect(
      entitlements,
      contains('<key>com.apple.developer.associated-domains</key>'),
    );
    expect(
      entitlements,
      contains(
        '<string>applinks:specimen-digitization.firebaseapp.com</string>',
      ),
    );
    expect(entitlements, isNot(contains('specimen-digitization.web.app')));

    expect(
      RegExp(
        r'CODE_SIGN_ENTITLEMENTS = Runner/Runner\.entitlements;',
      ).allMatches(project).length,
      3,
      reason: 'Debug, Profile, and Release must sign with the entitlement.',
    );
  });
}
