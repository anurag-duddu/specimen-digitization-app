// The platform gate (10 section 8, `no_platform_branching`).
//
// CLAUDE.md: layout decisions use window size, never platform or device type.
// 09 section 2 principle 5 draws the line the other way round too: behaviour
// may follow the platform (scroll physics, back gestures, page transitions,
// haptics, pickers), identity may not. The shell broke that until 2026-10-17,
// drawing one tab bar on iOS and another on Android from a
// `defaultTargetPlatform` switch, and no gate looked.
//
// So a platform check is a capability, and each one is named by the
// declaration it sits in, with how many checks of each kind it makes and where
// the declaration is read. A declaration not named may make none; a named one
// may make no more than it is named with; and its value may be read only where
// it is read today, because a capability that hands its answer to a widget as
// a boolean would otherwise carry the platform out of the list with no
// platform token. A fact passed as an argument is tracked to the call, not into
// the callee: `web: kIsWeb` in `main` is counted, what the callee does with
// `web` is review's to judge.
//
// Counted, in code only (comments and strings are not code, interpolations
// are): `kIsWeb`, `defaultTargetPlatform`, `TargetPlatform` (as a type or a
// value), `Platform` from `dart:io`, `Theme.of(context).platform` and
// `debugDefaultTargetPlatformOverride`, which belongs in tests alone.

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';
import 'platform_scan.dart';

