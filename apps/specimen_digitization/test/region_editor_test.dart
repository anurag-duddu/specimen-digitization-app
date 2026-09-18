import 'dart:io';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/source_pixels.dart';
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

/// Presses the editor's save wherever the top bar drew it.
///
/// 13 section 4.3 puts it in the bar, and `UiTopBar` keeps the first two
/// commands as discs and puts the rest in its own overflow menu, so which of
/// the two a test finds is a property of the width rather than of the editor.
Future<void> tapEditorSave(WidgetTester tester) async {
  final Finder disc = uiIconButton(saveRegionsLabel);
  if (disc.evaluate().isNotEmpty) {
    await tester.tap(disc);
  } else {
    await tester.tap(uiMenuTrigger(UiTopBarStyle.overflowLabel));
    await tester.pumpAndSettle();
    await tester.tap(find.text(saveRegionsLabel).last);
  }
  await tester.pumpAndSettle();
}

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

    testWidgets('the photograph is the header, floored at two fifths', (
      WidgetTester tester,
    ) async {
      await pumpPhoneEditor(tester);
      // 13 section 4.3: the band is a collapsing header floored at 40
      // percent of the viewport, which is what gives a 48 dp corner handle
      // somewhere to go on a phone (finding V-7).
      final UiCollapsingHeader header = tester.widget<UiCollapsingHeader>(
        find.byType(UiCollapsingHeader),
      );
      expect(header.minFraction, sourceHeaderMinFraction);
      // The band takes what the photograph needs between the floor and the
      // 55 percent a source header starts at, so a wide label does not leave
      // half a phone of empty ground above the form.
      expect(
        header.maxFraction,
        inInclusiveRange(sourceHeaderMinFraction, sourceHeaderMaxFraction),
      );

      final Rect image = tester.getRect(find.byType(SourcePixels).first);
      expect(image.top, greaterThanOrEqualTo(0));
      expect(image.bottom, lessThanOrEqualTo(compactWindow.height));
      expect(
        image.height,
        greaterThanOrEqualTo(2 * 48),
        reason: 'a handle at each end of the box needs the room',
      );
    });

    testWidgets('the preview is the first thing and the form is beneath it', (
      WidgetTester tester,
    ) async {
      await pumpPhoneEditor(tester);
      final double image = tester
          .getSize(find.byType(SourcePixels).first)
          .height;
      // The disclosure that used to hold everything that is not the
      // photograph is gone: the header holds the pixels and the form scrolls
      // under them, which is one region per job rather than two collapse
      // controls three rows apart (13 sections 2.4 and 4.3).
      expect(find.text('Exact coordinates'), findsOneWidget);
      expect(uiField('Left x'), findsOneWidget);
      expect(image, greaterThan(compactWindow.height * 0.15));
      expect(
        tester.getRect(find.byType(SourcePixels).first).top,
        lessThan(tester.getRect(uiField('Left x')).top),
      );
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

    testWidgets('the pointer free path needs no tap, and says what is wrong', (
      WidgetTester tester,
    ) async {
      await pumpPhoneEditor(tester);
      final Finder left = uiField('Left x');
      expect(
        left,
        findsOneWidget,
        reason: 'the path WCAG 2.2 SC 2.5.7 asks for is behind nothing',
      );
      await tester.enterText(left, '');
      await tester.pump();
      // The save is the bar's, and the reason it is recorded under is at the
      // end of the scroll, so an editor that refuses has to put the sentence
      // that says why back on the screen (13 section 4.3).
      await tapEditorSave(tester);
      expect(
        find.textContaining('whole pixel numbers before you save'),
        findsOneWidget,
      );
      expect(
        tester.getRect(uiTextArea('Reason')).bottom,
        lessThanOrEqualTo(compactWindow.height),
        reason: 'the reason the save needs is off the screen',
      );
    });
  });
}
