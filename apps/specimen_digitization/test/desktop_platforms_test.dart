import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/firebase_options.dart';

void main() {
  test('project metadata keeps every supported platform', () {
    final String metadata = File('.metadata').readAsStringSync();
    for (final String platform in <String>[
      'android',
      'ios',
      'linux',
      'macos',
      'web',
      'windows',
    ]) {
      expect(
        metadata,
        contains('- platform: $platform\n'),
        reason: 'flutter create must not drop $platform from .metadata.',
      );
    }
  });

  test('desktop hosts keep the Field Museum application identity', () {
    expect(
      File('linux/CMakeLists.txt').readAsStringSync(),
      contains('set(APPLICATION_ID "org.fieldmuseum.specimen_digitization")'),
    );
    expect(
      File('macos/Runner/Configs/AppInfo.xcconfig').readAsStringSync(),
      contains(
        'PRODUCT_BUNDLE_IDENTIFIER = org.fieldmuseum.specimenDigitization',
      ),
    );
    expect(
      File('windows/runner/Runner.rc').readAsStringSync(),
      contains('VALUE "CompanyName", "org.fieldmuseum"'),
    );
  });

  test('macOS sandbox can reach the API and read chosen files', () {
    for (final String path in <String>[
      'macos/Runner/DebugProfile.entitlements',
      'macos/Runner/Release.entitlements',
    ]) {
      final String flat = File(
        path,
      ).readAsStringSync().replaceAll(RegExp(r'\s+'), ' ');
      expect(
        flat,
        contains('<key>com.apple.security.app-sandbox</key> <true/>'),
      );
      expect(
        flat,
        contains('<key>com.apple.security.network.client</key> <true/>'),
        reason:
            'A sandboxed macOS build cannot call the collection API without it.',
      );
      expect(
        flat,
        contains(
          '<key>com.apple.security.files.user-selected.read-write</key> <true/>',
        ),
        reason:
            'File selection and drop need access to files the operator chose.',
      );
    }
    expect(
      File(
        'macos/Runner/DebugProfile.entitlements',
      ).readAsStringSync().replaceAll(RegExp(r'\s+'), ' '),
      contains('<key>com.apple.security.network.server</key> <true/>'),
      reason: 'Debug builds still need the observatory port.',
    );
  });

  test('desktop plugin registrants match what each host can load', () {
    final String linuxPlugins = File(
      'linux/flutter/generated_plugin_registrant.cc',
    ).readAsStringSync();
    expect(linuxPlugins, contains('desktop_drop_plugin.h'));
    expect(
      linuxPlugins,
      contains('file_selector_linux/file_selector_plugin.h'),
    );
    expect(
      linuxPlugins,
      isNot(contains('firebase_')),
      reason: 'firebase_core has no Linux implementation.',
    );

    final String windowsPlugins = File(
      'windows/flutter/generated_plugin_registrant.cc',
    ).readAsStringSync();
    expect(windowsPlugins, contains('desktop_drop_plugin.h'));
    expect(windowsPlugins, contains('file_selector_windows.h'));
    expect(windowsPlugins, contains('firebase_core_plugin_c_api.h'));
    expect(windowsPlugins, contains('firebase_auth_plugin_c_api.h'));
    expect(windowsPlugins, contains('firebase_app_check_plugin_c_api.h'));

    final String macosPlugins = File(
      'macos/Flutter/GeneratedPluginRegistrant.swift',
    ).readAsStringSync();
    expect(macosPlugins, contains('import desktop_drop'));
    expect(macosPlugins, contains('import file_selector_macos'));
    expect(macosPlugins, contains('import firebase_core'));
    expect(macosPlugins, contains('import firebase_auth'));
    expect(macosPlugins, contains('import firebase_app_check'));
    expect(macosPlugins, contains('import google_sign_in_ios'));
    expect(macosPlugins, contains('import shared_preferences_foundation'));
  });

  test('CI Firebase options stay unconfigured on every desktop host', () {
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    const Map<TargetPlatform, String> hosts = <TargetPlatform, String>{
      TargetPlatform.linux: 'linux',
      TargetPlatform.macOS: 'macos',
      TargetPlatform.windows: 'windows',
      TargetPlatform.android: 'android',
      TargetPlatform.iOS: 'ios',
    };
    for (final MapEntry<TargetPlatform, String> host in hosts.entries) {
      debugDefaultTargetPlatformOverride = host.key;
      final options = DefaultFirebaseOptions.currentPlatform;
      expect(options.appId, '1:000000000000:${host.value}:ci-placeholder');
      expect(options.appId, endsWith(':ci-placeholder'));
      expect(options.projectId, 'specimen-digitization');
    }
    debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
    expect(
      DefaultFirebaseOptions.currentPlatform.iosBundleId,
      'org.fieldmuseum.specimenDigitization',
    );
  });
}
