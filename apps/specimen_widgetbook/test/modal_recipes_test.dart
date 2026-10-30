import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog/modal_recipes.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  testWidgets(
    'every modal recipe renders in narrow large-text RTL and desktop',
    (tester) async {
      addTearDown(tester.view.reset);
      tester.view.devicePixelRatio = 1;
      final root = WidgetbookRoot(children: modalRecipeComponents);
      final failures = <String>[];
      for (final useCase in root.leaves.whereType<WidgetbookUseCase>()) {
        final state = WidgetbookState(root: root, path: useCase.path);
        for (final narrow in [true, false]) {
          tester.view.physicalSize = narrow
              ? const Size(320, 900)
              : const Size(1180, 900);
          await tester.pumpWidget(
            WidgetbookScope(
              state: state,
              child: MaterialApp(
                home: Builder(
                  builder: (context) => MediaQuery(
                    data: MediaQuery.of(
                      context,
                    ).copyWith(textScaler: TextScaler.linear(narrow ? 2 : 1)),
                    child: SpecimenEnvironmentScope(
                      setting: SpecimenEnvironment(
                        dark: narrow,
                        density: narrow
                            ? UiDensityMode.touch
                            : UiDensityMode.pointer,
                        direction: narrow
                            ? TextDirection.rtl
                            : TextDirection.ltr,
                        reduceMotion: true,
                      ),
                      child: SpecimenPreview(
                        child: Builder(
                          key: ValueKey('${useCase.path}/$narrow'),
                          builder: useCase.builder,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          );
          await tester.pump(const Duration(milliseconds: 200));
          Object? exception;
          while ((exception = tester.takeException()) != null) {
            failures.add('${useCase.path}, narrow=$narrow: $exception');
          }
        }
        await tester.pumpWidget(const SizedBox.shrink());
        state.dispose();
      }
      expect(failures, isEmpty, reason: failures.join('\n\n'));
    },
  );

  testWidgets('notification preferences remain independent', (tester) async {
    final state = await _pumpTemplate(
      tester,
      'Notification settings checkboxes',
    );
    UiCheckbox option(String label) => tester.widget<UiCheckbox>(
      find.byWidgetPredicate((w) => w is UiCheckbox && w.label == label),
    );
    option('Mentions').onChanged!(true);
    await tester.pump();
    expect(option('Mentions').value, isTrue);
    expect(option('Collection updates').value, isFalse);
    expect(option('Review assignments').value, isFalse);
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });

  testWidgets('filter search preserves selections outside the query', (
    tester,
  ) async {
    final state = await _pumpTemplate(tester, 'Filters');
    await tester.enterText(find.byType(EditableText), 'images');
    await tester.pump();
    expect(find.text('Has collector'), findsNothing);
    final checkbox = tester.widget<UiCheckbox>(
      find.byWidgetPredicate(
        (w) => w is UiCheckbox && w.label == 'Images available',
      ),
    );
    checkbox.onChanged!(true);
    await tester.pump();
    expect(find.text('2 filters selected'), findsOneWidget);
    await tester.enterText(find.byType(EditableText), '');
    await tester.pump();
    expect(
      tester
          .widget<UiCheckbox>(
            find.byWidgetPredicate(
              (w) => w is UiCheckbox && w.label == 'Needs review',
            ),
          )
          .value,
      isTrue,
    );
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });

  testWidgets('every recipe opens with reachable actions at large text', (
    tester,
  ) async {
    for (final entry in [
      ...modalRecipeTypes.map((type) => (type, false)),
      ...drawerRecipeTypes.map((type) => (type, true)),
    ]) {
      final state = await _pumpTemplate(
        tester,
        entry.$1,
        narrow: true,
        drawer: entry.$2,
      );
      final open = find.text('Open ${entry.$1}');
      await tester.ensureVisible(open);
      await tester.tap(open);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: '${entry.$1} opened');
      final apply = find.text('Apply locally').last;
      await tester.ensureVisible(apply);
      await tester.tap(apply);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: '${entry.$1} applied');
      expect(
        find.text('${entry.$1} applied locally · 1 actions'),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox());
      state.dispose();
    }
  });
}

Future<WidgetbookState> _pumpTemplate(
  WidgetTester tester,
  String name, {
  bool narrow = false,
  bool? drawer,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = narrow
      ? const Size(320, 900)
      : const Size(1180, 900);
  addTearDown(tester.view.reset);
  final root = WidgetbookRoot(children: modalRecipeComponents);
  final story = root.leaves.whereType<WidgetbookUseCase>().singleWhere(
    (story) =>
        story.name == name &&
        (drawer == null ||
            story.path.startsWith(
              drawer ? 'slideout-recipes/' : 'modal-recipes/',
            )),
  );
  final state = WidgetbookState(root: root, path: story.path);
  await tester.pumpWidget(
    WidgetbookScope(
      state: state,
      child: MaterialApp(
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: TextScaler.linear(narrow ? 2 : 1)),
            child: SpecimenEnvironmentScope(
              setting: SpecimenEnvironment(
                dark: narrow,
                density: narrow ? UiDensityMode.touch : UiDensityMode.pointer,
                direction: narrow ? TextDirection.rtl : TextDirection.ltr,
                reduceMotion: true,
              ),
              child: SpecimenPreview(child: Builder(builder: story.builder)),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 200));
  return state;
}
