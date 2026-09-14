// The adaptive form: a sheet on a compact window, a dialog above it.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/adaptive_form.dart';

import 'harness.dart';

Widget _opener({double width = DialogWidths.standard}) => Builder(
  builder: (BuildContext context) => TextButton(
    onPressed: () => showAdaptiveForm<String>(
      context,
      width: width,
      builder: (BuildContext _) =>
          const SizedBox(height: 200, child: Center(child: Text('form body'))),
    ),
    child: const Text('Open'),
  ),
);

void main() {
  test('the three widths are the ones the design system names', () {
    expect(DialogWidths.narrow, 400);
    expect(DialogWidths.standard, 480);
    expect(DialogWidths.wide, 640);
  });

  testWidgets('below 600 it is a modal bottom sheet', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(420, 800));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.byType(BottomSheet), findsOneWidget);
    expect(find.byType(Dialog), findsNothing);
    expect(find.text('form body'), findsOneWidget);
  });

  testWidgets('at 600 and above it is a dialog at the given width', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(1000, 800));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsOneWidget);
    expect(find.byType(BottomSheet), findsNothing);
    expect(
      tester.getSize(find.text('form body').first).width,
      lessThanOrEqualTo(DialogWidths.standard),
    );
  });

  testWidgets('exactly 600 is already the dialog form', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _opener(), size: const Size(600, 800));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsOneWidget);
  });

  testWidgets('the wide dialog is wider than the standard one', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _opener(width: DialogWidths.wide),
      size: const Size(1200, 800),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    final Iterable<ConstrainedBox> boxes = tester.widgetList<ConstrainedBox>(
      find.descendant(
        of: find.byType(Dialog),
        matching: find.byType(ConstrainedBox),
      ),
    );
    expect(
      boxes.map((ConstrainedBox box) => box.constraints.maxWidth),
      contains(DialogWidths.wide),
    );
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
    await tester.tap(find.text('Open'));
    await tester.pump();
    await tester.pump();
    expect(find.text('form body'), findsOneWidget);
  });
}
