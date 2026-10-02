import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('choice activation is idempotent and reset is explicit', (
    tester,
  ) async {
    int? value = 1;
    final reports = <int?>[];
    final activations = <int?>[];
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (context, setState) => UiChoiceGroup<int>(
            label: 'Review state',
            choices: const [
              UiChoice(value: 1, label: 'Needs review'),
              UiChoice(value: 2, label: 'Approved'),
            ],
            value: value,
            onChanged: (next) {
              reports.add(next);
              setState(() => value = next);
            },
            onSelected: activations.add,
          ),
        ),
      ),
    );
    await tester.tap(find.text('Needs review'));
    await tester.pump();
    expect(value, 1);
    expect(reports, isEmpty);
    expect(activations, [1]);
    await tester.tap(find.text('Reset view'));
    await tester.pump();
    expect(value, isNull);
    expect(reports, [null]);
  });

  testWidgets('choices wrap visibly and retain full target at enlarged text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: SizedBox(
          width: 320,
          child: UiChoiceGroup<int>(
            label: 'Review state',
            choices: const [
              UiChoice(value: 1, label: 'Needs review'),
              UiChoice(value: 2, label: 'Approved'),
              UiChoice(value: 3, label: 'Processing'),
            ],
            value: 1,
            onChanged: (_) {},
          ),
        ),
      ),
    );
    for (final name in ['Needs review', 'Approved', 'Processing']) {
      final target = find.bySemanticsLabel(name);
      expect(tester.getSize(target).height, greaterThanOrEqualTo(48));
      expect(tester.getRect(target).right, lessThanOrEqualTo(390));
    }
    expect(
      tester.getTopLeft(find.text('Approved')).dy,
      greaterThan(tester.getTopLeft(find.text('Needs review')).dy),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('value group is radio semantics with roving keyboard focus', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    int? value = 2;
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (context, setState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              UiChoiceGroup<int>(
                label: 'Review state',
                choices: const [
                  UiChoice(value: 1, label: 'Needs review'),
                  UiChoice(value: 2, label: 'Approved'),
                ],
                value: value,
                onChanged: (next) => setState(() => value = next),
              ),
              UiButton(label: 'Next action', onPressed: () {}),
            ],
          ),
        ),
      ),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Approved');
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Needs review');
    expect(value, 2);
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pump();
    expect(value, 1);
    final data = tester
        .getSemantics(find.bySemanticsLabel('Needs review'))
        .getSemanticsData();
    expect(data.flagsCollection.isInMutuallyExclusiveGroup, isTrue);
    expect(data.role, isNot(SemanticsRole.tab));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    expect(FocusManager.instance.primaryFocus?.debugLabel, isNot('Approved'));
    semantics.dispose();
  });
}
