// The source pane as a surface: what it puts on the screen, and what it keeps
// off it (07 section 6.2; 09 section 2 principle 1; 11 sections 2 and 3.3).
//
// The geometry of the photograph is checked in `source_geometry_test.dart`.
// This file checks the pane's chrome: the clear band around the evidence, the
// one glass capsule of view controls and the variant it collapses into, the
// region list, and both screens at 200 percent text in a phone window.

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
            onSelectRegion: onSelect ?? (String? _) {},
          ),
        ),
      ),
    ),
  );

  final Finder matte = find.byWidgetPredicate(
    (Widget widget) => widget is Surface && widget.role == SurfaceRole.matte,
    description: 'the photograph matte',
  );

  final Finder photograph = find.byWidgetPredicate(
    (Widget widget) =>
        widget is Image &&
        widget.semanticLabel == 'Immutable original specimen image',
    description: 'the source photograph',
  );

  /// One option of the region list, which is a capsule toggle in single mode.
  Finder regionOption(String label) => find.byWidgetPredicate(
    (Widget widget) =>
        widget is Pressable &&
        widget.role == PressableRole.toggle &&
        widget.semanticsLabel == label,
    description: 'region option "$label"',
  );

  group('the clear band around the evidence', () {
    testWidgets('no colour comes within the exclusion of the matte', (
      WidgetTester tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane());
      await tester.pumpAndSettle();

      final Rect band = tester.getRect(find.byType(SourceMatte));
      final Rect letterbox = tester.getRect(matte);
      // 09 section 2, principle 1: a colour cast on a faded label is a data
      // error, so the ground reaches at least this far past the matte on
      // every side before any field, glass or tint can start.
      for (final double gap in <double>[
        letterbox.left - band.left,
        band.right - letterbox.right,
        letterbox.top - band.top,
        band.bottom - letterbox.bottom,
      ]) {
        expect(gap, greaterThanOrEqualTo(UiFields.matteExclusion));
      }
    });

    testWidgets('the band is painted in the neutral ground', (
      WidgetTester tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane());
      await tester.pumpAndSettle();

      final BuildContext context = tester.element(find.byType(SourceMatte));
      final ColoredBox painted = tester.widget<ColoredBox>(
        find
            .descendant(
              of: find.byType(SourceMatte),
              matching: find.byType(ColoredBox),
            )
            .first,
      );
      expect(painted.color, context.ui.color.ground);
    });

    testWidgets('the photograph is inset from the matte and never clipped', (
      WidgetTester tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane());
      await tester.pumpAndSettle();

      final BuildContext context = tester.element(find.byType(SourceMatte));
      final double inset = SourceMatte.insetOf(context.ui);
      final Rect letterbox = tester.getRect(matte);
      final Rect pixels = tester.getRect(photograph);
      // Twelve is what clears a 28 dp superellipse at the corner, where the
      // shape comes closest to the box inside it.
      expect(inset, greaterThanOrEqualTo(12));
      expect(pixels.left - letterbox.left, greaterThanOrEqualTo(inset - 0.001));
      expect(
        letterbox.right - pixels.right,
        greaterThanOrEqualTo(inset - 0.001),
      );
      expect(pixels.top - letterbox.top, greaterThanOrEqualTo(inset - 0.001));
      expect(
        letterbox.bottom - pixels.bottom,
        greaterThanOrEqualTo(inset - 0.001),
      );
    });
  });

  group('the view controls', () {
    testWidgets('sit in one floating glass capsule over the matte', (
      WidgetTester tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane());
      await tester.pumpAndSettle();

      final Finder capsule = find.descendant(
        of: find.byType(SourceMatte),
        matching: find.byType(GlassSurface),
      );
      expect(capsule, findsOneWidget);
      final GlassSurface glass = tester.widget<GlassSurface>(capsule);
      expect(glass.level, GlassLevel.floating);
      expect(glass.capsule, isTrue);
      // The capsule is over the matte rather than beside it, which is what
      // keeps the pane's height for the photograph.
      expect(tester.getRect(matte).contains(tester.getCenter(capsule)), isTrue);

      for (final String name in <String>[
        'Rotate the view 90 degrees',
        'Zoom in',
        'Zoom out',
        'Fit the whole photograph',
      ]) {
        expect(uiIconButton(name), findsOneWidget);
      }
    });

    testWidgets('collapse into one menu where the pane is too narrow', (
      WidgetTester tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(pane(width: 200));
      await tester.pumpAndSettle();

      expect(uiIconButton('Zoom in'), findsNothing);
      final Finder trigger = uiMenuTrigger('Photograph view controls');
      expect(trigger, findsOneWidget);

      // The same set, with the same words: a reviewer who learned the row
      // has nothing new to learn in the menu (07 section 6.2).
      await tester.tap(trigger);
      await tester.pumpAndSettle();
      for (final String name in <String>[
        'Rotate the view 90 degrees',
        'Zoom in',
        'Zoom out',
        'Fit the whole photograph',
      ]) {
        expect(find.text(name), findsOneWidget);
      }
    });
  });

  group('the region list', () {
    testWidgets('is a single mode capsule toggle including the whole image', (
      WidgetTester tester,
    ) async {
      useWindow(tester, largeWindow);
      String? chosen = 'unset';
      await tester.pumpWidget(pane(onSelect: (String? id) => chosen = id));
      await tester.pumpAndSettle();

      final UiCapsuleToggle<String?> toggle = tester
          .widget<UiCapsuleToggle<String?>>(
            find.byType(UiCapsuleToggle<String?>),
          );
      expect(toggle.selection, UiToggleSelection.single);
      expect(
        toggle.options.map((UiToggleOption<String?> o) => o.label),
        <String>['Whole image', 'Label 1', 'Label 2'],
      );

      await tester.tap(regionOption('Label 2'));
      await tester.pumpAndSettle();
      expect(chosen, 'r2');
    });

    testWidgets('choosing the region already on keeps the whole image on', (
      WidgetTester tester,
    ) async {
      useWindow(tester, largeWindow);
      String? chosen = 'unset';
      await tester.pumpWidget(pane(onSelect: (String? id) => chosen = id));
      await tester.pumpAndSettle();

      // A single mode toggle clears itself when the option already on is
      // chosen again, and the whole image is a state rather than the absence
      // of one.
      await tester.tap(regionOption('Whole image'));
      await tester.pumpAndSettle();
      expect(chosen, isNull);
    });
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
