// The source pane as a surface: what it puts on the screen, and what it keeps
// off it (07 section 6.2; 09 section 2 principle 1; 11 sections 2 and 3.3).
//
// The geometry of the photograph is checked in `source_geometry_test.dart`.
// This file checks the pane's chrome: the clear band around the evidence, the
// neutral image tools and accessible label menu, and both screens at
// 200 percent text in a phone window.

import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/gestures.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

void main() {
  final Uint8List bytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();

  Specimen record({
    String id = 'source-pane',
    int revision = 1,
    bool unverifiedOrientation = false,
    int assetWidth = 1000,
    int assetHeight = 520,
  }) => Specimen(<String, dynamic>{
    'specimen_id': id,
    'display_name': 'Synthetic source record',
    'revision': revision,
    'assets': <Json>[
      <String, dynamic>{
        'width': assetWidth,
        'height': assetHeight,
        'asset_id': 'asset-1',
        'sha256': 'a' * 64,
        'preview_bytes': bytes,
        if (unverifiedOrientation) 'media_type': 'image/tiff',
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
    double? height,
    Specimen? specimen,
    SourceViewController? controller,
    bool fullScreen = false,
    TextScaler scaler = TextScaler.noScaling,
  }) => workbenchHost(
    MediaQuery(
      data: MediaQueryData(textScaler: scaler),
      child: Center(
        child: SizedBox(
          width: width,
          height: height,
          child: WorkbenchSourcePane(
            specimen: specimen ?? record(),
            selectedRegionId: selected,
            fullScreen: fullScreen,
            onSelectRegion: onSelect ?? (String? _) {},
            controller: controller,
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

  Widget review(Specimen specimen) => workbenchHost(
    ReviewWorkbench(
      specimen: specimen,
      onChange: (_) async => fail('Image inspection must not save a decision'),
      onRetry: (_) async => fail('Image inspection must not run models'),
      onRefresh: () {},
    ),
  );

  Matrix4 viewTransform(WidgetTester tester) => tester
      .widget<InteractiveViewer>(find.byType(InteractiveViewer))
      .transformationController!
      .value;

  void expectWholeImage(WidgetTester tester) {
    final Rect viewport = tester.getRect(canvas);
    final Rect pixels = tester.getRect(photograph);
    expect(pixels.left, greaterThanOrEqualTo(viewport.left - .001));
    expect(pixels.right, lessThanOrEqualTo(viewport.right + .001));
    expect(pixels.top, greaterThanOrEqualTo(viewport.top - .001));
    expect(pixels.bottom, lessThanOrEqualTo(viewport.bottom + .001));
  }

  group('opening a specimen', () {
    testWidgets('starts with the whole photograph and no chosen label', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(review(record()));
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
            .selectedRegionId,
        isNull,
      );
      await tester.tap(uiRecordView('Label review'));
      await tester.pumpAndSettle();
      expect(tester.widget<UiSelect<String>>(uiSelect('Label')).value, '');
      expect(find.text('All labels'), findsOneWidget);
      expect(viewTransform(tester), Matrix4.identity());
      expectWholeImage(tester);
    });

    testWidgets(
      'deliberate label framing survives refresh and resets on the next record',
      (tester) async {
        useWindow(tester, largeWindow);
        await tester.pumpWidget(review(record()));
        await tester.pumpAndSettle();
        await tester.tap(uiRecordView('Label review'));
        await tester.pumpAndSettle();
        await pickUiSelect(tester, 'Label', 'Label 2');
        expect(
          tester
              .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
              .selectedRegionId,
          'r2',
        );
        expect(viewTransform(tester).getMaxScaleOnAxis(), greaterThan(1));

        tester.view.physicalSize = compactWindow;
        await tester.pumpAndSettle();
        expect(
          tester
              .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
              .selectedRegionId,
          'r2',
        );
        expect(viewTransform(tester).getMaxScaleOnAxis(), greaterThan(1));
        tester.view.physicalSize = largeWindow;
        await tester.pumpAndSettle();

        await tester.pumpWidget(review(record(revision: 2)));
        await tester.pumpAndSettle();
        expect(
          tester
              .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
              .selectedRegionId,
          'r2',
        );
        expect(viewTransform(tester).getMaxScaleOnAxis(), greaterThan(1));

        await tester.pumpWidget(review(record(id: 'next-source')));
        await tester.pumpAndSettle();
        expect(
          tester
              .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
              .selectedRegionId,
          isNull,
        );
        expect(viewTransform(tester), Matrix4.identity());
        expectWholeImage(tester);
        expect(tester.widget<UiTabs>(uiTabs('Record view')).selected.value, 0);
        await tester.tap(uiRecordView('Label review'));
        await tester.pumpAndSettle();
        expect(tester.widget<UiSelect<String>>(uiSelect('Label')).value, '');
        expect(tester.takeException(), isNull);
      },
    );
  });

  group('the inspection cursor', () {
    testWidgets('revalidates a stationary pointer after zoom and rotation', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      final controller = SourceViewController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(pane(controller: controller));
      await tester.pumpAndSettle();
      final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await mouse.addPointer(location: Offset.zero);
      addTearDown(mouse.removePointer);
      final pixels = tester.getRect(photograph);
      await mouse.moveTo(pixels.center);
      await tester.pumpAndSettle();

      controller.zoomIn();
      await tester.pumpAndSettle();
      expect(tester.getCenter(find.byType(RawMagnifier)), pixels.center);
      controller.fit();
      await tester.pumpAndSettle();
      final edge = Offset(pixels.left + 1, pixels.center.dy);
      await mouse.moveTo(edge);
      await tester.pumpAndSettle();
      expect(tester.getCenter(find.byType(RawMagnifier)), edge);

      controller.zoomOut();
      await tester.pumpAndSettle();
      expect(find.byType(RawMagnifier), findsNothing);
      expect(
        RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
        SystemMouseCursors.basic,
      );
      controller.fit();
      await tester.pumpAndSettle();
      expect(tester.getCenter(find.byType(RawMagnifier)), edge);
      controller.rotate();
      await tester.pumpAndSettle();
      expect(find.byType(RawMagnifier), findsNothing);
      expect(
        RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
        SystemMouseCursors.basic,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('keeps screen alignment on resize and rechecks a new source', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane(width: 600));
      await tester.pumpAndSettle();
      final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await mouse.addPointer(location: Offset.zero);
      addTearDown(mouse.removePointer);
      final point = tester.getCenter(photograph);
      await mouse.moveTo(point);
      await tester.pumpAndSettle();

      await tester.pumpWidget(pane(width: 600, height: 550));
      await tester.pumpAndSettle();
      expect(tester.getCenter(find.byType(RawMagnifier)), point);
      expect(
        RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
        SystemMouseCursors.none,
      );
      final pixels = tester.getRect(photograph);
      await mouse.moveTo(Offset(pixels.left + 1, pixels.center.dy));
      await tester.pumpAndSettle();
      expect(find.byType(RawMagnifier), findsOneWidget);

      await tester.pumpWidget(
        pane(
          width: 600,
          height: 550,
          specimen: record(
            id: 'portrait-source',
            assetWidth: 520,
            assetHeight: 1000,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(RawMagnifier), findsNothing);
      expect(
        RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
        SystemMouseCursors.basic,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'centres the lens on the mouse and restores cursors outside the photograph',
      (tester) async {
        useWindow(tester, largeWindow);
        await tester.pumpWidget(pane());
        await tester.pumpAndSettle();
        final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
        await mouse.addPointer(location: Offset.zero);
        addTearDown(mouse.removePointer);
        final Rect pixels = tester.getRect(photograph);
        final Offset point = pixels.center;
        await mouse.moveTo(point);
        await tester.pumpAndSettle();

        expect(tester.getCenter(find.byType(RawMagnifier)), point);
        expect(
          tester
              .widget<RawMagnifier>(find.byType(RawMagnifier))
              .focalPointOffset,
          Offset.zero,
        );
        expect(
          RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
          SystemMouseCursors.none,
        );
        final Offset edge = Offset(pixels.left + 1, pixels.center.dy);
        await mouse.moveTo(edge);
        await tester.pumpAndSettle();
        expect(tester.getCenter(find.byType(RawMagnifier)), edge);

        await mouse.moveTo(tester.getCenter(uiMenuTrigger('Image tools')));
        await tester.pumpAndSettle();
        expect(find.byType(RawMagnifier), findsNothing);
        expect(
          RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
          isNot(SystemMouseCursors.none),
        );
        await mouse.moveTo(Offset.zero);
        await tester.pumpAndSettle();
        expect(find.byType(RawMagnifier), findsNothing);
        expect(
          RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
          SystemMouseCursors.basic,
        );
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets('keeps label clicks available beneath the lens', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      String? chosen;
      await tester.pumpWidget(pane(onSelect: (id) => chosen = id));
      await tester.pumpAndSettle();
      final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await mouse.addPointer(location: Offset.zero);
      addTearDown(mouse.removePointer);
      final Rect pixels = tester.getRect(photograph);
      final Offset label = Offset(
        pixels.left + pixels.width * .25,
        pixels.top + pixels.height * .25,
      );
      await mouse.moveTo(label);
      await tester.pumpAndSettle();
      expect(tester.getCenter(find.byType(RawMagnifier)), label);
      expect(
        RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1),
        SystemMouseCursors.none,
      );
      await mouse.down(label);
      await mouse.up();
      await tester.pumpAndSettle();
      expect(chosen, 'r1');
      expect(find.byType(RawMagnifier), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  group('the neutral surface around the evidence', () {
    testWidgets('a wide photograph uses the whole available pane viewport', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      const Size available = Size(600, 700);
      await tester.pumpWidget(
        workbenchHost(
          Center(
            child: SizedBox.fromSize(
              size: available,
              child: WorkbenchSourcePane(
                specimen: record(),
                selectedRegionId: null,
                onSelectRegion: (_) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.getSize(find.byType(SourceMatte)), available);
      expect(tester.getSize(canvas), const Size(584, 684));
      expectWholeImage(tester);
      expect(viewTransform(tester), Matrix4.identity());
      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'a short pane keeps its orientation caveat and image scrollable',
      (tester) async {
        useWindow(tester, largeWindow);
        await tester.pumpWidget(
          workbenchHost(
            Center(
              child: SizedBox(
                width: 320,
                height: 100,
                child: WorkbenchSourcePane(
                  specimen: record(unverifiedOrientation: true),
                  selectedRegionId: null,
                  onSelectRegion: (_) {},
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.byType(SourceOrientationCaveat), findsOneWidget);
        expect(
          find.descendant(
            of: find.byType(WorkbenchSourcePane),
            matching: find.byType(SingleChildScrollView),
          ),
          findsOneWidget,
        );
        expect(tester.getSize(canvas).height, 120);
        expectWholeImage(tester);
        expect(tester.takeException(), isNull);
      },
    );

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
