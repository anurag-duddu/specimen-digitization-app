import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workbench.dart';

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

  testWidgets(
    'each saved ROI rotation turns its original-coordinate crop without moving the rectangle',
    (tester) async {
      tester.view.physicalSize = const Size(1440, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      for (var rotation = 0; rotation < 4; rotation++) {
        final box = [100, 52, 700, 312];
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ReviewWorkbench(
                key: ValueKey(rotation),
                specimen: Specimen({
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
                onChange: (_) async {},
                onRetry: (_) async {},
                onRefresh: () {},
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(ChoiceChip, 'Label 1'));
        await tester.pumpAndSettle();
        final rotated = tester.widget<RotatedBox>(
          find.byType(RotatedBox).first,
        );
        expect(rotated.quarterTurns, rotation);
        final aspect = tester.renderObject<RenderBox>(
          find.byType(AspectRatio).first,
        );
        final bounds = globalRect(aspect);
        expect(
          bounds.width / bounds.height,
          closeTo(rotation.isOdd ? 260 / 600 : 600 / 260, .001),
        );
        expect(box, [100, 52, 700, 312]);
        expect(tester.takeException(), isNull);
      }
    },
  );

  testWidgets(
    'a new run clears an obsolete crop selection and restores current overlays',
    (tester) async {
      tester.view.physicalSize = const Size(1440, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      Widget view(String run, String region) => MaterialApp(
        home: Scaffold(
          body: ReviewWorkbench(
            specimen: Specimen({
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
            onChange: (_) async {},
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpWidget(view('run1', 'region1'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ChoiceChip, 'Label 1'));
      await tester.pumpAndSettle();
      expect(
        find.byWidgetPredicate(
          (w) =>
              w is Image &&
              w.semanticLabel == 'Source pixels for selected label region',
        ),
        findsOneWidget,
      );
      await tester.pumpWidget(view('run2', 'region2'));
      await tester.pumpAndSettle();
      expect(
        find.byWidgetPredicate(
          (w) =>
              w is Image &&
              w.semanticLabel == 'Immutable original specimen image',
        ),
        findsOneWidget,
      );
      expect(
        find.byWidgetPredicate(
          (w) => w is Semantics && w.properties.label == 'Label region region2',
        ),
        findsOneWidget,
      );
    },
  );

  for (final viewport in [const Size(390, 844), const Size(1440, 1000)]) {
    testWidgets(
      'source retains aspect and original coordinate overlays at $viewport for all rotations',
      (tester) async {
        tester.view.physicalSize = viewport;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ReviewWorkbench(
                specimen: Specimen({
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
                onChange: (_) async {},
                onRetry: (_) async {},
                onRefresh: () {},
              ),
            ),
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
          final viewer = globalRect(
            tester.renderObject<RenderBox>(find.byType(InteractiveViewer)),
          );
          expect(rect.left, greaterThanOrEqualTo(viewer.left - .001));
          expect(rect.right, lessThanOrEqualTo(viewer.right + .001));
          expect(rect.top, greaterThanOrEqualTo(viewer.top - .001));
          expect(rect.bottom, lessThanOrEqualTo(viewer.bottom + .001));
          final overlay = find.byWidgetPredicate(
            (w) => w is Semantics && w.properties.label == 'Label region r1',
          );
          final overlayBox = tester.renderObject<RenderBox>(overlay);
          expect(
            overlayBox.size.width,
            closeTo(imageBox.size.width * .6, .001),
          );
          expect(
            overlayBox.size.height,
            closeTo(imageBox.size.height * .5, .001),
          );
          final origin = imageBox.globalToLocal(
            overlayBox.localToGlobal(Offset.zero),
          );
          expect(origin.dx, closeTo(imageBox.size.width * .1, .001));
          expect(origin.dy, closeTo(imageBox.size.height * .1, .001));
          await tester.ensureVisible(find.byTooltip('Rotate view 90 degrees'));
          await tester.tap(find.byTooltip('Rotate view 90 degrees'));
          await tester.pumpAndSettle();
        }
        expect(tester.takeException(), isNull);
      },
    );
  }
  testWidgets(
    'independent readings retain complete accessible labels and differing text',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ReviewWorkbench(
              specimen: const Specimen({
                'specimen_id': 'readings',
                'revision': 1,
                'observations': [
                  {'model_id': 'Reader A', 'literal_text': 'Chicago 1912'},
                  {'model_id': 'Reader B', 'literal_text': 'Chicago 1917'},
                ],
              }),
              onChange: (_) async {},
              onRetry: (_) async {},
              onRefresh: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      for (final literal in ['Chicago 1912', 'Chicago 1917']) {
        final text = find.byWidgetPredicate(
          (w) => w is Text && w.textSpan?.toPlainText() == literal,
        );
        expect(text, findsOneWidget);
        expect(
          find.ancestor(of: text, matching: find.byType(SelectionArea)),
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
