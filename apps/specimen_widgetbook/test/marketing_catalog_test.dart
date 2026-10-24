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
    expect(find.text('Preserving label detail'), findsOneWidget);
    expect(find.text('Connecting collection histories'), findsNothing);
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

  testWidgets('journal sorting and pagination preserve category filtering', (
    tester,
  ) async {
    final state = await _show(tester, 'uimarketingpage/blog');
    UiBlogSection journal() =>
        tester.widget<UiBlogSection>(find.byType(UiBlogSection));
    expect(journal().articles.map((article) => article.title), [
      'Reading the record',
      'A shared review practice',
    ]);
    await tester.ensureVisible(find.byType(UiSelect<String>));
    await tester.tap(find.byType(UiSelect<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Oldest first'));
    await tester.pumpAndSettle();
    expect(journal().articles.first.title, 'Preserving label detail');
    await tester.ensureVisible(find.byType(UiPagination));
    await tester.tap(find.bySemanticsLabel('Next page'));
    await tester.pumpAndSettle();
    expect(journal().articles.first.title, 'A shared review practice');
    await tester.ensureVisible(find.widgetWithText(UiButton, 'Research'));
    await tester.tap(find.widgetWithText(UiButton, 'Research'));
    await tester.pumpAndSettle();
    expect(tester.widget<UiPagination>(find.byType(UiPagination)).page, 1);
    expect(journal().articles.map((article) => article.category).toSet(), {
      'Research',
    });
    expect(journal().articles.first.title, 'Connecting collection histories');
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });

  testWidgets('FAQ searches answers, handles no results and resets the query', (
    tester,
  ) async {
    final state = await _show(tester, 'uimarketingpage/faq');
    final field = find.descendant(
      of: find.byType(UiSearchField),
      matching: find.byType(EditableText),
    );
    await tester.enterText(field, 'permissions');
    await tester.pumpAndSettle();
    expect(find.text('How does access work?'), findsOneWidget);
    expect(find.text('Can records be exported?'), findsNothing);
    await tester.enterText(field, 'unmatched phrase');
    await tester.pumpAndSettle();
    expect(find.text('No questions match this search.'), findsOneWidget);
    await tester.tap(find.text('Show all questions'));
    await tester.pumpAndSettle();
    expect(tester.widget<EditableText>(field).controller.text, isEmpty);
    expect(find.text('Can records be exported?'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });

  testWidgets(
    'missing-page recovery supports submit, no result and destination',
    (tester) async {
      final state = await _show(tester, 'uimarketingpage/not-found');
      final field = find.descendant(
        of: find.byType(UiSearchField),
        matching: find.byType(EditableText),
      );
      await tester.enterText(field, 'unknown');
      await tester.testTextInput.receiveAction(TextInputAction.search);
      await tester.pumpAndSettle();
      expect(
        find.text('No sample destinations match this search.'),
        findsOneWidget,
      );
      await tester.enterText(field, 'guides');
      await tester.tap(find.widgetWithText(UiButton, 'Search destinations'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Open collection guides'));
      await tester.pumpAndSettle();
      expect(
        find.text('Collection guides opened in this preview'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      state.dispose();
    },
  );

  testWidgets(
    'article page browses evidence and keeps related content available',
    (tester) async {
      final state = await _show(tester, 'uimarketingpage/article');
      final carousel = find.byType(UiCarousel);
      expect(find.text('Original specimen photograph'), findsOneWidget);
      await tester.ensureVisible(carousel);
      final next = find.descendant(
        of: carousel,
        matching: find.bySemanticsLabel('Next page'),
      );
      await tester.ensureVisible(next);
      await tester.tap(next);
      await tester.pumpAndSettle();
      expect(find.text('Source label detail'), findsOneWidget);
      expect(find.text('Original specimen photograph'), findsNothing);
      expect(find.text('Related collection stories'), findsOneWidget);
      expect(find.byType(UiNewsletterSection), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      state.dispose();
    },
  );

  testWidgets('team page exposes real roles and department filtering', (
    tester,
  ) async {
    final state = await _show(tester, 'uimarketingpage/team');
    await tester.ensureVisible(find.text('View open roles'));
    await tester.tap(find.text('View open roles'));
    await tester.pumpAndSettle();
    final careers = find.byType(UiCareersSection);
    final engineering = find
        .descendant(of: careers, matching: find.text('Engineering'))
        .first;
    await tester.ensureVisible(engineering);
    await tester.tap(engineering);
    await tester.pumpAndSettle();
    expect(find.text('Product engineer'), findsOneWidget);
    expect(find.text('Collection specialist'), findsNothing);
    expect(find.byType(UiNewsletterSection), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });

  testWidgets(
    'authentication retains submitted session preference in its receipt',
    (tester) async {
      final state = await _show(tester, 'uimarketingpage/authentication');
      final form = find.byType(UiAuthForm);
      final inputs = find.descendant(
        of: form,
        matching: find.byType(EditableText),
      );
      await tester.enterText(inputs.at(0), 'sample@example.org');
      await tester.enterText(inputs.at(1), 'synthetic password');
      await tester.tap(find.text('Remember me'));
      await tester.pump();
      expect(tester.widget<UiAuthForm>(form).rememberSession, isTrue);
      final submit = find.descendant(
        of: form,
        matching: find.widgetWithText(UiButton, 'Sign in'),
      );
      await tester.ensureVisible(submit);
      await tester.tap(submit);
      await tester.pump(const Duration(seconds: 1));
      await tester.pumpAndSettle();
      expect(
        find.text('Synthetic request accepted · Session preference: remember'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      state.dispose();
    },
  );
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
