import 'dart:ui' show Tristate;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const _destinations = [
  UiNavDestination(label: 'Specimens', icon: UiIcons.queue),
  UiNavDestination(label: 'Intake', icon: UiIcons.intake),
];

class _AdaptiveRailHost extends StatefulWidget {
  const _AdaptiveRailHost({this.inputs, this.footer});
  final UiInputCapabilities? inputs;
  final Widget? footer;

  @override
  State<_AdaptiveRailHost> createState() => _AdaptiveRailHostState();
}

class _AdaptiveRailHostState extends State<_AdaptiveRailHost> {
  int current = 0;

  @override
  Widget build(BuildContext context) => Density(
    inputCapabilities: widget.inputs,
    child: Builder(
      builder: (context) => Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          UiRail(
            destinations: _destinations,
            currentIndex: current,
            leading: const UiMark(label: 'Specimen Digitization'),
            footer: widget.footer,
            semanticsLabel: 'Workspace navigation',
            onSelect: (value) => setState(() => current = value),
          ),
          const Expanded(child: SizedBox()),
        ],
      ),
    ),
  );
}

Future<void> _pumpRail(
  WidgetTester tester, {
  UiInputCapabilities? inputs,
  Size size = const Size(1280, 720),
  TextScaler textScaler = TextScaler.noScaling,
  Widget? footer,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    uiHarness(
      size: size,
      textScaler: textScaler,
      child: _AdaptiveRailHost(inputs: inputs, footer: footer),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final width in [768.0, 1600.0]) {
    for (final (name, inputs, labels) in [
      (
        'pointer desktop',
        const UiInputCapabilities(touch: false, hover: true),
        false,
      ),
      (
        'touch tablet',
        const UiInputCapabilities(touch: true, hover: false),
        true,
      ),
      (
        'hybrid tablet',
        const UiInputCapabilities(touch: true, hover: true),
        true,
      ),
      (
        'unknown hover',
        const UiInputCapabilities(touch: false, hover: false),
        true,
      ),
    ]) {
      testWidgets('$name labels follow capability, not width $width', (
        tester,
      ) async {
        await _pumpRail(tester, inputs: inputs, size: Size(width, 720));
        final context = tester.element(find.byType(UiRail));
        expect(UiRail.showsLabelsOf(context), labels);
        expect(
          tester.getSize(find.byType(UiRail)).width,
          UiRail.widthOf(context, destinations: _destinations),
        );
        for (final destination in _destinations) {
          expect(
            find.text(destination.label),
            labels ? findsOneWidget : findsNothing,
          );
          expect(find.bySemanticsLabel(destination.label), findsOneWidget);
        }
      });
    }
  }

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    testWidgets('native $platform keeps labels in a wide docked window', (
      tester,
    ) async {
      debugDefaultTargetPlatformOverride = platform;
      try {
        await _pumpRail(tester, size: const Size(1600, 900));
        expect(find.text('Specimens'), findsOneWidget);
        expect(find.text('Intake'), findsOneWidget);
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });
  }

  testWidgets('touch remains available after a later mouse gesture', (
    tester,
  ) async {
    await _pumpRail(
      tester,
      inputs: const UiInputCapabilities(touch: false, hover: true),
    );
    expect(find.text('Intake'), findsNothing);
    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(find.text('Specimens'), findsOneWidget);
    expect(find.text('Intake'), findsOneWidget);
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: const Offset(700, 300));
    await mouse.moveTo(const Offset(650, 300));
    await tester.pumpAndSettle();
    final context = tester.element(find.byType(UiRail));
    expect(Density.of(context).mode, UiDensityMode.pointer);
    expect(Density.inputsOf(context).touch, isTrue);
    expect(find.text('Specimens'), findsOneWidget);
    expect(find.text('Intake'), findsOneWidget);
    await mouse.removePointer();
  });

  testWidgets('touch labels remain below icons and fit at 200 percent text', (
    tester,
  ) async {
    await _pumpRail(
      tester,
      inputs: const UiInputCapabilities(touch: true, hover: true),
      textScaler: const TextScaler.linear(2),
    );
    final context = tester.element(find.byType(UiRail));
    expect(
      tester.getSize(find.byType(UiRail)).width,
      greaterThan(UiRailStyle.minWidthOf(context.ui)),
    );
    for (final destination in _destinations) {
      final icon = find.descendant(
        of: find.bySemanticsLabel(destination.label),
        matching: find.byType(Icon),
      );
      expect(
        tester.getTopLeft(find.text(destination.label)).dy,
        greaterThan(tester.getBottomLeft(icon).dy),
      );
      final labelRect = tester.getRect(find.text(destination.label));
      final railRect = tester.getRect(find.byType(UiRail));
      expect(labelRect.left, greaterThanOrEqualTo(railRect.left));
      expect(labelRect.right, lessThanOrEqualTo(railRect.right));
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('selection uses neutral subtle fill and a filled Phosphor icon', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    try {
      await _pumpRail(
        tester,
        inputs: const UiInputCapabilities(touch: false, hover: true),
      );
      final context = tester.element(find.byType(UiRail));
      final style = UiRailStyle.resolve(
        context.ui,
        extended: false,
        destinations: _destinations,
        textScaler: TextScaler.noScaling,
        textDirection: TextDirection.ltr,
      );
      expect(style.currentFill, isNot(context.ui.color.ink));
      expect(style.currentFill.a, lessThan(1));
      final selectedIcon = tester.widget<UiIcon>(
        find.descendant(
          of: find.bySemanticsLabel('Specimens'),
          matching: find.byType(UiIcon),
        ),
      );
      expect(selectedIcon.current, isTrue);
      expect(
        selectedIcon.spec.resolve(current: true),
        UiIcons.queue.resolve(current: true),
      );
      expect(selectedIcon.color, context.ui.color.ink);
      final data = tester
          .getSemantics(find.bySemanticsLabel('Specimens'))
          .getSemanticsData();
      expect(data.role, SemanticsRole.tab);
      expect(data.flagsCollection.isSelected, Tristate.isTrue);
    } finally {
      semantics.dispose();
    }
  });

  testWidgets('pointer hover and keyboard focus expose destination labels', (
    tester,
  ) async {
    await _pumpRail(
      tester,
      inputs: const UiInputCapabilities(touch: false, hover: true),
    );
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: const Offset(700, 300));
    await mouse.moveTo(tester.getCenter(find.bySemanticsLabel('Intake')));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.text('Intake'), findsOneWidget);
    await mouse.moveTo(const Offset(700, 300));
    await tester.pumpAndSettle();
    expect(find.text('Intake'), findsNothing);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    expect(find.text('Specimens'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(find.text('Intake'), findsOneWidget);
    await mouse.removePointer();
  });

  testWidgets('short touch rail scrolls account into reach without clipping', (
    tester,
  ) async {
    await _pumpRail(
      tester,
      inputs: const UiInputCapabilities(touch: true, hover: true),
      size: const Size(500, 170),
      textScaler: const TextScaler.linear(2),
      footer: UiMenuTrigger(
        label: 'Account',
        labelBelow: true,
        icon: UiIcons.account,
        semanticsLabel: 'Account menu',
        items: [UiMenuItem(label: 'Help', onSelected: () {})],
      ),
    );
    await tester.scrollUntilVisible(
      find.bySemanticsLabel('Account menu'),
      100,
      scrollable: find.byType(Scrollable),
    );
    expect(find.bySemanticsLabel('Account menu').hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('below-icon account label opens the same accessible menu', (
    tester,
  ) async {
    await _pumpRail(
      tester,
      inputs: const UiInputCapabilities(touch: true, hover: true),
      textScaler: const TextScaler.linear(2),
      footer: UiMenuTrigger(
        label: 'Account',
        labelBelow: true,
        icon: UiIcons.account,
        semanticsLabel: 'Account menu',
        items: [UiMenuItem(label: 'Help', onSelected: () {})],
      ),
    );
    final trigger = find.bySemanticsLabel('Account menu');
    expect(trigger, findsOneWidget);
    final glyph = find.descendant(of: trigger, matching: find.byType(Icon));
    expect(
      tester.getTopLeft(find.text('Account')).dy,
      greaterThan(tester.getBottomLeft(glyph).dy),
    );
    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();
    expect(find.text('Help'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text('Help'), findsNothing);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text('Help'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
