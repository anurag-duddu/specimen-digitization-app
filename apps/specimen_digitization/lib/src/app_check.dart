import 'package:firebase_app_check/firebase_app_check.dart';
import 'connection_config.dart';

Future<void> activateProductionAppCheck(
  ConnectionConfig config, {
  required bool web,
  Future<void> Function({WebProvider? providerWeb})? activate,
}) async {
  config.validate(web: web);
  await (activate ?? FirebaseAppCheck.instance.activate)(
    providerWeb: web ? ReCaptchaEnterpriseProvider(config.siteKey) : null,
  );
}
