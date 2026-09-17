// The adaptive form: a sheet on a compact window, a dialog above it.

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

  testWidgets('below 600 it is a sheet against the bottom of the window', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(420, 800));
    await tester.tap(uiButton('Open'));
    await tester.pumpAndSettle();
    expect(find.text('form body'), findsOneWidget);
    expect(modalIsSheet(tester), isTrue);
  });

  testWidgets('at 600 and above it is a dialog at the given width', (
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

  testWidgets('exactly 600 is already the dialog form', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(600, 800));
    await tester.tap(uiButton('Open'));
    await tester.pumpAndSettle();
    expect(modalIsSheet(tester), isFalse);
  });

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
