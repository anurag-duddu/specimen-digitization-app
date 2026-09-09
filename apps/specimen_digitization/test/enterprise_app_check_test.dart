import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app_check.dart';
import 'package:specimen_digitization/src/connection_config.dart';

const configured = ConnectionConfig(
  apiUrl: 'https://specimen-api.example.test',
  siteKey: 'synthetic-enterprise-site-key',
);

void main() {
  test(
    'configured website activates the registered Enterprise provider',
    () async {
      var activations = 0;
      await activateProductionAppCheck(
        configured,
        web: true,
        activate: ({providerWeb}) async {
          activations++;
          // The locked FlutterFire web adapter dispatches on these real types.
          // A v3 provider would use the wrong attestation for our registration.
          expect(providerWeb, isA<ReCaptchaEnterpriseProvider>());
          expect(providerWeb!.siteKey, configured.siteKey);
        },
      );
      expect(activations, 1);
    },
  );

  test(
    'native activation preserves default providers without a web key',
    () async {
      var activations = 0;
      await activateProductionAppCheck(
        ConnectionConfig(apiUrl: configured.apiUrl, siteKey: ''),
        web: false,
        activate: ({providerWeb}) async {
          activations++;
          expect(providerWeb, isNull);
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
          activate: ({providerWeb}) async => activations++,
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
        activate: ({providerWeb}) async {
          activations++;
          throw failure;
        },
      ),
      throwsA(same(failure)),
    );
    expect(activations, 1);
  });
}
