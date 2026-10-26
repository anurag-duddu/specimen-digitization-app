import 'package:flutter/services.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

class _PanelHost extends StatefulWidget {
  const _PanelHost({super.key, this.initiallyOpen = false});

  final bool initiallyOpen;

  @override
  State<_PanelHost> createState() => _PanelHostState();
}

class _PanelHostState extends State<_PanelHost> {
  late bool open = widget.initiallyOpen;
  UiSidePanelMode mode = UiSidePanelMode.docked;
  bool hasPanel = true;
  int bodyActivations = 0;
  int navigationActivations = 0;
  final opener = FocusNode();
  final search = FocusNode();
  final navigation = FocusNode();
  final close = FocusNode();
  final body = FocusNode();
  final text = TextEditingController();
  final scroll = ScrollController();

  void change({bool? visible, UiSidePanelMode? placement, bool? available}) {
    setState(() {
      open = visible ?? open;
      mode = placement ?? mode;
      hasPanel = available ?? hasPanel;
    });
  }

  @override
  void dispose() {
    opener.dispose();
    search.dispose();
    navigation.dispose();
    close.dispose();
    body.dispose();
    text.dispose();
    scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => UiSidePanel(
    open: open,
    mode: mode,
    width: 300,
    leadingWidth: 100,
    leading: Align(
      alignment: Alignment.topCenter,
      child: UiButton(
        label: 'Navigation',
        focusNode: navigation,
        onPressed: () => navigationActivations++,
      ),
    ),
    initialFocusNode: search,
    semanticsLabel: 'Specimens panel',
    dismissLabel: 'Close specimens',
    onDismiss: () => change(visible: false),
    panel: hasPanel
        ? Column(
            key: const ValueKey('panel-content'),
            children: [
              UiField(label: 'Search', controller: text, focusNode: search),
              UiButton(
                label: 'Close specimens',
                focusNode: close,
                onPressed: () => change(visible: false),
              ),
              Expanded(
                child: ListView(
                  controller: scroll,
                  children: [
                    for (var i = 0; i < 60; i++)
                      SizedBox(height: 40, child: Text('Specimen $i')),
                  ],
                ),
              ),
            ],
          )
        : null,
    child: Column(
      key: const ValueKey('body-content'),
      children: [
        UiButton(
          label: 'Open specimens',
          focusNode: opener,
          onPressed: () {
            opener.requestFocus();
            FocusManager.instance.applyFocusChangesIfNeeded();
            change(visible: true);
          },
        ),
        UiButton(
          label: 'Body action',
          focusNode: body,
          onPressed: () => bodyActivations++,
        ),
        const _RetainedCounter(),
      ],
    ),
  );
}

class _RetainedCounter extends StatefulWidget {
  const _RetainedCounter();

  @override
  State<_RetainedCounter> createState() => _RetainedCounterState();
}

class _RetainedCounterState extends State<_RetainedCounter> {
  int count = 0;

