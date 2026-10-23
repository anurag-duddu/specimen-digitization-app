import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

// Compare the laid-out paragraph with its complete, unconstrained-height text.
// A Stack can silently clip text without reporting a RenderFlex overflow.
void expectCompleteParagraph(WidgetTester tester, Finder finder) {
  final paragraph = tester.renderObject<RenderParagraph>(
    find.descendant(of: finder, matching: find.byType(RichText)),
  );
  final painter = TextPainter(
    text: paragraph.text,
    textDirection: paragraph.textDirection,
    textScaler: paragraph.textScaler,
    locale: paragraph.locale,
  )..layout(maxWidth: paragraph.size.width);
  expect(
    paragraph.size.height,
    greaterThanOrEqualTo(painter.height - .01),
    reason: 'The entire value must remain visible at the requested text size.',
  );
  painter.dispose();
}

void main() {
  for (final mode in UiSelectionMode.values) {
    testWidgets('selection cards leave a discoverable disabled card in $mode', (
      tester,
    ) async {
      Set<int> selected = {};
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 280,
            child: UiSelectionCards<int>(
              label: 'Collection',
              options: const [
                UiSelectionCardOption(value: 0, label: 'Botany'),
                UiSelectionCardOption(
                  value: 1,
                  label: 'Fossils',
                  enabled: false,
                  disabledReason: 'Collection is read only',
                ),
                UiSelectionCardOption(value: 2, label: 'Insects'),
              ],
              selected: selected,
              mode: mode,
              onChanged: (next) => selected = next,
            ),
          ),
        ),
      );
      final blocked = tester
          .widget<Pressable>(
            find.byWidgetPredicate(
              (widget) =>
                  widget is Pressable && widget.semanticsLabel == 'Fossils',
            ),
          )
          .focusNode!;
      blocked.requestFocus();
      await tester.pumpAndSettle();
      expect(blocked.hasFocus, isTrue);
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Insects');
      expect(selected, mode == UiSelectionMode.single ? {2} : <int>{});
      blocked.requestFocus();
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus?.debugLabel, 'Botany');
      expect(selected, mode == UiSelectionMode.single ? {0} : <int>{});
      expect(tester.takeException(), isNull);
    });
  }

  for (final direction in TextDirection.values) {
    testWidgets(
      'combobox reaches offscreen options by keyboard in $direction',
      (tester) async {
        Set<int> selected = {};
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            child: SizedBox(
              width: 280,
              child: UiCombobox<int>(
                label: 'Reviewer',
                options: [
                  for (int i = 0; i < 75; i++)
                    UiComboboxOption(
                      value: i,
                      label: 'Reviewer $i',
                      supporting: 'Collection ${i ~/ 10}',
                      enabled: i != 73,
                    ),
                ],
                selected: selected,
                onChanged: (next) => selected = next,
              ),
            ),
          ),
        );
        await tester.tap(find.text('Choose an option'));
        await tester.pumpAndSettle();
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Reviewer 74');
        expect(find.text('Reviewer 74').hitTestable(), findsOneWidget);
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Reviewer 72');
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
        await tester.pumpAndSettle();
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
        await tester.pumpAndSettle();
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Reviewer 0');
        expect(find.text('Reviewer 0').hitTestable(), findsOneWidget);
        for (int i = 0; i < 30; i++) {
          await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
          await tester.pumpAndSettle();
        }
        expect(FocusManager.instance.primaryFocus?.debugLabel, 'Reviewer 30');
        expect(find.text('Reviewer 30').hitTestable(), findsOneWidget);
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pumpAndSettle();
        expect(selected, {30});
        expect(tester.takeException(), isNull);
      },
    );
  }

  for (final form in UiProgressDisplayForm.values) {
    for (final scale in [2.0, 4.0]) {
      testWidgets('progress $form retains complete metric at ${scale}x', (
        tester,
      ) async {
        const value = '150 of 200 records';
        await tester.pumpWidget(
          uiHarness(
            textScaler: TextScaler.linear(scale),
            child: SizedBox(
              width: 200,
              child: UiProgressDisplay(
                label: 'Progress',
                value: .75,
                valueLabel: value,
                form: form,
                labelPosition: form == UiProgressDisplayForm.bar
                    ? UiProgressLabelPosition.trailing
                    : UiProgressLabelPosition.center,
              ),
            ),
          ),
        );
        expect(tester.takeException(), isNull);
        expectCompleteParagraph(tester, find.text(value));
        expect(
          tester
              .getRect(find.byType(UiProgressDisplay))
              .contains(
                tester.getBottomRight(find.text(value)) -
                    const Offset(.01, .01),
              ),
          isTrue,
        );
      });
    }
  }

  for (final scale in [2.0, 4.0]) {
    testWidgets('avatar overflow count stays readable at ${scale}x', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      final people = [
        for (int i = 0; i < 123; i++) UiAvatarPerson(name: 'Reviewer $i'),
      ];
      await tester.pumpWidget(
        uiHarness(
          textScaler: TextScaler.linear(scale),
          child: SizedBox(
            width: 200,
            child: UiAvatarGroup(
              label: 'Reviewers',
              people: people,
              maxVisible: 3,
              size: UiAvatarSize.small,
              onAdd: () {},
            ),
          ),
        ),
      );
      final count = find.byWidgetPredicate(
        (widget) => widget is Text && (widget.data?.startsWith('+') ?? false),
      );
      expect(count, findsOneWidget);
      expectCompleteParagraph(tester, count);
      expect(tester.takeException(), isNull);
      expect(
        find.bySemanticsLabel(
          'Reviewers: ${people.map((p) => p.name).join(', ')}',
        ),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel('Add person'), findsOneWidget);
      semantics.dispose();
    });
  }

  testWidgets(
    'verification distinguishes host replacement from accepted echo',
    (tester) async {
      String value = '';
      late StateSetter update;
      final completed = <String>[];
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (_, setState) {
              update = setState;
              return UiVerificationCode(
                label: 'Code',
                value: value,
                onChanged: (next) => setState(() => value = next),
                onCompleted: completed.add,
              );
            },
          ),
        ),
      );
      final first = find.byType(EditableText).first;
      await tester.enterText(first, '123456');
      await tester.pump();
      expect(completed, ['123456']);
      // Accepted echoes and repeated unchanged input do not resubmit a code.
      update(() => value = '123456');
      await tester.pump();
      await tester.enterText(first, '123456');
      await tester.pump();
      expect(completed, ['123456']);
      // Host replacement changes the current code without submitting it.
      update(() => value = '654321');
      await tester.pump();
      expect(completed, ['123456']);
      expect(
        tester
            .widgetList<EditableText>(find.byType(EditableText))
            .map((field) => field.controller.text)
            .join(),
        '654321',
      );
      // Returning to an earlier code is a new completion after replacement.
      await tester.enterText(first, '123456');
      await tester.pump();
      expect(completed, ['123456', '123456']);
      await tester.enterText(first, '123456');
      await tester.pump();
      expect(completed, ['123456', '123456']);
    },
  );
}
