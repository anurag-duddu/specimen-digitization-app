// UiSwitch (10 section 4.2).

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const String _label = 'Announce decisions';

Widget _switch({
  required bool value,
  ValueChanged<bool>? onChanged,
  String? disabledReason,
}) => UiSwitch(
  label: _label,
  value: value,
  onChanged: onChanged,
  disabledReason: disabledReason,
);

AlignmentGeometry _thumb(WidgetTester tester) =>
    tester.widget<AnimatedAlign>(find.byType(AnimatedAlign)).alignment;

void main() {
  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _switch(value: true, onChanged: (bool _) {}),
      semanticsLabel: _label,
    );
  });

  testWidgets('a disabled switch carries the reason on its hint', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _switch(
        value: true,
        disabledReason: 'Turn on a screen reader to use this.',
      ),
      semanticsLabel: _label,
      disabledWithReason: true,
    );
  });

  testWidgets('pressing anywhere on the row toggles it', (
    WidgetTester tester,
  ) async {
    bool value = false;
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (BuildContext context, StateSetter setState) => _switch(
            value: value,
            onChanged: (bool next) => setState(() => value = next),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // The label, not the track: the whole row is the hit box.
    await tester.tap(find.text(_label));
    await tester.pumpAndSettle();
    expect(value, isTrue);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(value, isFalse);
  });

  testWidgets('the node reports toggled rather than checked', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: _switch(value: true, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel(_label))
        .getSemanticsData();
    expect(data.flagsCollection.isToggled, Tristate.isTrue);
    expect(data.flagsCollection.isEnabled, Tristate.isTrue);
    semantics.dispose();
  });

  testWidgets('the thumb glides to the end when it is on', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _switch(value: false, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    expect(_thumb(tester), AlignmentDirectional.centerStart);

    await tester.pumpWidget(
      uiHarness(child: _switch(value: true, onChanged: (bool _) {})),
    );
    await tester.pumpAndSettle();
    expect(_thumb(tester), AlignmentDirectional.centerEnd);
  });

  testWidgets('under reduced motion the thumb jumps rather than glides', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        disableAnimations: true,
        child: _switch(value: false, onChanged: (bool _) {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.widget<AnimatedAlign>(find.byType(AnimatedAlign)).duration,
      Duration.zero,
      reason: '09 section 8: the thumb appears at the new position',
    );
    await tester.pumpWidget(
      uiHarness(
        disableAnimations: true,
        child: _switch(value: true, onChanged: (bool _) {}),
      ),
    );
    await tester.pump();
    expect(
      tester.binding.transientCallbackCount,
      0,
      reason: 'a zero duration never starts a ticker',
    );
  });

  testWidgets('the thumb travels the reading direction under RTL', (
    WidgetTester tester,
  ) async {
    Future<double> thumbCentre(TextDirection direction) async {
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: _switch(value: true, onChanged: (bool _) {}),
        ),
      );
      await tester.pumpAndSettle();
      return tester.getCenter(find.byType(AnimatedAlign)).dx -
          tester
              .getCenter(
                find.descendant(
                  of: find.byType(AnimatedAlign),
                  matching: find.byType(DecoratedBox),
                ),
              )
              .dx;
    }

    expect(
      (await thumbCentre(TextDirection.ltr)).sign,
      -(await thumbCentre(TextDirection.rtl)).sign,
      reason: 'on means "at the end of the row", which flips under RTL',
    );
  });

  testWidgets('a disabled switch does not move', (WidgetTester tester) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: _switch(
          value: false,
          disabledReason: 'Turn on a screen reader to use this.',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(_thumb(tester), AlignmentDirectional.centerStart);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(
      _thumb(tester),
      AlignmentDirectional.centerStart,
      reason: 'a switch with nothing to call has nothing to move it',
    );
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel(_label))
        .getSemanticsData();
    expect(data.flagsCollection.isEnabled, Tristate.isFalse);
    expect(data.hint, 'Turn on a screen reader to use this.');
    semantics.dispose();
  });
}
