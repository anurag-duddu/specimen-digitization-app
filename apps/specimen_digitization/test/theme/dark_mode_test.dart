// Every top-level screen, in both themes, against the text contrast
// guideline (screen blueprints, section 12; design system, section 3).
//
// Dark is not a filter over light in this product. It is defined by hand,
// it carries its own container ladder, and the one surface that must not be
// re-toned is the photograph: a specimen image sits on a fixed dark matte in
// both themes so that label paper reads as paper. A screen that renders in
// light and fails in dark has not been checked, so this file pumps the same
// screen twice and runs `textContrastGuideline` over both.
//
// `textContrastGuideline` is the WCAG AA contrast check flutter_test ships.
// It is never relaxed here; a screen that trips it is a token misuse to fix,
// not a skip to add.

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/help_screen.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';

/// A session that reaches nothing, so the sign-in screen renders its form.
class _OfflineSession implements SessionAccess {
  @override
  Stream<bool> get changes => const Stream<bool>.empty();
  @override
  bool get signedIn => false;
  @override
  String get userId => '';
  @override
  String get displayName => 'Offline reviewer';
  @override
  Future<String?> token() async => null;
  @override
  Future<void> signIn(String email, String password) async {}
  @override
  Future<void> signOut() async {}
  @override
  Future<void> resetPassword(String email) async {}
}

/// An `EmailLinkAccess` that records instead of calling Firebase.
class _OfflineLinkAccess implements EmailLinkAccess {
  @override
  bool isSignInWithEmailLink(String link) => false;
  @override
  Future<void> sendSignInLink(String email) async {}
  @override
  Future<void> completeEmailLink(String email, String link) async {}
}

/// In-memory `EmailLinkStorage`, so the screen never touches preferences.
class _MemoryLinkStorage implements EmailLinkStorage {
  RememberedEmailLink value = const RememberedEmailLink();
  @override
  Future<RememberedEmailLink> read() async => value;
  @override
  Future<void> write(RememberedEmailLink input) async => value = input;
}

/// A browser that records the address bar instead of touching one.
class _MemoryEmailLinkBrowser implements EmailLinkBrowser {
  @override
  Uri get initialUri => Uri.parse('https://example.org/');
  @override
  void clearLink() {}
}

/// The two themes, by the name a failure message should print.
final Map<String, ThemeData> themes = <String, ThemeData>{
  'light': AppTheme.light(),
  'dark': AppTheme.dark(),
};

Future<void> _pump(
  WidgetTester tester,
  ThemeData theme,
  Widget child, {
  Size size = const Size(1024, 2400),
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(theme: theme, home: child));
  await tester.pumpAndSettle();
}

