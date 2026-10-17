// The platform gate (10 section 8, `no_platform_branching`).
//
// CLAUDE.md: layout decisions use window size, never platform or device type.
// 09 section 2 principle 5 draws the line the other way round too: behaviour
// may follow the platform (scroll physics, back gestures, page transitions,
// haptics, pickers), identity may not. The shell broke that until 2026-10-17,
// drawing one tab bar on iOS and another on Android from a
// `defaultTargetPlatform` switch, and no gate looked.
//
// So a platform check is a capability, and every file that makes one is named
// below with the checks it makes and why. A file not named may make none, and a
// named file may make only the checks it is named with: the web flag in
// `main.dart` is not a licence to branch on iOS there.
//
// Counted, in code only (comments and strings are masked): `kIsWeb`,
// `defaultTargetPlatform`, `Theme.of(context).platform` (counted with it, as
// the same question asked through the theme), `TargetPlatform.<value>`,
// `Platform.is<OS>` and `Platform.operatingSystem` from `dart:io`, and
// `debugDefaultTargetPlatformOverride`, which belongs in tests alone.

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';

/// A file allowed to ask which platform it runs on.
class PlatformCapability {
  /// Allows [path] the check kinds in [checks], for the reason [why].
  const PlatformCapability(this.path, this.checks, this.why);

  /// The file, relative to the application root.
  final String path;

  /// The kinds of check it may make, named as [platformCheckKind] names them.
  final Set<String> checks;

  /// One line: the capability that differs by platform.
  final String why;
}

/// The check kinds, by the name a finding reports.
const String webFlag = 'kIsWeb';
const String targetPlatform = 'defaultTargetPlatform';
const String targetPlatformValue = 'TargetPlatform';
const String ioPlatform = 'Platform';
const String platformOverride = 'debugDefaultTargetPlatformOverride';

/// Every file allowed a platform check. Sorted by path.
///
/// Nine come from the inventory of 2026-10-17. Three more were in the tree and
/// are behaviour 09 section 2 principle 5 gives the platform: the iOS page
/// transition, pull to refresh, and the transitions map, which is keyed by
/// platform but gives every platform the same builder.
const List<PlatformCapability> platformCapabilities = <PlatformCapability>[
  PlatformCapability(
    'lib/firebase_options.ci.dart',
    <String>{webFlag, targetPlatform, targetPlatformValue},
    'the committed stand-in for the generated options, which pick a Firebase '
        'app per platform',
  ),
  PlatformCapability(
    'lib/main.dart',
    <String>{webFlag},
    'startup hands the web flag to configuration, the session and App Check, '
        'which are set up differently in a browser',
  ),
  PlatformCapability(
    'lib/src/app/app_router.dart',
    <String>{targetPlatform, targetPlatformValue},
    'the phone iOS push takes the platform page transition (04 row 18; 09 '
        'section 2 principle 5)',
  ),
  PlatformCapability(
    'lib/src/auth.dart',
    <String>{webFlag, targetPlatform, targetPlatformValue},
    'a sign-in link names the Android package or iOS bundle that opens it',
  ),
  PlatformCapability(
    'lib/src/capture/capture_camera.dart',
    <String>{webFlag},
    'camera_web has no image stream and no focus point',
  ),
  PlatformCapability(
    'lib/src/email_link_source_factory_io.dart',
    <String>{ioPlatform},
    'incoming app links exist only on Android and iOS',
  ),
  PlatformCapability(
    'lib/src/intake.dart',
    <String>{webFlag, targetPlatform, targetPlatformValue},
    'the native camera exists on Android and iOS, and only Android hands back '
        'a photo lost when the system closed the app',
  ),
  PlatformCapability(
    'lib/src/magic_link_screen.dart',
    <String>{webFlag, targetPlatform, targetPlatformValue},
    'the paste field is a debug-only aid for the opted-in iPhone demo',
  ),
  PlatformCapability(
    'lib/src/screens/queue/queue_screen.dart',
    <String>{webFlag, targetPlatform, targetPlatformValue},
    'pull to refresh is iOS and Android; in a browser it fights the '
        "browser's own (04 row 21)",
  ),
  PlatformCapability(
    'lib/src/screens/workbench/readings_panel.dart',
    <String>{webFlag},
    'a reparented web semantics input loses focus, so focus is parked first',
  ),
  PlatformCapability(
    'lib/src/theme/app_theme.dart',
    <String>{targetPlatformValue},
    'PageTransitionsTheme is keyed by platform; every key gets the same '
        'in-place builder',
  ),
  PlatformCapability('lib/src/theme/motion.dart', <String>{
    webFlag,
    targetPlatform,
    targetPlatformValue,
  }, 'system haptics reach iOS and Android only'),
];

/// The generated options `flutterfire configure` writes. It is gitignored and
/// never committed (CLAUDE.md), and CI writes it before testing, so the gate
/// skips it; its committed stand-in is named above.
const String generatedOptions = 'lib/firebase_options.dart';

final RegExp _platformCheck = RegExp(
  r'\b(?:kIsWeb|defaultTargetPlatform|debugDefaultTargetPlatformOverride)\b'
  r'|\bTheme\.of\(\s*\w+\s*\)\s*\.platform\b'
  r'|\bTargetPlatform\.\w+'
  r'|\bPlatform\.(?:is\w+|operatingSystem\w*)',
);

