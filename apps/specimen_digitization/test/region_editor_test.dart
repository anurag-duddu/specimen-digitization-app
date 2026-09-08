import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';

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
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  decision = await showDialog<Json>(
                    context: context,
                    builder: (_) => RegionEditor(
                      regions: source,
                      asset: {
                        'width': 1000,
                        'height': 520,
                        'preview_bytes': File(
                          'test/fixtures/synthetic-wide-label.png',
                        ).readAsBytesSync(),
                      },
                    ),
                  );
                },
                child: const Text('Edit'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Edit'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Rotate label reading 90 degrees'));
      await tester.tap(find.text('Rotate label reading 90 degrees'));
      await tester.pumpAndSettle();
      expect(find.textContaining('90° clockwise'), findsOneWidget);
      final left = find.widgetWithText(TextFormField, 'Left x');
      await tester.ensureVisible(left);
      await tester.enterText(left, '800');
      await tester.pump();
      await tester.ensureVisible(
        find.widgetWithText(TextField, 'Reason for segmentation correction'),
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Reason for segmentation correction'),
        'Correct orientation',
      );
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
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async => saved(
                await showDialog<Json>(
                  context: context,
                  builder: (_) => const RegionEditor(
                    regions: [
                      {
                        'region_id': 'small',
                        'bbox': [5, 7, 45, 57],
                        'order': 0,
                        'rotation_quarter_turns': 1,
                      },
                    ],
                    asset: {'width': 64, 'height': 96},
                  ),
                ),
              ),
              child: const Text('Edit small region'),
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
      final reason = find.widgetWithText(
        TextField,
        'Reason for segmentation correction',
      );
      await tester.ensureVisible(reason);
      await tester.enterText(reason, 'Synthetic coordinate replacement');
      final left = find.widgetWithText(TextFormField, 'Left x');
      final top = find.widgetWithText(TextFormField, 'Top y');
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
        find.text('Correct invalid pixel coordinates before saving.'),
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
        find.text('Correct invalid pixel coordinates before saving.'),
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
      expect(find.text('A reason is required.'), findsOneWidget);
      final left = find.widgetWithText(TextFormField, 'Left x');
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
      expect(find.text('A reason is required.'), findsOneWidget);
      await tester.tap(find.text('Save region version'));
      await tester.pumpAndSettle();
      expect(decision, isNull);
    },
  );
}