/// Registers one contrast test per theme for one screen.
void bothThemes(String screen, Widget Function() build, {Size? size}) {
  themes.forEach((String name, ThemeData theme) {
    testWidgets('$screen reads in $name', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await _pump(tester, theme, build(), size: size ?? const Size(1024, 2400));
      // The screen has to be on screen for the guideline to mean anything.
      // Text rather than a frame type: the entry screens are `UiScaffold`
      // now and the panels are pumped bare, and what a contrast guideline
      // needs is words to measure.
      expect(find.byType(Text), findsWidgets);
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    });
  });
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  final Uint8List labelBytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();

  Specimen record() => Specimen(<String, dynamic>{
    'specimen_id': 'dark-001',
    'display_name': 'Synthetic dark mode record',
    'revision': 3,
    'disposition': 'needs_human_review',
    'available_actions': const <String>['field', 'transcription', 'coverage'],
    'assets': <Json>[
      <String, dynamic>{
        'width': 1000,
        'height': 520,
        'preview_bytes': labelBytes,
      },
    ],
    'regions': const <Json>[
      <String, dynamic>{
        'region_id': 'r1',
        'bbox': <int>[100, 52, 400, 212],
      },
    ],
    'observations': const <Json>[
      <String, dynamic>{
        'id': 'o1',
        'model_id': 'Reader A',
        'provider': 'synthetic',
        'region_id': 'r1',
        'literal_text': 'Chicago 1912',
      },
    ],
    'fields': const <Json>[
      <String, dynamic>{
        'field_key': 'country',
        'display_name': 'Country',
        'required': true,
        'state': 'unknown',
        'literal_value': null,
      },
    ],
    'validation_findings': const <Json>[
      <String, dynamic>{
        'field_key': 'country',
        'message': 'A supported country is required',
        'severity': 'hard',
        'rule_id': 'country.required',
      },
    ],
  });

  bothThemes('Sign in', () => SignInScreen(session: _OfflineSession()));

  bothThemes('Magic link sign in', () {
    final _OfflineLinkAccess access = _OfflineLinkAccess();
    return MagicLinkSignInScreen(
      access: access,
      controller: MagicLinkController(
        access: access,
        browser: _MemoryEmailLinkBrowser(),
        storage: _MemoryLinkStorage(),
      ),
    );
  });

  bothThemes(
    'Filters',
    () => const Scaffold(
      body: SingleChildScrollView(
        child: SearchFilters(initial: <String, String>{}),
      ),
    ),
  );

  bothThemes(
    'Workbench',
    () => Scaffold(
      body: ReviewWorkbench(
        specimen: record(),
        onChange: (Json _) async => true,
        onRetry: (String _) async {},
        onRefresh: () {},
      ),
    ),
    size: const Size(1440, 1200),
  );

  bothThemes(
    'Workbench at compact',
    () => Scaffold(
      body: ReviewWorkbench(
        specimen: record(),
        onChange: (Json _) async => true,
        onRetry: (String _) async {},
        onRefresh: () {},
      ),
    ),
    size: const Size(390, 844),
  );

  bothThemes(
    'Region editor',
    () => const Scaffold(
      body: RegionEditor(
        regions: <Json>[
          <String, dynamic>{
            'region_id': 'r1',
            'bbox': <int>[10, 10, 90, 60],
            'rotation_quarter_turns': 0,
          },
        ],
        asset: <String, dynamic>{'width': 100, 'height': 80},
      ),
    ),
  );

  bothThemes(
    'Capture quality',
    () => Scaffold(
      body: SingleChildScrollView(
        child: CaptureQualityView(
          quality: CaptureQuality.measure(
            Uint8List.fromList(
              <int>[
                0,
                255,
                0,
                255,
              ].expand((int v) => <int>[v, v, v, 255]).toList(),
            ),
            2,
            2,
          ),
        ),
      ),
    ),
  );

  bothThemes(
    'Intake manifest',
    () => Scaffold(
      body: IntakeManifest(
        entries: <ManifestEntry>[
          ManifestEntry(digest: 'a' * 64, name: 'IMG_0001.jpg')
            ..state = UploadState.accepted,
          ManifestEntry(digest: 'b' * 64, name: 'IMG_0002.jpg')
            ..state = UploadState.failed
            ..reason = 'The server could not read the file.',
        ],
        busy: false,
        stopping: false,
        onStop: () {},
        onRemove: (ManifestEntry _) {},
        onServerCheck: (ManifestEntry _) {},
      ),
    ),
  );

  // The help panel is a modal drawn over a route, and its pane is
  // `glass.modal`. Pumped on nothing it captures half transparent pixels and
  // a contrast guideline measuring one measures nothing, so it is given the
  // opaque surface a route would be.
  bothThemes('Help', () => const Scaffold(body: HelpScreen()));

  bothThemes(
    'Empty state',
    () => const Scaffold(
      body: EmptyState(
        icon: Icons.inbox,
        title: 'No specimens yet',
        body: 'Upload a photograph to create the first record.',
      ),
    ),
  );

  bothThemes(
    'Skeleton placeholders',
    // The pulse never settles, so the placeholders are pumped with their
    // tickers stopped; what is under test here is their colour.
    () => const Scaffold(
      body: Padding(
        padding: EdgeInsets.all(16),
        child: TickerMode(
          enabled: false,
          child: Column(
            children: <Widget>[
              LoadingAnnouncement(thing: 'queue', visible: true),
              SkeletonRow(),
              SkeletonRow(),
            ],
          ),
        ),
      ),
    ),
  );
}
