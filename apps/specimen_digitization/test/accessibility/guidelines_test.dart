// Automated accessibility guideline matchers.
//
// design/06-accessibility.md section 4.1 ("Automated") asks for the four
// built-in flutter_test AccessibilityGuidelines over every screen, and section
// 4.3 makes `flutter test test/accessibility/` a merge gate. This file covers
// the screens that can be constructed with no network and no Firebase:
// SignInScreen, MagicLinkSignInScreen, SearchFilters, RegionEditor and
// CaptureQualityView.
//
// A guideline that a screen fails is marked `skip:` with the finding it belongs
// to, never weakened, so the skip list doubles as the remediation backlog. As
// of this commit the list is empty: all five screens pass all four guidelines.
// That is a real result, not an empty harness. Material's default
// `MaterialTapTargetSize.padded` already lifts the 36 dp-tall text buttons to a
// 48 dp tap target, every icon-only control here already carries a tooltip, and
// the seeded scheme clears 4.5:1. The `renders an inspectable semantics tree`
// test in each group is what keeps that claim honest: it fails if a screen ever
// stops producing nodes for the guidelines to inspect.
//
// https://api.flutter.dev/flutter/flutter_test/AccessibilityGuideline-class.html

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/magic_link_screen.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

/// A `SessionAccess` that reaches nothing. `SignInScreen` renders its fixture
/// form for any session that is not an `EmailLinkAccess`, which is the branch
/// this exercises; the magic-link branch is covered separately below.
class OfflineSession implements SessionAccess {
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
class OfflineLinkAccess implements EmailLinkAccess {
  @override
  bool isSignInWithEmailLink(String link) => false;
  @override
  Future<void> sendSignInLink(String email) async {}
  @override
  Future<void> completeEmailLink(String email, String link) async {}
}

/// In-memory `EmailLinkStorage`, so the screen never touches preferences.
class MemoryLinkStorage implements EmailLinkStorage {
  RememberedEmailLink value = const RememberedEmailLink();
  @override
  Future<RememberedEmailLink> read() async => value;
  @override
  Future<void> write(RememberedEmailLink input) async => value = input;
}

/// A region and an asset small enough to need no decoded image, matching the
/// fake `test/region_editor_test.dart` builds for its small-region cases.
const smallRegions = <Json>[
  {
    'region_id': 'small',
    'bbox': [5, 7, 45, 57],
    'order': 0,
    'rotation_quarter_turns': 0,
  },
];
const smallAsset = <String, dynamic>{'width': 64, 'height': 96};

/// Pumps `child` inside the app's own theme, so the contrast guideline reads
/// the colors the client actually ships rather than the bare Material default.
///
/// The surface is deliberately taller than the 800x600 test default. A
/// guideline only ever sees the semantics tree, and a control scrolled out of
/// view contributes no node, so at the default size most of these dialogs would
/// pass by not being rendered at all.
Future<void> pumpScreen(WidgetTester tester, Widget child) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(1024, 2400);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      // The product theme, not a stand-in: a screen that reads the product
      // `ThemeExtension`s cannot be checked against a bare Material theme,
      // and the contrast guideline must see the colors that ship.
      theme: AppTheme.light(),
      home: child,
    ),
  );
  await tester.pumpAndSettle();
}

/// Pumps a dialog widget the way the app opens it, then settles the route.
Future<void> pumpDialog(WidgetTester tester, Widget dialog) async {
  await pumpScreen(
    tester,
    Builder(
      builder: (context) => Scaffold(
        body: TextButton(
          onPressed: () => unawaited(
            showDialog<void>(context: context, builder: (_) => dialog),
          ),
          child: const Text('Open'),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}

/// Counts semantics nodes matching [matches], depth first from the app root.
int countSemantics(WidgetTester tester, bool Function(SemanticsNode) matches) {
  final root = tester.semantics.find(find.byType(MaterialApp));
  var total = 0;
  void visit(SemanticsNode node) {
    if (matches(node)) total++;
    node.visitChildren((child) {
      visit(child);
      return true;
    });
  }

  visit(root);
  return total;
}

const guidelines = <String, AccessibilityGuideline>{
  'android tap target': androidTapTargetGuideline,
  'iOS tap target': iOSTapTargetGuideline,
  'labeled tap target': labeledTapTargetGuideline,
  'text contrast': textContrastGuideline,
};

/// Registers one test per guideline for one screen.
///
/// [skips] maps a guideline name to the reason recording the finding that
/// guideline currently trips. A guideline absent from the map must pass.
///
/// The reason is carried on a one-test `group`, because `testWidgets` takes
/// only `bool? skip` while `group` takes a reason string and prints it. The
/// guideline is never relaxed, so each entry here is a backlog item, and
/// deleting one is how a fix gets proven.
void guidelineSuite(
  String screen,
  Future<void> Function(WidgetTester tester) pump, {
  Map<String, String> skips = const {},
}) {
  group(screen, () {
    // A guideline only inspects the semantics tree, so a harness that renders
    // nothing passes all four. This asserts the screen is actually on screen,
    // which is what makes the four results below mean something.
    testWidgets('$screen renders an inspectable semantics tree', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pump(tester);
      expect(
        countSemantics(tester, (node) => true),
        greaterThanOrEqualTo(4),
        reason: '$screen produced almost no semantics nodes',
      );
      expect(
        countSemantics(
          tester,
          (node) => node.getSemanticsData().hasAction(SemanticsAction.tap),
        ),
        greaterThanOrEqualTo(1),
        reason:
            '$screen exposed no tappable node, so the tap target and '
            'labelled-target guidelines had nothing to check',
      );
      handle.dispose();
    });

    guidelines.forEach((name, guideline) {
      final label = '$screen meets the $name guideline';
      void register() {
        testWidgets(label, (tester) async {
          final handle = tester.ensureSemantics();
          await pump(tester);
          await expectLater(tester, meetsGuideline(guideline));
          handle.dispose();
        });
      }

      final reason = skips[name];
      if (reason == null) {
        register();
      } else {
        group('', register, skip: reason);
      }
    });
  });
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  guidelineSuite(
    'SignInScreen',
    (tester) => pumpScreen(tester, SignInScreen(session: OfflineSession())),
  );

  guidelineSuite('MagicLinkSignInScreen', (tester) async {
    final access = OfflineLinkAccess();
    await pumpScreen(
      tester,
      MagicLinkSignInScreen(
        access: access,
        controller: MagicLinkController(
          access: access,
          browser: MemoryEmailLinkBrowser(),
          storage: MemoryLinkStorage(),
        ),
      ),
    );
  });

  // The filter form is the child of `showAdaptiveForm` now, not a dialog of
  // its own, so it is pumped as a screen.
  guidelineSuite(
    'SearchFilters',
    (tester) => pumpScreen(
      tester,
      const Scaffold(
        body: SingleChildScrollView(child: SearchFilters(initial: {})),
      ),
    ),
  );

  guidelineSuite(
    'RegionEditor',
    (tester) => pumpDialog(
      tester,
      const RegionEditor(regions: smallRegions, asset: smallAsset),
    ),
  );

  guidelineSuite(
    'CaptureQualityView',
    (tester) => pumpScreen(
      tester,
      Scaffold(
        body: SingleChildScrollView(
          child: CaptureQualityView(
            quality: CaptureQuality.measure(
              Uint8List.fromList(
                [0, 255, 0, 255].expand((v) => [v, v, v, 255]).toList(),
              ),
              2,
              2,
            ),
          ),
        ),
      ),
    ),
  );
}
