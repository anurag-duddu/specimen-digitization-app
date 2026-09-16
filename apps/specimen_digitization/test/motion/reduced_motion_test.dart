// One reduced-motion test per animated component
// (motion and microinteractions, 6.3 B).
//
// Every test drives the iOS path, `AccessibilityFeatures.reduceMotion`,
// because that is the one production will actually hit on an iPad and the one
// `MediaQuery` does not carry. A component that reads `MediaQuery` alone
// passes nothing here.
//
// The assertion is always the same shape: change the state, pump exactly one
// frame with no clock advance, and require the component to already be at its
// destination. A token that was bypassed shows up as a running animation, or
// as a value still on its way.

import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Turns on the platform signal the iPad sends, for one test.
void reduceMotion(WidgetTester tester) {
  tester.platformDispatcher.accessibilityFeaturesTestValue =
      const FakeAccessibilityFeatures(reduceMotion: true);
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
}

/// The shared assertion: no token was bypassed.
///
/// Deliberately not used after a `tap`. Material's own ink splash is a running
/// animation and it is not ours to stop: the reduced-motion policy drops
/// ripples to an instant colour change through the theme, not by halting
/// Flutter's controller. Where a test has to press something, it asserts on
/// the tree and on the value instead.
void expectNoRunningAnimations(WidgetTester tester) => expect(
  tester.hasRunningAnimations,
  isFalse,
  reason:
      'A motion token was bypassed. Every duration must go through '
      'MotionTokens.d(), which returns Duration.zero under reduced motion.',
);

Future<void> pump(
  WidgetTester tester,
  Widget child, {
  Size size = const Size(1000, 1600),
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(body: child),
    ),
  );
}

/// Pumps [build] at false, then at true, then exactly one frame.
///
/// One frame with no clock advance is the whole animation under reduced
/// motion, which is the property every test below asserts.
Future<void> flipTo(
  WidgetTester tester,
  Widget Function(BuildContext context, bool on) build, {
  Size size = const Size(1000, 1600),
}) async {
  await pump(
    tester,
    Builder(builder: (BuildContext c) => build(c, false)),
    size: size,
  );
  await pump(
    tester,
    Builder(builder: (BuildContext c) => build(c, true)),
    size: size,
  );
  await tester.pump();
}

/// The magnification the source viewer is currently at.
double viewerScale(WidgetTester tester) => tester
    .widget<InteractiveViewer>(find.byType(InteractiveViewer))
    .transformationController!
    .value
    .getMaxScaleOnAxis();