/// The kind a matched check reports under.
String platformCheckKind(String match) {
  if (match.startsWith('TargetPlatform.')) return targetPlatformValue;
  if (match.startsWith('Theme.')) return targetPlatform;
  if (match.startsWith('Platform.')) return ioPlatform;
  return match;
}

/// The kinds of platform check [source] makes in code, each once, sorted.
List<String> platformChecksIn(String source) => <String>{
  for (final RegExpMatch m in _platformCheck.allMatches(maskProse(source)))
    platformCheckKind(m.group(0)!),
}.toList()..sort();

/// Every file under `lib/` of the application at [base] that makes a platform
/// check, with the kinds it makes.
Map<String, List<String>> platformCensus({String base = '.'}) {
  final Map<String, List<String>> found = <String, List<String>>{};
  for (final GateSource source in libSources(base: base)) {
    if (source.path == generatedOptions) continue;
    final List<String> checks = platformChecksIn(source.text);
    if (checks.isNotEmpty) found[source.path] = checks;
  }
  return found;
}

/// What the gate objects to in [census]: a check in a file with no capability,
/// or a kind of check its capability does not name.
List<String> platformViolations(Map<String, List<String>> census) {
  final Map<String, PlatformCapability> allowed = <String, PlatformCapability>{
    for (final PlatformCapability c in platformCapabilities) c.path: c,
  };
  final List<String> found = <String>[];
  census.forEach((String path, List<String> checks) {
    final Set<String> may = allowed[path]?.checks ?? const <String>{};
    final List<String> extra = <String>[
      for (final String check in checks)
        if (!may.contains(check)) check,
    ];
    if (extra.isNotEmpty) found.add('$path: ${extra.join(', ')}');
  });
  return found;
}

void main() {
  test('the scanner names each kind of check and skips prose', () {
    expect(platformChecksIn('if (kIsWeb) return;'), <String>[webFlag]);
    expect(
      platformChecksIn('defaultTargetPlatform == TargetPlatform.iOS'),
      <String>[targetPlatformValue, targetPlatform],
    );
    expect(platformChecksIn('Platform.isAndroid || Platform.isIOS'), <String>[
      ioPlatform,
    ]);
    expect(platformChecksIn('Platform.operatingSystem'), <String>[ioPlatform]);
    expect(
      platformChecksIn("Theme.of(context).platform.name == 'iOS'"),
      <String>[targetPlatform],
    );
    expect(
      platformChecksIn('debugDefaultTargetPlatformOverride = null;'),
      <String>[platformOverride],
    );

    // A parameter typed `TargetPlatform` is a seam, not a check; prose and
    // strings are not code.
    expect(platformChecksIn('void f({TargetPlatform? platform}) {}'), isEmpty);
    expect(platformChecksIn('/// Production always uses [kIsWeb].'), isEmpty);
    expect(platformChecksIn("label('TargetPlatform.iOS')"), isEmpty);
  });

  test('a planted platform check fails the gate', () {
    // The same census and verdict the gate runs, over a temporary application:
    // a shell that forks its bar by platform, `main.dart` reaching past its
    // web flag, a `dart:io` check in a widget, and the generated options,
    // which are skipped.
    final String base = plantedApplication(<String, String>{
      'lib/main.dart':
          'final bool web = kIsWeb;\n'
          'final bool apple = defaultTargetPlatform == TargetPlatform.iOS;\n',
      'lib/firebase_options.dart':
          'final Object o = switch (defaultTargetPlatform) { _ => 0 };\n',
      'lib/src/app/shell.dart':
          'Widget bar() => defaultTargetPlatform == TargetPlatform.iOS\n'
          '    ? const A() : const B();\n',
      'lib/src/widgets/row.dart': 'final bool phone = Platform.isIOS;\n',
    });
    expect(platformViolations(platformCensus(base: base)), <String>[
      'lib/main.dart: $targetPlatformValue, $targetPlatform',
      'lib/src/app/shell.dart: $targetPlatformValue, $targetPlatform',
      'lib/src/widgets/row.dart: $ioPlatform',
    ]);
  });

  test('no file branches on the platform without a named capability', () {
    final List<String> violations = platformViolations(platformCensus());
    expect(
      violations,
      isEmpty,
      reason:
          'decide layout and appearance by window size (LayoutBuilder, '
          'MediaQuery.sizeOf, WindowClass), never by platform. A capability '
          'that really differs by platform needs the owner to approve a new '
          'entry in platformCapabilities:\n${violations.join('\n')}',
    );
  });

  test('every capability is a statement about today', () {
    // A file that stops making a check comes off, or loses that kind, so the
    // next reader sees only live reasons.
    final Map<String, List<String>> census = platformCensus();
    for (final PlatformCapability capability in platformCapabilities) {
      expect(
        census[capability.path]?.toSet() ?? const <String>{},
        capability.checks,
        reason:
            '${capability.path} is allowed ${capability.checks.join(', ')} '
            '(${capability.why}); make the entry match what the file checks',
      );
    }
  });

  test('the list is sorted and names each file once', () {
    final List<String> paths = <String>[
      for (final PlatformCapability c in platformCapabilities) c.path,
    ];
    expect(paths, <String>[...paths]..sort());
    expect(paths.toSet().length, paths.length);
  });
}
