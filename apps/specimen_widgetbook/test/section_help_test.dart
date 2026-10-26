import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog/data_patterns.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  for (final direction in TextDirection.values) {
    testWidgets('section help opens and restores focus in $direction', (
      tester,
    ) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.reset);
      final root = WidgetbookRoot(children: dataPatternComponents);
      final story = root.leaves.whereType<WidgetbookUseCase>().firstWhere(
        (story) => story.name == 'Text · no tabs · Search',
      );
      final state = WidgetbookState(root: root, path: story.path);
      addTearDown(state.dispose);
      await tester.pumpWidget(
        WidgetbookScope(
          state: state,
          child: MaterialApp(
            home: Builder(
              builder: (context) => MediaQuery(
                data: MediaQuery.of(
                  context,
                ).copyWith(textScaler: const TextScaler.linear(2)),
                child: SpecimenEnvironmentScope(
                  setting: SpecimenEnvironment(
                    direction: direction,
                    reduceMotion: true,
                  ),
                  child: SpecimenPreview(
                    child: Builder(builder: story.builder),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final trigger = find.byWidgetPredicate(
        (widget) =>
            widget is UiIconButton &&
            widget.semanticsLabel == 'About collection records',
      );
      final focus = tester.widget<UiIconButton>(trigger).focusNode!;
      await tester.tap(find.byType(EditableText));
      await tester.tap(trigger);
      await tester.pumpAndSettle();
      expect(find.widgetWithText(UiButton, 'Close help'), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(find.widgetWithText(UiButton, 'Close help'), findsNothing);
      expect(focus.hasFocus, isTrue);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(UiButton, 'Close help'));
      await tester.pumpAndSettle();
      expect(focus.hasFocus, isTrue);
      expect(tester.takeException(), isNull);
    });
  }
}
