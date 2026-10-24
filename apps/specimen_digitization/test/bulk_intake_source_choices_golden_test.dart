import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'bulk_intake_source_choices_test.dart';
import 'golden/golden_harness.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  for (final size in [const Size(390, 844), const Size(1440, 900)]) {
    for (final scale in [1.0, 2.0]) {
      for (final expanded in [false, true]) {
        testWidgets('saved source chooser $size text $scale expanded $expanded', (
          tester,
        ) async {
          await openSavedSourceChoices(tester, size: size, scale: scale);
          if (expanded) {
            await tester.ensureVisible(find.text('Import from a source'));
            await tester.tap(find.text('Import from a source'));
            await tester.pumpAndSettle();
          }
          expect(sourceButton('Close').hitTestable(), findsOneWidget);
          expect(tester.takeException(), isNull);
          await expectGoldenFinder(
            tester,
            find.byType(MaterialApp),
            'intake-add-photos-${size.width.toInt()}-dark-text$scale-${expanded ? 'sources' : 'local'}',
          );
        });
      }
    }
  }
}
