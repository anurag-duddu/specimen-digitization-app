// UiCheckbox (10 section 4.2).

import 'dart:ui' show CheckedState;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const String _label = 'Label coverage';

Widget _box({
  required bool? value,
  ValueChanged<bool>? onChanged,
  String? disabledReason,
}) => UiCheckbox(
  label: _label,
  value: value,
  onChanged: onChanged,
  disabledReason: disabledReason,
);

SemanticsData _data(WidgetTester tester) =>
    tester.getSemantics(find.bySemanticsLabel(_label)).getSemanticsData();

void main() {
  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _box(value: false, onChanged: (bool _) {}),
      semanticsLabel: _label,
    );
  });

  testWidgets('an indeterminate box satisfies the contract too', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _box(value: null, onChanged: (bool _) {}),
      semanticsLabel: _label,
    );
  });

  testWidgets('a disabled box carries the reason on its hint', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _box(
        value: false,
        disabledReason: 'Open the region editor to correct these.',
      ),
      semanticsLabel: _label,
      disabledWithReason: true,
    );
  });

  testWidgets('pressing anywhere on the row checks it', (
    WidgetTester tester,
  ) async {
    bool? value = false;
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) => _box(
            value: value,
            onChanged: (bool next) => setState(() => value = next),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(_label));
    await tester.pumpAndSettle();
    expect(value, isTrue);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(value, isFalse);
  });

  testWidgets('an indeterminate box moves to checked, never back to mixed', (
    WidgetTester tester,
  ) async {
    bool? value;
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) => _box(
            value: value,
            onChanged: (bool next) => setState(() => value = next),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(
      value,
      isTrue,
      reason:
          'a reviewer pressing a partly selected group means "select all of '
          'it", and there is no way back to a state they cannot ask for',
    );
  });

  testWidgets('the node reports checked, unchecked and mixed', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      uiHarness(child: _box(value: false, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    expect(_data(tester).flagsCollection.isChecked, CheckedState.isFalse);

    await tester.pumpWidget(
      uiHarness(child: _box(value: true, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    expect(_data(tester).flagsCollection.isChecked, CheckedState.isTrue);

    await tester.pumpWidget(
      uiHarness(child: _box(value: null, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    expect(
      _data(tester).flagsCollection.isChecked,
      CheckedState.mixed,
      reason:
          'mixed says "some of this group", which is a different fact from '
          'unchecked (10 section 4.2)',
    );
    semantics.dispose();
  });

  testWidgets('the box fills when it is checked and when it is mixed', (
    WidgetTester tester,
  ) async {
    Color fill() {
      final DecoratedBox box = tester.widget<DecoratedBox>(
        find
            .descendant(
              of: find.byType(UiCheckbox),
              matching: find.byType(DecoratedBox),
            )
            .first,
      );
      return (box.decoration as ShapeDecoration).color!;
    }

    await tester.pumpWidget(
      uiHarness(child: _box(value: false, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    final UiThemeData ui = tester.element(find.byType(UiCheckbox)).ui;
    expect(fill(), ui.color.paper);

    await tester.pumpWidget(
      uiHarness(child: _box(value: true, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    expect(fill(), ui.color.ink);
    expect(
      tester.widget<UiIcon>(find.byType(UiIcon)).spec,
      UiIcons.check,
      reason: 'a checked box draws the check glyph',
    );

    await tester.pumpWidget(
      uiHarness(child: _box(value: null, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    expect(fill(), ui.color.ink);
    expect(
      find.byType(UiIcon),
      findsNothing,
      reason: 'indeterminate draws a bar, not a check (10 section 4.2)',
    );
  });

  testWidgets('a disabled box does not change', (WidgetTester tester) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: _box(
          value: false,
          disabledReason: 'Open the region editor to correct these.',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(_data(tester).flagsCollection.isChecked, CheckedState.isFalse);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(
      _data(tester).flagsCollection.isChecked,
      CheckedState.isFalse,
      reason: 'a box with nothing to call has nothing to check it',
    );
    expect(
      _data(tester).hint,
      'Open the region editor to correct these.',
      reason: 'the reason the server forbids it (03 section 3.6)',
    );
    semantics.dispose();
  });
}
