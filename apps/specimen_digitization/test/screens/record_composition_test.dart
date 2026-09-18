// The record screen composed (13 section 4.1), measured with the instruments
// the composition gates measure it with.
//
// The gates hold every screen to the five clauses of 13 section 2. This holds
// the one screen 13 was written from to the table of 13 section 4.1, at the
// window it was written from: the photograph at two fifths of a phone, the
// status strip and the first reading under it, and the chrome inside the
// budget with everything the screen pins counted.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../composition/chrome_budget_test.dart' show chromeBudgetFor, chromeNow;
import '../composition/composition_harness.dart';
import '../golden/golden_harness.dart';

/// The phone 13 section 0 measured the defect on.
const Size phone = Size(390, 844);

/// The rectangle [finder] occupies, or null where it is not laid out.
Rect? rectOfFirst(Finder finder) {
  final List<Element> found = finder.evaluate().toList();
  return found.isEmpty ? null : rectOf(found.first);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('the photograph, the strip and the first reading are above the '
      'fold at 390 by 844', (WidgetTester tester) async {
    await pumpGoldenApp(
      tester,
      window: phone,
      brightness: Brightness.light,
      location: goldenSpecimenLocation,
    );

    final Rect matte = rectOfFirst(find.byType(SourceMatte))!;
    final double shown =
        (matte.bottom < phone.height ? matte.bottom : phone.height) - matte.top;
    expect(
      shown,
      greaterThanOrEqualTo(phone.height * sourceHeaderMinFraction),
      reason:
          'the photograph shows ${shown.round()} dp and 13 section 4.1 gives '
          'it 40 percent of the viewport, which is '
          '${(phone.height * sourceHeaderMinFraction).round()}',
    );

    final Rect strip = rectOfFirst(find.byType(WorkbenchStatusStrip))!;
    expect(
      strip.top,
      inInclusiveRange(matte.bottom, phone.height),
      reason:
          'the status strip is not under the photograph on the first '
          'viewport',
    );

    final Rect reading = rectOfFirst(find.byType(ReadingCard))!;
    expect(
      reading.top,
      inInclusiveRange(strip.top, phone.height),
      reason:
          'the first reading is not on the first viewport, which is the '
          'sentence 13 section 0 was written from',
    );
  });

  testWidgets('the chrome is inside the budget with every region counted', (
    WidgetTester tester,
  ) async {
    const String window = 'compact-390x844';
    double worst = 0;
    String parts = '';
    await overCell(
      tester,
      screen: compositionScreens.firstWhere(
        (CompositionScreen screen) => screen.name == 'record',
      ),
      window: phone,
      measure: (String where) async {
        final ({double share, String parts, List<String> problems}) chrome =
            chromeNow(phone.height);
        expect(chrome.problems, isEmpty, reason: chrome.problems.join(' '));
        if (chrome.share > worst) {
          worst = chrome.share;
          parts = '$where: ${chrome.parts}';
        }
      },
    );
    expect(
      worst,
      lessThanOrEqualTo(chromeBudgetFor(window)),
      reason:
          'the record pins ${(worst * 100).toStringAsFixed(1)} percent of the '
          'viewport and 13 section 2.3 allows 28. The regions are $parts.',
    );
  });
}