void main() {
  final Uint8List labelBytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();

  Specimen record({String disposition = 'needs_human_review'}) =>
      Specimen(<String, dynamic>{
        'specimen_id': 'motion-001',
        'display_name': 'Synthetic motion record',
        'revision': 2,
        'disposition': disposition,
        'available_actions': const <String>['field', 'coverage'],
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
          <String, dynamic>{
            'region_id': 'r2',
            'bbox': <int>[420, 52, 700, 212],
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
        'validation_findings': const <Json>[],
      });

  testWidgets('MotionReveal: a banner appears with no travel', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await flipTo(
      tester,
      (BuildContext context, bool on) => MotionReveal(
        visible: on,
        child: const Text('Working offline. Showing the last sync.'),
      ),
    );
    expect(find.textContaining('Working offline'), findsOneWidget);
    // Not wrapped at all: the block simply is, rather than growing into place.
    expect(find.byType(AnimatedSize), findsNothing);
    expect(find.byType(AnimatedOpacity), findsNothing);
    expectNoRunningAnimations(tester);
  });

  testWidgets('MotionReveal: an unbounded payload arrives whole, with no size '
      'animation to cap', (WidgetTester tester) async {
    reduceMotion(tester);
    await flipTo(
      tester,
      (BuildContext context, bool on) => MotionReveal(
        visible: on,
        heightCap: MotionReveal.evidenceHeightCap,
        child: const SizedBox(height: 3000, child: Text('A large payload')),
      ),
    );
    expect(find.text('A large payload'), findsOneWidget);
    expect(find.byType(AnimatedSize), findsNothing);
    expectNoRunningAnimations(tester);
  });

  testWidgets('InFlightGlyph: the indicator replaces the icon at once', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await flipTo(
      tester,
      (BuildContext context, bool on) =>
          InFlightGlyph(busy: on, resting: Icons.save),
    );
    expect(find.byIcon(Icons.save), findsNothing);
    // The indeterminate indicator itself keeps turning: it says the server has
    // not answered, and that is information, not decoration (04 section 2.5).
    expect(find.byType(UiProgress), findsOneWidget);
  });

  testWidgets('StatusChip: a state change is instant', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await flipTo(
      tester,
      (BuildContext context, bool on) => StatusChip.presented(
        (on ? UploadState.accepted : UploadState.ready).presentation(context),
      ),
    );
    expect(find.text('Accepted'), findsOneWidget);
    expect(find.text('Ready'), findsNothing);
    expectNoRunningAnimations(tester);
  });

  testWidgets('EvidenceDrawer: the disclosure opens without a size animation', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await pump(
      tester,
      const EvidenceDrawer(payload: <String, dynamic>{'phase': 'parse'}),
    );
    await tester.tap(find.text(EvidenceDrawer.defaultTitle));
    await tester.pump();
    expect(find.textContaining('parse'), findsOneWidget);
    expect(find.byType(AnimatedSize), findsNothing);
  });

  testWidgets('CaveatText: the explanation opens without a size animation', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await pump(
      tester,
      const CaveatText(
        label: 'This score is not calibrated.',
        why: 'No reference set has been measured against this collection.',
      ),
    );
    await tester.tap(find.text('Why'));
    await tester.pump();
    expect(find.textContaining('No reference set'), findsOneWidget);
    expect(find.byType(AnimatedSize), findsNothing);
  });

  testWidgets('The source viewer: selecting a region re-crops instantly', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    String? selected;
    await pump(
      tester,
      StatefulBuilder(
        builder: (BuildContext context, StateSetter set) => WorkbenchSourcePane(
          specimen: record(),
          selectedRegionId: selected,
          onSelectRegion: (String? id) => set(() => selected = id),
        ),
      ),
    );
    await tester.pump();
    final double before = viewerScale(tester);
    await tester.tap(find.text('Label 2'));
    // Two frames: one for the selection, one for the post-frame that frames
    // the region. Neither advances the clock, so a value still on its way here
    // would mean the emphasized token was not collapsed.
    await tester.pump();
    await tester.pump();
    final double after = viewerScale(tester);
    expect(after, greaterThan(before), reason: 'the view did not re-crop');
    await tester.pump();
    expect(viewerScale(tester), closeTo(after, 0.000001));
  });

  testWidgets('The workbench: a segment change is a fade with no offset', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await pump(
      tester,
      ReviewWorkbench(
        specimen: record(),
        onChange: (Json _) async => true,
        onRetry: (String _) async {},
        onRefresh: () {},
      ),
    );
    await tester.pump();
    await tester.tap(find.text('Fields'));
    await tester.pump();
    // A slide would put a `SlideTransition` under the switcher. Under reduced
    // motion the panel cross-fades in place, which is what Apple's
    // accessibility guidance asks for in place of an x-axis transition.
    expect(
      find.descendant(
        of: find.byType(AnimatedSwitcher),
        matching: find.byType(SlideTransition),
      ),
      findsNothing,
    );
  });

  testWidgets('The status strip: the saved check appears at full size', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await flipTo(
      tester,
      (BuildContext context, bool on) => WorkbenchStatusStrip(
        specimen: record(disposition: on ? 'cleared' : 'needs_human_review'),
        blockers: const <ClearanceBlocker>[],
        pending: const <PendingFieldChange>[],
        canOperate: true,
        busy: false,
        onAction: (Json _) async {},
        onGoToBlocker: (ClearanceBlocker _) {},
        onReviewPending: () {},
      ),
    );
    expect(find.bySemanticsLabel('Saved'), findsOneWidget);
    final Transform scaled = tester.widget<Transform>(
      find
          .descendant(
            of: find.bySemanticsLabel('Saved'),
            matching: find.byType(Transform),
          )
          .first,
    );
    // Already at full size on the first frame: the check appears, it does not
    // grow.
    expect(scaled.transform.getMaxScaleOnAxis(), closeTo(1, 0.001));
  });

  testWidgets('The intake manifest: a determinate ring keeps its motion', (
    WidgetTester tester,
  ) async {
    reduceMotion(tester);
    await pump(
      tester,
      IntakeManifest(
        entries: <ManifestEntry>[
          ManifestEntry(digest: 'a' * 64, name: 'IMG_0001.jpg')
            ..state = UploadState.uploading
            ..progress = 0.42,
        ],
        busy: true,
        stopping: false,
        onStop: () {},
        onRemove: (ManifestEntry _) {},
        onServerCheck: (ManifestEntry _) {},
      ),
    );
    await tester.pump();
    // The ring is the rendering of a number the byte stream gave us. Removing
    // its motion removes data, so it is the one exception in this file.
    expect(find.byType(TweenAnimationBuilder<double>), findsWidgets);
    expect(find.byType(UiProgress), findsWidgets);
  });
}