  @override
  Widget build(BuildContext context) =>
      UiButton(label: 'Draft $count', onPressed: () => setState(() => count++));
}

Future<GlobalKey<_PanelHostState>> _pump(
  WidgetTester tester, {
  bool reduced = false,
  bool initiallyOpen = false,
  TextDirection direction = TextDirection.ltr,
}) async {
  const size = Size(1000, 700);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  final key = GlobalKey<_PanelHostState>();
  await tester.pumpWidget(
    uiHarness(
      size: size,
      disableAnimations: reduced,
      textDirection: direction,
      child: _PanelHost(key: key, initiallyOpen: initiallyOpen),
    ),
  );
  await tester.pumpAndSettle();
  return key;
}

// The WidgetsApp route owns its own barrier outside this component.
Finder get _panelBarrier => find.descendant(
  of: find.byType(UiSidePanel),
  matching: find.byType(ModalBarrier),
);

Set<String> _accessibleLabels(WidgetTester tester) {
  final labels = <String>{};
  void visit(SemanticsNode node) {
    labels.add(node.label);
    node.visitChildren((child) {
      visit(child);
      return true;
    });
  }

  visit(tester.getSemantics(find.byType(UiSidePanel)));
  return labels;
}

void main() {
  test('docking preserves the requested body width and bounds overlays', () {
    final docked = UiSidePanelLayout.resolve(
      availableWidth: 1120,
      panelWidth: 312,
      minBodyWidth: 800,
    );
    expect(docked.mode, UiSidePanelMode.docked);
    expect(docked.width, 312);
    final overlay = UiSidePanelLayout.resolve(
      availableWidth: 1000,
      panelWidth: 312,
      minBodyWidth: 800,
    );
    expect(overlay.mode, UiSidePanelMode.overlay);
    expect(overlay.width, 312);
    final narrow = UiSidePanelLayout.resolve(
      availableWidth: 280,
      panelWidth: 312,
      minBodyWidth: 800,
    );
    expect(narrow.width, 232);
  });

  testWidgets('reveal retains full panel width, scroll, input and body state', (
    tester,
  ) async {
    final key = await _pump(tester);
    await tester.tap(find.text('Draft 0'));
    await tester.tap(find.text('Open specimens'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 70));
    expect(
      tester.getSize(find.byKey(const ValueKey('panel-content'))).width,
      300,
    );
    final openingWidth = tester
        .getSize(find.byKey(const ValueKey('body-content')))
        .width;
    expect(openingWidth, greaterThan(600));
    expect(openingWidth, lessThan(900));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(EditableText), 'preserved query');
    key.currentState!.scroll.jumpTo(400);
    await tester.pump();
    final panelElement = find
        .byKey(const ValueKey('panel-content'))
        .evaluate()
        .single;
    final bodyState = tester.state(find.byType(_RetainedCounter));
    key.currentState!.change(visible: false);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 70));
    expect(
      tester.getSize(find.byKey(const ValueKey('panel-content'))).width,
      300,
    );
    expect(key.currentState!.search.canRequestFocus, isFalse);
    expect(find.byType(EditableText).hitTestable(), findsNothing);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('panel-content')), findsNothing);
    key.currentState!.change(visible: true);
    await tester.pumpAndSettle();
    expect(find.text('Draft 1'), findsOneWidget);
    expect(key.currentState!.text.text, 'preserved query');
    expect(key.currentState!.scroll.offset, 400);
    expect(
      find.byKey(const ValueKey('panel-content')).evaluate().single,
      same(panelElement),
    );
    expect(tester.state(find.byType(_RetainedCounter)), same(bodyState));
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'overlay blocks navigation and body, traps focus, and returns it',
    (tester) async {
      final semantics = tester.ensureSemantics();
      try {
        final key = await _pump(tester);
        key.currentState!.change(placement: UiSidePanelMode.overlay);
        await tester.pump();
        await tester.tap(find.text('Open specimens'));
        await tester.pumpAndSettle();
        expect(key.currentState!.search.hasFocus, isTrue);
        expect(key.currentState!.navigation.canRequestFocus, isFalse);
        expect(key.currentState!.body.canRequestFocus, isFalse);
        expect(_accessibleLabels(tester), isNot(contains('Navigation')));
        expect(_accessibleLabels(tester), isNot(contains('Body action')));
        expect(_accessibleLabels(tester), contains('Specimens panel'));
        expect(
          tester.getSize(find.byKey(const ValueKey('body-content'))).width,
          900,
        );
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        expect(key.currentState!.close.hasFocus, isTrue);
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        expect(key.currentState!.search.hasFocus, isTrue);
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
        expect(key.currentState!.open, isFalse);
        expect(key.currentState!.opener.hasFocus, isTrue);
        expect(key.currentState!.navigation.canRequestFocus, isTrue);
        expect(find.bySemanticsLabel('Body action'), findsOneWidget);
      } finally {
        semantics.dispose();
      }
    },
  );

  testWidgets('overlay scrim dismisses instead of activating covered body', (
    tester,
  ) async {
    final key = await _pump(tester);
    key.currentState!.change(placement: UiSidePanelMode.overlay);
    await tester.pump();
    await tester.tap(find.text('Open specimens'));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(800, 300));
    await tester.pumpAndSettle();
    expect(key.currentState!.open, isFalse);
    expect(key.currentState!.opener.hasFocus, isTrue);
    expect(find.text('Draft 0'), findsOneWidget);
  });

  testWidgets('only a visible overlay contributes a modal barrier', (
    tester,
  ) async {
    final key = await _pump(tester);
    expect(_panelBarrier, findsNothing);
    key.currentState!.change(visible: true);
    await tester.pumpAndSettle();
    expect(_panelBarrier, findsNothing);
    key.currentState!.change(placement: UiSidePanelMode.overlay);
    await tester.pumpAndSettle();
    expect(_panelBarrier, findsOneWidget);
    key.currentState!.change(visible: false);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 70));
    expect(_panelBarrier, findsOneWidget);
    await tester.pumpAndSettle();
    expect(_panelBarrier, findsNothing);
    key.currentState!.change(visible: true, available: false);
    await tester.pump();
    expect(_panelBarrier, findsNothing);
  });

  testWidgets('mode changes retain content and correctly release modal focus', (
    tester,
  ) async {
    final key = await _pump(tester, initiallyOpen: true);
    final content = tester.state(find.byType(_RetainedCounter));
    key.currentState!.body.requestFocus();
    await tester.pump();
    key.currentState!.change(placement: UiSidePanelMode.overlay);
    await tester.pumpAndSettle();
    expect(key.currentState!.search.hasFocus, isTrue);
    expect(key.currentState!.body.canRequestFocus, isFalse);
    key.currentState!.change(placement: UiSidePanelMode.docked);
    await tester.pumpAndSettle();
    expect(key.currentState!.body.canRequestFocus, isTrue);
    key.currentState!.body.requestFocus();
    await tester.pump();
    key.currentState!.change(visible: false);
    await tester.pumpAndSettle();
    expect(key.currentState!.body.hasFocus, isTrue);
    expect(tester.state(find.byType(_RetainedCounter)), same(content));
    expect(tester.takeException(), isNull);
  });

  testWidgets('closing overlay blocks click-through until its pixels leave', (
    tester,
  ) async {
    final key = await _pump(tester);
    key.currentState!.change(placement: UiSidePanelMode.overlay);
    await tester.pump();
    final bodyTarget = tester.getCenter(find.text('Body action'));
    final navigationTarget = tester.getCenter(find.text('Navigation'));
    await tester.tap(find.text('Open specimens'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 70));
    expect(key.currentState!.open, isFalse);
    expect(find.byKey(const ValueKey('panel-content')), findsOneWidget);
    expect(key.currentState!.search.canRequestFocus, isFalse);
    expect(key.currentState!.body.canRequestFocus, isFalse);
    expect(key.currentState!.navigation.canRequestFocus, isFalse);
    await tester.tapAt(bodyTarget);
    await tester.tapAt(navigationTarget);
    expect(key.currentState!.bodyActivations, 0);
    expect(key.currentState!.navigationActivations, 0);
    await tester.pumpAndSettle();
    expect(key.currentState!.opener.hasFocus, isTrue);
    await tester.tapAt(bodyTarget);
    expect(key.currentState!.bodyActivations, 1);
  });

  testWidgets('reduced motion changes geometry in one frame', (tester) async {
    final key = await _pump(tester, reduced: true);
    key.currentState!.change(visible: true);
    await tester.pump();
    expect(
      tester.getSize(find.byKey(const ValueKey('body-content'))).width,
      600,
    );
    key.currentState!.change(visible: false);
    await tester.pump();
    expect(
      tester.getSize(find.byKey(const ValueKey('body-content'))).width,
      900,
    );
    expect(find.byKey(const ValueKey('panel-content')), findsNothing);
  });

  testWidgets('enabling reduced motion finishes an active overlay exit', (
    tester,
  ) async {
    final key = await _pump(tester);
    key.currentState!.change(placement: UiSidePanelMode.overlay);
    await tester.pump();
    await tester.tap(find.text('Open specimens'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 70));
    expect(_panelBarrier, findsOneWidget);
    expect(key.currentState!.body.canRequestFocus, isFalse);
    await tester.pumpWidget(
      uiHarness(
        size: const Size(1000, 700),
        disableAnimations: true,
        child: _PanelHost(key: key),
      ),
    );
    await tester.pump();
    expect(_panelBarrier, findsNothing);
    expect(find.byKey(const ValueKey('panel-content')), findsNothing);
    expect(key.currentState!.body.canRequestFocus, isTrue);
    expect(key.currentState!.opener.hasFocus, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('removing an open overlay releases coverage and returns focus', (
    tester,
  ) async {
    final key = await _pump(tester);
    key.currentState!.change(placement: UiSidePanelMode.overlay);
    await tester.pump();
    await tester.tap(find.text('Open specimens'));
    await tester.pumpAndSettle();
    expect(key.currentState!.search.hasFocus, isTrue);
    expect(_panelBarrier, findsOneWidget);
    key.currentState!.change(available: false);
    await tester.pump();
    expect(_panelBarrier, findsNothing);
    expect(key.currentState!.body.canRequestFocus, isTrue);
    expect(
      tester.getSize(find.byKey(const ValueKey('body-content'))).width,
      900,
    );
    await tester.pump();
    expect(key.currentState!.opener.hasFocus, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('removing panel content releases its reservation immediately', (
    tester,
  ) async {
    final key = await _pump(tester, initiallyOpen: true);
    final bodyState = tester.state(find.byType(_RetainedCounter));
    expect(
      tester.getSize(find.byKey(const ValueKey('body-content'))).width,
      600,
    );
    key.currentState!.change(available: false);
    await tester.pump();
    expect(
      tester.getSize(find.byKey(const ValueKey('body-content'))).width,
      900,
    );
    expect(tester.state(find.byType(_RetainedCounter)), same(bodyState));
    expect(tester.takeException(), isNull);
  });

  testWidgets('closing a default-open dock restores a visible body control', (
    tester,
  ) async {
    final key = await _pump(tester, initiallyOpen: true);
    key.currentState!.search.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(key.currentState!.opener.hasFocus, isTrue);
    expect(key.currentState!.search.canRequestFocus, isFalse);
  });

  testWidgets('RTL panel opens after navigation at the reading start', (
    tester,
  ) async {
    await _pump(tester, initiallyOpen: true, direction: TextDirection.rtl);
    final panel = tester.getRect(find.byKey(const ValueKey('panel-content')));
    expect(panel.right, 900);
    expect(panel.left, 600);
    expect(
      tester.getRect(find.byKey(const ValueKey('body-content'))).right,
      600,
    );
  });

  testWidgets('rapid close, mode change and reopen discard stale focus work', (
    tester,
  ) async {
    final key = await _pump(tester);
    await tester.tap(find.text('Open specimens'));
    await tester.pump();
    key.currentState!.change(visible: false);
    await tester.pump();
    key.currentState!.change(visible: true, placement: UiSidePanelMode.overlay);
    await tester.pumpAndSettle();
    expect(key.currentState!.search.hasFocus, isTrue);
    expect(key.currentState!.navigation.canRequestFocus, isFalse);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(key.currentState!.opener.hasFocus, isTrue);
    key.currentState!.change(visible: true);
    await tester.pumpAndSettle();
    key.currentState!.change(available: false);
    await tester.pumpAndSettle();
    expect(key.currentState!.navigation.canRequestFocus, isTrue);
    expect(tester.takeException(), isNull);
  });
}
