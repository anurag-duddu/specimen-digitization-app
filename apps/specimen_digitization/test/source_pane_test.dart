// The source pane as a surface: what it puts on the screen, and what it keeps
// off it (07 section 6.2; 09 section 2 principle 1; 11 sections 2 and 3.3).
//
// The geometry of the photograph is checked in `source_geometry_test.dart`.
// This file checks the pane's chrome: the clear band around the evidence, the
// neutral image tools and accessible label menu, and both screens at
// 200 percent text in a phone window.

import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

void main() {
  final Uint8List bytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();

  Specimen record() => Specimen(<String, dynamic>{
    'specimen_id': 'source-pane',
    'display_name': 'Synthetic source record',
    'revision': 1,
    'assets': <Json>[
      <String, dynamic>{
        'width': 1000,
        'height': 520,
        'asset_id': 'asset-1',
        'sha256': 'a' * 64,
        'preview_bytes': bytes,
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
  });

  Widget pane({
    String? selected,
    ValueChanged<String?>? onSelect,
    double? width,
    bool fullScreen = false,
    TextScaler scaler = TextScaler.noScaling,
  }) => workbenchHost(
    MediaQuery(
      data: MediaQueryData(textScaler: scaler),
      child: Center(
        child: SizedBox(
          width: width,
          child: WorkbenchSourcePane(
            specimen: record(),
            selectedRegionId: selected,
            fullScreen: fullScreen,
            onSelectRegion: onSelect ?? (String? _) {},
          ),
        ),
      ),
    ),
  );

  final Finder canvas = find.byKey(
    const ValueKey<String>('source-photo-viewport'),
  );

  final Finder photograph = find.byWidgetPredicate(
    (Widget widget) =>
        widget is Image &&
        widget.semanticLabel == 'Immutable original specimen image',
    description: 'the source photograph',
  );

  group('the neutral surface around the evidence', () {
    testWidgets('the canvas has one eight point matte inset', (tester) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane());
      await tester.pumpAndSettle();
      final Rect matte = tester.getRect(find.byType(SourceMatte));
      final Rect pixels = tester.getRect(canvas);
      final context = tester.element(find.byType(SourceMatte));
      final double inset = SourceMatte.insetOf(context.ui);
      expect(inset, 8);
      for (final double gap in <double>[
        pixels.left - matte.left,
        matte.right - pixels.right,
        pixels.top - matte.top,
        matte.bottom - pixels.bottom,
      ]) {
        expect(gap, closeTo(inset, .001));
      }
      expect(
        find.descendant(
          of: find.byType(SourceMatte),
          matching: find.byType(GlassSurface),
        ),
        findsNothing,
      );
    });

    testWidgets('the surface is painted in the neutral matte', (tester) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane());
      await tester.pumpAndSettle();
      final context = tester.element(find.byType(SourceMatte));
      final painted = tester.widget<ColoredBox>(
        find
            .descendant(
              of: find.byType(SourceMatte),
              matching: find.byType(ColoredBox),
            )
            .first,
      );
      expect(painted.color, context.ui.color.matte);
    });

    testWidgets('the fitted photograph is fully inside the canvas', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane());
      await tester.pumpAndSettle();
      final Rect viewport = tester.getRect(canvas);
      final Rect pixels = tester.getRect(photograph);
      expect(pixels.left, greaterThanOrEqualTo(viewport.left - .001));
      expect(pixels.right, lessThanOrEqualTo(viewport.right + .001));
      expect(pixels.top, greaterThanOrEqualTo(viewport.top - .001));
      expect(pixels.bottom, lessThanOrEqualTo(viewport.bottom + .001));
      expect(pixels.width / pixels.height, closeTo(1000 / 520, .00001));
    });
  });

  group('the view controls', () {
    for (final double width in <double>[1000, 200]) {
      testWidgets('retain their commands at width $width', (tester) async {
        useWindow(tester, largeWindow);
        await tester.pumpWidget(pane(width: width));
        await tester.pumpAndSettle();
        final Finder tools = uiMenuTrigger('Image tools');
        expect(tools, findsOneWidget);
        expect(uiIconButton('Open photograph'), findsOneWidget);
        // Reset is contextual: the already-fitted image has nothing to reset.
        expect(uiButton('Reset view'), findsNothing);
        expect(
          tester.getRect(canvas).contains(tester.getCenter(tools)),
          isTrue,
        );
        await tester.tap(tools);
        await tester.pumpAndSettle();
        for (final String name in <String>[
          'Zoom in',
          'Zoom out',
          'Rotate image clockwise',
        ]) {
          expect(find.text(name), findsOneWidget);
        }
        await tester.tap(find.text('Zoom in'));
        await tester.pumpAndSettle();
        final viewer = tester.widget<InteractiveViewer>(
          find.byType(InteractiveViewer),
        );
        expect(
          viewer.transformationController!.value.getMaxScaleOnAxis(),
          greaterThan(1),
        );
        expect(uiButton('Reset view'), findsOneWidget);
        await tester.tap(uiButton('Reset view'));
        await tester.pumpAndSettle();
        expect(viewer.transformationController!.value, Matrix4.identity());
        expect(uiButton('Reset view'), findsNothing);
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('the full screen label menu', () {
    testWidgets('names every region and chooses its stable identifier', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      String? chosen = 'unset';
      await tester.pumpWidget(
        pane(fullScreen: true, onSelect: (String? id) => chosen = id),
      );
      await tester.pumpAndSettle();
      final trigger = uiMenuTrigger('Choose a label');
      expect(
        tester.widget<UiMenuTrigger>(trigger).items.map((item) => item.label),
        <String>['Label 1', 'Label 2'],
      );
      await tester.tap(trigger);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Label 2'));
      await tester.pumpAndSettle();
      expect(chosen, 'r2');
    });

    testWidgets(
      'reset returns to the whole image without changing the regions',
      (tester) async {
        useWindow(tester, largeWindow);
        String? chosen = 'unset';
        await tester.pumpWidget(
          pane(
            fullScreen: true,
            selected: 'r1',
            onSelect: (String? id) => chosen = id,
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(uiButton('Reset view'));
        await tester.pumpAndSettle();
        expect(chosen, isNull);
        expect(
          tester
              .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
              .specimen
              .regions
              .map((region) => region['bbox']),
          <List<int>>[
            [100, 52, 400, 212],
            [420, 52, 700, 212],
          ],
        );
      },
    );
  });

  group('two hundred percent text in a phone window', () {
    testWidgets('the source pane lays out with no overflow', (
      WidgetTester tester,
    ) async {
      useWindow(tester, compactWindow);
      await tester.pumpWidget(pane(scaler: const TextScaler.linear(2)));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(photograph, findsOneWidget);
    });

    testWidgets('and so does the region editor', (WidgetTester tester) async {
      useWindow(tester, compactWindow);
      await tester.pumpWidget(
        workbenchHost(
          MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(2)),
            child: UiScaffold(
              sky: SkyPreset.none,
              topBar: const UiTopBar(title: regionEditorTitle),
              body: RegionEditorBody(
                regions: const <Json>[
                  <String, dynamic>{
                    'region_id': 'r1',
                    'bbox': <int>[100, 52, 700, 312],
                    'order': 0,
                    'rotation_quarter_turns': 0,
                  },
                ],
                asset: <String, dynamic>{
                  'width': 1000,
                  'height': 520,
                  'preview_bytes': bytes,
                },
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      // 13 section 4.3 gives the save to the bar, which the editor publishes
      // into the frame itself; at this text scale the bar may have put it in
      // its own overflow menu, so the assertion is on the command rather than
      // on whichever of the two arrangements the width earned.
      final UiTopBar bar = tester.widget<UiTopBar>(find.byType(UiTopBar));
      expect(
        bar.actions.whereType<UiTopBarAction>().map(
          (UiTopBarAction action) => action.label,
        ),
        contains(saveRegionsLabel),
      );
    });
  });
}
