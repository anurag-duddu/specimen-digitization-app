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
}
