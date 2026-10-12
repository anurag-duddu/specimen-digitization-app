import 'package:firebase_app_check/firebase_app_check.dart';
import 'connection_config.dart';

typedef AppCheckActivator =
    Future<void> Function({
      WebProvider? providerWeb,
      required AndroidAppCheckProvider providerAndroid,
      required AppleAppCheckProvider providerApple,
    });

Future<void> activateProductionAppCheck(
  ConnectionConfig config, {
  required bool web,
  bool debugBuild = false,
  bool androidDebugRequested = false,
  bool appleDebugRequested = false,
  AppCheckActivator? activate,
}) async {
  config.validate(web: web);
  final providerAndroid = !web && debugBuild && androidDebugRequested
      ? const AndroidDebugProvider()
      : const AndroidPlayIntegrityProvider();
  final providerApple = !web && debugBuild && appleDebugRequested
      ? const AppleDebugProvider()
      : const AppleDeviceCheckProvider();
  if (activate != null) {
    await activate(
      providerWeb: web ? ReCaptchaEnterpriseProvider(config.siteKey) : null,
      providerAndroid: providerAndroid,
      providerApple: providerApple,
    );
    return;
  }
  await FirebaseAppCheck.instance.activate(
    providerWeb: web ? ReCaptchaEnterpriseProvider(config.siteKey) : null,
    providerAndroid: providerAndroid,
    providerApple: providerApple,
  );
}
