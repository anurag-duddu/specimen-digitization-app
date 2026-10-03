// The record screen composed (13 section 4.1), measured with the instruments
// the composition gates measure it with.
//
// The gates hold every screen to the five clauses of 13 section 2. This holds
// the one screen 13 was written from to the table of 13 section 4.1, at the
// window it was written from: an aspect-correct photograph, the
// label selector and first reading under it, and the chrome inside the
// budget with everything the screen pins counted.

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/workbench.dart'
    show evidenceScrollKey;
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../composition/chrome_budget_test.dart'
    show chromeBudgetFor, chromeNow, pinnedRegionsIn;
import '../composition/composition_harness.dart';
import '../golden/golden_harness.dart';
import '../reading_region_comparison_test.dart' show selectLabel;
import '../ui_finders.dart' show uiRecordView;

/// The phone 13 section 0 measured the defect on.
const Size phone = Size(390, 844);
const Set<TargetPlatform> mobilePlatforms = <TargetPlatform>{
  TargetPlatform.iOS,
  TargetPlatform.android,
};

/// The rectangle [finder] occupies, or null where it is not laid out.
Rect? rectOfFirst(Finder finder) {
  final List<Element> found = finder.evaluate().toList();
  return found.isEmpty ? null : rectOf(found.first);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets(
    'Label review keeps the photograph and chooser above the fold; selection reveals the reading',
    (WidgetTester tester) async {
      tester.view.padding = const FakeViewPadding(top: 44, bottom: 34);
      tester.view.viewPadding = const FakeViewPadding(top: 44, bottom: 34);
      await pumpGoldenApp(
        tester,
        window: phone,
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
      );

      final labelReview = uiRecordView('Label review');
      expect(labelReview.hitTestable(), findsOneWidget);
      await tester.tap(labelReview);
      await tester.pumpAndSettle();

      expect(nativeNavigation(), findsOneWidget);
      final Rect content = contentAboveNativeNavigation(tester);
      final Rect navigation = tester.getRect(nativeNavigation());
      final Rect evidence = tester.getRect(find.byKey(evidenceScrollKey));
      final Rect decision = tester.getRect(find.byType(WorkbenchDecisionBar));
      expect(content.bottom, navigation.top);
      expect(navigation.bottom, lessThanOrEqualTo(phone.height));
      expect(evidence.top, greaterThanOrEqualTo(content.top));
      expect(evidence.height, greaterThan(0));
      expect(evidence.bottom, lessThanOrEqualTo(decision.top));
      expect(decision.bottom, lessThanOrEqualTo(content.bottom));

      final Rect matte = rectOfFirst(find.byType(SourceMatte))!;
      final photo = tester.getRect(
        find.byKey(const ValueKey('source-photo-viewport')),
      );
      expect(photo.height, closeTo(photo.width * 520 / 1000, .01));
      expect(
        photo.height,
        greaterThanOrEqualTo(sourceImageMinHeight),
        reason: 'the photograph must retain a usable pixel viewport',
      );
      expect(matte.top, greaterThanOrEqualTo(evidence.top));
      expect(matte.bottom, lessThanOrEqualTo(evidence.bottom));

      final Finder labelChooser = find.byWidgetPredicate(
        (widget) =>
            widget is UiSelect<String> &&
            widget.semanticsLabel == 'Label to review',
      );
      final Rect choose = tester.getRect(labelChooser);
      expect(choose.top, greaterThanOrEqualTo(matte.bottom));
      expect(choose.bottom, lessThanOrEqualTo(evidence.bottom));
      expect(labelChooser.hitTestable(), findsOneWidget);
      await selectLabel(tester, 1);
      final Rect reading = rectOfFirst(find.byType(DiffText))!;
      final Rect visibleEvidence = tester.getRect(
        find.byKey(evidenceScrollKey),
      );
      expect(
        reading.top,
        greaterThanOrEqualTo(visibleEvidence.top),
        reason: 'the selected reading must remain in the evidence viewport',
      );
      expect(reading.bottom, lessThanOrEqualTo(visibleEvidence.bottom));
      expect(visibleEvidence.bottom, lessThanOrEqualTo(content.bottom));
    },
    variant: TargetPlatformVariant(mobilePlatforms),
  );

  testWidgets(
    'the chrome is inside the budget with every region counted',
    (WidgetTester tester) async {
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
          expect(nativeNavigation(), findsOneWidget);
          final Element bar = nativeNavigation().evaluate().single;
          final regions = pinnedRegionsIn(compositionElements());
          expect(
            regions.where((element) => identical(element, bar)),
            hasLength(1),
          );
          final decisions = regions.where(
            (element) => element.widget is WorkbenchDecisionBar,
          );
          expect(decisions, hasLength(1));
          final double reserved =
              pinnedExtent(bar)! + pinnedExtent(decisions.single)!;
          expect(chrome.share * phone.height, greaterThanOrEqualTo(reserved));
          final Rect content = contentAboveNativeNavigation(tester);
          final Rect decision = tester.getRect(
            find.byType(WorkbenchDecisionBar),
          );
          final Rect evidence = tester.getRect(find.byKey(evidenceScrollKey));
          expect(evidence.height, greaterThan(0));
          expect(evidence.bottom, lessThanOrEqualTo(decision.top));
          expect(decision.bottom, lessThanOrEqualTo(content.bottom));
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
    },
    variant: TargetPlatformVariant(mobilePlatforms),
  );
}
