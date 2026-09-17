// Intake, the source list and the source browse pane at 200 percent text
// (11 section 2; control contract clause 7).
//
// The promise the system makes is 200 percent, and a compact window is where
// it costs the most: every control that carries a label has to switch to a
// variant that fits rather than overflow, and every line of content has to
// wrap rather than clip. These tests pump each screen at the promise's
// ceiling in a phone sized window and fail on any layout error at all, which
// is stricter than looking for an overflow: a clipped glyph and a failed
// assertion are both defects a reviewer would meet.

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_digitization/src/screens/sources/source_controller.dart';
import 'package:specimen_digitization/src/screens/sources/source_screen.dart';
import 'package:specimen_digitization/src/screens/sources/sources_screen.dart';
import 'package:specimen_digitization/src/sources.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

import '../sources/source_fixtures.dart';
import '../widget_test.dart' show TestRepository;

/// A phone in portrait, which is the narrowest window the product promises.
const Size compactWindow = Size(390, 844);

/// The scale the control contract promises and nothing above it.
const double maxTextScale = 2;

List<String> _errors = <String>[];
void Function(FlutterErrorDetails)? _previous;

/// Collects every layout error the frame raises instead of failing on it, so
/// the assertion can name all of them at once.
void _capture() {
  _previous = FlutterError.onError;
  _errors = <String>[];
  FlutterError.onError = (FlutterErrorDetails details) =>
      _errors.add(details.exceptionAsString());
}

/// Puts the framework's own handler back before any `expect` runs, because a
/// failure raised while the collector is installed is swallowed by it.
void _stop() {
  if (_previous == null) return;
  FlutterError.onError = _previous;
  _previous = null;
}

/// Pumps [child] at 200 percent text in a compact window.
Future<void> _pumpScaled(WidgetTester tester, Widget child) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = compactWindow;
  tester.platformDispatcher.textScaleFactorTestValue = maxTextScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  addTearDown(_stop);
  _capture();
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(body: child),
    ),
  );
  await tester.pumpAndSettle();
}

/// Fails on any layout error, naming every one of them.
void _expectNoLayoutError(WidgetTester tester, String screen) {
  _stop();
  expect(
    _errors,
    isEmpty,
    reason: '$screen raised a layout error at 200 percent text',
  );
  expect(tester.takeException(), isNull, reason: screen);
}

void main() {
  testWidgets('intake lays out at 200 percent text in a compact window', (
    WidgetTester tester,
  ) async {
    await _pumpScaled(
      tester,
      IntakeScreen(
        repository: TestRepository(),
        scope: const CollectionScope(
          organizationId: 'org',
          collectionId: 'insects',
          name: 'Synthetic insects',
        ),
        userId: 'owner',
        onComplete: () {},
        onBrowseSources: () {},
        pickImages: (bool _) async => <XFile>[],
      ),
    );
    _expectNoLayoutError(tester, 'Intake');
    // The capture card's own controls survive the scale: the file action
    // keeps its word and the sensitivity track falls back to its glyphs.
    expect(find.text('Choose files'), findsOneWidget);
    expect(find.text(IntakeCaptureCard.title), findsOneWidget);
  });

  testWidgets('the source list lays out at 200 percent text', (
    WidgetTester tester,
  ) async {
    await _pumpScaled(
      tester,
      SourcesScreen(
        repository: FakeSourceRepository(),
        scope: testScope,
        onOpen: (RegisteredSource _) {},
      ),
    );
    _expectNoLayoutError(tester, 'SourcesScreen');
    expect(find.text('microscopic-slides'), findsOneWidget);
  });

  testWidgets('the source browse pane lays out at 200 percent text', (
    WidgetTester tester,
  ) async {
    final SourceBrowseController controller = SourceBrowseController(
      repository: FakeSourceRepository(),
      scope: testScope,
      sourceId: 'src-1',
    );
    addTearDown(controller.dispose);
    await _pumpScaled(
      tester,
      SourceBrowsePane(controller: controller, source: source()),
    );
    _expectNoLayoutError(tester, 'SourceBrowsePane');
    expect(find.text('subject_105526321.jpg'), findsOneWidget);
  });
}
