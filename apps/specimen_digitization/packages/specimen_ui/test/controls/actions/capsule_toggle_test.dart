// `UiCapsuleToggle` is the family's first composite: one Tab stop into the
// group, arrows inside it, and a check disc that carries signature motion 2.

import 'dart:ui' show SemanticsFlags, Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

enum _Reading { model, reviewer, authority }

const List<UiToggleOption<_Reading>> _options = <UiToggleOption<_Reading>>[
  UiToggleOption<_Reading>(value: _Reading.model, label: 'Model'),
  UiToggleOption<_Reading>(value: _Reading.reviewer, label: 'Reviewer'),
  UiToggleOption<_Reading>(value: _Reading.authority, label: 'Authority'),
];

/// A group whose selection lives in the test, so a tap really changes it.
class _Host extends StatefulWidget {
  const _Host({
    this.selection = UiToggleSelection.multiple,
    this.initial = const <_Reading>{},
    this.onChanged,
  });

  final UiToggleSelection selection;
  final Set<_Reading> initial;
  final ValueChanged<Set<_Reading>>? onChanged;

  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> {
  late Set<_Reading> _selected = widget.initial;

  @override
  Widget build(BuildContext context) => UiCapsuleToggle<_Reading>(
    options: _options,
    selected: _selected,
    selection: widget.selection,
    onChanged: (Set<_Reading> next) {
      setState(() => _selected = next);
      widget.onChanged?.call(next);
    },
  );
}

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('an option satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiCapsuleToggle<_Reading>(
        options: _options,
        selected: const <_Reading>{},
        onChanged: (Set<_Reading> next) {},
      ),
      semanticsLabel: 'Model',
      hasRole: (SemanticsFlags flags) => flags.isToggled != Tristate.none,
    );
  });

  testWidgets('a disabled group satisfies the contract and states the reason',
      (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiCapsuleToggle<_Reading>(
        options: _options,
        selected: <_Reading>{},
        onChanged: null,
        disabledReason: 'This run has one reading to compare.',
      ),
      semanticsLabel: 'Model',
      disabledWithReason: true,
    );
  });

  testWidgets('each option reports toggled, so a screen reader hears on or '
      'off', (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const _Host(initial: <_Reading>{_Reading.reviewer}),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Reviewer'))
          .getSemanticsData()
          .flagsCollection
          .isToggled,
      Tristate.isTrue,
    );
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Model'))
          .getSemanticsData()
          .flagsCollection
          .isToggled,
      Tristate.isFalse,
    );
    handle.dispose();
  });

  testWidgets('multiple selection adds and removes, and reports the whole '
      'set', (WidgetTester tester) async {
    final List<Set<_Reading>> reported = <Set<_Reading>>[];
    await tester.pumpWidget(
      uiHarness(
        child: _Host(
          initial: const <_Reading>{_Reading.model},
          onChanged: reported.add,
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Reviewer'));
    await tester.pumpAndSettle();
    expect(reported.last, <_Reading>{_Reading.model, _Reading.reviewer});

    await tester.tap(find.bySemanticsLabel('Model'));
    await tester.pumpAndSettle();
    expect(reported.last, <_Reading>{_Reading.reviewer});
  });

  testWidgets('single selection replaces, and clears when the chosen option '
      'is chosen again', (WidgetTester tester) async {
    final List<Set<_Reading>> reported = <Set<_Reading>>[];
    await tester.pumpWidget(
      uiHarness(
        child: _Host(
          selection: UiToggleSelection.single,
          initial: const <_Reading>{_Reading.model},
          onChanged: reported.add,
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Authority'));
    await tester.pumpAndSettle();
    expect(reported.last, <_Reading>{_Reading.authority});

    await tester.tap(find.bySemanticsLabel('Authority'));
    await tester.pumpAndSettle();
    expect(
      reported.last,
      isEmpty,
      reason: 'a single group can be emptied without a second control',
    );
  });

  testWidgets('a disabled group changes nothing', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiCapsuleToggle<_Reading>(
          options: _options,
          selected: <_Reading>{_Reading.model},
          onChanged: null,
          disabledReason: 'This run has one reading to compare.',
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Reviewer'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('arrow keys move focus within the group and stop at the ends', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _Host()));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Model');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Reviewer');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      'Authority',
      reason: 'focus stops at the last option rather than wrapping',
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Reviewer');
  });

  testWidgets('left and right mirror under RTL, and up and down do not', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(textDirection: TextDirection.rtl, child: const _Host()),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Model');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pumpAndSettle();
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      'Reviewer',
      reason: 'the left key moves along the reading order under RTL',
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      'Authority',
      reason: 'reading order runs top to bottom in both directions',
    );
  });

  testWidgets('Space toggles the focused option', (WidgetTester tester) async {
    final List<Set<_Reading>> reported = <Set<_Reading>>[];
    await tester.pumpWidget(
      uiHarness(child: _Host(onChanged: reported.add)),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pumpAndSettle();
    expect(reported.last, <_Reading>{_Reading.reviewer});
  });

  testWidgets('the check disc fills over the capsule fill duration, and the '
      'check follows it', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: const _Host()));
    await tester.pumpAndSettle();
    expect(_checkOpacity(tester, 'Model'), 0);

    await tester.tap(find.bySemanticsLabel('Model'));
    await tester.pump();
    expect(
      _checkOpacity(tester, 'Model'),
      0,
      reason: 'the check waits until 40 percent of the fill (09 section 8)',
    );

    await tester.pump(MotionTokens.shortRaw);
    await tester.pumpAndSettle();
    expect(_checkOpacity(tester, 'Model'), 1);
  });

  testWidgets('under reduced motion the fill and the check arrive together', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: const _Host()),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Model'));
    await tester.pump();
    expect(_checkOpacity(tester, 'Model'), 1);
    expect(
      tester.binding.transientCallbackCount,
      0,
      reason: 'nothing is still animating (04 section 2.5)',
    );
  });

  testWidgets('it builds at 200 percent text and wraps rather than clipping', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        size: const Size(400, 600),
        child: const _Host(),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}

/// The opacity of the check inside the option labelled [label].
double _checkOpacity(WidgetTester tester, String label) => tester
    .widget<Opacity>(
      find.descendant(
        of: find.ancestor(
          of: find.text(label),
          matching: find.byType(Pressable),
        ),
        matching: find.byType(Opacity),
      ),
    )
    .opacity;