/// Every declaration allowed a platform check. Sorted by path, then site.
///
/// The brief of 2026-10-17 named nine files; their declarations are below.
/// Three more files make checks: `app_router.dart` (the iOS page transition,
/// 04 row 18), `queue_screen.dart` (pull to refresh on iOS and Android, 04
/// row 21) and `app_theme.dart` (`PageTransitionsTheme` is keyed by platform
/// and gives every key the same builder). The owner approved all three, and
/// the skip of the generated options below, on 2026-10-17; each entry carries
/// the sign-off.
const List<PlatformCapability> platformCapabilities = <PlatformCapability>[
  PlatformCapability(
    'lib/firebase_options.ci.dart',
    '<directives>',
    <String, int>{webFlag: 1, targetPlatform: 1, targetPlatformType: 1},
    'imports the three names the stand-in options switch on',
  ),
  PlatformCapability(
    'lib/firebase_options.ci.dart',
    'DefaultFirebaseOptions.currentPlatform',
    <String, int>{webFlag: 1, targetPlatform: 1, targetPlatformType: 2},
    'the committed stand-in for the generated options, which pick a Firebase '
        'app per platform',
    readers: <String, int>{'lib/main.dart main': 1},
  ),
  PlatformCapability(
    'lib/main.dart',
    'main',
    <String, int>{webFlag: 3},
    'startup hands the web flag to configuration, the session and App Check, '
        'which are set up differently in a browser',
  ),
  // owner-approved: 2026-10-17 "Yes approved" (the owner, in the guard-gates
  // Claude Code session, answering whether to approve the four platform
  // exemptions on PR #358)
  PlatformCapability(
    'lib/src/app/app_router.dart',
    '_WorkspacePageRoute.buildTransitions',
    <String, int>{targetPlatform: 1, targetPlatformType: 1},
    'the phone iOS push takes the platform page transition (04 row 18)',
  ),
  // owner-approved: 2026-10-17 "Yes approved" (the owner, in the guard-gates
  // Claude Code session, answering whether to approve the four platform
  // exemptions on PR #358)
  PlatformCapability(
    'lib/src/app/app_router.dart',
    'buildAppRouter',
    <String, int>{targetPlatform: 2, targetPlatformType: 2},
    'the iOS page transition takes the platform duration (04 row 18)',
    readers: <String, int>{
      'lib/main.dart _SpecimenDigitizationAppState.initState': 1,
    },
  ),
  PlatformCapability(
    'lib/src/auth.dart',
    'emailLinkActionCodeSettings',
    <String, int>{webFlag: 1, targetPlatform: 1, targetPlatformType: 4},
    'a sign-in link names the Android package or iOS bundle that opens it',
    readers: <String, int>{
      'lib/src/auth.dart FirebaseSession.sendSignInLink': 1,
    },
  ),
  PlatformCapability(
    'lib/src/capture/capture_camera.dart',
    '<directives>',
    <String, int>{webFlag: 1},
    'imports the web flag the camera checks',
  ),
  PlatformCapability(
    'lib/src/capture/capture_camera.dart',
    'PlatformCaptureCamera._startStream',
    <String, int>{webFlag: 1},
    'camera_web has no image stream',
    readers: <String, int>{
      'lib/src/capture/capture_camera.dart PlatformCaptureCamera.capture': 1,
      'lib/src/capture/capture_camera.dart PlatformCaptureCamera.start': 1,
    },
  ),
  PlatformCapability(
    'lib/src/capture/capture_camera.dart',
    'PlatformCaptureCamera.focusAt',
    <String, int>{webFlag: 1},
    'camera_web has no focus point',
    readers: <String, int>{
      'lib/src/capture/capture_screen.dart _CaptureScreenState._focus': 1,
    },
  ),
  PlatformCapability(
    'lib/src/email_link_source_factory_io.dart',
    'createNativeEmailLinkSource',
    <String, int>{ioPlatform: 2},
    'incoming app links exist only on Android and iOS',
    readers: <String, int>{'lib/main.dart main': 1},
  ),
  PlatformCapability(
    'lib/src/intake.dart',
    '_IntakeScreenState._isWeb',
    <String, int>{webFlag: 1},
    'the browser intake takes dropped files',
    readers: <String, int>{
      'lib/src/intake.dart _IntakeScreenState._captureCard': 2,
      'lib/src/intake.dart _IntakeScreenState._nativeCameraAvailable': 1,
      'lib/src/intake.dart _IntakeScreenState._recoverCamera': 1,
      'lib/src/intake.dart _IntakeScreenState.build': 1,
    },
  ),
  PlatformCapability(
    'lib/src/intake.dart',
    '_IntakeScreenState._nativeCameraAvailable',
    <String, int>{webFlag: 1, targetPlatform: 2, targetPlatformType: 2},
    'the native camera exists on Android and iOS',
    readers: <String, int>{
      'lib/src/intake.dart _IntakeScreenState._capture': 1,
      'lib/src/intake.dart _IntakeScreenState._openCapture': 1,
    },
  ),
  PlatformCapability(
    'lib/src/intake.dart',
    '_IntakeScreenState._recoverCamera',
    <String, int>{targetPlatform: 1, targetPlatformType: 1},
    'only Android hands back a photo lost when the system closed the app',
    readers: <String, int>{
      'lib/src/intake.dart _IntakeScreenState.initState': 1,
    },
  ),
  PlatformCapability(
    'lib/src/magic_link_screen.dart',
    'MagicLinkSignInScreen.platform',
    <String, int>{targetPlatformType: 1},
    'the test seam for the iPhone demo paste field',
    readers: <String, int>{
      'lib/src/magic_link_screen.dart _MagicLinkSignInScreenState.build': 1,
    },
  ),
  PlatformCapability(
    'lib/src/magic_link_screen.dart',
    'applePersonalDemoPasteEnabled',
    <String, int>{webFlag: 1, targetPlatform: 1, targetPlatformType: 2},
    'the paste field is a debug-only aid for the opted-in iPhone demo',
    readers: <String, int>{
      'lib/src/magic_link_screen.dart _MagicLinkSignInScreenState.build': 1,
    },
  ),
  // owner-approved: 2026-10-17 "Yes approved" (the owner, in the guard-gates
  // Claude Code session, answering whether to approve the four platform
  // exemptions on PR #358)
  PlatformCapability(
    'lib/src/screens/queue/queue_screen.dart',
    '_QueuePaneState._pullToRefresh',
    <String, int>{webFlag: 1, targetPlatform: 2, targetPlatformType: 2},
    'pull to refresh is iOS and Android; in a browser it fights the '
        "browser's own (04 row 21)",
    readers: <String, int>{
      'lib/src/screens/queue/queue_screen.dart _QueuePaneState._list': 1,
    },
  ),
  PlatformCapability(
    'lib/src/screens/workbench/readings_panel.dart',
    '_WorkbenchReadingsState.didUpdateWidget',
    <String, int>{webFlag: 1},
    'a reparented web semantics input loses focus, so focus is parked first',
  ),
  // owner-approved: 2026-10-17 "Yes approved" (the owner, in the guard-gates
  // Claude Code session, answering whether to approve the four platform
  // exemptions on PR #358)
  PlatformCapability(
    'lib/src/theme/app_theme.dart',
    'specimenPageTransitions',
    <String, int>{targetPlatformType: 7},
    'PageTransitionsTheme is keyed by platform; every key gets the same '
        'in-place builder',
    readers: <String, int>{'lib/src/theme/app_theme.dart AppTheme._build': 1},
  ),
  PlatformCapability(
    'lib/src/theme/motion.dart',
    'SpecimenHaptics.available',
    <String, int>{webFlag: 1, targetPlatform: 2, targetPlatformType: 2},
    'system haptics reach iOS and Android only',
    readers: <String, int>{
      'lib/src/theme/motion.dart SpecimenHaptics.batchComplete': 1,
      'lib/src/theme/motion.dart SpecimenHaptics.decisionLanded': 1,
      'lib/src/theme/motion.dart SpecimenHaptics.selectionChanged': 1,
    },
  ),
];

