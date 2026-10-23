import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app_check.dart';
import 'package:specimen_digitization/src/connection_config.dart';

const configured = ConnectionConfig(
  apiUrl: 'https://specimen-api.example.test',
  siteKey: 'synthetic-enterprise-site-key',
);

void main() {
  test('configured website activates the registered Enterprise provider', () async {
    var activations = 0;
    await activateProductionAppCheck(
      configured,
      web: true,
      activate:
          ({
            providerWeb,
            required providerAndroid,
            required providerApple,
          }) async {
            activations++;
            // The locked FlutterFire web adapter dispatches on these real types.
            // A v3 provider would use the wrong attestation for our registration.
            expect(providerWeb, isA<ReCaptchaEnterpriseProvider>());
            expect(providerWeb!.siteKey, configured.siteKey);
            expect(providerAndroid, isA<AndroidPlayIntegrityProvider>());
            expect(providerApple, isA<AppleDeviceCheckProvider>());
          },
    );
    expect(activations, 1);
  });

  test(
    'native activation preserves default providers without a web key',
    () async {
      var activations = 0;
      await activateProductionAppCheck(
        ConnectionConfig(apiUrl: configured.apiUrl, siteKey: ''),
        web: false,
        activate:
            ({
              providerWeb,
              required providerAndroid,
              required providerApple,
            }) async {
              activations++;
              expect(providerWeb, isNull);
              expect(providerAndroid, isA<AndroidPlayIntegrityProvider>());
              expect(providerApple, isA<AppleDeviceCheckProvider>());
            },
      );
      expect(activations, 1);
    },
  );

  test('invalid live configuration cannot reach provider activation', () async {
    var activations = 0;
    for (final config in [
      ConnectionConfig(apiUrl: configured.apiUrl, siteKey: ''),
      ConnectionConfig(apiUrl: configured.apiUrl, siteKey: '  '),
      ConnectionConfig(apiUrl: 'http://localhost', siteKey: configured.siteKey),
      ConnectionConfig(
        apiUrl: configured.apiUrl,
        siteKey: configured.siteKey,
        authEmulatorHost: 'localhost:9099',
      ),
    ]) {
      await expectLater(
        activateProductionAppCheck(
          config,
          web: true,
          activate:
              ({
                providerWeb,
                required providerAndroid,
                required providerApple,
              }) async => activations++,
        ),
        throwsFormatException,
      );
    }
    expect(activations, 0);
  });

  test('activation failure is propagated without fallback or retry', () async {
    var activations = 0;
    final failure = FirebaseException(
      plugin: 'firebase_app_check',
      code: 'app-check/invalid-configuration',
    );
    await expectLater(
      activateProductionAppCheck(
        configured,
        web: true,
        activate:
            ({
              providerWeb,
              required providerAndroid,
              required providerApple,
            }) async {
              activations++;
              throw failure;
            },
      ),
      throwsA(same(failure)),
    );
    expect(activations, 1);
  });

  test(
    'explicit native debug build uses only Android debug provider',
    () async {
      await activateProductionAppCheck(
        ConnectionConfig(apiUrl: configured.apiUrl, siteKey: ''),
        web: false,
        debugBuild: true,
        androidDebugRequested: true,
        activate:
            ({
              providerWeb,
              required providerAndroid,
              required providerApple,
            }) async {
              expect(providerWeb, isNull);
              expect(providerAndroid, isA<AndroidDebugProvider>());
              expect(providerApple, isA<AppleDeviceCheckProvider>());
            },
      );
    },
  );

  test('explicit native debug build uses only Apple debug provider', () async {
    await activateProductionAppCheck(
      ConnectionConfig(apiUrl: configured.apiUrl, siteKey: ''),
      web: false,
      debugBuild: true,
      appleDebugRequested: true,
      activate:
          ({
            providerWeb,
            required providerAndroid,
            required providerApple,
          }) async {
            expect(providerWeb, isNull);
            expect(providerAndroid, isA<AndroidPlayIntegrityProvider>());
            expect(providerApple, isA<AppleDebugProvider>());
          },
    );
  });

  test('Android and Apple debug requests are independent', () async {
    await activateProductionAppCheck(
      ConnectionConfig(apiUrl: configured.apiUrl, siteKey: ''),
      web: false,
      debugBuild: true,
      androidDebugRequested: true,
      appleDebugRequested: true,
      activate:
          ({
            providerWeb,
            required providerAndroid,
            required providerApple,
          }) async {
            expect(providerWeb, isNull);
            expect(providerAndroid, isA<AndroidDebugProvider>());
            expect(providerApple, isA<AppleDebugProvider>());
          },
    );
  });

  test('release, profile, and web builds ignore debug requests', () async {
    for (final values in [
      (name: 'release', web: false, debugBuild: false, profileBuild: false),
      (name: 'profile', web: false, debugBuild: false, profileBuild: true),
      (name: 'web debug', web: true, debugBuild: true, profileBuild: false),
    ]) {
      await activateProductionAppCheck(
        configured,
        web: values.web,
        debugBuild: values.debugBuild,
        profileBuild: values.profileBuild,
        androidDebugRequested: true,
        appleDebugRequested: true,
        activate:
            ({
              providerWeb,
              required providerAndroid,
              required providerApple,
            }) async {
              expect(
                providerAndroid,
                isA<AndroidPlayIntegrityProvider>(),
                reason: values.name,
              );
              expect(
                providerApple,
                isA<AppleDeviceCheckProvider>(),
                reason: values.name,
              );
              expect(
                providerWeb,
                values.web ? isA<ReCaptchaEnterpriseProvider>() : isNull,
                reason: values.name,
              );
            },
      );
    }
  });

  test('Apple Profile testing requires its separate opt-in', () async {
    for (final values in [
      (web: false, debugBuild: false, profileBuild: true, enabled: true),
      (web: false, debugBuild: false, profileBuild: false, enabled: false),
      (web: false, debugBuild: true, profileBuild: false, enabled: false),
      (web: true, debugBuild: false, profileBuild: true, enabled: false),
    ]) {
      await activateProductionAppCheck(
        configured,
        web: values.web,
        debugBuild: values.debugBuild,
        profileBuild: values.profileBuild,
        appleProfileDebugRequested: true,
        activate:
            ({
              providerWeb,
              required providerAndroid,
              required providerApple,
            }) async {
              expect(providerAndroid, isA<AndroidPlayIntegrityProvider>());
              expect(
                providerApple,
                values.enabled
                    ? isA<AppleDebugProvider>()
                    : isA<AppleDeviceCheckProvider>(),
              );
              expect(
                providerWeb,
                values.web ? isA<ReCaptchaEnterpriseProvider>() : isNull,
              );
            },
      );
    }
  });

  test(
    'native debug build keeps production providers unless requested',
    () async {
      await activateProductionAppCheck(
        ConnectionConfig(apiUrl: configured.apiUrl, siteKey: ''),
        web: false,
        debugBuild: true,
        activate:
            ({
              providerWeb,
              required providerAndroid,
              required providerApple,
            }) async {
              expect(providerWeb, isNull);
              expect(providerAndroid, isA<AndroidPlayIntegrityProvider>());
              expect(providerApple, isA<AppleDeviceCheckProvider>());
            },
      );
    },
  );
}
