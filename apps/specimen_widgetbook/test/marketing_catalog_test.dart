import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog/marketing.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  testWidgets('every marketing case renders in five device environments', (
    tester,
  ) async {
    addTearDown(tester.view.reset);
    tester.view.devicePixelRatio = 1;
    final root = WidgetbookRoot(children: marketingComponents);
    final failures = <String>[];
    for (final useCase in root.leaves.whereType<WidgetbookUseCase>()) {
      final state = WidgetbookState(root: root, path: useCase.path);
      for (final configuration in [
        (const Size(320, 720), 2.0, true, TextDirection.rtl),
        (const Size(390, 844), 1.0, false, TextDirection.ltr),
        (const Size(768, 1024), 2.0, false, TextDirection.rtl),
        (const Size(1180, 820), 1.0, true, TextDirection.ltr),
        (const Size(1440, 900), 1.0, false, TextDirection.ltr),
      ]) {
        tester.view.physicalSize = configuration.$1;
        await tester.pumpWidget(
          WidgetbookScope(
            state: state,
            child: MaterialApp(
              home: Builder(
                builder: (context) => MediaQuery(
                  data: MediaQuery.of(
                    context,
                  ).copyWith(textScaler: TextScaler.linear(configuration.$2)),
                  child: SpecimenEnvironmentScope(
                    setting: SpecimenEnvironment(
                      dark: configuration.$3,
                      direction: configuration.$4,
                      reduceMotion: true,
                      density: configuration.$1.width >= 1180
                          ? UiDensityMode.pointer
                          : UiDensityMode.touch,
                    ),
                    child: SpecimenPreview(
                      child: Builder(
                        key: ValueKey('${useCase.path} $configuration'),
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
        Object? error;
        while ((error = tester.takeException()) != null) {
          failures.add('${useCase.path} / $configuration: $error');
        }
      }
      await tester.pumpWidget(const SizedBox());
      state.dispose();
    }
    expect(failures, isEmpty, reason: failures.join('\n\n'));
  });

  testWidgets('pricing story changes authoritative displayed prices', (
    tester,
  ) async {
    final state = await _show(
      tester,
      'uipricingsection/billing-toggle-and-tier-cards',
    );
    expect(find.text(r'$12'), findsOneWidget);
    await tester.tap(find.text('Annually'));
    await tester.pumpAndSettle();
    expect(find.text(r'$120'), findsOneWidget);
    expect(find.text(r'$360'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });

  testWidgets('blog story actually filters and loads more articles', (
    tester,
  ) async {
    final state = await _show(
      tester,
      'uiblogsection/category-filtering-and-load-more',
    );
    await tester.tap(find.text('Practice').first);
    await tester.pumpAndSettle();
    expect(find.text('Reading the record'), findsNothing);
    expect(find.text('A shared review practice'), findsOneWidget);
    await tester.ensureVisible(find.text('Load more articles'));
    await tester.tap(find.text('Load more articles'));
    await tester.pumpAndSettle();
    expect(find.text('Connecting collection histories'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });

  testWidgets('announcement dismissal and restoration are real', (
    tester,
  ) async {
    final state = await _show(
      tester,
      'uiannouncementbanner/dismissible-announcement',
    );
    await tester.tap(find.bySemanticsLabel('Dismiss announcement'));
    await tester.pumpAndSettle();
    expect(find.text('Explore the new collection workspace.'), findsNothing);
    await tester.tap(find.text('Restore announcement'));
    await tester.pumpAndSettle();
    expect(find.text('Explore the new collection workspace.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });
}

Future<WidgetbookState> _show(WidgetTester tester, String path) async {
  addTearDown(tester.view.reset);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1180, 1200);
  final root = WidgetbookRoot(children: marketingComponents);
  final useCase = root.find((node) => node.path == path)! as WidgetbookUseCase;
  final state = WidgetbookState(root: root, path: path);
  await tester.pumpWidget(
    WidgetbookScope(
      state: state,
      child: MaterialApp(
        home: SpecimenEnvironmentScope(
          setting: const SpecimenEnvironment(reduceMotion: true),
          child: SpecimenPreview(child: Builder(builder: useCase.builder)),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return state;
}
