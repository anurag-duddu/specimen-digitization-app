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
// are), in the application's `lib/` and every package under `packages/`:
// `kIsWeb`, `kIsWasm`, `defaultTargetPlatform`, `TargetPlatform` (as a type
// or a value), `Platform` from `dart:io`, `Theme.of(context).platform` and
// the `.platform` of a theme held in a variable (initialised from
// `Theme.of`, typed `ThemeData`, or named for a theme), a scroll behaviour's
// `getPlatform`, `identical(0, 0.0)` and `0.0 is int`, which are true only on
// the web, a conditional import or export (`if (dart.library.io)`), which
// picks code by platform, and `debugDefaultTargetPlatformOverride`, which
// belongs in tests alone. A read of a capability counts in its own library's
// files and in every file that imports it, directly, through an export or
// a part's library, with or without a prefix.

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';
import 'platform_scan.dart';

/// Every declaration allowed a platform check. Sorted by path, then site.
///
/// The brief of 2026-10-17 named nine files; their declarations are below.
/// Three more files make checks, all behaviour 09 section 2 principle 5 gives
/// the platform: `app_router.dart` (the iOS page transition, 04 row 18),
/// `queue_screen.dart` (pull to refresh in the iOS and Android apps, 04 row
/// 21) and `app_theme.dart` (`PageTransitionsTheme` is keyed by platform and
/// gives every key the same builder). The owner approved all three, and the
/// skip of the generated options below, on 2026-10-17; each entry carries
/// the owner's words.
const List<PlatformCapability> platformCapabilities = <PlatformCapability>[
  PlatformCapability(
    'lib/firebase_options.ci.dart',
    '<directives>',
    <String, int>{webFlag: 1, targetPlatform: 1, targetPlatformType: 1},
    'imports the three names the stand-in options switch on',
  ),
  // owner-approved: 2026-10-17 "I see, linux windows, mac should all work"
  // (owner, cloud agent session bc-78e1a1fb-1509-4934-bb1a-5a6dded53c17,
  // after the Linux desktop launch, directing that Linux, Windows and macOS
  // are part of the client)
  PlatformCapability(
    'lib/firebase_options.ci.dart',
    'DefaultFirebaseOptions.currentPlatform',
    <String, int>{webFlag: 1, targetPlatform: 1, targetPlatformType: 5},
    'the committed stand-in for the generated options, which pick a Firebase '
        'app per platform including Linux, macOS and Windows',
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
  // owner-approved: 2026-10-17 "Page transitions (Recommended), Firebase
  // config file (Recommended)" (the owner's selection in the coordinating
  // Claude Code session, asked which existing platform checks to approve)
  PlatformCapability(
    'lib/src/app/app_router.dart',
    '_WorkspacePageRoute.buildTransitions',
    <String, int>{targetPlatform: 1, targetPlatformType: 1},
    'the phone iOS push takes the platform page transition (04 row 18)',
  ),
  // owner-approved: 2026-10-17 "Yes approved" (the owner, in the guard-gates
  // Claude Code session, answering whether to approve the four platform
  // exemptions on PR #358)
  // owner-approved: 2026-10-17 "Page transitions (Recommended), Firebase
  // config file (Recommended)" (the owner's selection in the coordinating
  // Claude Code session, asked which existing platform checks to approve)
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
    'lib/src/email_link_browser.dart',
    '<directives>',
    <String, int>{conditionalImport: 1},
    'the email link reads the browser address in a browser build only',
  ),
  PlatformCapability(
    'lib/src/email_link_source_factory.dart',
    '<directives>',
    <String, int>{conditionalImport: 1},
    'picks the io half, where incoming app links exist',
  ),
  PlatformCapability(
    'lib/src/email_link_source_factory_io.dart',
    'createNativeEmailLinkSource',
    <String, int>{ioPlatform: 2},
    'incoming app links exist only on Android and iOS',
    readers: <String, int>{'lib/main.dart main': 1},
  ),
  // owner-approved: 2026-10-17 "Google sign-in may be offered differently by
  // platform (always on web; on iPhone and Android when it's set up)."
  // (owner, coordinator Claude Code session, 2026-10-17, about 17:41Z,
  // answering the coordinator's question on how the Google sign-in button
  // should be handled)
  PlatformCapability(
    'lib/src/firebase_google_sign_in.dart',
    'GoogleFirebaseSignInAdapter.<constructor>',
    <String, int>{webFlag: 1, targetPlatform: 1, targetPlatformType: 1},
    'Google sign-in is offered on the web, and in the iOS and Android apps '
        'when native sign-in is configured',
  ),
  // owner-approved: 2026-10-17 "Google sign-in may be offered differently by
  // platform (always on web; on iPhone and Android when it's set up)."
  // (owner, coordinator Claude Code session, 2026-10-17, about 17:41Z,
  // answering the coordinator's question on how the Google sign-in button
  // should be handled)
  PlatformCapability(
    'lib/src/firebase_google_sign_in.dart',
    'GoogleFirebaseSignInAdapter._platform',
    <String, int>{targetPlatformType: 1},
    'Google sign-in is offered on the web, and in the iOS and Android apps '
        'when native sign-in is configured',
    // The constructor's `_platform = ...` is the field being set; the gate
    // reads its name there as a read.
    readers: <String, int>{
      'lib/src/firebase_google_sign_in.dart GoogleFirebaseSignInAdapter.<constructor>':
          1,
      'lib/src/firebase_google_sign_in.dart GoogleFirebaseSignInAdapter.available':
          2,
    },
  ),
  // owner-approved: 2026-10-17 "Google sign-in may be offered differently by
  // platform (always on web; on iPhone and Android when it's set up)."
  // (owner, coordinator Claude Code session, 2026-10-17, about 17:41Z,
  // answering the coordinator's question on how the Google sign-in button
  // should be handled)
  PlatformCapability(
    'lib/src/firebase_google_sign_in.dart',
    'GoogleFirebaseSignInAdapter.available',
    <String, int>{targetPlatformType: 2},
    'Google sign-in is offered on the web, and in the iOS and Android apps '
        'when native sign-in is configured',
    // `source_screen.dart` reads `SourceObjectState.available`, an enum value;
    // the gate counts any `.available` in a file that can see the adapter.
    readers: <String, int>{
      'lib/src/auth.dart FirebaseSession.googleSignInAvailable': 1,
      'lib/src/firebase_google_sign_in.dart GoogleFirebaseSignInAdapter.authenticate':
          1,
      'lib/src/screens/sources/source_screen.dart _SourceBrowsePaneState._body':
          1,
    },
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
  // owner-approved: 2026-10-17 "Any two way door decision, you don't need me."
  // Owner delegated reversible technical choices after the coordinator named
  // these two capability directives and network timing. This allows file
  // persistence APIs only; it does not permit platform-dependent layout.
  PlatformCapability(
    'lib/src/screens/intake/draft_file_store.dart',
    '<directives>',
    <String, int>{conditionalImport: 1},
    'native drafts retain durable files; browser drafts track reselection',
  ),
  // owner-approved: 2026-10-17 "Any two way door decision, you don't need me."
  // Same bounded delegation: browser and native OAuth callbacks use different
  // transport APIs, without branching the visual design.
  PlatformCapability(
    'lib/src/screens/intake/intake_auth_session.dart',
    '<directives>',
    <String, int>{conditionalImport: 1},
    'OAuth returns through browser messaging or native application links',
  ),
  // owner-approved: 2026-10-17 "Yes approved" (the owner, in the guard-gates
  // Claude Code session, answering whether to approve the four platform
  // exemptions on PR #358)
  // owner-approved: 2026-10-17 "Mobile and tablet stay on pull to refresh web
  // nd desktop might need exception the refresh icon we already have is
  // relevant there" (owner, coordinator Claude Code session, 2026-10-17,
  // answer to the coordinator's question on which answer stands): pull to
  // refresh on the iOS and Android apps, phones and tablets; web and desktop
  // rely on the refresh icon, the account menu's reload control.
  PlatformCapability(
    'lib/src/screens/queue/queue_screen.dart',
    '_QueuePaneState._pullToRefresh',
    <String, int>{webFlag: 1, targetPlatform: 2, targetPlatformType: 2},
    'pull to refresh is the iOS and Android apps\' gesture; web and desktop '
        'reload from the account menu (04 row 21)',
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
  // owner-approved: 2026-10-17 "Page transitions (Recommended), Firebase
  // config file (Recommended)" (the owner's selection in the coordinating
  // Claude Code session, asked which existing platform checks to approve)
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
  PlatformCapability(
    'packages/specimen_ui/lib/src/foundation/reduced_motion_platform.dart',
    '<directives>',
    <String, int>{conditionalImport: 1},
    'the reduced-motion query Flutter 3.38.5 does not carry on the web (04 '
        'section 6.2b)',
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
/// owner-approved: 2026-10-17 "Page transitions (Recommended), Firebase
/// config file (Recommended)" (the owner's selection in the coordinating
/// Claude Code session, asked which existing platform checks to approve)
const String generatedOptions = 'lib/firebase_options.dart';

/// Every platform check the product ships from the application at [base],
/// its `lib/` and the design system's, by file.
Map<String, List<PlatformCheck>> platformCensus({String base = '.'}) {
  final Map<String, List<PlatformCheck>> found =
      <String, List<PlatformCheck>>{};
  for (final GateSource source in productSources(base: base)) {
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

    expect(kindsOf('final w = kIsWasm;'), <String>[wasmFlag]);
    expect(kindsOf('bool f(ThemeData theme) => theme.platform == p;'), <String>[
      themePlatform,
    ]);
    expect(
      kindsOf(
        "export 'a_stub.dart'\n    if (dart.library.js_interop) 'a_web.dart';",
      ),
      <String>[conditionalImport],
    );
    // A theme under any name, the scroll behaviour's platform, and the
    // number tests that are true only on the web.
    expect(
      kindsOf(
        'Widget f(BuildContext c) {\n'
        '  final t = Theme.of(c);\n'
        "  return t.platform.name == 'iOS' ? a : b;\n"
        '}',
      ),
      <String>[themePlatform],
    );
    expect(kindsOf('final a = m.Theme.of(c).platform;'), <String>[
      themePlatform,
    ]);
    expect(
      kindsOf("final a = ScrollConfiguration.of(c).getPlatform(c).name;"),
      <String>[scrollPlatform],
    );
    expect(kindsOf('const bool web = identical(0, 0.0);'), <String>[
      numberWebTest,
    ]);
    expect(kindsOf('const bool web = 0.0 is int;'), <String>[numberWebTest]);
    expect(kindsOf('final same = identical(a, b);'), isEmpty);
    expect(kindsOf('final same = identical(0, 1);'), isEmpty);
    expect(kindsOf('final n = value is int;'), isEmpty);

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
    // past its counts, a forwarded predicate read by a widget that imports
    // it, by a part of a library that imports it and through an import
    // prefix (and not by one that cannot see it), a conditional export, and
    // the generated options, which are skipped.
    const List<PlatformCapability> allowed = <PlatformCapability>[
      PlatformCapability(
        'lib/src/theme/motion.dart',
        'Haptics.available',
        <String, int>{webFlag: 1},
        'planted',
        readers: <String, int>{'lib/src/theme/motion.dart Haptics.buzz': 1},
      ),
      PlatformCapability(
        'lib/src/widgets/host.dart',
        '_hostWeb',
        <String, int>{webFlag: 1},
        'planted: a private fact its part can read',
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
          "import '../theme/motion.dart';\n"
          'Widget row() => Haptics.available ? const A() : const B();\n',
      // A file that cannot see motion.dart reads some other `Haptics`.
      'lib/src/widgets/elsewhere.dart':
          'Widget other() => Haptics.available ? const A() : const B();\n',
      // A part sees what its library imports; a prefix is the same import.
      'lib/src/widgets/host.dart':
          "import '../theme/motion.dart';\n"
          "part 'part.dart';\n"
          'bool get _hostWeb => kIsWeb;\n',
      'lib/src/widgets/part.dart':
          "part of 'host.dart';\n"
          'Widget inPart() => Haptics.available ? const A() : const B();\n'
          'Widget partWeb() => _hostWeb ? const A() : const B();\n',
      'lib/src/widgets/prefixed.dart':
          "import '../theme/motion.dart' as m;\n"
          'Widget prefixed() => m.Haptics.available ? const A() : const B();\n',
      'lib/src/picker.dart':
          "export 'picker_stub.dart' if (dart.library.io) 'picker_io.dart';\n",
    });
    expect(
      platformViolations(
        census: platformCensus(base: base),
        readers: readersOf(allowed, productSources(base: base)),
        capabilities: allowed,
      ),
      <String>[
        'lib/src/app/shell.dart bar: 1 defaultTargetPlatform, allowed 0',
        'lib/src/app/shell.dart bar: 1 TargetPlatform, allowed 0',
        'lib/src/picker.dart <directives>: 1 conditional import, allowed 0',
        'lib/src/theme/motion.dart Haptics.available: 2 kIsWeb, allowed 1',
        'lib/src/theme/motion.dart Haptics.look: 1 kIsWeb, allowed 0',
        'lib/src/theme/motion.dart Haptics.available is read 1 times by '
            'lib/src/widgets/part.dart inPart, allowed 0',
        'lib/src/theme/motion.dart Haptics.available is read 1 times by '
            'lib/src/widgets/prefixed.dart prefixed, allowed 0',
        'lib/src/theme/motion.dart Haptics.available is read 1 times by '
            'lib/src/widgets/row.dart row, allowed 0',
        'lib/src/widgets/host.dart _hostWeb is read 1 times by '
            'lib/src/widgets/part.dart partWeb, allowed 0',
      ],
    );
  });

  test('no declaration branches on the platform past its capability', () {
    final List<String> violations = platformViolations(
      census: platformCensus(),
      readers: readersOf(platformCapabilities, productSources()),
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
      productSources(),
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
