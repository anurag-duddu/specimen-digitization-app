import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Android receives Firebase Hosting email links as App Links', () {
    final String manifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();

    final List<String> verifiedFilters = RegExp(
      r'<intent-filter\s+android:autoVerify="true"[^>]*>(.*?)</intent-filter>',
      dotAll: true,
    ).allMatches(manifest).map((match) => match.group(1)!).toList();

    expect(verifiedFilters, hasLength(1));
    final String filter = verifiedFilters.single;
    expect(filter, contains('android:name="android.intent.action.VIEW"'));
    expect(filter, contains('android:name="android.intent.category.DEFAULT"'));
    expect(
      filter,
      contains('android:name="android.intent.category.BROWSABLE"'),
    );
    expect(filter, contains('android:scheme="https"'));
    expect(
      filter,
      contains('android:host="specimen-digitization.firebaseapp.com"'),
    );
    expect(filter, contains('android:pathPrefix="/__/auth/links"'));
    expect(filter, isNot(contains('specimen-digitization.web.app')));
  });

  test('app_links exclusively owns Android deep-link delivery', () {
    final String manifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();

    expect(
      RegExp(
        r'<meta-data\s+android:name="flutter_deeplinking_enabled"\s+'
        r'android:value="false"\s*/>',
      ).allMatches(manifest),
      hasLength(1),
    );
  });
}
