import 'dart:io';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/source_pixels.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

/// The field named [label], by the name it publishes rather than by a
/// Material type.
Finder uiField(String label) => find.byWidgetPredicate(
  (Widget widget) => widget is UiField && widget.label == label,
  description: 'UiField("$label")',
);

/// The text area named [label]. The reason is the only one in this editor.
Finder uiTextArea(String label) => find.byWidgetPredicate(
  (Widget widget) => widget is UiTextArea && widget.label == label,
  description: 'UiTextArea("$label")',
);

/// One option of the region list, which is a capsule toggle in single mode.
Finder regionOption(String label) => find.byWidgetPredicate(
  (Widget widget) =>
      widget is Pressable &&
      widget.role == PressableRole.toggle &&
      widget.semanticsLabel == label,
  description: 'region option "$label"',
);

/// A trigger that opens the editor, so each test says what it presses.
Widget opener(String label, Future<void> Function(BuildContext) onPressed) =>
    Builder(
      builder: (BuildContext context) => Center(
        child: UiButton(label: label, onPressed: () => onPressed(context)),
      ),
    );

void main() {
  testWidgets(
    'label rotation retains original bounds and invalid edits cannot save',
    (tester) async {
      Json? decision;
      final source = <Json>[
        {
          'region_id': 'r',
          'bbox': [100, 52, 700, 312],
          'order': 0,
          'rotation_quarter_turns': 0,
        },
      ];
      useWindow(tester, largeWindow);
      await tester.pumpWidget(
        workbenchHost(
          opener('Edit', (BuildContext context) async {
            decision = await showUiDialog<Json>(
              context: context,
              semanticsLabel: regionEditorTitle,
              builder: (_) => RegionEditor(
                regions: source,
                asset: <String, dynamic>{
                  'width': 1000,
                  'height': 520,
                  'preview_bytes': File(
                    'test/fixtures/synthetic-wide-label.png',
                  ).readAsBytesSync(),
                },
              ),
            );
          }),
        ),
      );
      await tester.tap(find.text('Edit'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Rotate label reading 90 degrees'));
      await tester.tap(find.text('Rotate label reading 90 degrees'));
      await tester.pumpAndSettle();
      expect(find.textContaining('90 degrees clockwise'), findsOneWidget);
      final left = uiField('Left x');
      await tester.ensureVisible(left);
      await tester.enterText(left, '800');
      await tester.pump();
      await tester.ensureVisible(uiTextArea('Reason'));
      await tester.enterText(uiTextArea('Reason'), 'Correct orientation');
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(find.textContaining('positive area'), findsOneWidget);
      expect(decision, isNull);
      await tester.ensureVisible(left);
      await tester.enterText(left, '100');
      await tester.pump();
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(decision?['regions'][0]['rotation_quarter_turns'], 1);
      expect(decision?['regions'][0]['bbox'], [100, 52, 700, 312]);
      expect(source[0]['rotation_quarter_turns'], 0);
      expect(source[0]['bbox'], [100, 52, 700, 312]);
      expect(tester.takeException(), isNull);
    },
  );
  Future<void> openSmallEditor(
    WidgetTester tester,
    void Function(Json?) saved,
  ) async {
    useWindow(tester, largeWindow);
    await tester.pumpWidget(
      workbenchHost(
        opener(
          'Edit small region',
          (BuildContext context) async => saved(
            await showUiDialog<Json>(
              context: context,
              semanticsLabel: regionEditorTitle,
              builder: (_) => const RegionEditor(
                regions: <Json>[
                  <String, dynamic>{
                    'region_id': 'small',
                    'bbox': <int>[5, 7, 45, 57],
                    'order': 0,
                    'rotation_quarter_turns': 1,
                  },
                ],
                asset: <String, dynamic>{'width': 64, 'height': 96},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Edit small region'));
    await tester.pumpAndSettle();
  }

  testWidgets(
    'coordinate parse errors clear only after every input is valid and preserve saved geometry',
    (tester) async {
      Json? decision;
      await openSmallEditor(tester, (value) => decision = value);
      final reason = uiTextArea('Reason');
      await tester.ensureVisible(reason);
      await tester.enterText(reason, 'Synthetic coordinate replacement');
      final left = uiField('Left x');
      final top = uiField('Top y');
      await tester.ensureVisible(left);
      await tester.enterText(left, '');
      await tester.pump();
      expect(
        find.text('Coordinates must be whole pixel numbers.'),
        findsOneWidget,
      );
      await tester.enterText(top, '');
      await tester.enterText(left, '5');
      await tester.pump();
      expect(
        find.text('Coordinates must be whole pixel numbers.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(
        find.text('Enter whole pixel numbers before you save.'),
        findsOneWidget,
      );
      expect(decision, isNull);
      await tester.ensureVisible(top);
      await tester.enterText(top, '7');
      await tester.pump();
      expect(
        find.text('Coordinates must be whole pixel numbers.'),
        findsNothing,
      );
      expect(
        find.text('Enter whole pixel numbers before you save.'),
        findsNothing,
      );
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(decision?['regions'][0]['bbox'], [5, 7, 45, 57]);
      expect(decision?['regions'][0]['rotation_quarter_turns'], 1);
      expect(decision?['reason'], 'Synthetic coordinate replacement');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'correcting numeric input does not erase an unrelated validation error',
    (tester) async {
      Json? decision;
      await openSmallEditor(tester, (value) => decision = value);
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(find.text('Enter a reason for this decision.'), findsOneWidget);
      final left = uiField('Left x');
      await tester.ensureVisible(left);
      await tester.enterText(left, '');
      await tester.pump();
      expect(
        find.text('Coordinates must be whole pixel numbers.'),
        findsOneWidget,
      );
      await tester.enterText(left, '5');
      await tester.pump();
      expect(
        find.text('Coordinates must be whole pixel numbers.'),
        findsNothing,
      );
      expect(find.text('Enter a reason for this decision.'), findsOneWidget);
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(decision, isNull);
    },
  );

  testWidgets('delete is undoable inside the editor', (tester) async {
    useWindow(tester, largeWindow);
    Json? decision;
    await tester.pumpWidget(
      workbenchHost(
        opener(
          'Edit regions',
          (BuildContext context) async => decision = await showRegionEditor(
            context,
            regions: const <Json>[
              <String, dynamic>{
                'region_id': 'a',
                'bbox': <int>[0, 0, 20, 20],
                'order': 0,
              },
              <String, dynamic>{
                'region_id': 'b',
                'bbox': <int>[20, 20, 40, 40],
                'order': 1,
              },
            ],
            asset: const <String, dynamic>{'width': 64, 'height': 96},
          ),
        ),
      ),
    );
    await tester.tap(find.text('Edit regions'));
    await tester.pumpAndSettle();
    expect(regionOption('Label 2'), findsOneWidget);

    await tester.ensureVisible(uiIconButton('Delete region'));
    await tester.tap(uiIconButton('Delete region'));
    await tester.pumpAndSettle();
    expect(regionOption('Label 2'), findsNothing);

    // A local delete is reversible without closing the editor
    // (pass criterion 3.5).
    await tester.ensureVisible(find.text('Undo delete label region'));
    await tester.tap(find.text('Undo delete label region'));
    await tester.pumpAndSettle();
    expect(regionOption('Label 2'), findsOneWidget);
    expect(decision, isNull);
  });

  testWidgets('merge is undoable and restores both regions', (tester) async {
    useWindow(tester, largeWindow);
    Json? decision;
    await tester.pumpWidget(
      workbenchHost(
        opener(
          'Edit regions',
          (BuildContext context) async => decision = await showRegionEditor(
            context,
            regions: const <Json>[
              <String, dynamic>{
                'region_id': 'a',
                'bbox': <int>[0, 0, 20, 20],
                'order': 0,
              },
              <String, dynamic>{
                'region_id': 'b',
                'bbox': <int>[30, 30, 40, 40],
                'order': 1,
              },
            ],
            asset: const <String, dynamic>{'width': 64, 'height': 96},
          ),
        ),
      ),
    );
    await tester.tap(find.text('Edit regions'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Merge with next'));
    await tester.tap(find.text('Merge with next'));
    await tester.pumpAndSettle();
    expect(regionOption('Label 2'), findsNothing);
    await tester.ensureVisible(
      find.text('Undo merge with the next label region'),
    );
    await tester.tap(find.text('Undo merge with the next label region'));
    await tester.pumpAndSettle();
    expect(regionOption('Label 2'), findsOneWidget);

    await tester.ensureVisible(uiTextArea('Reason'));
    await tester.enterText(uiTextArea('Reason'), 'Kept both label regions');
    await tester.tap(find.text('Save region version'));
    await tester.pumpAndSettle();
    expect(decision?['regions'], hasLength(2));
    expect(decision!['regions'][0]['bbox'], [0, 0, 20, 20]);
    expect(decision!['regions'][1]['bbox'], [30, 30, 40, 40]);
  });

  testWidgets('saving with no regions is refused, with the reason', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    Json? decision;
    await tester.pumpWidget(
      workbenchHost(
        opener(
          'Edit regions',
          (BuildContext context) async => decision = await showRegionEditor(
            context,
            regions: const <Json>[
              <String, dynamic>{
                'region_id': 'only',
                'bbox': <int>[0, 0, 20, 20],
                'order': 0,
              },
            ],
            asset: const <String, dynamic>{'width': 64, 'height': 96},
          ),
        ),
      ),
    );
    await tester.tap(find.text('Edit regions'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(uiIconButton('Delete region'));
    await tester.tap(uiIconButton('Delete region'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(uiTextArea('Reason'));
    await tester.enterText(uiTextArea('Reason'), 'Removed the only region');
    await tester.tap(find.text('Save region version'));
    await tester.pumpAndSettle();
    // A record cannot be saved into a structurally impossible state
    // (pass criterion 5.3), and the refusal says what to do.
    expect(
      find.textContaining('A record needs at least one label region'),
      findsOneWidget,
    );
    expect(decision, isNull);
  });

  testWidgets('a corner handle is draggable and a full sized target', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    Json? saved;
    await tester.pumpWidget(
      workbenchHost(
        opener(
          'Edit regions',
          (BuildContext context) async => saved = await showRegionEditor(
            context,
            regions: <Json>[
              <String, dynamic>{
                'region_id': 'r',
                'bbox': <int>[100, 52, 700, 312],
                'order': 0,
              },
            ],
            asset: <String, dynamic>{
              'width': 1000,
              'height': 520,
              'preview_bytes': File(
                'test/fixtures/synthetic-wide-label.png',
              ).readAsBytesSync(),
            },
          ),
        ),
      ),
    );
    await tester.tap(find.text('Edit regions'));
    await tester.pumpAndSettle();
    final handle = find.bySemanticsLabel('Label 1 top left corner');
    expect(handle, findsOneWidget);
    // The visible square is small; the target never is.
    final size = tester.getSize(handle);
    expect(size.width, greaterThanOrEqualTo(48));
    expect(size.height, greaterThanOrEqualTo(48));

    // Horizontal only, and past the pan slop: a vertical component would be
    // claimed by the surrounding scroll view before the handle saw it.
    final TestGesture gesture = await tester.startGesture(
      tester.getCenter(handle),
    );
    for (var step = 0; step < 6; step++) {
      await gesture.moveBy(const Offset(10, 0));
      await tester.pump();
    }
    await gesture.up();
    await tester.pumpAndSettle();
    // Direct manipulation and the pointer-free path are one state, not two:
    // the drag is readable in the saved coordinates.
    await tester.ensureVisible(uiTextArea('Reason'));
    await tester.enterText(uiTextArea('Reason'), 'Resized by hand');
    await tester.tap(find.text('Save region version'));
    await tester.pumpAndSettle();
    expect(saved!['regions'][0]['bbox'][0], isNot(100));
  });

  // Finding V-7. On a phone the photograph was a thin strip between the
  // region chips and the coordinate form, which is not enough to drag a
  // corner handle on. These four hold the fix the verification report asked
  // for: a floored preview, the coordinate form behind a disclosure, the
  // handles still at a full target, and the pointer free path still reachable.
  group('finding V-7, the editor on a phone', () {
    Json wideAsset() => <String, dynamic>{
      'width': 1000,
      'height': 520,
      'preview_bytes': File(
        'test/fixtures/synthetic-wide-label.png',
      ).readAsBytesSync(),
    };

    List<Json> oneRegion() => <Json>[
      <String, dynamic>{
        'region_id': 'r',
        'bbox': <num>[100, 52, 700, 312],
        'order': 0,
        'rotation_quarter_turns': 0,
      },
    ];

    Future<void> pumpPhoneEditor(WidgetTester tester) async {
      useWindow(tester, compactWindow);
      await tester.pumpWidget(
        workbenchHost(
          UiScaffold(
            sky: SkyPreset.none,
            topBar: const UiTopBar(title: regionEditorTitle),
            body: RegionEditorBody(regions: oneRegion(), asset: wideAsset()),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('the photograph gets the height the report specifies', (
      WidgetTester tester,
    ) async {
      await pumpPhoneEditor(tester);
      final Finder preview = find.byType(RegionOverlay).first;
      final Rect band = tester.getRect(
        find.ancestor(of: preview, matching: find.byType(SizedBox)).last,
      );
      expect(
        band.height,
        greaterThanOrEqualTo(RegionEditorBody.compactPreviewMinHeight),
        reason:
            'the compact preview is floored so a 48 dp handle has room; '
            'finding V-7',
      );
    });

    testWidgets('the preview is the dominant element of the sheet', (
      WidgetTester tester,
    ) async {
      await pumpPhoneEditor(tester);
      final double image = tester
          .getSize(find.byType(SourcePixels).first)
          .height;
      // Everything that is not the photograph and not the footer now sits
      // behind one closed disclosure, so nothing else on the scrolled body
      // is taller than the pixels.
      expect(find.text('Exact coordinates'), findsNothing);
      expect(uiField('Left x'), findsNothing);
      expect(find.text(RegionEditorBody.coordinatesTitle), findsOneWidget);
      expect(image, greaterThan(compactWindow.height * 0.15));
    });

    testWidgets('every corner handle is still a full target', (
      WidgetTester tester,
    ) async {
      await pumpPhoneEditor(tester);
      final Finder handles = find.bySemanticsLabel(
        RegExp('Label 1 (top|bottom) (left|right) corner'),
      );
      expect(handles, findsNWidgets(4));
      for (final Element element in handles.evaluate()) {
        final Size size = tester.getSize(
          find.byElementPredicate((Element e) => e == element),
        );
        expect(size.width, greaterThanOrEqualTo(48));
        expect(size.height, greaterThanOrEqualTo(48));
      }
    });

    testWidgets('the pointer free path is one tap away, and opens on error', (
      WidgetTester tester,
    ) async {
      await pumpPhoneEditor(tester);
      final Finder disclosure = find.text(RegionEditorBody.coordinatesTitle);
      await tester.ensureVisible(disclosure);
      await tester.tap(disclosure);
      await tester.pumpAndSettle();
      final Finder left = uiField('Left x');
      expect(left, findsOneWidget);
      await tester.enterText(left, '');
      await tester.pump();
      // Close it again, then ask to save: the editor has to bring the field
      // that is wrong back on screen rather than reporting an error about
      // something the reviewer cannot see.
      await tester.ensureVisible(disclosure);
      await tester.tap(disclosure);
      await tester.pumpAndSettle();
      expect(uiField('Left x'), findsNothing);
      await tester.ensureVisible(find.text('Save region version'));
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(uiField('Left x'), findsOneWidget);
      expect(
        find.textContaining('whole pixel numbers before you save'),
        findsOneWidget,
      );
    });
  });
}
