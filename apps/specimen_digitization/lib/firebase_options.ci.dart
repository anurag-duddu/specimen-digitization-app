// Non-production Firebase configuration used only for credential-free CI
// analysis, tests, and pull-request builds. The deployment job restores the
// real FlutterFire-generated file from an encrypted GitHub Actions secret.

import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show TargetPlatform, defaultTargetPlatform, kIsWeb;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }

    // Desktop returns the same unconfigured placeholder as mobile CI. The
    // `:ci-placeholder` suffix keeps startup from calling Firebase.initializeApp.
    // Linux has no Firebase native plugin, so a real Linux app id would fail
    // at that call; Windows and macOS can take a production FlutterFire file.
    return switch (defaultTargetPlatform) {
      TargetPlatform.android => android,
      TargetPlatform.iOS => ios,
      TargetPlatform.linux => linux,
      TargetPlatform.macOS => macos,
      TargetPlatform.windows => windows,
      _ => throw UnsupportedError(
        'The CI Firebase placeholder supports Web, Android, iOS, Linux, macOS, and Windows only.',
      ),
    };
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'ci-placeholder', // pragma: allowlist secret
    appId: '1:000000000000:web:ci-placeholder',
    messagingSenderId: '000000000000',
    projectId: 'specimen-digitization',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'ci-placeholder', // pragma: allowlist secret
    appId: '1:000000000000:android:ci-placeholder',
    messagingSenderId: '000000000000',
    projectId: 'specimen-digitization',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'ci-placeholder', // pragma: allowlist secret
    appId: '1:000000000000:ios:ci-placeholder',
    messagingSenderId: '000000000000',
    projectId: 'specimen-digitization',
    iosBundleId: 'org.fieldmuseum.specimenDigitization',
  );

  static const FirebaseOptions macos = FirebaseOptions(
    apiKey: 'ci-placeholder', // pragma: allowlist secret
    appId: '1:000000000000:macos:ci-placeholder',
    messagingSenderId: '000000000000',
    projectId: 'specimen-digitization',
    iosBundleId: 'org.fieldmuseum.specimenDigitization',
  );

  static const FirebaseOptions windows = FirebaseOptions(
    apiKey: 'ci-placeholder', // pragma: allowlist secret
    appId: '1:000000000000:windows:ci-placeholder',
    messagingSenderId: '000000000000',
    projectId: 'specimen-digitization',
  );

  static const FirebaseOptions linux = FirebaseOptions(
    apiKey: 'ci-placeholder', // pragma: allowlist secret
    appId: '1:000000000000:linux:ci-placeholder',
    messagingSenderId: '000000000000',
    projectId: 'specimen-digitization',
  );
}
