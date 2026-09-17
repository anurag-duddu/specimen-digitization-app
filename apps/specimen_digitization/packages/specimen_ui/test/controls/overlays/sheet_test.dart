// `UiSheet` and `UiModalActions` (10 section 4.3).

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const String _title = 'Record a reason';
const String _body =
    'Recorded in the audit history with your name and the '
    'time.';

/// The context of the page under the sheet.
late BuildContext pageContext;

Widget _page() => Builder(
  builder: (BuildContext context) {
    pageContext = context;
    return UiButton(
      label: 'Open a sheet',
      variant: UiButtonVariant.secondary,
      onPressed: () => open(context),
    );
  },
);

Future<String?> open(BuildContext context, {bool dismissible = true}) =>
    UiSheet.show<String>(
      context: context,
      title: _title,
      dismissLabel: 'Close the sheet',
      dismissible: dismissible,
      body: (BuildContext context) => const Text(_body),
      secondaryAction: (BuildContext context) => UiButton(
        label: 'Cancel',
        variant: UiButtonVariant.ghost,
        onPressed: () => Navigator.of(context).pop(),
      ),
      primaryAction: (BuildContext context) => UiButton(
        label: 'Save correction',
        onPressed: () => Navigator.of(context).pop('saved'),
      ),
    );

