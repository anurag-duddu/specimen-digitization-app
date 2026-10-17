// The adaptive form: a sheet where the window is stacked, a dialog where it
// docks (05 section 3.7, amended 2026-10-17: the window's arrangement, not
// the compact width class, so it agrees with the tab bar).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/adaptive_form.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import 'harness.dart';

/// The height of the body, so the pane has a size of its own to measure.
const double _bodyHeight = 200;

Widget _opener({double width = DialogWidths.standard}) => Builder(
  builder: (BuildContext context) => UiButton(
    label: 'Open',
    onPressed: () => showAdaptiveForm<String>(
      context,
      width: width,
      semanticsLabel: 'A form',
      builder: (BuildContext _) => const SizedBox(
        height: _bodyHeight,
        child: Center(child: Text('form body')),
      ),
    ),
  ),
);

void main() {
  test('the three widths are the ones the design system names', () {
    expect(DialogWidths.narrow, 400);
    expect(DialogWidths.standard, 480);
    expect(DialogWidths.wide, 640);
  });

  testWidgets('a stacked window gets a sheet against the bottom of it', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(420, 800));
    await tester.tap(uiButton('Open'));
    await tester.pumpAndSettle();
    expect(find.text('form body'), findsOneWidget);
    expect(modalIsSheet(tester), isTrue);
  });

  testWidgets('a docked window gets a dialog at the given width', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(1000, 800));
    await tester.tap(uiButton('Open'));
    await tester.pumpAndSettle();
    expect(modalIsSheet(tester), isFalse);
    expect(
      tester.getSize(uiModalPane()).width,
      lessThanOrEqualTo(DialogWidths.standard),
    );
  });

  // The boundary moved with the arrangement: a window from 600 to 767 wide
  // draws the tab bar, so its forms are sheets too. Both sides of the new
  // boundary are pinned, as both sides of 600 were.
  for (final (Size window, bool sheet) in <(Size, bool)>[
    (const Size(600, 800), true),
    (const Size(767, 800), true),
    (const Size(768, 800), false),
    (const Size(1000, 599), true),
    (const Size(1000, 600), false),
  ]) {
    testWidgets('at $window it is ${sheet ? 'a sheet' : 'the dialog form'}', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, _opener(), size: window);
      await tester.tap(uiButton('Open'));
      await tester.pumpAndSettle();
      expect(modalIsSheet(tester), sheet);
    });
  }

  testWidgets('the wide dialog is wider than the standard one', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(1200, 800));
    await tester.tap(uiButton('Open'));
    await tester.pumpAndSettle();
    final double standard = tester.getSize(uiModalPane()).width;
    await tester.tapAt(Offset.zero);
    await tester.pumpAndSettle();

    await pumpComponent(
      tester,
      _opener(width: DialogWidths.wide),
      size: const Size(1200, 800),
    );
    await tester.tap(uiButton('Open'));
    await tester.pumpAndSettle();
    final double wide = tester.getSize(uiModalPane()).width;
    expect(wide, greaterThan(standard));
    // The modal frame caps every dialog at `space.dialogMax`, so a width
    // above it is a request for as much room as the system gives rather than
    // a number the pane takes (11 section 5).
    expect(wide, lessThanOrEqualTo(UiSpace.standard.dialogMax));
  });

  testWidgets('under reduced motion the form arrives without a transition', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _opener(),
      size: const Size(1000, 800),
      reduceMotion: true,
    );
    await tester.tap(uiButton('Open'));
    await tester.pump();
    await tester.pump();
    expect(find.text('form body'), findsOneWidget);
  });
}
