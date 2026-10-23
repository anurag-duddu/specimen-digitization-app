import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:specimen_widgetbook/main.dart';
import 'package:specimen_widgetbook/inventory.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  testWidgets(
    'button preview defaults to visible content without a hidden pending label',
    (tester) async {
      final root = WidgetbookRoot(children: specimenCatalog);
      final useCase = root.leaves.whereType<WidgetbookUseCase>().singleWhere(
        (item) => item.name == 'primary · lg · Focused',
      );
      final state = await _showStory(tester, useCase.path);
      final button = tester.widget<UiButton>(find.byType(UiButton));
      expect(button.busyLabel, isNull);
      expect(button.leading, isNull);
      expect(button.trailing, isNull);
      expect(button.expand, isFalse);
      expect(button.label, 'Save correction');
      await tester.tap(find.text('Save correction'));
      await tester.pumpAndSettle();
      expect(find.text('Saved correction · 1 actions'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      state.dispose();
    },
  );

  test(
    'catalog paths are unique and every public control has a documented slot',
    () {
      final WidgetbookRoot root = WidgetbookRoot(children: specimenCatalog);
      final List<WidgetbookUseCase> cases = root.leaves
          .whereType<WidgetbookUseCase>()
          .toList();
      expect(
        cases.map((WidgetbookUseCase c) => c.path).toSet().length,
        cases.length,
        reason: 'Duplicate paths hide cases in Widgetbook navigation.',
      );
      final Directory controls = Directory(
        '../specimen_digitization/packages/specimen_ui/lib/src/controls',
      );
      final RegExp widgets = RegExp(
        r'class (Ui\w+)(?:<[^>]+>)? extends (?:StatefulWidget|StatelessWidget)',
      );
      final Set<String> publicControls = <String>{
        for (final File source
            in controls
                .listSync(recursive: true)
                .whereType<File>()
                .where((File f) => f.path.endsWith('.dart')))
          for (final RegExpMatch match in widgets.allMatches(
            source.readAsStringSync(),
          ))
            match.group(1)!,
      };
      final Set<String> documentedControls = <String>{
        ...publicControls,
        'UiSelectableText',
        'UiSelectionArea',
      };
      expect(
        publicControlComponents.keys.toSet(),
        documentedControls,
        reason:
            'Add every public control to the ownership manifest and remove retired controls.',
      );
      for (final MapEntry<String, String> entry
          in publicControlComponents.entries) {
        final WidgetbookNode? component = root.find(
          (WidgetbookNode node) => node.path == entry.value,
        );
        expect(
          component,
          isA<WidgetbookComponent>(),
          reason:
              '${entry.key} must resolve to its registered component ${entry.value}.',
        );
        final List<WidgetbookUseCase> ownedCases = component!.leaves
            .whereType<WidgetbookUseCase>()
            .toList();
        expect(
          ownedCases,
          isNotEmpty,
          reason: '${entry.key} requires a reachable story.',
        );
        for (final WidgetbookUseCase useCase in ownedCases) {
          expect(useCase.name.trim(), isNotEmpty);
          expect(
            root.find((WidgetbookNode node) => node.path == useCase.path),
            same(useCase),
          );
        }
      }
    },
  );

  testWidgets('all catalog cases render across five device environments', (
    WidgetTester tester,
  ) async {
    addTearDown(tester.view.reset);
    tester.view.devicePixelRatio = 1;
    final WidgetbookRoot root = WidgetbookRoot(children: specimenCatalog);
    final List<String> failures = <String>[];
    for (final WidgetbookUseCase useCase
        in root.leaves.whereType<WidgetbookUseCase>()) {
      final WidgetbookState state = WidgetbookState(
        root: root,
        path: useCase.path,
      );
      for (final _Environment configuration in _environments) {
        tester.view.physicalSize = configuration.size;
        await tester.pumpWidget(
          WidgetbookScope(
            state: state,
            child: MaterialApp(
              home: Builder(
                builder: (BuildContext context) => MediaQuery(
                  data: MediaQuery.of(context).copyWith(
                    textScaler: TextScaler.linear(configuration.scale),
                  ),
                  child: SpecimenEnvironmentScope(
                    setting: SpecimenEnvironment(
                      dark: configuration.dark,
                      density: configuration.density,
                      direction: configuration.direction,
                      reduceMotion: true,
                    ),
                    child: SpecimenPreview(
                      child: Builder(
                        key: ValueKey<String>('${useCase.path} $configuration'),
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
          failures.add('${useCase.path} / $configuration: $exception');
        }
      }
      await tester.pumpWidget(const SizedBox.shrink());
      state.dispose();
    }
    expect(failures, isEmpty, reason: failures.join('\n\n'));
  });

  testWidgets(
    'viewport modal routes inherit brand, density, direction and text scale',
    (WidgetTester tester) async {
      addTearDown(tester.view.reset);
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1600, 1200);
      await tester.pumpWidget(const SpecimenWidgetbook());
      await tester.pumpAndSettle();
      final WidgetbookState state = tester
          .widget<WidgetbookScope>(find.byType(WidgetbookScope).first)
          .notifier!;
      final Router<dynamic> router = tester.widget<Router<dynamic>>(
        find.byWidgetPredicate((Widget widget) => widget is Router).first,
      );
      final PlatformRouteInformationProvider routes =
          router.routeInformationProvider! as PlatformRouteInformationProvider;
      await routes.didPushRouteInformation(
        RouteInformation(
          uri: Uri.parse('/?path=feedback/uidialog/centred-dialog'),
        ),
      );
      await tester.pumpAndSettle();
      final String environmentGroup = state.addons!
          .whereType<SpecimenEnvironmentAddon>()
          .single
          .groupName;
      final String scaleGroup = state.addons!
          .whereType<TextScaleAddon>()
          .single
          .groupName;
      final String viewportGroup = state.addons!
          .whereType<ViewportAddon>()
          .single
          .groupName;
      state.updateQueryField(
        group: environmentGroup,
        field: 'appearance',
        value: 'Dark',
      );
      state.updateQueryField(
        group: environmentGroup,
        field: 'input',
        value: 'Pointer',
      );
      state.updateQueryField(
        group: environmentGroup,
        field: 'direction',
        value: 'RTL',
      );
      state.updateQueryField(
        group: environmentGroup,
        field: 'reduced motion',
        value: 'true',
      );
      state.updateQueryField(group: scaleGroup, field: 'factor', value: '2');
      state.updateQueryField(
        group: viewportGroup,
        field: 'name',
        value: 'Desktop',
      );
      await tester.pumpAndSettle();
      final BuildContext trigger = tester.element(
        find.text('Review synthetic changes'),
      );
      expect(trigger.ui.color.brightness, Brightness.dark);
      expect(Density.of(trigger).mode, UiDensityMode.pointer);
      expect(Directionality.of(trigger), TextDirection.rtl);
      expect(MediaQuery.textScalerOf(trigger).scale(10), 20);
      await tester.tap(find.text('Review synthetic changes'));
      await tester.pumpAndSettle();
      final BuildContext modal = tester.element(
        find.text(
          'This example updates local story state only. Review the new catalogue number before saving.',
        ),
      );
      expect(modal.ui.color.brightness, Brightness.dark);
      expect(Density.of(modal).mode, UiDensityMode.pointer);
      expect(Directionality.of(modal), TextDirection.rtl);
      expect(MediaQuery.textScalerOf(modal).scale(10), 20);
      await tester.tap(find.text('Save changes'));
      await tester.pumpAndSettle();
      expect(find.text('Changes saved · 1 actions'), findsOneWidget);
    },
  );

  testWidgets('import composition retains its local draft when reopened', (
    WidgetTester tester,
  ) async {
    final WidgetbookState state = await _showStory(
      tester,
      'compositions/uiimportworkspace/source-selection-and-private-draft',
    );
    await tester.tap(find.text('Add sample photo'));
    await tester.pumpAndSettle();
    expect(find.text('1 photos in this private story draft.'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Close photo sources'));
    await tester.pumpAndSettle();
    expect(find.text('Draft retained: 1 synthetic photos.'), findsOneWidget);
    await tester.tap(find.text('Reopen source browser'));
    await tester.pumpAndSettle();
    expect(find.text('example-photo-1.jpg'), findsOneWidget);
    expect(find.text('1 photos in this private story draft.'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    state.dispose();
  });

  testWidgets('tab composition changes the controlled content panel', (
    WidgetTester tester,
  ) async {
    final WidgetbookState state = await _showStory(
      tester,
      'compositions/uitabview/manual-activation-and-pane-changes',
    );
    expect(find.text('Synthetic specimen overview'), findsOneWidget);
    await tester.tap(find.text('Labels'));
    await tester.pumpAndSettle();
    expect(find.text('No transcribed labels'), findsOneWidget);
    expect(find.text('Synthetic specimen overview'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    state.dispose();
  });

  testWidgets('custom field composition edits and updates its counter', (
    WidgetTester tester,
  ) async {
    final WidgetbookState state = await _showStory(
      tester,
      'compositions/uifieldframe/label-editor-validation-and-counter',
    );
    expect(find.text('11 characters'), findsOneWidget);
    await tester.enterText(find.byType(EditableText), 'EXAMPLE-2026');
    await tester.pump();
    expect(find.text('12 characters'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    state.dispose();
  });
}

Future<WidgetbookState> _showStory(WidgetTester tester, String path) async {
  addTearDown(tester.view.reset);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1180, 1200);
  final WidgetbookRoot root = WidgetbookRoot(children: specimenCatalog);
  final WidgetbookUseCase useCase =
      root.find((WidgetbookNode node) => node.path == path)!
          as WidgetbookUseCase;
  final WidgetbookState state = WidgetbookState(root: root, path: path);
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

/// Deliberate representative combinations, not a claim of a full Cartesian sweep.
const List<_Environment> _environments = <_Environment>[
  _Environment(
    Size(320, 720),
    scale: 2,
    dark: true,
    direction: TextDirection.rtl,
  ),
  _Environment(Size(390, 844)),
  _Environment(Size(768, 1024), scale: 2, direction: TextDirection.rtl),
  _Environment(Size(1180, 820), dark: true, density: UiDensityMode.pointer),
  _Environment(Size(1440, 900), density: UiDensityMode.pointer),
];

class _Environment {
  const _Environment(
    this.size, {
    this.scale = 1,
    this.dark = false,
    this.direction = TextDirection.ltr,
    this.density = UiDensityMode.touch,
  });
  final Size size;
  final double scale;
  final bool dark;
  final TextDirection direction;
  final UiDensityMode density;
  @override
  String toString() =>
      '${size.width}×${size.height} / $scale× / ${dark ? 'dark' : 'light'} / ${direction.name} / ${density.name}';
}
