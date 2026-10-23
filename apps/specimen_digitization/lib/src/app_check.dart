import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:flutter/foundation.dart';
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
  bool profileBuild = false,
  bool androidDebugRequested = false,
  bool appleDebugRequested = false,
  bool appleProfileDebugRequested = false,
  AppCheckActivator? activate,
}) async {
  config.validate(web: web);
  final providerAndroid = !web && debugBuild && androidDebugRequested
      ? const AndroidDebugProvider()
      : const AndroidPlayIntegrityProvider();
  // A separately opted-in Profile build can test a personal iPhone without
  // Flutter's JIT debugger. Release binaries always retain device attestation.
  final appleTestProvider =
      !kReleaseMode &&
      !web &&
      ((debugBuild && appleDebugRequested) ||
          (profileBuild && appleProfileDebugRequested));
  final providerApple = appleTestProvider
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