/// The generated options `flutterfire configure` writes. It is gitignored and
/// never committed (CLAUDE.md); CI writes it before testing, from the
/// committed stand-in on a pull request and from the production secret on
/// main, so its contents are not this repository's to count. The gate skips
/// it; the stand-in is counted above.
///
/// owner-approved: 2026-10-17 "Yes approved" (the owner, in the guard-gates
/// Claude Code session, answering whether to approve the four platform
/// exemptions on PR #358)
const String generatedOptions = 'lib/firebase_options.dart';

/// Every platform check under `lib/` of the application at [base], by file.
Map<String, List<PlatformCheck>> platformCensus({String base = '.'}) {
  final Map<String, List<PlatformCheck>> found =
      <String, List<PlatformCheck>>{};
  for (final GateSource source in libSources(base: base)) {
    if (source.path == generatedOptions) continue;
    final List<PlatformCheck> checks = platformChecksIn(source);
    if (checks.isNotEmpty) found[source.path] = checks;
  }
  return found;
}

/// The checks of [census] counted by `path site`, then by kind.
Map<String, Map<String, int>> checksBySite(
  Map<String, List<PlatformCheck>> census,
) {
  final Map<String, Map<String, int>> found = <String, Map<String, int>>{};
  census.forEach((String path, List<PlatformCheck> checks) {
    for (final PlatformCheck c in checks) {
      final Map<String, int> kinds = found.putIfAbsent(
        '$path ${c.site}',
        () => <String, int>{},
      );
      kinds[c.kind] = (kinds[c.kind] ?? 0) + 1;
    }
  });
  return found;
}

/// What the gate objects to: a check in a declaration with no capability or
/// past its count, and a capability read somewhere new or more often.
List<String> platformViolations({
  required Map<String, List<PlatformCheck>> census,
  required Map<String, Map<String, int>> readers,
  List<PlatformCapability> capabilities = platformCapabilities,
}) {
  final Map<String, PlatformCapability> allowed = <String, PlatformCapability>{
    for (final PlatformCapability c in capabilities) '${c.path} ${c.site}': c,
  };
  final List<String> found = <String>[];
  checksBySite(census).forEach((String site, Map<String, int> kinds) {
    final PlatformCapability? capability = allowed[site];
    kinds.forEach((String kind, int count) {
      final int may = capability?.checks[kind] ?? 0;
      if (count > may) found.add('$site: $count $kind, allowed $may');
    });
  });
  readers.forEach((String site, Map<String, int> reads) {
    final PlatformCapability? capability = allowed[site];
    if (capability == null) return;
    reads.forEach((String reader, int count) {
      final int may = capability.readers[reader] ?? 0;
      if (count > may) {
        found.add('$site is read $count times by $reader, allowed $may');
      }
    });
  });
  return found;
}

