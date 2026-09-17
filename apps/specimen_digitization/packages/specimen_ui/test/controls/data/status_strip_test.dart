// `UiStatusStrip` (13 section 3.2).

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const String _summary = '2 things block clearance';
const String _first = 'Label coverage is not confirmed';
const String _second = 'The classification has no authority';
const String _correct = 'Correct label regions';

UiBlockers _blockers({VoidCallback? onAction}) => UiBlockers(
  summary: _summary,
  sheetTitle: 'What blocks clearance',
  items: <UiBlocker>[
    UiBlocker(
      label: _first,
      detail: 'Three regions cover 40 percent of the label',
      actionLabel: _correct,
      onAction: onAction ?? () {},
    ),
    const UiBlocker(label: _second),
  ],
);

Widget _strip({
  VoidCallback? onAction,
  List<String> facts = const <String>[],
}) => UiStatusStrip(
  disposition: const UiChip(label: 'Cleared'),
  facts: facts,
  blockers: _blockers(onAction: onAction),
);

void main() {
  testWidgets('satisfies the control contract through its summary', (
    WidgetTester tester,
  ) async {
    // The contract activates a control several times and never pops what it
    // opened, so the summary is given its own callback here rather than the
    // sheet: a route left on the navigator covers the control for every
    // clause after the keyboard one. The sheet has its own tests below.
    await expectControlContract(
      tester,
      (BuildContext context) => UiStatusStrip(
        disposition: const UiChip(label: 'Cleared'),
        facts: const <String>['Run 42'],
        blockers: _blockers(),
        onBlockers: () {},
      ),
      semanticsLabel: _summary,
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          // Both rungs publish the same node, so a screen reader hears the
          // same sentence at every width; only the words on screen change.
          expect(find.bySemanticsLabel(_summary), findsOneWidget);
        },
      ),
    );
  });

  testWidgets('is one line: the facts are joined and ellipsise', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(390, 844),
        child: SizedBox(
          width: 390,
          child: _strip(facts: const <String>['Run 42', 'Version 3']),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final RenderParagraph facts = tester
        .renderObjectList<RenderParagraph>(find.byType(RichText))
        .firstWhere(
          (RenderParagraph paragraph) =>
              paragraph.text.toPlainText().contains('Run 42'),
        );
    expect(
      facts.text.toPlainText(),
      contains('Version 3'),
      reason:
          'the facts are one label, so the line ellipsises at its end '
          'rather than dropping the fact the reviewer was reading',
    );
    expect(facts.maxLines, 1);
  });

  testWidgets('a strip with nothing blocking is 40 dp and has no control', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 390,
          child: UiStatusStrip(facts: <String>['Run 42']),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.bySemanticsLabel(_summary), findsNothing);
    expect(
      tester.getSize(find.byType(UiStatusStrip)).height,
      UiThemeData.light().space.s10,
      reason:
          'the strip is 40 dp of its own; a control in it is what makes '
          'it 48, because a hit box is never shrunk',
    );
  });

  testWidgets('the summary drops its word before the line overflows', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(280, 800),
        child: SizedBox(width: 280, child: _strip()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(_summary), findsNothing);
    expect(
      find.bySemanticsLabel(_summary),
      findsOneWidget,
      reason:
          'nothing is lost: the words move to the tooltip and the '
          'semantics label (11 section 3.3, rule 4)',
    );
  });

  testWidgets('the sheet lists each blocker and the control that clears it', (
    WidgetTester tester,
  ) async {
    int corrected = 0;
    await tester.pumpWidget(
      uiHarness(
        size: const Size(800, 800),
        child: SizedBox(width: 600, child: _strip(onAction: () => corrected++)),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel(_summary));
    await tester.pumpAndSettle();

    expect(find.text('What blocks clearance'), findsOneWidget);
    expect(find.text(_first), findsOneWidget);
    expect(find.text(_second), findsOneWidget);
    expect(find.text(_correct), findsOneWidget);

    await tester.tap(find.text(_first));
    await tester.pumpAndSettle();

    // The sheet closes on the way to the control: a reviewer who has chosen
    // what to correct is finished with the list of what is wrong.
    expect(corrected, 1);
    expect(find.text('What blocks clearance'), findsNothing);
  });

  testWidgets('a blocker with nothing to do is not announced as a control', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        size: const Size(800, 800),
        child: SizedBox(width: 600, child: _strip()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_summary));
    await tester.pumpAndSettle();

    final SemanticsNode node = tester.getSemantics(find.text(_second));
    expect(
      node.getSemanticsData().flagsCollection.isButton,
      isFalse,
      reason:
          'a blocker with no control is a statement, and announcing it as '
          'a button sends a reviewer looking for one that is not there',
    );
    handle.dispose();
  });
}
