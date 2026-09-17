// The source pane's geometry: what the reviewer sees against what the record
// records. Nothing here may rewrite the saved coordinates, and the overlay a
// reviewer taps must land on the pixels the bounding box names.

import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/source_geometry.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

void main() {
  final bytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();

  Rect globalRect(RenderBox box) {
    final points = [
      Offset.zero,
      Offset(box.size.width, 0),
      Offset(0, box.size.height),
      Offset(box.size.width, box.size.height),
    ].map(box.localToGlobal).toList();
    return Rect.fromLTRB(
      points.map((p) => p.dx).reduce(math.min),
      points.map((p) => p.dy).reduce(math.min),
      points.map((p) => p.dx).reduce(math.max),
      points.map((p) => p.dy).reduce(math.max),
    );
  }

  // The overlay and the region list speak the same name, so the overlay is
  // found by where it is rather than by the name alone: both publish a node
  // called "Label 1", which is the point of the pairing.
  Finder overlayNamed(String label) => find.descendant(
    of: find.byType(RegionOverlay),
    matching: find.byWidgetPredicate(
      (w) => w is Semantics && w.properties.label == label,
    ),
    matchRoot: true,
  );

  /// One option of the region list, which is a capsule toggle in single mode.
  Finder regionOption(String label) => find.byWidgetPredicate(
    (w) =>
        w is Pressable &&
        w.role == PressableRole.toggle &&
        w.semanticsLabel == label,
    description: 'region option "$label"',
  );

  Widget pane(Specimen specimen, {Key? key}) => workbenchHost(
    ReviewWorkbench(
      key: key,
      specimen: specimen,
      onChange: (_) async => false,
      onRetry: (_) async {},
      onRefresh: () {},
    ),
  );

  group('regionRectIn', () {
    // The rotation mapping is arithmetic, so it is checked as arithmetic
    // rather than by reading numbers off a rendered image.
    const viewport = Size(1000, 520);
    test('an unrotated region keeps its fraction of the photograph', () {
      final rect = regionRectIn(viewport, [100, 52, 700, 312], 1000, 520, 0);
      expect(rect.left, closeTo(100, .001));
      expect(rect.top, closeTo(52, .001));
      expect(rect.width, closeTo(600, .001));
      expect(rect.height, closeTo(260, .001));
    });

    test('a quarter turn swaps the region the way it swaps the box', () {
      final box = sourceBoxIn(viewport, 1000, 520, 1);
      final rect = regionRectIn(viewport, [100, 52, 700, 312], 1000, 520, 1);
      expect(rect.width / rect.height, closeTo(260 / 600, .001));
      expect(rect.left, greaterThanOrEqualTo(box.left - .001));
      expect(rect.right, lessThanOrEqualTo(box.right + .001));
    });

    test('framing a region never asks for more scale than the viewer has', () {
      final matrix = frameRect(
        viewport,
        const Rect.fromLTWH(0, 0, 1, 1),
        minScale: 0.2,
        maxScale: 12,
      );
      expect(matrix.getMaxScaleOnAxis(), closeTo(12, .001));
    });

    test('a region with no area leaves the view alone', () {
      final matrix = frameRect(
        viewport,
        const Rect.fromLTWH(10, 10, 0, 0),
        minScale: 0.2,
        maxScale: 12,
      );
      expect(matrix, Matrix4.identity());
    });
  });

  testWidgets(
    'each saved label rotation turns the view without moving the rectangle',
    (tester) async {
      useWindow(tester, largeWindow);
      for (var rotation = 0; rotation < 4; rotation++) {
        final box = [100, 52, 700, 312];
        await tester.pumpWidget(
          pane(
            Specimen({
              'specimen_id': 'roi',
              'revision': rotation + 1,
              'assets': [
                {'width': 1000, 'height': 520, 'preview_bytes': bytes},
              ],
              'regions': [
                {
                  'region_id': 'r1',
                  'bbox': box,
                  'rotation_quarter_turns': rotation,
                },
              ],
            }),
            key: ValueKey(rotation),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(regionOption('Label 1'));
        await tester.pumpAndSettle();
        final rotated = tester.widget<RotatedBox>(
          find.byType(RotatedBox).first,
        );
        // The reviewer's own view rotation is zero here, so the turn is
        // entirely the region's recorded reading rotation.
        expect(rotated.quarterTurns, rotation);
        expect(box, [100, 52, 700, 312]);
        expect(tester.takeException(), isNull);
      }
    },
  );

  testWidgets('selecting a region moves the view instead of cropping', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    await tester.pumpWidget(
      pane(
        Specimen({
          'specimen_id': 'zoom',
          'revision': 1,
          'assets': [
            {'width': 1000, 'height': 520, 'preview_bytes': bytes},
          ],
          'regions': [
            {
              'region_id': 'r1',
              'bbox': [100, 52, 400, 212],
            },
          ],
        }),
      ),
    );
    await tester.pumpAndSettle();
    final viewer = tester.widget<InteractiveViewer>(
      find.byType(InteractiveViewer),
    );
    expect(viewer.transformationController!.value, Matrix4.identity());
    await tester.tap(regionOption('Label 1'));
    await tester.pumpAndSettle();
    // One image, magnified: the whole photograph is still the widget on
    // screen, so the reviewer keeps their place on the specimen.
    expect(
      viewer.transformationController!.value.getMaxScaleOnAxis(),
      greaterThan(1),
    );
    expect(
      find.byWidgetPredicate(
        (w) =>
            w is Image &&
            w.semanticLabel == 'Immutable original specimen image',
      ),
      findsOneWidget,
    );
  });

  testWidgets('a new run clears an obsolete selection and keeps the overlays', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    Widget view(String run, String region) => pane(
      Specimen({
        'specimen_id': 'same',
        'active_run_id': run,
        'revision': 1,
        'assets': [
          {'width': 1000, 'height': 520, 'preview_bytes': bytes},
        ],
        'regions': [
          {
            'region_id': region,
            'bbox': [100, 52, 700, 312],
          },
        ],
      }),
    );
    await tester.pumpWidget(view('run1', 'region1'));
    await tester.pumpAndSettle();
    await tester.tap(regionOption('Label 1'));
    await tester.pumpAndSettle();
    expect(tester.widget<Pressable>(regionOption('Label 1')).selected, isTrue);
    await tester.pumpWidget(view('run2', 'region2'));
    await tester.pumpAndSettle();
    expect(tester.widget<Pressable>(regionOption('Label 1')).selected, isFalse);
    // The overlay speaks the same name the region list shows, never the raw
    // identifier (accessibility, 2.2 finding 2).
    expect(overlayNamed('Label 1'), findsOneWidget);
    expect(overlayNamed('Label region region2'), findsNothing);
  });

  for (final viewport in [compactWindow, largeWindow]) {
    testWidgets(
      'source keeps its aspect and its original coordinate overlays at '
      '$viewport',
      (tester) async {
        useWindow(tester, viewport);
        await tester.pumpWidget(
          pane(
            Specimen({
              'specimen_id': 'geometry',
              'revision': 1,
              'assets': [
                {'width': 1000, 'height': 520, 'preview_bytes': bytes},
              ],
              'regions': [
                {
                  'region_id': 'r1',
                  'bbox': [100, 52, 700, 312],
                },
              ],
            }),
          ),
        );
        await tester.pumpAndSettle();
        for (var turn = 0; turn < 4; turn++) {
          final image = find.byWidgetPredicate(
            (w) =>
                w is Image &&
                w.semanticLabel == 'Immutable original specimen image',
          );
          final imageBox = tester.renderObject<RenderBox>(image);
          expect(
            imageBox.size.width / imageBox.size.height,
            closeTo(1000 / 520, .00001),
          );
          final rect = globalRect(imageBox);
          expect(
            rect.width / rect.height,
            closeTo(turn.isEven ? 1000 / 520 : 520 / 1000, .00001),
          );
          final viewerRect = globalRect(
            tester.renderObject<RenderBox>(find.byType(InteractiveViewer)),
          );
          expect(rect.left, greaterThanOrEqualTo(viewerRect.left - .001));
          expect(rect.right, lessThanOrEqualTo(viewerRect.right + .001));
          expect(rect.top, greaterThanOrEqualTo(viewerRect.top - .001));
          expect(rect.bottom, lessThanOrEqualTo(viewerRect.bottom + .001));
          final overlayBox = tester.renderObject<RenderBox>(
            overlayNamed('Label 1'),
          );
          // The hit box follows the recorded fraction, except that it never
          // shrinks below a target a finger can hit (accessibility, 3.2).
          const target = 48.0;
          expect(
            overlayBox.size.width,
            closeTo(math.max(imageBox.size.width * .6, target), .001),
          );
          expect(
            overlayBox.size.height,
            closeTo(math.max(imageBox.size.height * .5, target), .001),
          );
          await tester.tap(uiIconButton('Rotate the view 90 degrees'));
          await tester.pumpAndSettle();
        }
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets(
    'independent readings retain complete accessible labels and differing text',
    (tester) async {
      useWindow(tester, largeWindow);
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        pane(
          const Specimen({
            'specimen_id': 'readings',
            'revision': 1,
            'observations': [
              {
                'model_id': 'Reader A',
                'region_id': 'r1',
                'literal_text': 'Chicago 1912',
              },
              {
                'model_id': 'Reader B',
                'region_id': 'r1',
                'literal_text': 'Chicago 1917',
              },
            ],
          }),
        ),
      );
      await tester.pumpAndSettle();
      for (final literal in ['Chicago 1912', 'Chicago 1917']) {
        // The first reading of a region has nothing to differ from, so it
        // renders plain; the second renders as marked runs.
        final text = find.byWidgetPredicate(
          (w) =>
              w is Text &&
              (w.data == literal || w.textSpan?.toPlainText() == literal),
        );
        expect(text, findsOneWidget);
        expect(
          find.ancestor(of: text, matching: find.byType(SelectableEvidence)),
          findsOneWidget,
        );
        expect(
          tester.getSemantics(text).getSemanticsData().label,
          contains(literal),
        );
      }
      semantics.dispose();
    },
  );
}