void main() {
  List<String> kindsOf(String text) => <String>[
    for (final PlatformCheck c in platformChecksIn(GateSource('x.dart', text)))
      c.kind,
  ];

  test('the scanner reads each kind of check, whatever the trivia', () {
    expect(kindsOf('final w = kIsWeb;'), <String>[webFlag]);
    expect(kindsOf('final w = foundation.kIsWeb;'), <String>[webFlag]);
    expect(
      kindsOf('final a = defaultTargetPlatform == TargetPlatform.iOS;'),
      <String>[targetPlatform, targetPlatformType],
    );
    expect(kindsOf('final a = TargetPlatform /* why */ .iOS;'), <String>[
      targetPlatformType,
    ]);
    expect(kindsOf('final a = Platform /* capability? */ .isIOS;'), <String>[
      ioPlatform,
    ]);
    expect(kindsOf('final a = io.Platform.operatingSystem;'), <String>[
      ioPlatform,
    ]);
    expect(
      kindsOf("final a = Theme.of(context).platform.name == 'iOS';"),
      <String>[themePlatform],
    );
    expect(kindsOf("final s = '\${defaultTargetPlatform.name}';"), <String>[
      targetPlatform,
    ]);
    expect(kindsOf('void f(TargetPlatform p) {}'), <String>[
      targetPlatformType,
    ]);
    expect(
      kindsOf('void f() { debugDefaultTargetPlatformOverride = null; }'),
      <String>[platformOverride],
    );

    // Prose and strings are not code.
    expect(
      kindsOf('/// Production always uses [kIsWeb].\nvoid f() {}'),
      isEmpty,
    );
    expect(kindsOf('// if (kIsWeb) return;\nvoid f() {}'), isEmpty);
    expect(kindsOf("final s = 'TargetPlatform.iOS';"), isEmpty);
  });

  test('a planted platform check fails the gate', () {
    // The same census and verdict the gate runs, over a temporary
    // application: a shell that forks its bar by platform, an appearance
    // branch added inside an allowed file, an allowed declaration reaching
    // past its counts, a forwarded predicate read by a widget, and the
    // generated options, which are skipped.
    const List<PlatformCapability> allowed = <PlatformCapability>[
      PlatformCapability(
        'lib/src/theme/motion.dart',
        'Haptics.available',
        <String, int>{webFlag: 1},
        'planted',
        readers: <String, int>{'lib/src/theme/motion.dart Haptics.buzz': 1},
      ),
    ];
    final String base = plantedApplication(<String, String>{
      'lib/firebase_options.dart':
          'final Object o = switch (defaultTargetPlatform) { _ => 0 };\n',
      'lib/src/app/shell.dart':
          'Widget bar() => defaultTargetPlatform == TargetPlatform.iOS\n'
          '    ? const A() : const B();\n',
      'lib/src/theme/motion.dart':
          'abstract final class Haptics {\n'
          '  static bool get available => !kIsWeb && !kIsWeb;\n'
          '  static void buzz() { if (available) go(); }\n'
          '  static Widget look() => kIsWeb ? const A() : const B();\n'
          '}\n',
      'lib/src/widgets/row.dart':
          'Widget row() => Haptics.available ? const A() : const B();\n',
    });
    expect(
      platformViolations(
        census: platformCensus(base: base),
        readers: readersOf(allowed, libSources(base: base)),
        capabilities: allowed,
      ),
      <String>[
        'lib/src/app/shell.dart bar: 1 defaultTargetPlatform, allowed 0',
        'lib/src/app/shell.dart bar: 1 TargetPlatform, allowed 0',
        'lib/src/theme/motion.dart Haptics.available: 2 kIsWeb, allowed 1',
        'lib/src/theme/motion.dart Haptics.look: 1 kIsWeb, allowed 0',
        'lib/src/theme/motion.dart Haptics.available is read 1 times by '
            'lib/src/widgets/row.dart row, allowed 0',
      ],
    );
  });

  test('no declaration branches on the platform past its capability', () {
    final List<String> violations = platformViolations(
      census: platformCensus(),
      readers: readersOf(platformCapabilities, libSources()),
    );
    expect(
      violations,
      isEmpty,
      reason:
          'decide layout and appearance by window size (LayoutBuilder, '
          'MediaQuery.sizeOf, WindowClass), never by platform. A capability '
          'that really differs by platform needs the owner to approve its '
          'entry in platformCapabilities:\n${violations.join('\n')}',
    );
  });

  test('every capability is a statement about today', () {
    // Counts and readers match the tree exactly, so a capability that stops
    // checking, or stops being read somewhere, says so, and the slack cannot
    // be spent later without a sign-off.
    final Map<String, Map<String, int>> checks = checksBySite(platformCensus());
    final Map<String, Map<String, int>> readers = readersOf(
      platformCapabilities,
      libSources(),
    );
    for (final PlatformCapability c in platformCapabilities) {
      final String site = '${c.path} ${c.site}';
      expect(checks[site] ?? const <String, int>{}, c.checks, reason: site);
      expect(readers[site] ?? const <String, int>{}, c.readers, reason: site);
    }
  });

  test('the list is sorted and names each declaration once', () {
    final List<String> sites = <String>[
      for (final PlatformCapability c in platformCapabilities)
        '${c.path} ${c.site}',
    ];
    expect(sites, <String>[...sites]..sort());
    expect(sites.toSet().length, sites.length);
  });
}
