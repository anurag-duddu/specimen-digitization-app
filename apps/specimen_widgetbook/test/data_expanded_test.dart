import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog/data_expanded.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  testWidgets(
    'every expanded data story renders in narrow large-text RTL and desktop',
    (tester) async {
      addTearDown(tester.view.reset);
      tester.view.devicePixelRatio = 1;
      final root = WidgetbookRoot(children: dataExpandedComponents);
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

  testWidgets('directory search, row details and selection stay controlled', (
    tester,
  ) async {
    final state = await _pumpTemplate(tester, 'Informational directory');
    expect(find.text('EXAMPLE-002'), findsOneWidget);
    await tester.enterText(find.byType(EditableText), 'EXAMPLE-001');
    await tester.pump();
    expect(find.text('EXAMPLE-002'), findsNothing);
    expect(
      find.descendant(
        of: find.byType(UiTableCell),
        matching: find.text('EXAMPLE-001'),
      ),
      findsOneWidget,
    );
    final selection = find.byWidgetPredicate(
      (widget) => widget is UiCheckbox && widget.label == 'Select EXAMPLE-001',
    );
    await tester.ensureVisible(selection);
    await tester.tap(selection);
    await tester.pump();
    expect(find.text('1 selected'), findsOneWidget);
    await tester.ensureVisible(find.text('Open record'));
    await tester.tap(find.text('Open record'));
    await tester.pump();
    expect(
      find.text('Example original label and source metadata.'),
      findsOneWidget,
    );
    await tester.ensureVisible(find.text('Close record'));
    await tester.tap(find.text('Close record'));
    await tester.pump();
    expect(
      find.text('Example original label and source metadata.'),
      findsNothing,
    );
    await tester.ensureVisible(find.text('Export records').last);
    await tester.tap(find.text('Export records').last);
    await tester.pump();
    expect(find.text('Export requested for 1 records'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    state.dispose();
  });

  testWidgets(
    'settings persists local edits across sections and supports reset',
    (tester) async {
      final state = await _pumpTemplate(tester, 'Settings', narrow: true);
      final name = find.descendant(
        of: find.byWidgetPredicate(
          (widget) => widget is UiField && widget.label == 'Full name',
        ),
        matching: find.byType(EditableText),
      );
      await tester.ensureVisible(name);
      await tester.enterText(name, 'Maya Chen');
      await tester.ensureVisible(find.text('Save settings').last);
      await tester.tap(find.text('Save settings').last);
      await tester.pump();
      expect(find.text('Saved locally for Maya Chen'), findsOneWidget);
      await tester.ensureVisible(find.text('Notifications'));
      await tester.tap(find.text('Notifications'));
      await tester.pump();
      await tester.ensureVisible(find.text('Collection review updates'));
      await tester.tap(find.text('Collection review updates'));
      await tester.pump();
      expect(
        find.text('Review updates are disabled in this example.'),
        findsOneWidget,
      );
      await tester.ensureVisible(find.text('Profile'));
      await tester.tap(find.text('Profile'));
      await tester.pump();
      expect(find.text('Maya Chen'), findsOneWidget);
      await tester.ensureVisible(find.text('Reset settings'));
      await tester.tap(find.text('Reset settings'));
      await tester.pump();
      expect(find.text('Alex Morgan'), findsOneWidget);
      expect(find.text('Settings reset locally'), findsOneWidget);
      await tester.ensureVisible(find.text('Workspace navigation'));
      await tester.tap(find.text('Workspace navigation'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Overview'));
      await tester.pumpAndSettle();
      expect(find.text('Collection overview'), findsOneWidget);
      expect(find.byType(UiDrawer), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      state.dispose();
    },
  );
}

Future<WidgetbookState> _pumpTemplate(
  WidgetTester tester,
  String name, {
  bool narrow = false,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = narrow
      ? const Size(320, 900)
      : const Size(1180, 900);
  addTearDown(tester.view.reset);
  final root = WidgetbookRoot(children: dataExpandedComponents);
  final story = root.leaves.whereType<WidgetbookUseCase>().singleWhere(
    (story) => story.name == name,
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