void main() {
  testWidgets('it opens with its title, body and actions in order', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a sheet'));
    await tester.pumpAndSettle();

    expect(find.text(_title), findsOneWidget);
    expect(find.text(_body), findsOneWidget);
    expect(
      tester.getCenter(find.text('Cancel')).dx,
      lessThan(tester.getCenter(find.text('Save correction')).dx),
      reason: 'the way out comes before the verb (10 section 4.3)',
    );
  });

  testWidgets('the primary action returns what the sheet was closed with', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    String? closed;
    unawaited(open(pageContext).then((String? value) => closed = value));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Save correction'));
    await tester.pumpAndSettle();
    expect(closed, 'saved');
    expect(find.text(_title), findsNothing);
  });

  testWidgets('Escape and the scrim both close it', (
    WidgetTester tester,
  ) async {
    for (final bool byKey in <bool>[true, false]) {
      await tester.pumpWidget(uiHarness(child: _page()));
      unawaited(open(pageContext));
      await tester.pumpAndSettle();
      expect(find.text(_title), findsOneWidget);

      if (byKey) {
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      } else {
        await tester.tapAt(const Offset(5, 5));
      }
      await tester.pumpAndSettle();
      expect(find.text(_title), findsNothing, reason: 'closed by key: $byKey');
    }
  });

  testWidgets('focus returns to the trigger when it closes', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final FocusNode? trigger = FocusManager.instance.primaryFocus;
    expect(trigger, isNotNull);

    await tester.tap(find.text('Open a sheet'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus, trigger);
  });

  testWidgets('it is round on top and square where it meets the window', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a sheet'));
    await tester.pumpAndSettle();

    final GlassSurface pane = tester.widget<GlassSurface>(
      find.byType(GlassSurface),
    );
    final double radius = UiShape.standard.sheet;
    expect(
      pane.corners,
      BorderRadius.vertical(top: Radius.circular(radius)),
      reason: '10 section 4.3: top corners for the sheet',
    );
  });

  testWidgets('it carries one modal pane and a scrim', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a sheet'));
    await tester.pumpAndSettle();
    expect(find.byType(Scrim), findsOneWidget);
    expect(
      glassPaneCount(),
      1,
      reason: 'the chrome is the content of the route pane, not a second one',
    );
    expect(modalGlassPaneCount(), 1);
    expectGlassBudget(tester);
  });

  testWidgets('a downward flick on the handle closes it', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a sheet'));
    await tester.pumpAndSettle();

    final Rect pane = tester.getRect(find.byType(GlassSurface));
    await tester.flingFrom(
      pane.topCenter + const Offset(0, 12),
      const Offset(0, 240),
      1200,
    );
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing);
  });

  testWidgets('a sheet that must be answered ignores the scrim', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    unawaited(open(pageContext, dismissible: false));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(find.text(_title), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    for (final (TextDirection direction, TextScaler scaler)
        in <(TextDirection, TextScaler)>[
          (TextDirection.rtl, TextScaler.noScaling),
          (TextDirection.ltr, const TextScaler.linear(2)),
        ]) {
      await tester.pumpWidget(
        uiHarness(textDirection: direction, textScaler: scaler, child: _page()),
      );
      await tester.tap(find.text('Open a sheet'));
      await tester.pumpAndSettle();
      expect(find.text(_title), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('the entrance collapses under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(disableAnimations: true, child: _page()));
    await tester.tap(find.text('Open a sheet'));
    await tester.pumpAndSettle();
    expect(
      find.descendant(
        of: find.byType(UiSheet),
        matching: find.byType(SlideTransition),
      ),
      findsNothing,
      reason: 'a sheet appears without travel under reduced motion',
    );
  });

  testWidgets('a second primary action is rejected', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiModalActions(
          primary: UiButton(label: 'Save correction'),
          secondary: UiButton(label: 'Start new run'),
        ),
      ),
    );
    expect(
      tester.takeException(),
      isAssertionError,
      reason: 'a modal carries at most one primary action',
    );
  });

  testWidgets('the body is bounded by the window and scrolls inside it', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(390, 700),
        child: SizedBox(
          width: 390,
          height: 700,
          child: UiSheet(
            title: _title,
            primaryAction: UiButton(label: 'Save', onPressed: () {}),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (int i = 0; i < 40; i++)
                  SizedBox(height: 40, child: Text('Row $i')),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      tester.takeException(),
      isNull,
      reason:
          'a 1600 dp body in a 700 dp window overflowed the sheet before the '
          'padded block was made flexible',
    );
    expect(
      tester.getSize(find.byType(UiSheet)).height,
      lessThanOrEqualTo(700),
      reason: 'the sheet is the window height minus nothing it does not use',
    );
    expect(
      find.bySemanticsLabel('Save'),
      findsOneWidget,
      reason: 'and the action row is still on screen, which is the defect',
    );

    final ScrollableState scroller = tester.state<ScrollableState>(
      find.byType(Scrollable),
    );
    expect(
      scroller.position.maxScrollExtent,
      greaterThan(0),
      reason: 'the body scrolls rather than being cut off',
    );
  });

  testWidgets('a body that scrolls itself is not scrolled twice', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(390, 700),
        child: SizedBox(
          width: 390,
          height: 700,
          child: UiSheet(
            title: _title,
            scrollBody: false,
            child: ListView(
              children: <Widget>[
                for (int i = 0; i < 40; i++)
                  SizedBox(height: 40, child: Text('Row $i')),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byType(SingleChildScrollView), findsNothing);
  });

  testWidgets('the actions stack with the primary on top when they do not '
      'fit one line', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        // Wider than compact, so the stack is the row not fitting rather than
        // the window class deciding it.
        size: const Size(900, 700),
        child: SizedBox(
          width: 260,
          child: UiModalActions(
            primary: UiButton(
              label: 'Replace the classification',
              onPressed: () {},
            ),
            secondary: UiButton(
              label: 'Keep what is recorded',
              variant: UiButtonVariant.secondary,
              onPressed: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getTopLeft(find.bySemanticsLabel('Replace the classification')).dy,
      lessThan(
        tester.getTopLeft(find.bySemanticsLabel('Keep what is recorded')).dy,
      ),
      reason: '11 section 3.4: the actions stack, primary on top',
    );
  });

  testWidgets('the actions are a row with the primary last when they fit', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(900, 700),
        child: SizedBox(
          width: 900,
          child: UiModalActions(
            primary: UiButton(label: 'Save', onPressed: () {}),
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.secondary,
              onPressed: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getTopLeft(find.bySemanticsLabel('Cancel')).dx,
      lessThan(tester.getTopLeft(find.bySemanticsLabel('Save')).dx),
      reason: 'aligned to the end with the primary last',
    );
    expect(
      tester.getTopLeft(find.bySemanticsLabel('Cancel')).dy,
      tester.getTopLeft(find.bySemanticsLabel('Save')).dy,
    );
  });

  testWidgets('the actions stack on a compact window however short they are', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(390, 700),
        child: SizedBox(
          width: 390,
          child: UiModalActions(
            primary: UiButton(label: 'Save', onPressed: () {}),
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.secondary,
              onPressed: () {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getTopLeft(find.bySemanticsLabel('Save')).dy,
      lessThan(tester.getTopLeft(find.bySemanticsLabel('Cancel')).dy),
      reason: 'a compact window stacks whether or not the row would fit',
    );
  });

  testWidgets('the primary action satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiSheet(
        title: _title,
        primaryAction: UiButton(label: 'Save correction', onPressed: () {}),
        child: const Text(_body),
      ),
      semanticsLabel: 'Save correction',
      labelsNeverWrap: true,
      wrappingContent: <String>{
        _body,
        // See the same entry in `dialog_test.dart`: the button's own fit is
        // slot G1's row of the table.
        'Save correction',
      },
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(find.text(_title), findsOneWidget);
          expect(find.bySemanticsLabel('Save correction'), findsOneWidget);
        },
      ),
    );
  });
}
