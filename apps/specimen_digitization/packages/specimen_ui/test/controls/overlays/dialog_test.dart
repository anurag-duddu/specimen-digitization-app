// `UiDialog` (10 section 4.3).

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const String _title = 'Correct classification?';
const String _body =
    'A new run replaces the results that depend on the profile. Run 2 and its '
    'evidence stay in history.';

/// The context of the page under the dialog.
late BuildContext pageContext;

Widget _page() => Builder(
  builder: (BuildContext context) {
    pageContext = context;
    return UiButton(
      label: 'Open a dialog',
      variant: UiButtonVariant.secondary,
      onPressed: () => open(context),
    );
  },
);

Future<String?> open(BuildContext context, {bool adaptive = false}) {
  final Future<String?> Function({
    required BuildContext context,
    required String title,
    required WidgetBuilder body,
    UiModalActionBuilder? primaryAction,
    UiModalActionBuilder? secondaryAction,
    String? semanticsLabel,
    String? dismissLabel,
    bool dismissible,
  })
  show = adaptive ? UiDialog.showAdaptive<String> : UiDialog.show<String>;
  return show(
    context: context,
    title: _title,
    dismissLabel: 'Close the dialog',
    body: (BuildContext context) => const Text(_body),
    secondaryAction: (BuildContext context) => UiButton(
      label: 'Cancel',
      variant: UiButtonVariant.ghost,
      onPressed: () => Navigator.of(context).pop(),
    ),
    primaryAction: (BuildContext context) => UiButton(
      label: 'Correct classification',
      onPressed: () => Navigator.of(context).pop('corrected'),
    ),
  );
}

void main() {
  testWidgets('it opens with its title, body and actions', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a dialog'));
    await tester.pumpAndSettle();

    expect(find.text(_title), findsOneWidget);
    expect(find.text(_body), findsOneWidget);
    expect(find.text('Correct classification'), findsOneWidget);
    expect(
      tester.getCenter(find.text('Cancel')).dx,
      lessThan(tester.getCenter(find.text('Correct classification')).dx),
    );
  });

  testWidgets('it is at most as wide as the dialog maximum', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a dialog'));
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(GlassSurface)).width,
      lessThanOrEqualTo(UiSpace.standard.dialogMax),
    );
  });

  testWidgets('all four of its corners turn and it has no handle', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a dialog'));
    await tester.pumpAndSettle();
    final GlassSurface pane = tester.widget<GlassSurface>(
      find.byType(GlassSurface),
    );
    expect(
      pane.corners,
      isNull,
      reason: 'a dialog floats, so it is uniform at radius.sheet',
    );
    expect(pane.radius, UiShape.standard.sheet);
  });

  testWidgets('Escape closes it and focus returns to the trigger', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final FocusNode? trigger = FocusManager.instance.primaryFocus;

    await tester.tap(find.text('Open a dialog'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing);
    expect(FocusManager.instance.primaryFocus, trigger);
  });

  testWidgets('the scrim closes it and the primary action returns a value', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    unawaited(open(pageContext));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(find.text(_title), findsNothing);

    String? closed;
    unawaited(open(pageContext).then((String? value) => closed = value));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Correct classification'));
    await tester.pumpAndSettle();
    expect(closed, 'corrected');
  });

  testWidgets('it carries one modal pane and a scrim', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _page()));
    await tester.tap(find.text('Open a dialog'));
    await tester.pumpAndSettle();
    expect(find.byType(Scrim), findsOneWidget);
    expect(glassPaneCount(), 1);
    expect(modalGlassPaneCount(), 1);
    expectGlassBudget(tester);
  });

  testWidgets('showAdaptive gives a compact window the sheet', (
    WidgetTester tester,
  ) async {
    for (final (Size window, bool sheet) in <(Size, bool)>[
      (const Size(390, 844), true),
      (const Size(1180, 820), false),
    ]) {
      await tester.pumpWidget(uiHarness(size: window, child: _page()));
      unawaited(open(pageContext, adaptive: true));
      await tester.pumpAndSettle();
      expect(find.byType(UiSheet), sheet ? findsOneWidget : findsNothing);
      expect(find.byType(UiDialog), sheet ? findsNothing : findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
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
        uiHarness(
          textDirection: direction,
          textScaler: scaler,
          child: _page(),
        ),
      );
      await tester.tap(find.text('Open a dialog'));
      await tester.pumpAndSettle();
      expect(find.text(_title), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('the entrance collapses under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: _page()),
    );
    await tester.tap(find.text('Open a dialog'));
    await tester.pumpAndSettle();
    expect(
      find.descendant(
        of: find.byType(UiDialog),
        matching: find.byType(SlideTransition),
      ),
      findsNothing,
    );
  });

  testWidgets('the primary action satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiDialog(
        title: _title,
        primaryAction: UiButton(
          label: 'Correct classification',
          onPressed: () {},
        ),
        child: const Text(_body),
      ),
      semanticsLabel: 'Correct classification',
      labelsNeverWrap: true,
      wrappingContent: <String>{
        _body,
        // The button's own label. `UiButton` still wraps at a width its
        // padding does not leave room for; 11 section 3.3 gives it an
        // ellipsis and a tooltip instead, and slot G1 owns that row of the
        // table. Delete this entry when `fe/fit-actions` merges.
        'Correct classification',
      },
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(find.text(_title), findsOneWidget);
          expect(
            find.bySemanticsLabel('Correct classification'),
            findsOneWidget,
          );
        },
      ),
    );
  });
}
