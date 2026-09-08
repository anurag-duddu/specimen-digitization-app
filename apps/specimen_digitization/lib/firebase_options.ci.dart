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

    return switch (defaultTargetPlatform) {
      TargetPlatform.android => android,
      TargetPlatform.iOS => ios,
      _ => throw UnsupportedError(
        'The CI Firebase placeholder supports Web, Android, and iOS only.',
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
}
