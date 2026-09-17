// `Pressable` owns the control contract, so it is the one primitive whose
// test is the contract itself plus the behaviour the contract does not reach.

import 'package:flutter/gestures.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// A pressable that paints a box and records the states it was handed.
Widget _box(
  BuildContext context, {
  VoidCallback? onPressed,
  String? disabledReason,
  bool capsule = false,
  bool scaleOnPress = false,
  ValueChanged<Set<WidgetState>>? onStates,
  ValueChanged<String>? onDisabledReason,
}) {
  final UiThemeData ui = context.ui;
  return Pressable(
    semanticsLabel: 'Approve record',
    onPressed: onPressed,
    disabledReason: disabledReason,
    onDisabledReason: onDisabledReason,
    capsule: capsule,
    scaleOnPress: scaleOnPress,
    builder: (BuildContext context, Set<WidgetState> states) {
      onStates?.call(states);
      return SizedBox(
        width: 120,
        height: 40,
        child: DecoratedBox(
          decoration: ShapeDecoration(
            shape: ui.shape.capsule,
            color: ui.color.paper,
          ),
          child: Center(child: Text('Approve', style: ui.type.label)),
        ),
      );
    },
  );
}

void main() {
  // A hover state only exists where there is a pointer, and
  // `FocusableActionDetector` suppresses both highlights under
  // `FocusHighlightMode.touch`. A test that wants to see a hover has to say
  // it is on a pointer window, the way a real one is when a mouse moves.
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _box(context, onPressed: () {}),
      semanticsLabel: 'Approve record',
    );
  });

  testWidgets('a disabled control satisfies the contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _box(
        context,
        disabledReason: 'Confirm label coverage before you approve.',
      ),
      semanticsLabel: 'Approve record',
      disabledWithReason: true,
    );
  });

  testWidgets('the hit box pads a 40 dp visual to 48', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) => _box(context, onPressed: () {}),
        ),
      ),
    );
    expect(tester.getSize(find.byType(Pressable)).height, UiDensity.hitBox);
    // The visual keeps its own size; the extra is transparent slop.
    expect(tester.getSize(find.byType(SizedBox).first).height, 40);
  });

  testWidgets('a tap fires the callback and a disabled tap does not', (
    WidgetTester tester,
  ) async {
    int pressed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) =>
              _box(context, onPressed: () => pressed++),
        ),
      ),
    );
    await tester.tap(find.byType(Pressable));
    await tester.pumpAndSettle();
    expect(pressed, 1);

    String? reason;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) => _box(
            context,
            disabledReason: 'Waiting for label coverage.',
            onDisabledReason: (String r) => reason = r,
          ),
        ),
      ),
    );
    await tester.tap(find.byType(Pressable));
    await tester.pumpAndSettle();
    expect(pressed, 1, reason: 'a disabled control does nothing');
    expect(
      reason,
      'Waiting for label coverage.',
      reason:
          'the reason is handed to whatever will show it, so a tooltip can '
          'carry it without this primitive owning an overlay',
    );
  });

  testWidgets('hover and press reach the builder as states', (
    WidgetTester tester,
  ) async {
    late Set<WidgetState> seen;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) => _box(
            context,
            onPressed: () {},
            onStates: (Set<WidgetState> s) => seen = s,
          ),
        ),
      ),
    );
    expect(seen, isEmpty);

    final TestGesture pointer = await tester.createGesture(
      kind: PointerDeviceKind.mouse,
    );
    await pointer.addPointer(location: Offset.zero);
    addTearDown(pointer.removePointer);
    await tester.pump();
    await pointer.moveTo(tester.getCenter(find.byType(Pressable)));
    await tester.pumpAndSettle();
    expect(seen, contains(WidgetState.hovered));

    final TestGesture press = await tester.startGesture(
      tester.getCenter(find.byType(Pressable)),
    );
    await tester.pump();
    expect(seen, contains(WidgetState.pressed));
    await press.up();
    await tester.pumpAndSettle();
    expect(seen, isNot(contains(WidgetState.pressed)));
  });

  testWidgets('a disabled control is never hovered or pressed', (
    WidgetTester tester,
  ) async {
    late Set<WidgetState> seen;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) => _box(
            context,
            disabledReason: 'Not yet.',
            onStates: (Set<WidgetState> s) => seen = s,
          ),
        ),
      ),
    );
    final TestGesture pointer = await tester.createGesture(
      kind: PointerDeviceKind.mouse,
    );
    await pointer.addPointer(location: Offset.zero);
    addTearDown(pointer.removePointer);
    await tester.pump();
    await pointer.moveTo(tester.getCenter(find.byType(Pressable)));
    await tester.pumpAndSettle();
    expect(seen, contains(WidgetState.disabled));
    expect(seen, isNot(contains(WidgetState.hovered)));
  });

  testWidgets('a disabled control tells a pointer that arrives why', (
    WidgetTester tester,
  ) async {
    final List<String> reported = <String>[];
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) => _box(
            context,
            disabledReason: 'Waiting for label coverage to be confirmed.',
            onDisabledReason: reported.add,
          ),
        ),
      ),
    );
    final TestGesture pointer = await tester.createGesture(
      kind: PointerDeviceKind.mouse,
    );
    await pointer.addPointer(location: Offset.zero);
    addTearDown(pointer.removePointer);
    await tester.pump();
    await pointer.moveTo(tester.getCenter(find.byType(Pressable)));
    await tester.pumpAndSettle();
    expect(
      reported,
      <String>['Waiting for label coverage to be confirmed.'],
      reason:
          'the reason is what a disabled control owes a reviewer, and a '
          'pointer arriving on it is the cheapest way to ask; it used to be '
          'reachable only by pressing the control that does nothing',
    );
  });

  testWidgets('a control turned off under the pointer is not hovered', (
    WidgetTester tester,
  ) async {
    late Set<WidgetState> seen;
    Widget tree({required bool enabled}) => uiHarness(
      child: Builder(
        builder: (BuildContext context) => _box(
          context,
          onPressed: enabled ? () {} : null,
          disabledReason: enabled ? null : 'Not while a save is going out.',
          onStates: (Set<WidgetState> s) => seen = s,
        ),
      ),
    );

    await tester.pumpWidget(tree(enabled: true));
    final TestGesture pointer = await tester.createGesture(
      kind: PointerDeviceKind.mouse,
    );
    await pointer.addPointer(location: Offset.zero);
    addTearDown(pointer.removePointer);
    await tester.pump();
    await pointer.moveTo(tester.getCenter(find.byType(Pressable)));
    await tester.pumpAndSettle();
    expect(seen, contains(WidgetState.hovered));

    await tester.pumpWidget(tree(enabled: false));
    expect(
      seen,
      <WidgetState>{WidgetState.disabled},
      reason:
          'the frame that disables the control is the frame that clears its '
          'hover: the detector only clears it a frame later, and until this '
          'was cleared here every builder was handed hovered and disabled at '
          'once, which is a pair no style object has an answer for',
    );
  });

  testWidgets('the state layer carries the opacities the contract names', (
    WidgetTester tester,
  ) async {
    final UiThemeData light = UiThemeData.light();
    final UiThemeData dark = UiThemeData.dark();
    expect(light.color.hoverOpacity, 0.08);
    expect(light.color.pressedOpacity, 0.12);
    expect(dark.color.hoverOpacity, 0.10);
    expect(dark.color.pressedOpacity, 0.14);
    expect(
      StateLayer.opacityFor(<WidgetState>{WidgetState.disabled}, light),
      0,
      reason: 'a disabled control has no hover or press layer to show',
    );
    expect(
      StateLayer.opacityFor(<WidgetState>{
        WidgetState.hovered,
        WidgetState.pressed,
      }, light),
      light.color.pressedOpacity,
      reason: 'a press wins over a hover, because the press is the newer fact',
    );
  });

  testWidgets('scale on press applies on touch and not on a pointer', (
    WidgetTester tester,
  ) async {
    for (final (UiDensityMode density, double expected)
        in <(UiDensityMode, double)>[
          (UiDensityMode.touch, 0.98),
          (UiDensityMode.pointer, 1.0),
        ]) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: Builder(
            builder: (BuildContext context) =>
                _box(context, onPressed: () {}, scaleOnPress: true),
          ),
        ),
      );
      final TestGesture press = await tester.startGesture(
        tester.getCenter(find.byType(Pressable)),
      );
      await tester.pumpAndSettle();
      expect(
        tester.widget<AnimatedScale>(find.byType(AnimatedScale)).scale,
        expected,
        reason:
            'in ${density.name} the pressed scale should be $expected: a '
            'mouse has a hover state to say the same thing',
      );
      await press.up();
      await tester.pumpAndSettle();
    }
  });
}
